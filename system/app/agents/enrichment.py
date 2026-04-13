from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.agents.runtime_context import EnrichmentAgentRuntimeContext
from app.config.settings import get_settings
from app.services.onchainos_runner import OnchainOSReadonlyRunner
from app.services.okx_skills import OKXSkillRegistry
from app.tools.langchain_agent_tools import build_enrichment_agent_tools


class CandleOutput(BaseModel):
    close: float = Field(description="Candle close price used by deterministic TA scoring.")


class WalletSnapshotOutput(BaseModel):
    logged_in: bool = Field(description="Whether the Agentic Wallet is currently authenticated and usable.")
    account_id: str | None = Field(default=None, description="Wallet account identifier returned by onchainos wallet status.")
    account_name: str | None = Field(default=None, description="Human-readable wallet account name if available.")
    target_chain: str = Field(description="Execution chain selected for this trade candidate, such as xlayer or ethereum.")
    wallet_address: str | None = Field(default=None, description="Wallet address on the target chain.")
    available_balance_usd: float = Field(description="Available tradeable USD-equivalent balance on the target chain.")
    available_balance_token: float | None = Field(default=None, description="Available balance in the quoted funding token if available.")
    policy_single_tx_limit_usd: float | None = Field(default=None, description="Per-trade wallet policy limit, if exposed by wallet skill.")
    policy_daily_trade_limit_usd: float | None = Field(default=None, description="Daily wallet policy limit, if exposed by wallet skill.")
    policy_daily_trade_used_usd: float | None = Field(default=None, description="Daily traded amount already used, if exposed by wallet skill.")


class MarketSnapshotOutput(BaseModel):
    asset_lane: Literal["major", "regular"] = Field(description="Resolved asset lane for this trade candidate.")
    chain: str = Field(description="Chain from which the market data was gathered.")
    spot_price_usd: float | None = Field(default=None, description="Current spot price in USD.")
    market_cap_usd: float | None = Field(default=None, description="Token market cap in USD if available.")
    liquidity_usd: float | None = Field(default=None, description="Current liquidity in USD if available.")
    volume_24h_usd: float | None = Field(default=None, description="24-hour trading volume in USD if available.")
    price_change_24h_pct: float | None = Field(default=None, description="24-hour price change percentage if available.")
    kline_window: list[CandleOutput] = Field(
        description="Recent kline candles for deterministic TA. Use okx-dex-market and include at least 2 candles when available."
    )
    quote_available: bool = Field(description="Whether a swap quote or route is currently available.")
    quote_price_impact_pct: float | None = Field(default=None, description="Swap quote price impact percentage if available.")


class RiskSnapshotOutput(BaseModel):
    asset_lane: Literal["major", "regular"] = Field(description="Resolved asset lane for this trade candidate.")
    risk_scan_required: bool = Field(description="Whether the lane requires token risk scanning before a trade decision.")
    risk_scan_supported: bool = Field(description="Whether the required risk scan could be completed.")
    is_risk_token: bool | None = Field(default=None, description="Security-layer token risk flag.")
    buy_tax_pct: float | None = Field(default=None, description="Buy tax percentage if detected.")
    sell_tax_pct: float | None = Field(default=None, description="Sell tax percentage if detected.")
    risk_control_level: str | None = Field(default=None, description="Risk control level returned by token intelligence if available.")
    token_tags: list[str] = Field(default_factory=list, description="Token tags from advanced token intelligence.")
    dev_rug_pull_token_count: int | None = Field(default=None, description="Historical rug-pull count associated with the developer.")
    dev_create_token_count: int | None = Field(default=None, description="Total historical tokens created by the developer.")
    top10_hold_percent: float | None = Field(default=None, description="Top-10 holder concentration percentage.")
    lp_burned_percent: float | None = Field(default=None, description="Liquidity pool burned percentage if available.")
    creator_address: str | None = Field(default=None, description="Resolved creator address if available.")
    risk_summary: str = Field(description="Short summary of the risk context.")


class SignalOverlayOutput(BaseModel):
    supported: bool = Field(description="Whether optional overlay analysis was available.")
    smart_money_count: int | None = Field(default=None, description="Count of smart-money entities detected if available.")
    kol_count: int | None = Field(default=None, description="Count of KOL-like entities detected if available.")
    whale_count: int | None = Field(default=None, description="Count of whale entities detected if available.")
    overlay_summary: str = Field(description="Short natural-language summary of optional overlay context.")


class EnrichmentOutput(BaseModel):
    wallet_snapshot: WalletSnapshotOutput
    market_snapshot: MarketSnapshotOutput
    risk_snapshot: RiskSnapshotOutput
    signal_overlay: SignalOverlayOutput | None = None


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
            "For market context, you must load okx-dex-market and gather both spot/quote data and a recent kline window suitable for TA. "
            "The returned market_snapshot must always include kline_window as a non-empty list when market data is available. "
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
            "For wallet data, load okx-agentic-wallet.\n"
            "For market data, load okx-dex-market and explicitly call the market commands needed to populate market_snapshot, including market kline.\n"
            "For regular-token risk data, load okx-security and token intelligence context as needed.\n"
            "Do not omit market_snapshot.kline_window. If you cannot obtain it, return an empty list rather than fabricating candles.\n"
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
