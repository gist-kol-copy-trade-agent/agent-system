from app.agents.wallet_command import WalletCommandAgent, WalletCommandOutput
from app.services.wallet_command_flow import WalletCommandGraphService, WalletCommandRequest


class FakeWalletFlowBackend:
    def handle(self, *, user_id: str, command_name: str, raw_text: str) -> WalletCommandOutput:
        return WalletCommandOutput(
            command=command_name,
            message=f"{command_name} handled",
            payload={"skill": "okx-agentic-wallet", "raw_text": raw_text, "user_id": user_id},
        )


def build_service() -> WalletCommandGraphService:
    return WalletCommandGraphService(wallet_command_agent=WalletCommandAgent(backend=FakeWalletFlowBackend()))


def test_wallet_command_flow_start() -> None:
    service = build_service()
    state = service.run(WalletCommandRequest(user_id="u1", chat_id="c1", raw_text="/start"))
    assert state["supported_command"] is True
    assert state["command_name"] == "start"
    assert state["response_payload"]["skill"] == "okx-agentic-wallet"


def test_wallet_command_flow_history() -> None:
    service = build_service()
    state = service.run(WalletCommandRequest(user_id="u1", chat_id="c1", raw_text="/history 7d"))
    assert state["supported_command"] is True
    assert state["command_name"] == "history"
    assert state["response_message"] == "history handled"
