from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from app.agents.runtime_context import DecisionAgentRuntimeContext
from app.config.settings import get_settings
from app.services.onchainos_runner import OnchainOSReadonlyRunner
from app.services.okx_skills import OKXSkillRegistry
from app.tools.langchain_agent_tools import build_decision_agent_tools


class TradeDecisionOutput(BaseModel):
    asset_lane: str
    decision: str
    decision_reason_code: str
    confidence: float
    recommended_amount_usd: float
    capped_amount_usd: float
    rationale_summary: str
    telegram_summary: str


class DecisionBackend(Protocol):
    def decide(
        self,
        *,
        parsed_signal: dict[str, Any],
        resolved_asset: dict[str, Any],
        wallet_snapshot: dict[str, Any],
        market_snapshot: dict[str, Any],
        risk_snapshot: dict[str, Any],
        ta_snapshot: dict[str, Any],
        strategy_profile: dict[str, Any],
        signal_overlay: dict[str, Any] | None,
    ) -> dict[str, Any]: ...


@dataclass
class DecisionAgentConfig:
    min_ta_score_major: float = 0.50
    min_ta_score_regular: float = 0.60
    tools: list = field(default_factory=build_decision_agent_tools)


class LangChainDecisionBackend:
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
        self.tools = tools if tools is not None else build_decision_agent_tools()
        self.skill_registry = skill_registry or OKXSkillRegistry()
        self.readonly_runner = readonly_runner or OnchainOSReadonlyRunner(
            timeout_seconds=get_settings().models.timeout_seconds
        )

    def decide(
        self,
        *,
        parsed_signal: dict[str, Any],
        resolved_asset: dict[str, Any],
        wallet_snapshot: dict[str, Any],
        market_snapshot: dict[str, Any],
        risk_snapshot: dict[str, Any],
        ta_snapshot: dict[str, Any],
        strategy_profile: dict[str, Any],
        signal_overlay: dict[str, Any] | None,
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
                wallet_snapshot=wallet_snapshot,
                market_snapshot=market_snapshot,
                risk_snapshot=risk_snapshot,
                ta_snapshot=ta_snapshot,
                strategy_profile=strategy_profile,
                signal_overlay=signal_overlay,
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
            raise RuntimeError("LangChain is not installed for LangChainDecisionBackend.") from exc

        system_prompt = (
            "You are a decision agent for an on-chain copy-trading bot. "
            "You receive structured signal, resolved asset, and strategy-profile context. "
            "For OKX OnchainOS-covered capabilities, first load the relevant OKX skill and follow its guidance through "
            "run_onchainos_readonly rather than relying on hidden backend wrappers. "
            "Use app-owned tools only for capabilities not covered by OnchainOS, such as TA scoring and trade sizing inputs. "
            "Return a structured trade decision with one of: execute, skip, block. "
            "Be lane-aware: major assets and regular tokens have different analysis requirements. "
            "Do not invent missing data. Output only the structured schema."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.decision_model,
            tools=self.tools,
            system_prompt=system_prompt,
            context_schema=DecisionAgentRuntimeContext,
            response_format=ToolStrategy(TradeDecisionOutput),
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
            "Make a structured trade decision from this context.\n"
            "Load the relevant OKX skill prompts on demand. Use run_onchainos_readonly for wallet, market, risk, and quote data. "
            "Use app tools only for TA scoring and deterministic sizing.\n"
            "Do not assume that omitted context is safe.\n"
            + json.dumps(payload, ensure_ascii=True)
        )

    def _build_runtime_context(
        self,
        *,
        parsed_signal: dict[str, Any],
        resolved_asset: dict[str, Any],
        wallet_snapshot: dict[str, Any],
        market_snapshot: dict[str, Any],
        risk_snapshot: dict[str, Any],
        ta_snapshot: dict[str, Any],
        strategy_profile: dict[str, Any],
        signal_overlay: dict[str, Any] | None,
    ) -> DecisionAgentRuntimeContext:
        def major_asset_execution_context_provider() -> dict[str, Any]:
            if resolved_asset.get("asset_lane") != "major":
                return {}
            return {
                "approved_major_mapping": resolved_asset.get("approved_major_mapping"),
                "target_execution_chain": resolved_asset.get("target_execution_chain"),
                "wallet_snapshot": wallet_snapshot,
                "market_snapshot": market_snapshot,
            }

        def trade_sizing_inputs_provider() -> dict[str, Any]:
            max_amount = strategy_profile.get("max_amount_per_trade_usd", 0.0)
            lane_cap_key = (
                "major_asset_max_amount_usd"
                if resolved_asset.get("asset_lane") == "major"
                else "regular_token_max_amount_usd"
            )
            lane_cap = strategy_profile.get(lane_cap_key, max_amount)
            balance = wallet_snapshot.get("available_balance_usd", 0.0) if wallet_snapshot else 0.0
            ta_score = ta_snapshot.get("ta_score", 0.0) if ta_snapshot else 0.0
            recommended = min(float(max_amount), float(lane_cap), float(balance))
            return {
                "asset_lane": resolved_asset.get("asset_lane"),
                "wallet_balance_usd": balance,
                "max_amount_per_trade_usd": max_amount,
                "lane_cap_usd": lane_cap,
                "ta_score": ta_score,
                "recommended_amount_usd": recommended,
                "capped_amount_usd": recommended,
            }

        return DecisionAgentRuntimeContext(
            user_id=str(strategy_profile.get("user_id") or "unknown"),
            parsed_signal=parsed_signal,
            resolved_asset=resolved_asset,
            strategy_profile=strategy_profile,
            load_skill_provider=self.skill_registry.load_skill,
            load_reference_provider=self.skill_registry.load_reference,
            readonly_command_provider=self.readonly_runner.run,
            preloaded_wallet_snapshot=wallet_snapshot,
            preloaded_market_snapshot=market_snapshot,
            preloaded_risk_snapshot=risk_snapshot,
            preloaded_signal_overlay=signal_overlay,
            major_asset_execution_context_provider=major_asset_execution_context_provider,
            ta_score_provider=lambda: ta_snapshot,
            trade_sizing_inputs_provider=trade_sizing_inputs_provider,
        )

    def _extract_output(self, result) -> TradeDecisionOutput:
        if isinstance(result, TradeDecisionOutput):
            return result
        if isinstance(result, dict):
            if "structured_response" in result:
                structured = result["structured_response"]
                if isinstance(structured, TradeDecisionOutput):
                    return structured
                if isinstance(structured, dict):
                    return TradeDecisionOutput(**structured)
            if "output" in result and isinstance(result["output"], dict):
                return TradeDecisionOutput(**result["output"])
        if isinstance(result, str):
            return TradeDecisionOutput(**json.loads(result))
        raise RuntimeError("Could not extract structured decision output from LangChain agent result.")


class DecisionAgent:
    """Decision agent with injectable test backend and LangChain runtime default."""

    def __init__(self, config: DecisionAgentConfig | None = None, backend: DecisionBackend | None = None) -> None:
        self.config = config or DecisionAgentConfig()
        self.backend = backend or LangChainDecisionBackend(tools=self.config.tools)

    def decide(
        self,
        *,
        parsed_signal: dict[str, Any],
        resolved_asset: dict[str, Any],
        wallet_snapshot: dict[str, Any],
        market_snapshot: dict[str, Any],
        risk_snapshot: dict[str, Any],
        ta_snapshot: dict[str, Any],
        strategy_profile: dict[str, Any],
        signal_overlay: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return self.backend.decide(
            parsed_signal=parsed_signal,
            resolved_asset=resolved_asset,
            wallet_snapshot=wallet_snapshot,
            market_snapshot=market_snapshot,
            risk_snapshot=risk_snapshot,
            ta_snapshot=ta_snapshot,
            strategy_profile=strategy_profile,
            signal_overlay=signal_overlay,
        )
