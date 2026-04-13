from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from app.agents.runtime_context import SwapExecutionAgentRuntimeContext
from app.config.settings import get_settings
from app.services.okx_skills import OKXSkillRegistry
from app.tools.langchain_agent_tools import build_swap_execution_agent_tools


class SwapExecutionOutput(BaseModel):
    execution_request: dict[str, Any]
    execution_result: dict[str, Any]


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
        mutating_swap_provider=None,
    ) -> None:
        self._agent = None
        self.model = model
        self.tools = tools if tools is not None else build_swap_execution_agent_tools()
        self.skill_registry = skill_registry or OKXSkillRegistry()
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
        try:
            from langchain.agents import create_agent
            from langchain.agents.structured_output import ToolStrategy
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("LangChain is not installed for LangChainSwapExecutionBackend.") from exc

        system_prompt = (
            "You are a swap execution agent for an on-chain copy-trading bot. "
            "You receive already validated buy or sell intent after policy approval. "
            "Load okx-dex-swap skill, synthesize the exact execution request, and invoke the bounded swap tool. "
            "Do not change the trade intent or bypass the validated inputs. Output only the structured schema."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.decision_model,
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
            + json.dumps(intent, ensure_ascii=True)
        )

    def _build_runtime_context(self, *, intent: dict[str, Any]) -> SwapExecutionAgentRuntimeContext:
        return SwapExecutionAgentRuntimeContext(
            user_id=str(intent.get("user_id") or "unknown"),
            intent=intent,
            load_skill_provider=self.skill_registry.load_skill,
            load_reference_provider=self.skill_registry.load_reference,
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
