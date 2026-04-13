from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.agents.runtime_context import PositionTrackerAgentRuntimeContext
from app.config.settings import ensure_openai_runtime_env, get_settings
from app.services.onchainos_runner import OnchainOSReadonlyRunner
from app.services.okx_skills import OKXSkillRegistry
from app.tools.langchain_agent_tools import build_position_tracker_agent_tools


class CandleOutput(BaseModel):
    close: float = Field(description="Candle close price for current token monitoring.")


class RecentPnlRowOutput(BaseModel):
    token: str | None = Field(default=None, description="Token symbol if available.")
    pnl_usd: float | None = Field(default=None, description="Recent wallet PnL in USD if available.")
    pnl_pct: float | None = Field(default=None, description="Recent wallet PnL percentage if available.")


class PositionTrackingSnapshotOutput(BaseModel):
    symbol: str = Field(description="Tracked token symbol.")
    chain: str = Field(description="Tracked chain.")
    current_price_usd: float | None = Field(default=None, description="Latest token price in USD.")
    unrealized_pnl_pct: float | None = Field(default=None, description="Current unrealized PnL percentage for the token position.")
    realized_pnl_pct: float | None = Field(default=None, description="Current realized PnL percentage if available.")
    position_value_usd: float | None = Field(default=None, description="Current marked position value in USD if available.")
    cost_basis_usd: float | None = Field(default=None, description="Cost basis in USD if available.")
    liquidity_usd: float | None = Field(default=None, description="Current token liquidity in USD if available.")
    volume_24h_usd: float | None = Field(default=None, description="24-hour volume in USD if available.")
    quote_available: bool = Field(description="Whether exit quote or route appears available.")
    quote_price_impact_pct: float | None = Field(default=None, description="Sell quote price impact percentage if available.")
    kline_window: list[CandleOutput] = Field(description="Recent kline candles for TA and trailing.")


class PortfolioTokenPnlRowOutput(BaseModel):
    symbol: str | None = Field(default=None, description="Token symbol.")
    chain: str | None = Field(default=None, description="Token chain if available.")
    unrealized_pnl_pct: float | None = Field(default=None, description="Per-token unrealized PnL percentage.")
    realized_pnl_pct: float | None = Field(default=None, description="Per-token realized PnL percentage.")
    value_usd: float | None = Field(default=None, description="Current token value in USD.")


class PortfolioTrackingSnapshotOutput(BaseModel):
    wallet_recent_pnl: list[RecentPnlRowOutput] = Field(default_factory=list, description="Recent wallet PnL rows.")
    token_pnl_rows: list[PortfolioTokenPnlRowOutput] = Field(default_factory=list, description="Per-token portfolio PnL rows.")
    tracked_bot_positions: list[PortfolioTokenPnlRowOutput] = Field(
        default_factory=list,
        description="Bot-managed positions mapped to current token PnL snapshot when possible.",
    )


class PositionTrackerOutput(BaseModel):
    position_tracking_snapshot: PositionTrackingSnapshotOutput | None = None
    portfolio_tracking_snapshot: PortfolioTrackingSnapshotOutput | None = None


class PositionTrackerBackend(Protocol):
    def track_position(
        self,
        *,
        position_snapshot: dict[str, Any],
        strategy_profile: dict[str, Any],
        resolved_wallet_address: str | None = None,
        wallet_context_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def track_portfolio(
        self,
        *,
        user_id: str,
        bot_positions: list[dict[str, Any]],
        strategy_profile: dict[str, Any] | None = None,
        resolved_wallet_address: str | None = None,
        target_chain: str | None = None,
        wallet_context_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


@dataclass
class PositionTrackerAgentConfig:
    tools: list = field(default_factory=build_position_tracker_agent_tools)


class LangChainPositionTrackerBackend:
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
        self.tools = tools if tools is not None else build_position_tracker_agent_tools()
        self.skill_registry = skill_registry or OKXSkillRegistry()
        self.readonly_runner = readonly_runner or OnchainOSReadonlyRunner(
            timeout_seconds=get_settings().models.timeout_seconds
        )

    def track_position(
        self,
        *,
        position_snapshot: dict[str, Any],
        strategy_profile: dict[str, Any],
        resolved_wallet_address: str | None = None,
        wallet_context_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._invoke(
            mode="position",
            user_id=str(position_snapshot.get("user_id") or strategy_profile.get("user_id") or "unknown"),
            payload={
                "position_snapshot": position_snapshot,
                "strategy_profile": strategy_profile,
                "resolved_wallet_address": resolved_wallet_address,
                "wallet_context_hints": wallet_context_hints or {},
            },
            position_snapshot=position_snapshot,
            bot_positions=[],
            strategy_profile=strategy_profile,
            target_chain=str(position_snapshot.get("chain") or ""),
            resolved_wallet_address=resolved_wallet_address,
            wallet_context_hints=wallet_context_hints,
        )

    def track_portfolio(
        self,
        *,
        user_id: str,
        bot_positions: list[dict[str, Any]],
        strategy_profile: dict[str, Any] | None = None,
        resolved_wallet_address: str | None = None,
        target_chain: str | None = None,
        wallet_context_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._invoke(
            mode="portfolio",
            user_id=user_id,
            payload={
                "bot_positions": bot_positions,
                "strategy_profile": strategy_profile or {},
                "resolved_wallet_address": resolved_wallet_address,
                "target_chain": target_chain,
                "wallet_context_hints": wallet_context_hints or {},
            },
            position_snapshot=None,
            bot_positions=bot_positions,
            strategy_profile=strategy_profile or {},
            target_chain=target_chain,
            resolved_wallet_address=resolved_wallet_address,
            wallet_context_hints=wallet_context_hints,
        )

    def _invoke(
        self,
        *,
        mode: str,
        user_id: str,
        payload: dict[str, Any],
        position_snapshot: dict[str, Any] | None,
        bot_positions: list[dict[str, Any]],
        strategy_profile: dict[str, Any],
        target_chain: str | None,
        resolved_wallet_address: str | None,
        wallet_context_hints: dict[str, Any] | None,
    ) -> dict[str, Any]:
        agent = self._get_agent()
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": self._build_prompt(mode=mode, payload=payload),
                    }
                ]
            },
            context=PositionTrackerAgentRuntimeContext(
                user_id=user_id,
                mode=mode,
                position_snapshot=position_snapshot,
                bot_positions=bot_positions,
                strategy_profile=strategy_profile,
                target_chain=target_chain,
                resolved_wallet_address=resolved_wallet_address,
                wallet_context_hints=wallet_context_hints,
                load_skill_provider=self.skill_registry.load_skill,
                load_reference_provider=self.skill_registry.load_reference,
                readonly_command_provider=self.readonly_runner.run,
            ),
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
            raise RuntimeError("LangChain is not installed for LangChainPositionTrackerBackend.") from exc

        system_prompt = (
            "You are a position tracker agent for an OKX OnchainOS trading bot. "
            "Load okx-dex-market and use run_onchainos_readonly to collect portfolio and token PnL context. "
            "Use onchainos market portfolio-token-pnl and onchainos market portfolio-recent-pnl when available. "
            "Always prefer resolved_wallet_address from runtime context when present. "
            "If resolved_wallet_address is missing or stale, load okx-agentic-wallet and resolve active wallet via wallet status + wallet addresses first. "
            "For single-position tracking, also gather current market price and kline data needed for exit monitoring. "
            "Return only the structured schema."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.position_tracker_model,
            tools=self.tools,
            system_prompt=system_prompt,
            context_schema=PositionTrackerAgentRuntimeContext,
            response_format=ToolStrategy(PositionTrackerOutput),
        )
        return self._agent

    @staticmethod
    def _build_prompt(*, mode: str, payload: dict[str, Any]) -> str:
        if mode == "position":
            prefix = (
                "Refresh current market and PnL tracking context for one open bot-managed position.\n"
                "Load okx-dex-market and gather current price, kline, liquidity, and per-token pnl snapshot.\n"
                "Use resolved_wallet_address when present; if missing, resolve wallet via wallet status + wallet addresses.\n"
                "Return only position_tracking_snapshot.\n"
            )
        else:
            prefix = (
                "Build a current portfolio tracking snapshot for the user wallet.\n"
                "Load okx-dex-market and gather portfolio-recent-pnl plus portfolio-token-pnl.\n"
                "Use resolved_wallet_address when present; if missing, resolve wallet via wallet status + wallet addresses.\n"
                "Map bot-managed positions to token pnl rows when possible.\n"
                "Return only portfolio_tracking_snapshot.\n"
            )
        return prefix + json.dumps(payload, ensure_ascii=True)

    @staticmethod
    def _extract_output(result) -> PositionTrackerOutput:
        if isinstance(result, PositionTrackerOutput):
            return result
        if isinstance(result, dict):
            if "structured_response" in result:
                structured = result["structured_response"]
                if isinstance(structured, PositionTrackerOutput):
                    return structured
                if isinstance(structured, dict):
                    return PositionTrackerOutput(**structured)
            if "output" in result and isinstance(result["output"], dict):
                return PositionTrackerOutput(**result["output"])
        if isinstance(result, str):
            return PositionTrackerOutput(**json.loads(result))
        raise RuntimeError("Could not extract position tracker output from LangChain agent result.")


class PositionTrackerAgent:
    def __init__(
        self,
        config: PositionTrackerAgentConfig | None = None,
        backend: PositionTrackerBackend | None = None,
    ) -> None:
        self.config = config or PositionTrackerAgentConfig()
        self.backend = backend or LangChainPositionTrackerBackend(tools=self.config.tools)

    def track_position(
        self,
        *,
        position_snapshot: dict[str, Any],
        strategy_profile: dict[str, Any],
        resolved_wallet_address: str | None = None,
        wallet_context_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.backend.track_position(
            position_snapshot=position_snapshot,
            strategy_profile=strategy_profile,
            resolved_wallet_address=resolved_wallet_address,
            wallet_context_hints=wallet_context_hints,
        )

    def track_portfolio(
        self,
        *,
        user_id: str,
        bot_positions: list[dict[str, Any]],
        strategy_profile: dict[str, Any] | None = None,
        resolved_wallet_address: str | None = None,
        target_chain: str | None = None,
        wallet_context_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.backend.track_portfolio(
            user_id=user_id,
            bot_positions=bot_positions,
            strategy_profile=strategy_profile,
            resolved_wallet_address=resolved_wallet_address,
            target_chain=target_chain,
            wallet_context_hints=wallet_context_hints,
        )
