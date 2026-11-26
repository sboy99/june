import pytest

from june.safety import EndLoopGate, Verdict
from june.shared.errors import DomainError, SafetyDenied

pytestmark = pytest.mark.unit

SECRET = "sk-planted-secret-1234567890"


class FakeJudge:
    def __init__(self, verdict: Verdict) -> None:
        self.verdict = verdict
        self.calls = 0

    async def judge(self, subject, question) -> Verdict:
        self.calls += 1
        return self.verdict


class BrokenClassifier:
    def classify(self, text):
        raise RuntimeError("boom")


async def test_clean_reply_is_unchanged():
    assert await EndLoopGate().check("All done.") == "All done."


async def test_secret_is_redacted():
    reply = await EndLoopGate().check(f"Your key is {SECRET}, enjoy")

    assert SECRET not in reply
    assert "[REDACTED]" in reply


@pytest.mark.parametrize("reply", ["", "   \n"])
async def test_empty_reply_is_denied(reply):
    with pytest.raises(SafetyDenied):
        await EndLoopGate().check(reply)


async def test_oversize_reply_is_denied():
    with pytest.raises(SafetyDenied):
        await EndLoopGate(max_chars=10).check("x" * 11)


async def test_reply_at_the_limit_is_allowed():
    assert await EndLoopGate(max_chars=10).check("x" * 10) == "x" * 10


async def test_length_is_checked_after_redaction():
    reply = SECRET

    assert await EndLoopGate(max_chars=len("[REDACTED]")).check(reply) == "[REDACTED]"


def test_limit_below_one_is_rejected():
    with pytest.raises(DomainError):
        EndLoopGate(max_chars=0)


async def test_judge_deny_denies_medium_risk_reply():
    judge = FakeJudge(Verdict("deny", "high", "harmful"))
    gate = EndLoopGate(max_chars=100, judge=judge)

    with pytest.raises(SafetyDenied):
        await gate.check("x" * 60)
    assert judge.calls == 1


async def test_broken_checker_fails_open_with_redacted_reply(log_output):
    _, lines = log_output

    reply = await EndLoopGate(classifier=BrokenClassifier()).check(f"hi {SECRET}")

    assert SECRET not in reply
    assert any(line.get("gate") == "end_loop" and line["decision"] == "allow" for line in lines())


async def test_decision_logged_without_reply_text(log_output):
    _, lines = log_output

    await EndLoopGate().check("a private reply")

    entry = next(line for line in lines() if line.get("gate") == "end_loop")
    assert entry["decision"] == "allow"
    assert "a private reply" not in str(lines())
