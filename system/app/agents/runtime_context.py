from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


JSONDict = dict[str, Any]


@dataclass
class ParsingAgentRuntimeContext:
    source_id: str
    message_id: str
    load_skill_provider: Callable[[str], str] = field(default=lambda _skill_name: "")
    load_reference_provider: Callable[[str, str], str] = field(default=lambda _skill_name, _relative_path: "")
    readonly_command_provider: Callable[[str], JSONDict] = field(default=lambda _command: {})
    search_token_candidates_provider: Callable[[str, str | None], list[JSONDict]] = field(
        default=lambda _query, _chain_hint=None: []
    )
    get_token_metadata_provider: Callable[[str, str | None], JSONDict | None] = field(
        default=lambda _identifier, _chain_hint=None: None
    )


@dataclass
class DecisionAgentRuntimeContext:
    user_id: str
    parsed_signal: JSONDict
    resolved_asset: JSONDict
    strategy_profile: JSONDict
    load_skill_provider: Callable[[str], str] = field(default=lambda _skill_name: "")
    load_reference_provider: Callable[[str, str], str] = field(default=lambda _skill_name, _relative_path: "")
    readonly_command_provider: Callable[[str], JSONDict] = field(default=lambda _command: {})
    preloaded_wallet_snapshot: JSONDict | None = None
    preloaded_market_snapshot: JSONDict | None = None
    preloaded_risk_snapshot: JSONDict | None = None
    preloaded_signal_overlay: JSONDict | None = None
    wallet_context_provider: Callable[[str], JSONDict] = field(default=lambda _chain: {})
    market_snapshot_provider: Callable[[], JSONDict] = field(default=lambda: {})
    token_risk_provider: Callable[[], JSONDict] = field(default=lambda: {})
    signal_overlay_provider: Callable[[], JSONDict] = field(default=lambda: {})
    major_asset_execution_context_provider: Callable[[], JSONDict] = field(default=lambda: {})
    ta_score_provider: Callable[[], JSONDict] = field(default=lambda: {})
    trade_sizing_inputs_provider: Callable[[], JSONDict] = field(default=lambda: {})
