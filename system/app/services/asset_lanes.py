from __future__ import annotations

from app.config.settings import get_settings
from app.schemas.domain import AssetLane, ParsedSignal


class AssetLaneClassifier:
    def classify(self, parsed_signal: ParsedSignal) -> tuple[AssetLane, str | None]:
        settings = get_settings()
        symbol = parsed_signal.get("raw_symbol")
        if symbol and symbol.upper() in settings.wallet.major_assets:
            return "major", settings.wallet.major_execution_chain

        return "regular", parsed_signal.get("raw_chain_hint")
