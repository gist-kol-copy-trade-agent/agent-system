from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from app.agents.runtime_context import ExitAgentRuntimeContext
from app.config.settings import get_settings
from app.services.okx_skills import OKXSkillRegistry
from app.tools.langchain_agent_tools import build_exit_agent_tools


class ExitDecisionOutput(BaseModel):
    asset_lane: str
    decision: str
    decision_reason_code: str
    confidence: float
    rationale_summary: str
    telegram_summary: str


class ExitBackend(Protocol):
    def decide(
        self,
        *,
        position_snapshot: dict[str, Any],
        trailing_state: dict[str, Any],
        market_snapshot: dict[str, Any],
        ta_snapshot: dict[str, Any],
        strategy_profile: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass
class ExitAgentConfig:
    tools: list = field(default_factory=build_exit_agent_tools)


class LangChainExitBackend:
    def __init__(
        self,
        *,
        model: str | None = None,
        tools: list | None = None,
        skill_registry: OKXSkillRegistry | None = None,
    ) -> None:
        self._agent = None
        self.model = model
        self.tools = tools if tools is not None else build_exit_agent_tools()
        self.skill_registry = skill_registry or OKXSkillRegistry()

    def decide(
        self,
        *,
        position_snapshot: dict[str, Any],
        trailing_state: dict[str, Any],
        market_snapshot: dict[str, Any],
        ta_snapshot: dict[str, Any],
        strategy_profile: dict[str, Any],
    ) -> dict[str, Any]:
        agent = self._get_agent()
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": self._build_prompt(
                            position_snapshot=position_snapshot,
                            trailing_state=trailing_state,
                            strategy_profile=strategy_profile,
                        ),
                    }
                ]
            },
            context=self._build_runtime_context(
                position_snapshot=position_snapshot,
                trailing_state=trailing_state,
                market_snapshot=market_snapshot,
                ta_snapshot=ta_snapshot,
                strategy_profile=strategy_profile,
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
            raise RuntimeError("LangChain is not installed for LangChainExitBackend.") from exc

        system_prompt = (
            "You are an exit decision agent for an on-chain copy-trading bot. "
            "Use position state, market context, deterministic exit TA, and user strategy settings to decide whether to hold, "
            "hard exit, arm trailing logic, or fire a trailing exit. "
            "Use the provided tools for position snapshot, market snapshot, and exit TA. "
            "Do not call execution tools. Output only the structured schema."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.exit_model,
            tools=self.tools,
            system_prompt=system_prompt,
            context_schema=ExitAgentRuntimeContext,
            response_format=ToolStrategy(ExitDecisionOutput),
        )
        return self._agent

    def _build_prompt(
        self,
        *,
        position_snapshot: dict[str, Any],
        trailing_state: dict[str, Any],
        strategy_profile: dict[str, Any],
    ) -> str:
        payload = {
            "position_snapshot": position_snapshot,
            "trailing_state": trailing_state,
            "strategy_profile": strategy_profile,
        }
        return (
            "Make a structured exit decision.\n"
            "Use the tools to inspect normalized position, market, and deterministic exit TA context.\n"
            "Return one of: hold, exit_hard, exit_trailing_arm, exit_trailing_fire.\n"
            + json.dumps(payload, ensure_ascii=True)
        )

    def _build_runtime_context(
        self,
        *,
        position_snapshot: dict[str, Any],
        trailing_state: dict[str, Any],
        market_snapshot: dict[str, Any],
        ta_snapshot: dict[str, Any],
        strategy_profile: dict[str, Any],
    ) -> ExitAgentRuntimeContext:
        return ExitAgentRuntimeContext(
            user_id=str(position_snapshot.get("user_id") or strategy_profile.get("user_id") or "unknown"),
            position_snapshot=position_snapshot,
            trailing_state=trailing_state,
            strategy_profile=strategy_profile,
            load_skill_provider=self.skill_registry.load_skill,
            load_reference_provider=self.skill_registry.load_reference,
            position_snapshot_provider=lambda: position_snapshot,
            exit_market_snapshot_provider=lambda: market_snapshot,
            exit_ta_score_provider=lambda: ta_snapshot,
        )

    def _extract_output(self, result) -> ExitDecisionOutput:
        if isinstance(result, ExitDecisionOutput):
            return result
        if isinstance(result, dict):
            if "structured_response" in result:
                structured = result["structured_response"]
                if isinstance(structured, ExitDecisionOutput):
                    return structured
                if isinstance(structured, dict):
                    return ExitDecisionOutput(**structured)
            if "output" in result and isinstance(result["output"], dict):
                return ExitDecisionOutput(**result["output"])
        if isinstance(result, str):
            return ExitDecisionOutput(**json.loads(result))
        raise RuntimeError("Could not extract structured exit decision output from LangChain agent result.")


class ExitAgent:
    def __init__(self, config: ExitAgentConfig | None = None, backend: ExitBackend | None = None) -> None:
        self.config = config or ExitAgentConfig()
        self.backend = backend or LangChainExitBackend(tools=self.config.tools)

    def decide(
        self,
        *,
        position_snapshot: dict[str, Any],
        trailing_state: dict[str, Any],
        market_snapshot: dict[str, Any],
        ta_snapshot: dict[str, Any],
        strategy_profile: dict[str, Any],
    ) -> dict[str, Any]:
        return self.backend.decide(
            position_snapshot=position_snapshot,
            trailing_state=trailing_state,
            market_snapshot=market_snapshot,
            ta_snapshot=ta_snapshot,
            strategy_profile=strategy_profile,
        )
