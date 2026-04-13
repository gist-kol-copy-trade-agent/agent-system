from app.agents.wallet_command import WalletCommandAgent, WalletCommandOutput


class FakeWalletBackend:
    def handle(self, *, user_id: str, command_name: str, raw_text: str) -> WalletCommandOutput:
        return WalletCommandOutput(
            command=command_name,
            message=f"handled {command_name}",
            payload={"user_id": user_id, "raw_text": raw_text},
        )


def test_wallet_command_agent_uses_injected_backend() -> None:
    agent = WalletCommandAgent(backend=FakeWalletBackend())
    result = agent.handle(user_id="u1", command_name="status", raw_text="/status")
    assert result.command == "status"
    assert result.payload["user_id"] == "u1"
    assert result.payload["raw_text"] == "/status"
