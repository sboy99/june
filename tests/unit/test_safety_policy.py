from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from june.safety import (
    GATE_POLICIES,
    Classifier,
    Judge,
    Verdict,
    policy_for,
)
from june.shared.errors import DomainError

pytestmark = pytest.mark.unit

ARCHITECTURE_DOC = Path(__file__).parents[2] / "docs" / "ARCHITECTURE.md"
ALL_GATES = ("input", "tool", "memory_write", "end_loop")


def test_verdict_is_immutable():
    verdict = Verdict("deny", "high", "prompt injection")

    with pytest.raises(FrozenInstanceError):
        verdict.decision = "allow"  # type: ignore[misc]


def test_verdict_rejects_empty_reason():
    with pytest.raises(DomainError):
        Verdict("allow", "low", "  ")


def test_verdict_rejects_unknown_decision_and_risk():
    with pytest.raises(DomainError):
        Verdict("maybe", "low", "x")  # type: ignore[arg-type]
    with pytest.raises(DomainError):
        Verdict("allow", "extreme", "x")  # type: ignore[arg-type]


def test_table_lists_the_four_gates():
    assert tuple(GATE_POLICIES) == ALL_GATES


def test_policy_for_returns_row():
    row = policy_for("tool")

    assert row.gate == "tool"
    assert set(row.allowed) == {"allow", "deny", "ask"}


def test_policy_for_unknown_gate_raises_domain_error():
    with pytest.raises(DomainError):
        policy_for("typo")  # type: ignore[arg-type]


def test_table_is_read_only():
    with pytest.raises(TypeError):
        GATE_POLICIES["input"] = policy_for("tool")  # type: ignore[index]


@pytest.mark.parametrize("gate", ["input", "tool", "memory_write"])
def test_gates_fail_closed(gate):
    assert policy_for(gate).on_checker_error == "deny"


def test_end_loop_gate_fails_open_by_design():
    assert policy_for("end_loop").on_checker_error == "allow"


@pytest.mark.parametrize("gate", ALL_GATES)
def test_logged_fields_never_include_raw_subject(gate):
    fields = policy_for(gate).logged_fields

    assert {"gate", "decision", "risk", "reason", "subject_digest"} <= set(fields)
    assert "subject" not in fields


def test_fake_classifier_and_judge_satisfy_ports():
    class FakeClassifier:
        def classify(self, text: str) -> Verdict:
            return Verdict("allow", "low", "fine")

    class FakeJudge:
        async def judge(self, subject: str, question: str) -> Verdict:
            return Verdict("deny", "high", "no")

    classifier: Classifier = FakeClassifier()
    judge: Judge = FakeJudge()

    assert classifier.classify("hi").decision == "allow"
    assert judge is not None


@pytest.mark.parametrize("gate", ALL_GATES)
def test_architecture_doc_lists_every_gate_and_failure_default(gate):
    doc = ARCHITECTURE_DOC.read_text()
    row = next(line for line in doc.splitlines() if line.startswith(f"| `{gate}`"))

    assert f"`{policy_for(gate).on_checker_error}`" in row
