from app.agents.parsing import ParsingAgent


class FakeParsingBackend:
    def parse(self, *, source_id: str, message_id: str, message_text: str):
        text = message_text.lower()
        if "gm everyone" in text:
            return {
                "source_id": source_id,
                "message_id": message_id,
                "message_type": "noise",
                "is_actionable": False,
                "raw_symbol": None,
                "raw_contract_address": None,
                "raw_chain_hint": None,
                "entry_reference_text": None,
                "target_reference_text": None,
                "stop_reference_text": None,
                "urgency": None,
                "confidence": 0.2,
                "reasoning_summary": "classified as noise",
            }
        if "take profit" in text or "exit now" in text:
            return {
                "source_id": source_id,
                "message_id": message_id,
                "message_type": "exit_signal",
                "is_actionable": True,
                "raw_symbol": "ETH",
                "raw_contract_address": None,
                "raw_chain_hint": None,
                "entry_reference_text": None,
                "target_reference_text": None,
                "stop_reference_text": None,
                "urgency": "normal",
                "confidence": 0.8,
                "reasoning_summary": "classified as exit_signal",
            }
        if "0x6982508145454ce325ddbe47a25d4ec3d2311933" in text:
            return {
                "source_id": source_id,
                "message_id": message_id,
                "message_type": "trade_call",
                "is_actionable": True,
                "raw_symbol": "PEPE",
                "raw_contract_address": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
                "raw_chain_hint": "ethereum",
                "entry_reference_text": "entry now",
                "target_reference_text": None,
                "stop_reference_text": None,
                "urgency": "high",
                "confidence": 0.9,
                "reasoning_summary": "classified as trade_call",
            }
        return {
            "source_id": source_id,
            "message_id": message_id,
            "message_type": "trade_call",
            "is_actionable": True,
            "raw_symbol": "ETH",
            "raw_contract_address": None,
            "raw_chain_hint": "xlayer",
            "entry_reference_text": "entry around 3200",
            "target_reference_text": "target 3500",
            "stop_reference_text": "stop 3100",
            "urgency": "high",
            "confidence": 0.85,
            "reasoning_summary": "classified as trade_call",
        }


def test_parse_trade_call_major_asset() -> None:
    agent = ParsingAgent(backend=FakeParsingBackend())
    result = agent.parse(
        source_id="src1",
        message_id="msg1",
        message_text="Buy ETH now on X Layer. Entry around 3200, target 3500, stop 3100.",
    )
    assert result["message_type"] == "trade_call"
    assert result["is_actionable"] is True
    assert result["raw_symbol"] == "ETH"
    assert result["raw_chain_hint"] == "xlayer"
    assert result["urgency"] == "high"
    assert result["confidence"] >= 0.7


def test_parse_trade_call_regular_token_with_contract() -> None:
    agent = ParsingAgent(backend=FakeParsingBackend())
    result = agent.parse(
        source_id="src1",
        message_id="msg2",
        message_text="Buy $PEPE on ethereum CA 0x6982508145454ce325ddbe47a25d4ec3d2311933 entry now",
    )
    assert result["message_type"] == "trade_call"
    assert result["raw_symbol"] == "PEPE"
    assert result["raw_contract_address"] == "0x6982508145454ce325ddbe47a25d4ec3d2311933"
    assert result["raw_chain_hint"] == "ethereum"


def test_parse_exit_signal() -> None:
    agent = ParsingAgent(backend=FakeParsingBackend())
    result = agent.parse(
        source_id="src1",
        message_id="msg3",
        message_text="ETH take profit now, exit now.",
    )
    assert result["message_type"] == "exit_signal"
    assert result["is_actionable"] is True
    assert result["raw_symbol"] == "ETH"


def test_parse_noise_message() -> None:
    agent = ParsingAgent(backend=FakeParsingBackend())
    result = agent.parse(
        source_id="src1",
        message_id="msg4",
        message_text="GM everyone, market looks interesting today.",
    )
    assert result["message_type"] == "noise"
    assert result["is_actionable"] is False
    assert result["confidence"] == 0.2
