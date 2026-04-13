from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel

from app.agents.runtime_context import WalletCommandRuntimeContext
from app.config.settings import get_settings
from app.services.onchainos_runner import OnchainOSReadonlyRunner
from app.services.okx_skills import OKXSkillRegistry
from app.tools.langchain_agent_tools import build_wallet_command_agent_tools


class WalletCommandOutput(BaseModel):
    command: str
    message: str
    payload: dict
    summary_mode: str = "deterministic"


class WalletCommandBackend(Protocol):
    def handle(self, *, user_id: str, command_name: str, raw_text: str) -> WalletCommandOutput: ...


@dataclass
class WalletCommandAgentConfig:
    tools: list = field(default_factory=build_wallet_command_agent_tools)


class LangChainWalletCommandBackend:
    def __init__(
        self,
        *,
        model: str | None = None,
        tools: list | None = None,
        skill_registry: OKXSkillRegistry | None = None,
        readonly_runner: OnchainOSReadonlyRunner | None = None,
    ) -> None:
        self._agent = None
        self.model = model
        self.tools = tools if tools is not None else build_wallet_command_agent_tools()
        self.skill_registry = skill_registry or OKXSkillRegistry()
        self.readonly_runner = readonly_runner or OnchainOSReadonlyRunner(
            timeout_seconds=get_settings().models.timeout_seconds
        )

    def handle(self, *, user_id: str, command_name: str, raw_text: str) -> WalletCommandOutput:
        agent = self._get_agent()
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Handle this wallet-oriented Telegram command.\n"
                            "Always load okx-agentic-wallet first.\n"
                            "Use okx-dex-market only when portfolio or PnL context is needed.\n"
                            "Use run_onchainos_readonly for wallet status, addresses, balance, or history reads.\n"
                            f"Command:\n{raw_text}"
                        ),
                    }
                ]
            },
            context=WalletCommandRuntimeContext(
                user_id=user_id,
                command_name=command_name,
                raw_text=raw_text,
                load_skill_provider=self.skill_registry.load_skill,
                load_reference_provider=self.skill_registry.load_reference,
                readonly_command_provider=self.readonly_runner.run,
            ),
        )
        return self._extract_output(result)

    def _get_agent(self):
        if self._agent is not None:
            return self._agent

        try:
            from langchain.agents import create_agent
            from langchain.agents.structured_output import ToolStrategy
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("LangChain is not installed for LangChainWalletCommandBackend.") from exc

        system_prompt = (
            "You are a wallet and command agent for an OKX OnchainOS trading bot. "
            "You handle /start, /status, /portfolio, and /history. "
            "For wallet-origin data, load okx-agentic-wallet through the skills pattern and call run_onchainos_readonly. "
            "Use okx-dex-market only when portfolio or PnL information is needed. "
            "Do not invent balances, addresses, history, or login state. "
            "Return only the structured schema."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.summary_model,
            tools=self.tools,
            system_prompt=system_prompt,
            context_schema=WalletCommandRuntimeContext,
            response_format=ToolStrategy(WalletCommandOutput),
        )
        return self._agent

    def _extract_output(self, result) -> WalletCommandOutput:
        if isinstance(result, WalletCommandOutput):
            return result
        if isinstance(result, dict):
            if "structured_response" in result:
                structured = result["structured_response"]
                if isinstance(structured, WalletCommandOutput):
                    return structured
                if isinstance(structured, dict):
                    return WalletCommandOutput(**structured)
            if "output" in result and isinstance(result["output"], dict):
                return WalletCommandOutput(**result["output"])
        if isinstance(result, str):
            return WalletCommandOutput(**json.loads(result))
        raise RuntimeError("Could not extract wallet command output from LangChain agent result.")


class WalletCommandAgent:
    def __init__(self, config: WalletCommandAgentConfig | None = None, backend: WalletCommandBackend | None = None) -> None:
        self.config = config or WalletCommandAgentConfig()
        self.backend = backend or LangChainWalletCommandBackend(tools=self.config.tools)

    def handle(self, *, user_id: str, command_name: str, raw_text: str) -> WalletCommandOutput:
        return self.backend.handle(user_id=user_id, command_name=command_name, raw_text=raw_text)
