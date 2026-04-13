from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from app.agents.runtime_context import EnrichmentAgentRuntimeContext
from app.config.settings import get_settings
from app.services.onchainos_runner import OnchainOSReadonlyRunner
from app.services.okx_skills import OKXSkillRegistry
from app.tools.langchain_agent_tools import build_enrichment_agent_tools


class EnrichmentOutput(BaseModel):
    wallet_snapshot: dict[str, Any]
    market_snapshot: dict[str, Any]
    risk_snapshot: dict[str, Any]
    signal_overlay: dict[str, Any] | None = None


class EnrichmentBackend(Protocol):
    def enrich(
        self,
        *,
        parsed_signal: dict[str, Any],
        resolved_asset: dict[str, Any],
        strategy_profile: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass
class EnrichmentAgentConfig:
    tools: list = field(default_factory=build_enrichment_agent_tools)


class LangChainEnrichmentBackend:
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
        self.tools = tools if tools is not None else build_enrichment_agent_tools()
        self.skill_registry = skill_registry or OKXSkillRegistry()
        self.readonly_runner = readonly_runner or OnchainOSReadonlyRunner(
            timeout_seconds=get_settings().models.timeout_seconds
        )

    def enrich(
        self,
        *,
        parsed_signal: dict[str, Any],
        resolved_asset: dict[str, Any],
        strategy_profile: dict[str, Any],
    ) -> dict[str, Any]:
        agent = self._get_agent()
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": self._build_prompt(
                            parsed_signal=parsed_signal,
                            resolved_asset=resolved_asset,
                            strategy_profile=strategy_profile,
                        ),
                    }
                ]
            },
            context=self._build_runtime_context(
                parsed_signal=parsed_signal,
                resolved_asset=resolved_asset,
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
            raise RuntimeError("LangChain is not installed for LangChainEnrichmentBackend.") from exc

        system_prompt = (
            "You are an enrichment agent for an on-chain copy-trading bot. "
            "Your job is to gather and normalize trading context before any decision step. "
            "Load OKX OnchainOS skills on demand and use run_onchainos_readonly to collect wallet, market, risk, and optional overlay data. "
            "Return structured snapshots only. Do not make the trade decision."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.decision_model,
            tools=self.tools,
            system_prompt=system_prompt,
            context_schema=EnrichmentAgentRuntimeContext,
            response_format=ToolStrategy(EnrichmentOutput),
        )
        return self._agent

    def _build_prompt(
        self,
        *,
        parsed_signal: dict[str, Any],
        resolved_asset: dict[str, Any],
        strategy_profile: dict[str, Any],
    ) -> str:
        payload = {
            "parsed_signal": parsed_signal,
            "resolved_asset": resolved_asset,
            "strategy_profile": strategy_profile,
        }
        return (
            "Collect complete decision input context for this trade candidate.\n"
            "Use OKX skills and run_onchainos_readonly to gather wallet, market, risk, and optional overlay data.\n"
            "Return normalized snapshots only.\n"
            + json.dumps(payload, ensure_ascii=True)
        )

    def _build_runtime_context(
        self,
        *,
        parsed_signal: dict[str, Any],
        resolved_asset: dict[str, Any],
        strategy_profile: dict[str, Any],
    ) -> EnrichmentAgentRuntimeContext:
        return EnrichmentAgentRuntimeContext(
            user_id=str(strategy_profile.get("user_id") or "unknown"),
            parsed_signal=parsed_signal,
            resolved_asset=resolved_asset,
            strategy_profile=strategy_profile,
            load_skill_provider=self.skill_registry.load_skill,
            load_reference_provider=self.skill_registry.load_reference,
            readonly_command_provider=self.readonly_runner.run,
        )

    def _extract_output(self, result) -> EnrichmentOutput:
        if isinstance(result, EnrichmentOutput):
            return result
        if isinstance(result, dict):
            if "structured_response" in result:
                structured = result["structured_response"]
                if isinstance(structured, EnrichmentOutput):
                    return structured
                if isinstance(structured, dict):
                    return EnrichmentOutput(**structured)
            if "output" in result and isinstance(result["output"], dict):
                return EnrichmentOutput(**result["output"])
        if isinstance(result, str):
            return EnrichmentOutput(**json.loads(result))
        raise RuntimeError("Could not extract structured enrichment output from LangChain agent result.")


class EnrichmentAgent:
    def __init__(self, config: EnrichmentAgentConfig | None = None, backend: EnrichmentBackend | None = None) -> None:
        self.config = config or EnrichmentAgentConfig()
        self.backend = backend or LangChainEnrichmentBackend(tools=self.config.tools)

    def enrich(
        self,
        *,
        parsed_signal: dict[str, Any],
        resolved_asset: dict[str, Any],
        strategy_profile: dict[str, Any],
    ) -> dict[str, Any]:
        return self.backend.enrich(
            parsed_signal=parsed_signal,
            resolved_asset=resolved_asset,
            strategy_profile=strategy_profile,
        )
