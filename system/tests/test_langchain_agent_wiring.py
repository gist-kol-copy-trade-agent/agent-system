from __future__ import annotations

from typing import Any

import pytest

from app.agents.decision import LangChainDecisionBackend
from app.agents.exit import LangChainExitBackend
from app.agents.parsing import LangChainParsingBackend
from app.agents.runtime_context import (
    DecisionAgentRuntimeContext,
    ExitAgentRuntimeContext,
    ParsingAgentRuntimeContext,
    WalletCommandRuntimeContext,
)
from app.agents.wallet_command import LangChainWalletCommandBackend


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
    assert {tool.name for tool in kwargs["tools"]} == {
        "load_okx_skill",
        "load_okx_skill_reference",
        "run_onchainos_readonly",
        "compute_ta_score",
        "build_trade_sizing_inputs",
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
    assert "wallet_snapshot" not in payload_text
    assert "market_snapshot" not in payload_text
    assert "risk_snapshot" not in payload_text
    assert "ta_snapshot" not in payload_text
    assert backend._agent.context.preloaded_wallet_snapshot == {"logged_in": True, "available_balance_usd": 500.0}


def test_wallet_command_backend_registers_bound_tools_and_context_schema(monkeypatch) -> None:
    langchain = pytest.importorskip("langchain.agents")

    captured: dict[str, Any] = {}

    def fake_create_agent(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(langchain, "create_agent", fake_create_agent)

    backend = LangChainWalletCommandBackend()
    backend._get_agent()

    kwargs = captured["kwargs"]
    assert kwargs["context_schema"] is WalletCommandRuntimeContext
    assert {tool.name for tool in kwargs["tools"]} == {
        "load_okx_skill",
        "load_okx_skill_reference",
        "run_onchainos_readonly",
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
