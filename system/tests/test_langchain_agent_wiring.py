from __future__ import annotations

from typing import Any

import pytest

from app.agents.decision import LangChainDecisionBackend
from app.agents.enrichment import LangChainEnrichmentBackend
from app.agents.exit import LangChainExitBackend
from app.agents.follow_profiling import LangChainFollowProfilingBackend
from app.agents.history import LangChainHistoryBackend
from app.agents.parsing import LangChainParsingBackend
from app.agents.position_tracker import LangChainPositionTrackerBackend
from app.agents.swap_execution import LangChainSwapExecutionBackend
from app.agents.trade_style_override import LangChainTradeStyleOverrideBackend
from app.agents.wallet_agent import LangChainWalletBackend
from app.agents.runtime_context import (
    DecisionAgentRuntimeContext,
    EnrichmentAgentRuntimeContext,
    ExitAgentRuntimeContext,
    FollowProfilingAgentRuntimeContext,
    HistoryAgentRuntimeContext,
    ParsingAgentRuntimeContext,
    PositionTrackerAgentRuntimeContext,
    SwapExecutionAgentRuntimeContext,
    WalletAgentRuntimeContext,
)


def test_parsing_backend_registers_bound_tools_and_context_schema(monkeypatch) -> None:
    langchain = pytest.importorskip("langchain.agents")

    captured: dict[str, Any] = {}

    def fake_create_agent(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(langchain, "create_agent", fake_create_agent)

    backend = LangChainParsingBackend()
    backend._get_agent()

    kwargs = captured["kwargs"]
    assert kwargs["context_schema"] is ParsingAgentRuntimeContext
    assert {tool.name for tool in kwargs["tools"]} == {
        "load_okx_skill",
        "load_okx_skill_reference",
        "run_onchainos_readonly",
    }


def test_enrichment_backend_registers_bound_tools_and_context_schema(monkeypatch) -> None:
    langchain = pytest.importorskip("langchain.agents")

    captured: dict[str, Any] = {}

    def fake_create_agent(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(langchain, "create_agent", fake_create_agent)

    backend = LangChainEnrichmentBackend()
    backend._get_agent()

    kwargs = captured["kwargs"]
    assert kwargs["context_schema"] is EnrichmentAgentRuntimeContext
    assert {tool.name for tool in kwargs["tools"]} == {
        "load_okx_skill",
        "load_okx_skill_reference",
        "run_onchainos_readonly",
    }


def test_decision_backend_registers_bound_tools_and_context_schema(monkeypatch) -> None:
    langchain = pytest.importorskip("langchain.agents")

    captured: dict[str, Any] = {}

    def fake_create_agent(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(langchain, "create_agent", fake_create_agent)

    backend = LangChainDecisionBackend()
    backend._get_agent()

    kwargs = captured["kwargs"]
    assert kwargs["context_schema"] is DecisionAgentRuntimeContext
    assert kwargs["tools"] == []


def test_trade_style_override_backend_registers_no_tools(monkeypatch) -> None:
    langchain = pytest.importorskip("langchain.agents")

    captured: dict[str, Any] = {}

    def fake_create_agent(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(langchain, "create_agent", fake_create_agent)

    backend = LangChainTradeStyleOverrideBackend()
    backend._get_agent()

    kwargs = captured["kwargs"]
    assert kwargs["tools"] == []


def test_follow_profiling_backend_registers_bound_tools_and_context_schema(monkeypatch) -> None:
    langchain = pytest.importorskip("langchain.agents")

    captured: dict[str, Any] = {}

    def fake_create_agent(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(langchain, "create_agent", fake_create_agent)

    backend = LangChainFollowProfilingBackend()
    backend._get_agent()

    kwargs = captured["kwargs"]
    assert kwargs["context_schema"] is FollowProfilingAgentRuntimeContext
    assert {tool.name for tool in kwargs["tools"]} == {
        "load_okx_skill",
        "load_okx_skill_reference",
        "run_onchainos_readonly",
    }


def test_decision_backend_uses_runtime_context_instead_of_prompt_stuffing() -> None:
    class FakeAgent:
        def __init__(self) -> None:
            self.payload = None
            self.context = None

        def invoke(self, payload, *, context=None):
            self.payload = payload
            self.context = context
            return {
                "structured_response": {
                    "asset_lane": "major",
                    "decision": "execute",
                    "decision_reason_code": "READY_FOR_POLICY_GATE",
                    "confidence": 0.9,
                    "recommended_amount_usd": 100.0,
                    "capped_amount_usd": 100.0,
                    "rationale_summary": "ready",
                    "telegram_summary": "execute",
                }
            }

    backend = LangChainDecisionBackend()
    backend._agent = FakeAgent()

    result = backend.decide(
        parsed_signal={"message_type": "trade_call", "confidence": 0.9},
        resolved_asset={
            "asset_lane": "major",
            "target_execution_chain": "xlayer",
            "approved_major_mapping": "ETH",
        },
        wallet_snapshot={"logged_in": True, "available_balance_usd": 500.0},
        market_snapshot={"spot_price_usd": 3200.0, "quote_available": True},
        risk_snapshot={"asset_lane": "major"},
        ta_snapshot={"ta_score": 0.88},
        strategy_profile={
            "user_id": "u1",
            "base_style": "normal",
            "max_amount_per_trade_usd": 100.0,
            "major_asset_max_amount_usd": 100.0,
            "regular_token_max_amount_usd": 50.0,
        },
        signal_overlay=None,
    )

    assert result["decision"] == "execute"
    payload_text = backend._agent.payload["messages"][0]["content"]
    assert "wallet_snapshot" in payload_text
    assert "market_snapshot" in payload_text
    assert "risk_snapshot" in payload_text
    assert "ta_snapshot" in payload_text
    assert backend._agent.context.wallet_snapshot == {"logged_in": True, "available_balance_usd": 500.0}


def test_wallet_agent_backend_registers_bound_tools_and_context_schema(monkeypatch) -> None:
    langchain = pytest.importorskip("langchain.agents")

    captured: dict[str, Any] = {}

    def fake_create_agent(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(langchain, "create_agent", fake_create_agent)

    backend = LangChainWalletBackend()
    backend._get_agent()

    kwargs = captured["kwargs"]
    assert kwargs["context_schema"] is WalletAgentRuntimeContext
    assert {tool.name for tool in kwargs["tools"]} == {
        "load_okx_skill",
        "load_okx_skill_reference",
        "run_onchainos_readonly",
        "run_onchainos_mutating_wallet",
    }


def test_exit_backend_registers_bound_tools_and_context_schema(monkeypatch) -> None:
    langchain = pytest.importorskip("langchain.agents")

    captured: dict[str, Any] = {}

    def fake_create_agent(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(langchain, "create_agent", fake_create_agent)

    backend = LangChainExitBackend()
    backend._get_agent()

    kwargs = captured["kwargs"]
    assert kwargs["context_schema"] is ExitAgentRuntimeContext
    assert {tool.name for tool in kwargs["tools"]} == {
        "load_okx_skill",
        "load_okx_skill_reference",
        "get_position_snapshot",
        "get_token_market_snapshot",
        "compute_exit_ta_score",
    }


def test_swap_execution_backend_registers_bound_tools_and_context_schema(monkeypatch) -> None:
    langchain = pytest.importorskip("langchain.agents")

    captured: dict[str, Any] = {}

    def fake_create_agent(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(langchain, "create_agent", fake_create_agent)

    backend = LangChainSwapExecutionBackend()
    backend._get_agent()

    kwargs = captured["kwargs"]
    assert kwargs["context_schema"] is SwapExecutionAgentRuntimeContext
    assert {tool.name for tool in kwargs["tools"]} == {
        "load_okx_skill",
        "load_okx_skill_reference",
        "run_onchainos_readonly",
        "run_onchainos_mutating_swap",
    }


def test_position_tracker_backend_registers_bound_tools_and_context_schema(monkeypatch) -> None:
    langchain = pytest.importorskip("langchain.agents")

    captured: dict[str, Any] = {}

    def fake_create_agent(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(langchain, "create_agent", fake_create_agent)

    backend = LangChainPositionTrackerBackend()
    backend._get_agent()

    kwargs = captured["kwargs"]
    assert kwargs["context_schema"] is PositionTrackerAgentRuntimeContext
    assert {tool.name for tool in kwargs["tools"]} == {
        "load_okx_skill",
        "load_okx_skill_reference",
        "run_onchainos_readonly",
    }


def test_history_backend_registers_bound_tools_and_context_schema(monkeypatch) -> None:
    langchain = pytest.importorskip("langchain.agents")

    captured: dict[str, Any] = {}

    def fake_create_agent(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(langchain, "create_agent", fake_create_agent)

    backend = LangChainHistoryBackend()
    backend._get_agent()

    kwargs = captured["kwargs"]
    assert kwargs["context_schema"] is HistoryAgentRuntimeContext
    assert {tool.name for tool in kwargs["tools"]} == {
        "load_okx_skill",
        "load_okx_skill_reference",
        "run_onchainos_readonly",
    }
