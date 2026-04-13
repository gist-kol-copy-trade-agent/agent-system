from __future__ import annotations

from typing import Any

from app.schemas.domain import MarketSnapshot, RiskSnapshot, WalletSnapshot


def normalize_wallet_snapshot(
    *,
    chain: str,
    status_payload: dict[str, Any],
    balance_payload: dict[str, Any],
    addresses_payload: dict[str, Any],
) -> WalletSnapshot:
    data = status_payload.get("data", status_payload)
    balance_data = balance_payload.get("data", balance_payload)
    addresses_data = addresses_payload.get("data", addresses_payload)
    wallet_address = (
        addresses_data.get("address")
        or addresses_data.get("evmAddress")
        or addresses_data.get("solAddress")
        or addresses_data.get("xlayerAddress")
        or "unknown-address"
    )
    return WalletSnapshot(
        logged_in=bool(data.get("loggedIn", False)),
        account_id=data.get("currentAccountId"),
        account_name=data.get("currentAccountName"),
        target_chain=chain,
        wallet_address=wallet_address,
        available_balance_usd=float(balance_data.get("totalValueUsd", 0) or 0),
        available_balance_token=None,
        policy_single_tx_limit_usd=_to_float(data.get("policy", {}).get("singleTxLimit")),
        policy_daily_trade_limit_usd=_to_float(data.get("policy", {}).get("dailyTradeTxLimit")),
        policy_daily_trade_used_usd=_to_float(data.get("policy", {}).get("dailyTradeTxUsed")),
    )


def normalize_market_snapshot(
    *,
    asset_lane: str,
    chain: str,
    price_payload: dict[str, Any],
    price_info_payload: dict[str, Any] | None,
    kline_payload: dict[str, Any],
    quote_payload: dict[str, Any] | None,
) -> MarketSnapshot:
    price_data = price_payload.get("data", price_payload)
    info_data = (price_info_payload or {}).get("data", price_info_payload or {})
    quote_data = (quote_payload or {}).get("data", quote_payload or {})
    kline_data = kline_payload.get("data", kline_payload)
    return MarketSnapshot(
        asset_lane=asset_lane,
        chain=chain,
        spot_price_usd=_to_float(price_data.get("priceUsd") or price_data.get("price")),
        market_cap_usd=_to_float(info_data.get("marketCap")),
        liquidity_usd=_to_float(info_data.get("liquidity")),
        volume_24h_usd=_to_float(info_data.get("volume24h") or info_data.get("volume24H")),
        price_change_24h_pct=_to_float(info_data.get("priceChange24H")),
        kline_window=kline_data.get("list", []) if isinstance(kline_data, dict) else kline_data or [],
        quote_available=bool(quote_data),
        quote_price_impact_pct=_to_float(quote_data.get("priceImpactPercent")),
    )


def normalize_risk_snapshot(
    *,
    asset_lane: str,
    security_payload: dict[str, Any] | None,
    advanced_info_payload: dict[str, Any] | None,
) -> RiskSnapshot:
    security_data = (security_payload or {}).get("data", security_payload or {})
    if isinstance(security_data, list):
        security_data = security_data[0] if security_data else {}
    advanced_data = (advanced_info_payload or {}).get("data", advanced_info_payload or {})
    return RiskSnapshot(
        asset_lane=asset_lane,
        risk_scan_required=asset_lane == "regular",
        risk_scan_supported=bool(security_data) if asset_lane == "regular" else False,
        is_risk_token=_to_bool(security_data.get("isRiskToken")) if asset_lane == "regular" else None,
        buy_tax_pct=_to_float(security_data.get("buyTaxes")),
        sell_tax_pct=_to_float(security_data.get("sellTaxes")),
        risk_control_level=_to_str(advanced_data.get("riskControlLevel")),
        token_tags=list(advanced_data.get("tokenTags") or []),
        dev_rug_pull_token_count=_to_int(advanced_data.get("devRugPullTokenCount")),
        dev_create_token_count=_to_int(advanced_data.get("devCreateTokenCount")),
        top10_hold_percent=_to_float(advanced_data.get("top10HoldPercent")),
        lp_burned_percent=_to_float(advanced_data.get("lpBurnedPercent")),
        creator_address=_to_str(advanced_data.get("creatorAddress")),
        risk_summary="Normalized risk snapshot from OKX security and token intelligence data."
        if asset_lane == "regular"
        else "Major-asset lane skips regular-token risk scan.",
    )


def _to_float(value: Any) -> float | None:
    if value in (None, "", []):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value in (None, "", []):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool | None:
    if value in (None, "", []):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _to_str(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    return str(value)
