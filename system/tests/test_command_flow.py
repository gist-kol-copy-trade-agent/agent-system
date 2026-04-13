from app.adapters.scraper.client import ScraperClient, ScraperRegistrationRequest
from app.persistence.repositories import InMemoryFollowedSourceRepository, InMemoryStrategyProfileRepository
from app.services.command_flow import DeterministicCommandGraphService, DeterministicCommandRequest
from app.services.source_registry import SourceRegistryService
from app.services.strategy_profiles import StrategyProfileService


class FakeScraperClient(ScraperClient):
    def register_channel(self, request: ScraperRegistrationRequest) -> dict:
        return {
            "ok": True,
            "scraper_subscription_id": f"sub:{request.source_id}",
            "channel_name": request.channel_name,
            "status": "registered",
        }

    def unregister_channel(self, *, source_id: str, channel_name: str) -> dict:
        return {"ok": True, "status": "unregistered", "source_id": source_id}


def build_service() -> DeterministicCommandGraphService:
    strategy_service = StrategyProfileService(InMemoryStrategyProfileRepository())
    source_service = SourceRegistryService(InMemoryFollowedSourceRepository(), FakeScraperClient())
    return DeterministicCommandGraphService(
        strategy_profiles=strategy_service,
        source_registry=source_service,
        callback_url="https://bot.example.com/webhooks/scraper/messages",
        callback_secret="secret",
    )


def test_trade_style_graph_flow() -> None:
    service = build_service()
    state = service.run(DeterministicCommandRequest(user_id="u1", chat_id="c1", raw_text="/trade-style safe"))
    assert state["supported_command"] is True
    assert state["command_name"] == "trade-style"
    assert state["response_payload"]["base_style"] == "safe"


def test_follow_and_stop_graph_flow() -> None:
    service = build_service()
    follow = service.run(DeterministicCommandRequest(user_id="u1", chat_id="c1", raw_text="/follow alpha_kol"))
    assert follow["supported_command"] is True
    assert follow["command_name"] == "follow"
    assert follow["response_payload"]["status"] == "active"

    stop = service.run(DeterministicCommandRequest(user_id="u1", chat_id="c1", raw_text="/stop alpha_kol"))
    assert stop["supported_command"] is True
    assert stop["command_name"] == "stop"
    assert stop["response_payload"]["status"] == "inactive"
