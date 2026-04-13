from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.agents.runtime_context import ExitEnrichmentAgentRuntimeContext
from app.config.settings import get_settings
from app.services.onchainos_runner import OnchainOSReadonlyRunner
from app.services.okx_skills import OKXSkillRegistry
from app.tools.langchain_agent_tools import build_exit_enrichment_agent_tools


class ExitCandleOutput(BaseModel):
    close: float = Field(description="Candle close price used by exit TA and trailing logic.")


class ExitMarketSnapshotOutput(BaseModel):
    asset_lane: Literal["major", "regular"] = Field(description="Lane of the position being reevaluated.")
    chain: str = Field(description="Execution chain for the position.")
    current_price_usd: float | None = Field(default=None, description="Latest current price in USD for the tracked asset.")
    liquidity_usd: float | None = Field(default=None, description="Current liquidity in USD if available.")
    volume_24h_usd: float | None = Field(default=None, description="24-hour trading volume in USD if available.")
    quote_available: bool = Field(description="Whether a sell route or quote is currently available.")
    quote_price_impact_pct: float | None = Field(default=None, description="Current sell quote price impact percentage if available.")
    kline_window: list[ExitCandleOutput] = Field(
        description="Recent market kline candles for exit monitoring. Use okx-dex-market and include at least 2 candles when available."
    )


class ExitEnrichmentOutput(BaseModel):
    exit_market_snapshot: ExitMarketSnapshotOutput


class ExitEnrichmentBackend(Protocol):
    def enrich(
        self,
        *,
        position_snapshot: dict[str, Any],
        trailing_state: dict[str, Any],
        strategy_profile: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass
class ExitEnrichmentAgentConfig:
    tools: list = field(default_factory=build_exit_enrichment_agent_tools)


class LangChainExitEnrichmentBackend:
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
        self.tools = tools if tools is not None else build_exit_enrichment_agent_tools()
        self.skill_registry = skill_registry or OKXSkillRegistry()
        self.readonly_runner = readonly_runner or OnchainOSReadonlyRunner(
            timeout_seconds=get_settings().models.timeout_seconds
        )

    def enrich(
        self,
        *,
        position_snapshot: dict[str, Any],
        trailing_state: dict[str, Any],
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
            raise RuntimeError("LangChain is not installed for LangChainExitEnrichmentBackend.") from exc

        system_prompt = (
            "You are an exit enrichment agent for an on-chain copy-trading bot. "
            "Your job is to refresh market context for an existing open position before exit reasoning. "
            "Load OKX OnchainOS skills on demand and use run_onchainos_readonly to gather current market price, quote, liquidity, and recent kline data. "
            "You must load okx-dex-market and populate exit_market_snapshot.kline_window with recent candles whenever market data is available. "
            "Return only the structured exit market snapshot. Do not make the exit decision."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.exit_model,
            tools=self.tools,
            system_prompt=system_prompt,
            context_schema=ExitEnrichmentAgentRuntimeContext,
            response_format=ToolStrategy(ExitEnrichmentOutput),
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
            "Refresh exit market context for this open position.\n"
            "Load okx-dex-market and use run_onchainos_readonly to gather current market price, sell-side quote context, liquidity, volume, and market kline.\n"
            "Do not fabricate candles. If you cannot obtain klines, return an empty list.\n"
            "Return only the normalized exit_market_snapshot.\n"
            + json.dumps(payload, ensure_ascii=True)
        )

    def _build_runtime_context(
        self,
        *,
        position_snapshot: dict[str, Any],
        trailing_state: dict[str, Any],
        strategy_profile: dict[str, Any],
    ) -> ExitEnrichmentAgentRuntimeContext:
        return ExitEnrichmentAgentRuntimeContext(
            user_id=str(position_snapshot.get("user_id") or strategy_profile.get("user_id") or "unknown"),
            position_snapshot=position_snapshot,
            trailing_state=trailing_state,
            strategy_profile=strategy_profile,
            load_skill_provider=self.skill_registry.load_skill,
            load_reference_provider=self.skill_registry.load_reference,
            readonly_command_provider=self.readonly_runner.run,
        )

    def _extract_output(self, result) -> ExitEnrichmentOutput:
        if isinstance(result, ExitEnrichmentOutput):
            return result
        if isinstance(result, dict):
            if "structured_response" in result:
                structured = result["structured_response"]
                if isinstance(structured, ExitEnrichmentOutput):
                    return structured
                if isinstance(structured, dict):
                    return ExitEnrichmentOutput(**structured)
            if "output" in result and isinstance(result["output"], dict):
                return ExitEnrichmentOutput(**result["output"])
        if isinstance(result, str):
            return ExitEnrichmentOutput(**json.loads(result))
        raise RuntimeError("Could not extract structured exit enrichment output from LangChain agent result.")


class ExitEnrichmentAgent:
    def __init__(
        self,
        config: ExitEnrichmentAgentConfig | None = None,
        backend: ExitEnrichmentBackend | None = None,
    ) -> None:
        self.config = config or ExitEnrichmentAgentConfig()
        self.backend = backend or LangChainExitEnrichmentBackend(tools=self.config.tools)

    def enrich(
        self,
        *,
        position_snapshot: dict[str, Any],
        trailing_state: dict[str, Any],
        strategy_profile: dict[str, Any],
    ) -> dict[str, Any]:
        return self.backend.enrich(
            position_snapshot=position_snapshot,
            trailing_state=trailing_state,
            strategy_profile=strategy_profile,
        )
