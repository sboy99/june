# Protected paths (SHIP-336, P4.6)

Status: ready-for-agent
Source: Linear SHIP-336, milestone "Phase 4: Safety"
Branch: `contactsagarbera/ship-336-p46-protected-paths` (stacked on SHIP-335)

## Problem Statement

The Persona (`persona/SOUL.md`) is read-only to the agent and learned Skills live under `skills/`, but nothing stops a tool call or a remembered instruction from targeting those paths.

## Solution

`june.safety` gains `ProtectedPaths`, which knows the protected roots. The Tool gate denies a write-tool call whose path argument falls under a protected root, except that a named skill-management tool may write under `skills/` (never under `persona/`). The memory-write Gate denies text that tells the agent to write to a protected path.

## User Stories

1. As an operator, I want `persona/` and `skills/` protected by default.
2. As an operator, I want a path judged after normalisation, so `a/../persona/SOUL.md` and `./persona/x` are caught.
3. As an operator, I want an absolute path inside a protected root caught.
4. As an operator, I want a sibling such as `personal/notes.txt` not caught.
5. As an operator, I want a write tool with a protected path argument denied, with a reason naming the root and never the full path.
6. As an operator, I want a non-write tool unaffected by this rule.
7. As an operator, I want path arguments recognised by name (`path`, `file`, `filename`, `dest`, `destination`, `target`).
8. As an operator, I want a configured skill-management tool allowed to write under `skills/`.
9. As an operator, I want that tool still denied under `persona/`.
10. As an operator, I want a remembered text that says to write, edit, delete or overwrite a protected path denied by the memory-write Gate.
11. As an operator, I want text that merely mentions a protected path with no write verb allowed.
12. As an auditor, I want these denials logged like any other Gate decision.

## Implementation Decisions

- `ProtectedPaths(base_dir, roots=("persona", "skills"))` with `root_of(path) -> str | None` (pure string normalisation, no file system access) and `root_names`.
- `ToolGate` gains optional keyword arguments `protected`, `write_tools` and `skill_tools`; the path check runs first and produces a `deny` Verdict through the shared decision step.
- `ProtectedPathClassifier(protected)` adapter (root name followed by a separator or `SOUL.md`, plus a write verb); `memory_write_classifier(protected=None)` includes it when given.
- No symlink resolution: a symlink inside the data directory pointing into a root is a Phase 5 sandbox concern.

## Testing Decisions

- Through `ToolGate.check` and `MemoryWriteGate.check` with real classifiers and `ProtectedPaths` on a temp base directory; unit tests of `root_of` for the normalisation cases.
- `make check` passes; `june.safety` coverage at least 80%.

## Out of Scope

Symlink and sandbox escape handling (Phase 5), wiring (SHIP-337), the skill-management tool itself.

## Further Notes

Linear: SHIP-336.
