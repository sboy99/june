# Gate 1: input (SHIP-332, P4.2)

Status: ready-for-agent
Source: Linear SHIP-332, milestone "Phase 4: Safety"
Branch: `contactsagarbera/ship-332-p42-gate-1-input` (stacked on SHIP-331)

## Problem Statement

User messages and fetched content reach the model unchecked. A prompt-injection attempt ("ignore previous instructions") is treated like any other text, and fetched content can pose as instructions.

## Solution

`june.safety` gains a shared decision step (classify, optional judge, fail-closed, one log line per decision), a rule-based injection Classifier, and an `InputGate`. The gate returns the text unchanged for a user message, denies injection attempts with `SafetyDenied`, and can wrap fetched content in an `untrusted_content` block so the model treats it as data.

## User Stories

1. As an operator, I want a user message that tries to override instructions denied with `SafetyDenied`, so injection never reaches the model.
2. As an operator, I want an ordinary message returned unchanged, so normal chat is unaffected.
3. As an operator, I want matching to ignore case and extra whitespace, so trivial rewording does not bypass it.
4. As an operator, I want fetched content scanned the same way, so a web page cannot inject instructions.
5. As an operator, I want clean fetched content wrapped in an `untrusted_content` block naming its source, so the model sees it as data.
6. As an operator, I want a closing tag inside fetched content neutralised, so content cannot break out of its wrapper.
7. As an operator, I want an optional Judge consulted only when the Classifier returns `allow` at medium risk, so model calls are rare.
8. As an operator, I want a Classifier or Judge error to deny (fail closed per ADR 0011), so a broken checker never opens the gate.
9. As an operator, I want a verdict outside the Gate's allowed Decisions (`ask` for the input Gate) turned into `deny`.
10. As an auditor, I want one log line per decision with gate, decision, risk, reason and a subject digest, never the raw text.
11. As an auditor, I want a log line for a checker failure too.
12. As a maintainer, I want the shared decision step reusable by the other three Gates.

## Implementation Decisions

- `june.safety.decision.decide(gate, subject, classifier, judge=None) -> Verdict` (async). Applies the policy row: failure default, disallowed Decisions become `deny`, logs one INFO line (`gate`, `decision`, `risk`, `reason`, `subject_digest`, `subject_size`). The raw subject is never logged, not even at DEBUG.
- `PatternClassifier(rules)` adapter in `safety/adapters/patterns.py`: ordered `(regex, risk, reason)` rules, first match wins, no match is `allow`/`low`. `injection_classifier()` builds it with injection phrases (ignore/disregard previous instructions, reveal system prompt, "you are now", developer mode, act as DAN).
- `InputGate(classifier, judge=None)`: `async check(text) -> str` returns the text or raises `SafetyDenied`; `async check_untrusted(text, source) -> str` scans then wraps. Wrapper tag `untrusted_content` with a `source` attribute; any literal closing tag in the content has its `<` replaced by `&lt;`.
- Not wired into the runtime yet (SHIP-337).

## Testing Decisions

- Through the public API with fake Classifier/Judge, and the real pattern classifier on a small phrase list. Assert on returned text, raised `SafetyDenied`, and log lines (`log_output` fixture); never on internals.
- Prior art: `tests/unit/test_runtime_session_closer.py`, `tests/unit/conftest.py`.
- `make check` passes; `june.safety` coverage at least 80%.

## Out of Scope

Wiring, multilingual or semantic injection detection, a real Judge adapter, an approval flow for `ask`.

## Further Notes

Linear: SHIP-332.
