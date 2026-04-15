from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


JSONDict = dict[str, Any]


@dataclass
class ParsingAgentRuntimeContext:
    source_id: str
    message_id: str
    media_blobs: list[JSONDict] | None = None
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
class EnrichmentAgentRuntimeContext:
    user_id: str
    parsed_signal: JSONDict
    resolved_asset: JSONDict
    strategy_profile: JSONDict
    wallet_context_hints: JSONDict | None = None
    load_skill_provider: Callable[[str], str] = field(default=lambda _skill_name: "")
    load_reference_provider: Callable[[str, str], str] = field(default=lambda _skill_name, _relative_path: "")
    readonly_command_provider: Callable[[str], JSONDict] = field(default=lambda _command: {})


@dataclass
class FollowProfilingAgentRuntimeContext:
    user_id: str
    source_id: str
    channel_name: str
    load_skill_provider: Callable[[str], str] = field(default=lambda _skill_name: "")
    load_reference_provider: Callable[[str, str], str] = field(default=lambda _skill_name, _relative_path: "")
    readonly_command_provider: Callable[[str], JSONDict] = field(default=lambda _command: {})


@dataclass
class DecisionAgentRuntimeContext:
    user_id: str
    parsed_signal: JSONDict
    resolved_asset: JSONDict
    wallet_snapshot: JSONDict
    market_snapshot: JSONDict
    risk_snapshot: JSONDict
    ta_snapshot: JSONDict
    strategy_profile: JSONDict
    signal_overlay: JSONDict | None = None


@dataclass
class WalletAgentRuntimeContext:
    user_id: str
    raw_text: str
    phase: str
    locale: str
    load_skill_provider: Callable[[str], str] = field(default=lambda _skill_name: "")
    load_reference_provider: Callable[[str, str], str] = field(default=lambda _skill_name, _relative_path: "")
    readonly_command_provider: Callable[[str], JSONDict] = field(default=lambda _command: {})
    mutating_wallet_provider: Callable[[JSONDict], JSONDict] = field(default=lambda _request: {})


@dataclass
class ExitAgentRuntimeContext:
    user_id: str
    position_snapshot: JSONDict
    strategy_profile: JSONDict
    trailing_state: JSONDict | None = None
    load_skill_provider: Callable[[str], str] = field(default=lambda _skill_name: "")
    load_reference_provider: Callable[[str, str], str] = field(default=lambda _skill_name, _relative_path: "")
    readonly_command_provider: Callable[[str], JSONDict] = field(default=lambda _command: {})
    position_snapshot_provider: Callable[[], JSONDict] = field(default=lambda: {})
    exit_market_snapshot_provider: Callable[[], JSONDict] = field(default=lambda: {})
    exit_ta_score_provider: Callable[[], JSONDict] = field(default=lambda: {})


@dataclass
class PositionTrackerAgentRuntimeContext:
    user_id: str
    mode: str
    position_snapshot: JSONDict | None = None
    bot_positions: list[JSONDict] | None = None
    strategy_profile: JSONDict | None = None
    target_chain: str | None = None
    resolved_wallet_address: str | None = None
    wallet_context_hints: JSONDict | None = None
    load_skill_provider: Callable[[str], str] = field(default=lambda _skill_name: "")
    load_reference_provider: Callable[[str, str], str] = field(default=lambda _skill_name, _relative_path: "")
    readonly_command_provider: Callable[[str], JSONDict] = field(default=lambda _command: {})


@dataclass
class HistoryAgentRuntimeContext:
    user_id: str
    raw_text: str
    time_window: str | None = None
    target_chains: list[str] | None = None
    begin_ms: int | None = None
    end_ms: int | None = None
    resolved_wallet_address: str | None = None
    wallet_context_hints: JSONDict | None = None
    load_skill_provider: Callable[[str], str] = field(default=lambda _skill_name: "")
    load_reference_provider: Callable[[str, str], str] = field(default=lambda _skill_name, _relative_path: "")
    readonly_command_provider: Callable[[str], JSONDict] = field(default=lambda _command: {})


@dataclass
class SwapExecutionAgentRuntimeContext:
    user_id: str
    intent: JSONDict
    resolved_wallet_address: str | None = None
    load_skill_provider: Callable[[str], str] = field(default=lambda _skill_name: "")
    load_reference_provider: Callable[[str, str], str] = field(default=lambda _skill_name, _relative_path: "")
    readonly_command_provider: Callable[[str], JSONDict] = field(default=lambda _command: {})
    mutating_swap_provider: Callable[[JSONDict], JSONDict] = field(default=lambda _request: {})
