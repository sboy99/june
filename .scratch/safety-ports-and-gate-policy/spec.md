# Safety ports and gate policy table (SHIP-331, P4.1)

Status: ready-for-agent
Source: Linear SHIP-331, milestone "Phase 4: Safety"
Branch: `contactsagarbera/ship-331-p41-safety-ports-and-gate-policy` (first of the Phase 4 stack)

## Problem Statement

`june.safety` has two empty stub ports. The four Gates (input, tool, memory-write, end-loop) and Protected paths are the next issues, but nothing yet says what each Gate checks, what outcomes it may return, or what it must log. Without that, each Gate issue would invent its own vocabulary and the decisions would not be comparable or auditable.

## Solution

Define the safety vocabulary once, in `june.safety`: a Risk level, a Decision (`allow`, `deny`, `ask`), a Verdict, the `Classifier` and `Judge` ports, and a Gate policy table that states for every Gate what it checks, which Decisions are possible and what is logged. Later Gate issues implement against this table.

## User Stories

1. As a Gate author, I want one `Decision` type with `allow`, `deny` and `ask`, so every Gate speaks the same outcomes.
2. As a Gate author, I want a `RiskLevel` (`low`, `medium`, `high`), so Gates can scale their strictness.
3. As a Gate author, I want a `Verdict` carrying a Decision, a Risk level and a short reason, so a decision can be logged and explained.
4. As a Gate author, I want a `Verdict` to be immutable and to reject an empty reason, so decisions are never silent.
5. As a Gate author, I want a `Classifier` port that scores a piece of text and returns a Verdict synchronously, so cheap rule-based checks need no model.
6. As a Gate author, I want a `Judge` port that is async and returns a Verdict, so a model-backed check can be plugged in by the composition root.
7. As a maintainer, I want a Gate policy table listing the four Gates, so what each Gate guards is reviewable in one place.
8. As a maintainer, I want each table row to state the checked subject, the allowed Decisions, and which Decision is the default when a check fails or errors, so failure is safe.
9. As a maintainer, I want every Gate to fail closed (a checker error becomes `deny`, except the end-loop Gate, which becomes `allow` with a logged warning because it only guards the final answer), so a broken checker never opens a Gate silently.
10. As a maintainer, I want each row to list the fields a decision log line carries (gate, decision, risk, reason, subject digest), so decisions are auditable without logging secrets.
11. As a maintainer, I want the policy table exposed as read-only data and looked up by Gate name, so Gates and docs read the same source.
12. As a maintainer, I want an unknown Gate name rejected with `DomainError`, so typos fail fast.
13. As a maintainer, I want a human-readable policy table in `docs/ARCHITECTURE.md` matching the code, so readers need not read code.
14. As a maintainer, I want new terms in the glossary and an ADR for the fail-closed rule, so the rule is not overridden by accident.

## Implementation Decisions

- New value types in `june.safety.ports`: `Decision` (literal `allow`/`deny`/`ask`), `RiskLevel` (literal `low`/`medium`/`high`), `GateName` (literal `input`/`tool`/`memory_write`/`end_loop`), frozen dataclass `Verdict(decision, risk, reason)`.
- `Classifier.classify(text: str) -> Verdict` (sync, no I/O). `Judge.judge(subject: str, question: str) -> Verdict` (async, may call a model through an adapter filled by the composition root).
- Gate policy table in a new `june.safety.policy` module: frozen `GatePolicy(gate, checks, allowed, on_checker_error, logged_fields)` rows and `policy_for(gate)`; backed by a read-only mapping.
- Rows: input (user text; allow/deny; on error deny), tool (tool call name and arguments; allow/deny/ask; on error deny), memory_write (text to remember; allow/deny; on error deny), end_loop (final assistant answer; allow/deny; on error allow, logged as a warning).
- `ask` means the runtime must get explicit user confirmation; how that is surfaced is out of scope here. Until it exists, a Gate treats `ask` as `deny`.
- Logged fields never include raw subject text: the subject appears only as the Content digest from `june.observability`. The policy module imports nothing from `observability`; it only names the field.
- `june.safety` stays a sibling of the other mid-layer modules: no imports of `llm`, `memory` or `runtime`. The Judge takes plain strings for that reason.
- Add ADR 0011 (fail-closed Gates), glossary entries (Decision, Verdict, Classifier, Judge, Gate policy), and the policy table in `docs/ARCHITECTURE.md`.

## Testing Decisions

- The single seam is the public `june.safety` API. Tests assert external behaviour: Verdict validation and immutability, the table's contents, `policy_for` lookup and its error, and that fake Classifier and Judge classes satisfy the ports structurally.
- A consistency test reads the policy table in `docs/ARCHITECTURE.md` and checks every Gate name and its failure default appear, so docs and code cannot drift.
- Prior art: `tests/unit/test_llm_ports.py`, `tests/contract/test_architecture.py`.
- `make check` passes; `june.safety` coverage at least 80%.

## Out of Scope

- Any real Classifier or Judge adapter, the Gates themselves, Protected paths, the red-team set, the confirmation flow for `ask`, wiring into the composition root.

## Further Notes

- The seam choice (one seam: the public `june.safety` package) was made without a user check because the run is unattended; it follows the Phase 3 specs.
- Linear: SHIP-331.
