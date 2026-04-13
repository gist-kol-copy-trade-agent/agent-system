from app.agents.parsing import LangChainParsingBackend, ParsedSignalOutput, ParsingAgent


class FakeAgent:
    def invoke(self, _payload, *, context=None):
        return {
            "structured_response": {
                "message_type": "trade_call",
                "is_actionable": True,
                "raw_symbol": "ETH",
                "raw_contract_address": None,
                "raw_chain_hint": "xlayer",
                "entry_reference_text": "entry around 3200",
                "target_reference_text": "target 3500",
                "stop_reference_text": "stop 3100",
                "urgency": "high",
                "confidence": 0.9,
                "reasoning_summary": "classified as trade_call; symbol=ETH; chain_hint=xlayer",
            }
        }


class FakeLangChainParsingBackend(LangChainParsingBackend):
    def __init__(self) -> None:
        super().__init__()
        self._agent = FakeAgent()


def test_langchain_backend_extracts_structured_output() -> None:
    backend = FakeLangChainParsingBackend()
    result = backend.parse(source_id="src1", message_id="msg1", message_text="Buy ETH now on X Layer")
    assert result["message_type"] == "trade_call"
    assert result["raw_symbol"] == "ETH"
    assert result["raw_chain_hint"] == "xlayer"


def test_parsing_agent_can_use_explicit_langchain_backend() -> None:
    agent = ParsingAgent(backend=FakeLangChainParsingBackend())
    result = agent.parse(source_id="src1", message_id="msg1", message_text="Buy ETH now on X Layer")
    assert result["is_actionable"] is True
    assert result["confidence"] == 0.9
