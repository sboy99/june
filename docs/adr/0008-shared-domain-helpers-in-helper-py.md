# ADR 0008: Shared domain helpers live in `helper.py`

- Status: accepted

## Context
`require_text` started as a private function in `memory/domain/types.py`. `memory/ports.py` needed the same check, which pushed us to either copy it or make a private name public from an unrelated module. Both spread helpers across files with no predictable home.

## Decision
Each domain package has one `helper.py`. Any pure function that more than one file in that domain, or a module's ports, needs goes there, not in the file that happened to need it first. Helpers are pure (no I/O, no clock, no vendor imports), so the Pure domain contract still holds. Helpers are imported from `helper.py` directly and are not re-exported from the package `__init__`, since they are not part of the domain's public vocabulary.

## Consequences
Reuse has one obvious place to look and to add to. The risk is `helper.py` becoming a dumping ground; keep it to small, cohesive functions and split it by topic if it grows past the file-size guideline. A helper used by only one file stays in that file until a second user appears.

## Alternatives considered
Making helpers public in the module that first defined them (couples unrelated modules to `types.py`). Duplicating them per file (drifts). A cross-module `shared` helper (domain helpers should not leak into `june.shared`, which every module may import).
