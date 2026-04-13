from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.agents.runtime_context import HistoryAgentRuntimeContext
from app.config.settings import get_settings
from app.services.onchainos_runner import OnchainOSReadonlyRunner
from app.services.okx_skills import OKXSkillRegistry
from app.tools.langchain_agent_tools import build_history_agent_tools


class DexHistoryRowOutput(BaseModel):
    chain: str | None = Field(default=None, description="Chain of the historical DEX transaction.")
    token: str | None = Field(default=None, description="Primary token symbol if available.")
    side: str | None = Field(default=None, description="Trade direction if available.")
    amount_usd: float | None = Field(default=None, description="Transaction size in USD if available.")
    timestamp: str | None = Field(default=None, description="Transaction timestamp if available.")
    tx_hash: str | None = Field(default=None, description="Transaction hash if available.")


class HistorySnapshotOutput(BaseModel):
    dex_history_rows: list[DexHistoryRowOutput] = Field(default_factory=list, description="Wallet DEX transaction history rows.")


class HistoryBackend(Protocol):
    def load_history(self, *, user_id: str, raw_text: str, time_window: str | None) -> dict[str, Any]: ...


@dataclass
class HistoryAgentConfig:
    tools: list = field(default_factory=build_history_agent_tools)


class LangChainHistoryBackend:
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
        self.tools = tools if tools is not None else build_history_agent_tools()
        self.skill_registry = skill_registry or OKXSkillRegistry()
        self.readonly_runner = readonly_runner or OnchainOSReadonlyRunner(
            timeout_seconds=get_settings().models.timeout_seconds
        )

    def load_history(self, *, user_id: str, raw_text: str, time_window: str | None) -> dict[str, Any]:
        agent = self._get_agent()
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Load wallet DEX history for this history request.\n"
                            "Use okx-dex-market and call portfolio-dex-history.\n"
                            f"Request: {raw_text}"
                        ),
                    }
                ]
            },
            context=HistoryAgentRuntimeContext(
                user_id=user_id,
                raw_text=raw_text,
                time_window=time_window,
                load_skill_provider=self.skill_registry.load_skill,
                load_reference_provider=self.skill_registry.load_reference,
                readonly_command_provider=self.readonly_runner.run,
            ),
        )
        return self._extract_output(result).model_dump()

    def _get_agent(self):
        if self._agent is not None:
            return self._agent
        try:
            from langchain.agents import create_agent
            from langchain.agents.structured_output import ToolStrategy
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("LangChain is not installed for LangChainHistoryBackend.") from exc

        system_prompt = (
            "You are a history agent for an OKX OnchainOS trading bot. "
            "Load okx-dex-market and use run_onchainos_readonly to gather wallet DEX transaction history. "
            "Prefer onchainos market portfolio-dex-history. "
            "Return only the structured schema."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.summary_model,
            tools=self.tools,
            system_prompt=system_prompt,
            context_schema=HistoryAgentRuntimeContext,
            response_format=ToolStrategy(HistorySnapshotOutput),
        )
        return self._agent

    @staticmethod
    def _extract_output(result) -> HistorySnapshotOutput:
        if isinstance(result, HistorySnapshotOutput):
            return result
        if isinstance(result, dict):
            if "structured_response" in result:
                structured = result["structured_response"]
                if isinstance(structured, HistorySnapshotOutput):
                    return structured
                if isinstance(structured, dict):
                    return HistorySnapshotOutput(**structured)
            if "output" in result and isinstance(result["output"], dict):
                return HistorySnapshotOutput(**result["output"])
        if isinstance(result, str):
            return HistorySnapshotOutput(**json.loads(result))
        raise RuntimeError("Could not extract history output from LangChain agent result.")


class HistoryAgent:
    def __init__(self, config: HistoryAgentConfig | None = None, backend: HistoryBackend | None = None) -> None:
        self.config = config or HistoryAgentConfig()
        self.backend = backend or LangChainHistoryBackend(tools=self.config.tools)

    def load_history(self, *, user_id: str, raw_text: str, time_window: str | None) -> dict[str, Any]:
        return self.backend.load_history(user_id=user_id, raw_text=raw_text, time_window=time_window)
