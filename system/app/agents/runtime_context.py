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
class EnrichmentAgentRuntimeContext:
    user_id: str
    parsed_signal: JSONDict
    resolved_asset: JSONDict
    strategy_profile: JSONDict
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
class WalletCommandRuntimeContext:
    user_id: str
    command_name: str
    raw_text: str
    load_skill_provider: Callable[[str], str] = field(default=lambda _skill_name: "")
    load_reference_provider: Callable[[str, str], str] = field(default=lambda _skill_name, _relative_path: "")
    readonly_command_provider: Callable[[str], JSONDict] = field(default=lambda _command: {})


@dataclass
class WalletOnboardingRuntimeContext:
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
class SwapExecutionAgentRuntimeContext:
    user_id: str
    intent: JSONDict
    load_skill_provider: Callable[[str], str] = field(default=lambda _skill_name: "")
    load_reference_provider: Callable[[str, str], str] = field(default=lambda _skill_name, _relative_path: "")
    mutating_swap_provider: Callable[[JSONDict], JSONDict] = field(default=lambda _request: {})
