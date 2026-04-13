from __future__ import annotations

from app.policies.interfaces import PolicyEvaluation


class DefaultExitPolicyEngine:
    def evaluate(self, context: dict) -> PolicyEvaluation:
        position = context["position_snapshot"]
        trailing = context["trailing_state"] or {}
        market = context["exit_market_snapshot"] or {}
        strategy = context["strategy_profile"] or {}
        decision = context["exit_decision"] or {}

        decision_value = decision.get("decision")
        failure_codes: list[str] = []

        if not position:
            return PolicyEvaluation(False, "block", ["POSITION_NOT_FOUND"], "Position snapshot missing.")

        if position["status"] != "open":
            return PolicyEvaluation(False, "block", ["POSITION_NOT_OPEN"], "Position is not open.")

        if decision_value == "hold":
            return PolicyEvaluation(False, "hold", ["HOLD_DECISION"], "Exit agent decided to hold.")

        if decision_value == "exit_trailing_arm":
            if not strategy.get("trailing_enabled", True):
                return PolicyEvaluation(False, "block", ["TRAILING_DISABLED"], "Trailing is disabled.")
            if trailing.get("armed"):
                return PolicyEvaluation(False, "hold", ["TRAILING_ALREADY_ARMED"], "Trailing is already armed.")
            return PolicyEvaluation(True, "persist_trailing", failure_codes, "Trailing state can be armed.")

        if decision_value == "exit_trailing_fire":
            if not trailing.get("armed"):
                return PolicyEvaluation(False, "block", ["TRAILING_NOT_ARMED"], "Cannot fire trailing exit when not armed.")
            if not market.get("quote_available", False):
                return PolicyEvaluation(False, "block", ["EXIT_QUOTE_UNAVAILABLE"], "Exit quote is unavailable.")
            return PolicyEvaluation(True, "execute", failure_codes, "Trailing exit is executable.")

        if decision_value == "exit_hard":
            if not market.get("quote_available", False):
                return PolicyEvaluation(False, "block", ["EXIT_QUOTE_UNAVAILABLE"], "Exit quote is unavailable.")
            return PolicyEvaluation(True, "execute", failure_codes, "Hard exit is executable.")

        return PolicyEvaluation(False, "block", ["UNKNOWN_EXIT_DECISION"], "Unknown exit decision.")
