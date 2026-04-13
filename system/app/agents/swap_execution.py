from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.agents.runtime_context import SwapExecutionAgentRuntimeContext
from app.config.settings import ensure_openai_runtime_env, get_settings
from app.services.okx_skills import OKXSkillRegistry
from app.services.onchainos_runner import OnchainOSReadonlyRunner
from app.tools.langchain_agent_tools import build_swap_execution_agent_tools


class SwapExecutionRequestOutput(BaseModel):
    asset_lane: str = Field(description="Asset lane of the validated trade intent.")
    signal_id: str | None = Field(default=None, description="Related signal identifier for buy execution if present.")
    position_id: str | None = Field(default=None, description="Related position identifier for sell execution if present.")
    side: str = Field(description="Swap side, buy or sell.")
    chain: str = Field(description="Execution chain.")
    wallet_address: str = Field(description="Wallet address used for execution.")
    from_token: str = Field(description="Token swapped from.")
    to_token: str = Field(description="Token swapped to.")
    readable_amount: str = Field(description="Human-readable amount submitted to the swap command.")
    slippage_pct: float | None = Field(default=None, description="Slippage used for execution if present.")


class SwapExecutionResultOutput(BaseModel):
    signal_id: str | None = Field(default=None, description="Related signal identifier if present.")
    position_id: str | None = Field(default=None, description="Related position identifier if present.")
    success: bool = Field(description="Whether the swap execution succeeded.")
    execution_id: str | None = Field(default=None, description="Execution identifier returned by the runner.")
    approve_tx_hash: str | None = Field(default=None, description="Approval transaction hash if applicable.")
    swap_tx_hash: str | None = Field(default=None, description="Swap transaction hash if applicable.")
    received_token_amount: str | None = Field(default=None, description="Received token amount for buy execution if available.")
    received_token_symbol: str | None = Field(default=None, description="Received token symbol for buy execution if available.")
    realized_output_amount: str | None = Field(default=None, description="Realized output amount for sell execution if available.")
    realized_output_symbol: str | None = Field(default=None, description="Realized output symbol for sell execution if available.")
    error_code: str | None = Field(default=None, description="Normalized execution error code if the swap failed.")
    error_message: str | None = Field(default=None, description="Normalized execution error message if the swap failed.")


class SwapExecutionOutput(BaseModel):
    execution_request: SwapExecutionRequestOutput = Field(description="Structured execution request actually sent to the runner.")
    execution_result: SwapExecutionResultOutput = Field(description="Structured execution result returned by the runner.")


class SwapExecutionBackend(Protocol):
    def execute(self, *, intent: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class SwapExecutionAgentConfig:
    tools: list = field(default_factory=build_swap_execution_agent_tools)


class LangChainSwapExecutionBackend:
    def __init__(
        self,
        *,
        model: str | None = None,
        tools: list | None = None,
        skill_registry: OKXSkillRegistry | None = None,
        readonly_runner: OnchainOSReadonlyRunner | None = None,
        mutating_swap_provider=None,
    ) -> None:
        self._agent = None
        self.model = model
        self.tools = tools if tools is not None else build_swap_execution_agent_tools()
        self.skill_registry = skill_registry or OKXSkillRegistry()
        self.readonly_runner = readonly_runner or OnchainOSReadonlyRunner(
            timeout_seconds=get_settings().models.timeout_seconds
        )
        self.mutating_swap_provider = mutating_swap_provider or (lambda request: {"ok": False, "error": "missing swap provider"})

    def execute(self, *, intent: dict[str, Any]) -> dict[str, Any]:
        agent = self._get_agent()
        result = agent.invoke(
            {"messages": [{"role": "user", "content": self._build_prompt(intent=intent)}]},
            context=self._build_runtime_context(intent=intent),
        )
        return self._extract_output(result).model_dump()

    def _get_agent(self):
        if self._agent is not None:
            return self._agent
        ensure_openai_runtime_env()
        try:
            from langchain.agents import create_agent
            from langchain.agents.structured_output import ToolStrategy
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("LangChain is not installed for LangChainSwapExecutionBackend.") from exc

        system_prompt = (
            "You are a swap execution agent for an on-chain copy-trading bot. "
            "You receive already validated buy or sell intent after policy approval. "
            "Load okx-dex-swap skill, synthesize the exact execution request, and invoke the bounded swap tool. "
            "Always use resolved_wallet_address from runtime context when present. "
            "If wallet address is missing or stale, load okx-agentic-wallet and resolve active wallet via wallet status + wallet addresses first. "
            "Do not change the trade intent or bypass the validated inputs. Output only the structured schema."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.swap_execution_model,
            tools=self.tools,
            system_prompt=system_prompt,
            context_schema=SwapExecutionAgentRuntimeContext,
            response_format=ToolStrategy(SwapExecutionOutput),
        )
        return self._agent

    def _build_prompt(self, *, intent: dict[str, Any]) -> str:
        return (
            "Execute this already validated swap intent.\n"
            "Load okx-dex-swap and use the bounded mutating swap tool.\n"
            "Use resolved_wallet_address from context when available, otherwise resolve via wallet status + wallet addresses.\n"
            + json.dumps(intent, ensure_ascii=True)
        )

    def _build_runtime_context(self, *, intent: dict[str, Any]) -> SwapExecutionAgentRuntimeContext:
        return SwapExecutionAgentRuntimeContext(
            user_id=str(intent.get("user_id") or "unknown"),
            intent=intent,
            resolved_wallet_address=str(intent.get("wallet_address") or "") or None,
            load_skill_provider=self.skill_registry.load_skill,
            load_reference_provider=self.skill_registry.load_reference,
            readonly_command_provider=self.readonly_runner.run,
            mutating_swap_provider=self.mutating_swap_provider,
        )

    def _extract_output(self, result) -> SwapExecutionOutput:
        if isinstance(result, SwapExecutionOutput):
            return result
        if isinstance(result, dict):
            if "structured_response" in result:
                structured = result["structured_response"]
                if isinstance(structured, SwapExecutionOutput):
                    return structured
                if isinstance(structured, dict):
                    return SwapExecutionOutput(**structured)
            if "output" in result and isinstance(result["output"], dict):
                return SwapExecutionOutput(**result["output"])
        if isinstance(result, str):
            return SwapExecutionOutput(**json.loads(result))
        raise RuntimeError("Could not extract structured swap execution output from LangChain agent result.")


class SwapExecutionAgent:
    def __init__(self, config: SwapExecutionAgentConfig | None = None, backend: SwapExecutionBackend | None = None) -> None:
        self.config = config or SwapExecutionAgentConfig()
        self.backend = backend or LangChainSwapExecutionBackend(tools=self.config.tools)

    def execute(self, *, intent: dict[str, Any]) -> dict[str, Any]:
        return self.backend.execute(intent=intent)


class CallableSwapExecutionBackend:
    def __init__(self, provider) -> None:
        self.provider = provider

    def execute(self, *, intent: dict[str, Any]) -> dict[str, Any]:
        result = self.provider(intent)
        if isinstance(result, dict) and "execution_request" in result and "execution_result" in result:
            return result
        return {
            "execution_request": intent,
            "execution_result": result,
        }
