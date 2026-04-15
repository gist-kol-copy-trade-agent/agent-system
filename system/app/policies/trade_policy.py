from __future__ import annotations

from app.agents.decision import DecisionAgentConfig
from app.policies.interfaces import PolicyEvaluation, TradePolicyEngine


class DefaultTradePolicyEngine(TradePolicyEngine):
    def __init__(self, config: DecisionAgentConfig | None = None) -> None:
        self.config = config or DecisionAgentConfig()

    def evaluate(self, context: dict) -> PolicyEvaluation:
        decision = context["trade_decision"]
        resolved = context["resolved_asset"]
        wallet = context["wallet_snapshot"]
        market = context["market_snapshot"]
        risk = context["risk_snapshot"]
        ta = context["ta_snapshot"]
        strategy = context["strategy_profile"]
        active_position_count = int(context.get("active_position_count") or 0)

        action = decision["decision"]
        failure_codes: list[str] = []

        if action == "block":
            failure_codes.append(decision["decision_reason_code"])
            return PolicyEvaluation(False, "block", failure_codes, "Decision agent produced a block result.")

        if action == "skip":
            failure_codes.append(decision["decision_reason_code"])

        if wallet["logged_in"] is not True:
            return PolicyEvaluation(False, "block", self._append(failure_codes, "WALLET_NOT_READY"), "Wallet is not ready.")

        if not wallet["wallet_address"]:
            return PolicyEvaluation(
                False,
                "block",
                self._append(failure_codes, "CHAIN_ADDRESS_UNAVAILABLE"),
                "Target chain wallet address is unavailable.",
            )

        if wallet["available_balance_usd"] <= 0:
            return PolicyEvaluation(
                False,
                "skip",
                self._append(failure_codes, "INSUFFICIENT_CHAIN_BALANCE"),
                "No executable balance on target chain.",
            )

        if active_position_count >= int(strategy["max_active_positions"]):
            return PolicyEvaluation(
                False,
                "skip",
                self._append(failure_codes, "MAX_ACTIVE_POSITIONS_REACHED"),
                "Maximum active positions threshold has been reached.",
            )

        lane = resolved["asset_lane"]
        if lane == "major":
            if not strategy["major_asset_lane_enabled"]:
                return PolicyEvaluation(
                    False,
                    "skip",
                    self._append(failure_codes, "MAJOR_LANE_DISABLED"),
                    "Major asset lane is disabled.",
                )
            if resolved["approved_major_mapping"] in (None, ""):
                return PolicyEvaluation(
                    False,
                    "block",
                    self._append(failure_codes, "MAJOR_MAPPING_NOT_FOUND"),
                    "Major-asset mapping is missing.",
                )
            min_ta = self.config.min_ta_score_major
        else:
            if not strategy["regular_token_lane_enabled"]:
                return PolicyEvaluation(
                    False,
                    "skip",
                    self._append(failure_codes, "REGULAR_LANE_DISABLED"),
                    "Regular token lane is disabled.",
                )
            if resolved["token_contract_address"] is None:
                return PolicyEvaluation(
                    False,
                    "block",
                    self._append(failure_codes, "TOKEN_UNRESOLVED"),
                    "Regular token is unresolved.",
                )
            if risk["risk_scan_required"] and risk["risk_scan_supported"] is False:
                return PolicyEvaluation(
                    False,
                    "skip",
                    self._append(failure_codes, "TOKEN_RISK_UNAVAILABLE"),
                    "Regular token risk scan is unavailable.",
                )
            if risk["is_risk_token"] is True:
                return PolicyEvaluation(
                    False,
                    "block",
                    self._append(failure_codes, "TOKEN_RISK_BLOCKED"),
                    "Security-layer token risk scan blocked execution.",
                )
            if (risk["dev_rug_pull_token_count"] or 0) >= 10:
                return PolicyEvaluation(
                    False,
                    "block",
                    self._append(failure_codes, "DEV_RUG_HISTORY_SEVERE"),
                    "Creator rug-pull history exceeds block threshold.",
                )
            if (risk["dev_rug_pull_token_count"] or 0) >= 1:
                return PolicyEvaluation(
                    False,
                    "skip",
                    self._append(failure_codes, "DEV_RUG_HISTORY_PRESENT"),
                    "Creator rug-pull history triggers skip policy.",
                )
            if (risk["top10_hold_percent"] or 0) >= 60:
                return PolicyEvaluation(
                    False,
                    "block",
                    self._append(failure_codes, "HOLDER_CONCENTRATION_EXTREME"),
                    "Top-10 holder concentration exceeds block threshold.",
                )
            if (risk["top10_hold_percent"] or 0) >= 35:
                return PolicyEvaluation(
                    False,
                    "skip",
                    self._append(failure_codes, "HOLDER_CONCENTRATION_HIGH"),
                    "Top-10 holder concentration triggers skip policy.",
                )
            if (risk["buy_tax_pct"] or 0) > 10 or (risk["sell_tax_pct"] or 0) > 10:
                return PolicyEvaluation(
                    False,
                    "skip",
                    self._append(failure_codes, "HIGH_TOKEN_TAX"),
                    "Token tax exceeds configured skip threshold.",
                )
            if market["liquidity_usd"] is not None and market["liquidity_usd"] < strategy["min_liquidity_usd_regular"]:
                return PolicyEvaluation(
                    False,
                    "block",
                    self._append(failure_codes, "REGULAR_LIQUIDITY_TOO_LOW"),
                    "Liquidity is below configured threshold.",
                )
            min_ta = self.config.min_ta_score_regular

        if not market["quote_available"]:
            return PolicyEvaluation(
                False,
                "skip",
                self._append(failure_codes, "QUOTE_UNAVAILABLE"),
                "Quote is unavailable.",
            )

        price_impact = market.get("quote_price_impact_pct")
        if price_impact is not None:
            impact_threshold = (
                strategy["max_slippage_pct_major"] if lane == "major" else strategy["max_slippage_pct_regular"]
            )
            if price_impact > impact_threshold:
                return PolicyEvaluation(
                    False,
                    "block",
                    self._append(failure_codes, "PRICE_IMPACT_TOO_HIGH"),
                    "Quote price impact exceeds the configured threshold.",
                )

        deviation = ta.get("price_deviation_pct")
        if deviation is not None:
            max_deviation = (
                strategy["max_price_deviation_pct_major"]
                if lane == "major"
                else strategy["max_price_deviation_pct_regular"]
            )
            if deviation > max_deviation:
                code = "MAJOR_FOMO_TOO_HIGH" if lane == "major" else "REGULAR_FOMO_TOO_HIGH"
                return PolicyEvaluation(
                    False,
                    "skip",
                    self._append(failure_codes, code),
                    "Price deviation versus call reference exceeds the allowed threshold.",
                )

        if ta["ta_score"] < min_ta:
            code = "MAJOR_TA_WEAK" if lane == "major" else "REGULAR_TA_WEAK"
            return PolicyEvaluation(
                False,
                "skip",
                self._append(failure_codes, code),
                "TA score is below threshold.",
            )

        if decision["capped_amount_usd"] <= 0:
            return PolicyEvaluation(
                False,
                "skip",
                self._append(failure_codes, "TRADE_SIZE_TOO_SMALL"),
                "Trade size is not executable.",
            )

        return PolicyEvaluation(True, "execute", failure_codes, "Policy gate passed.")

    @staticmethod
    def _append(existing: list[str], code: str) -> list[str]:
        result = list(existing)
        if code not in result:
            result.append(code)
        return result
