"""Gate 2: rates each tool call by Risk level and asks an Approver for high-risk ones."""

import json
from collections.abc import Mapping
from typing import Any

from june.observability import get_logger
from june.safety.decision import decide
from june.safety.ports import Approver, Judge, RiskLevel, Verdict
from june.shared.errors import SafetyDenied

_log = get_logger(__name__)

_RISK_VERDICTS: Mapping[RiskLevel, Verdict] = {
    "low": Verdict("allow", "low", "low risk tool"),
    "medium": Verdict("allow", "medium", "medium risk tool"),
    "high": Verdict("ask", "high", "high risk tool needs approval"),
}


class _ToolRiskClassifier:
    def __init__(self, risk: RiskLevel) -> None:
        self._verdict = _RISK_VERDICTS[risk]

    def classify(self, text: str) -> Verdict:
        return self._verdict


class ToolGate:
    """Checks one tool call; raises `SafetyDenied` unless it may run."""

    def __init__(
        self,
        risks: Mapping[str, RiskLevel],
        approver: Approver | None = None,
        judge: Judge | None = None,
        default_risk: RiskLevel = "high",
    ) -> None:
        self._risks = dict(risks)
        self._approver = approver
        self._judge = judge
        self._default_risk = default_risk

    async def check(self, name: str, arguments: Mapping[str, Any]) -> None:
        subject = f"{name} {json.dumps(dict(arguments), sort_keys=True, default=str)}"
        classifier = _ToolRiskClassifier(self._risks.get(name, self._default_risk))
        verdict = await decide("tool", subject, classifier, self._judge)
        if verdict.decision == "deny":
            raise SafetyDenied(f"tool gate denied {name}: {verdict.reason}")
        if verdict.decision == "ask" and not await self._approved(name, arguments):
            raise SafetyDenied(f"tool gate denied {name}: approval not given")

    async def _approved(self, name: str, arguments: Mapping[str, Any]) -> bool:
        approved = False
        if self._approver is not None:
            try:
                approved = await self._approver.approve(name, arguments)
            except Exception:
                _log.warning("approver failed for %s", name, exc_info=True)
        _log.info("tool approval", extra={"gate": "tool", "tool": name, "approved": approved})
        return approved
