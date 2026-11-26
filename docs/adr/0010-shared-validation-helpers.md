# ADR 0010: Validation helpers live in `june.shared.helpers`

- Status: accepted
- Supersedes: [ADR 0008](0008-shared-domain-helpers-in-helper-py.md)

## Context
ADR 0008 kept domain helpers per package. `require_text` and `require_utc` were then duplicated in `conversation` and `memory`, and the blank-id check was copied across three adapters. The duplicates drift.

## Decision
Pure validation helpers (`require_text`, `require_utc`, `require_adapter_text`, `ZERO_DURATION`) live in `june/shared/helpers.py`, which every module may import. They are pure (no I/O, no clock), so the Pure domain contract still holds. `memory/domain/helper.py` is removed. Helpers are imported from `june.shared.helpers`, not re-exported from `june.shared`.

## Consequences
One definition, one place to look. `shared` must stay small: only helpers needed by two or more modules belong here.

## Alternatives considered
Per-package `helper.py` (ADR 0008; duplicated across modules). Re-exporting from `june.shared` (widens the public surface for small utilities).
