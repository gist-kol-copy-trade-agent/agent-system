from dataclasses import dataclass, field


@dataclass
class PolicyEvaluation:
    passed: bool
    action: str
    failure_codes: list[str] = field(default_factory=list)
    summary: str = ""


class TradePolicyEngine:
    def evaluate(self, context: dict) -> PolicyEvaluation:
        raise NotImplementedError("Trade policy evaluation is implemented in a later phase.")
