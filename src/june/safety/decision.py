"""The shared decision step every Gate uses: classify, maybe judge, fail closed, log."""

from june.observability import content_fields, get_logger
from june.safety.policy import policy_for
from june.safety.ports import Classifier, GateName, Judge, Verdict
from june.shared.errors import SafetyDenied

_log = get_logger(__name__)

JUDGE_QUESTION = "Is this safe to allow? Answer with a decision, a risk level and a reason."
CHECKER_FAILED = "checker failed"


async def decide(
    gate: GateName,
    subject: str,
    classifier: Classifier,
    judge: Judge | None = None,
) -> Verdict:
    """Return the Gate's Verdict for `subject` and log it.

    The Judge is consulted only when the Classifier allows at medium risk. A checker
    error becomes the policy's failure default. A Decision the Gate does not allow
    (such as `ask`) becomes `deny`.
    """
    policy = policy_for(gate)
    try:
        verdict = classifier.classify(subject)
        if judge is not None and verdict.decision == "allow" and verdict.risk == "medium":
            verdict = await judge.judge(subject, JUDGE_QUESTION)
    except Exception:
        _log.warning("%s gate checker failed", gate, exc_info=True)
        verdict = Verdict(policy.on_checker_error, "high", CHECKER_FAILED)
    if verdict.decision not in policy.allowed:
        verdict = Verdict("deny", verdict.risk, f"{verdict.decision} not allowed: {verdict.reason}")
    _log_decision(gate, subject, verdict)
    return verdict


async def enforce(
    gate: GateName,
    subject: str,
    classifier: Classifier,
    judge: Judge | None = None,
) -> Verdict:
    """Like `decide`, but raise `SafetyDenied` on `deny`. The message holds only the reason."""
    verdict = await decide(gate, subject, classifier, judge)
    if verdict.decision == "deny":
        raise SafetyDenied(f"{gate} gate denied: {verdict.reason}")
    return verdict


def _log_decision(gate: GateName, subject: str, verdict: Verdict) -> None:
    digest = content_fields(_log, "subject", subject)
    _log.info(
        "%s gate decision",
        gate,
        extra={
            "gate": gate,
            "decision": verdict.decision,
            "risk": verdict.risk,
            "reason": verdict.reason,
            "subject_digest": digest["subject_hash"],
            "subject_size": digest["subject_size"],
        },
    )
