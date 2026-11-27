# Confined file tools (SHIP-339, P5.2)

Status: ready-for-agent
Source: Linear SHIP-339, milestone "Phase 5: Tooling"
Branch: `contactsagarbera/ship-339-p52-confined-file-tools` (stacked on `contactsagarbera/ship-338-p51-tool-contract-and-registry`)

## Problem Statement

The Tool registry has no tools. The agent needs to read and write files, but a file tool that accepts any path can read secrets, escape the workspace through `..` or symlinks, or overwrite the persona and skills.

## Solution

`june.tooling` gains two Tools, `read_file` (Risk `low`) and `write_file` (Risk `high`), confined to a Workspace directory. Every path is resolved (symlinks followed) and must stay inside the Workspace. `write_file` also refuses the protected roots. Both are registered in composition.

## User Stories

1. As the model, I want `read_file(path)` to return a text file's contents, so I can inspect workspace files.
2. As the model, I want `write_file(path, content)` to create or overwrite a text file, creating parent directories, so I can produce output.
3. As an operator, I want paths resolved relative to the Workspace, so the model need not know absolute paths.
4. As an operator, I want an absolute path outside the Workspace refused, so the model cannot read the host.
5. As an operator, I want `..` segments that leave the Workspace refused.
6. As an operator, I want a symlink that points outside the Workspace refused, for reads and writes, including a symlinked parent directory.
7. As an operator, I want `write_file` refused under the protected roots (persona, skills), even when the Workspace contains them, so the persona cannot be overwritten.
8. As an operator, I want a read of a missing file, a directory, or a non-UTF-8 file to raise `ToolError` with a clear message, never a crash.
9. As an operator, I want reads larger than a size limit refused and writes larger than the limit refused, so a call cannot exhaust memory or disk.
10. As an operator, I want refusals to raise `ToolError` that names the tool and the reason without echoing file contents.
11. As an operator, I want `read_file` rated `low` and `write_file` rated `high` Risk, so writes ask the Approver (Gate 2).
12. As an operator, I want the Workspace directory configurable (`JUNE_WORKSPACE_DIR`, default `./workspace`) and created at startup.

## Implementation Decisions

- `tooling/adapters/files.py` (adapters may use the filesystem): `ReadFileTool`, `WriteFileTool`, sharing a `WorkspacePath` resolver: `resolve(path) -> Path` raising `ToolError`. Resolver uses `Path.resolve()` on the Workspace root and on the target (for writes, resolve the deepest existing ancestor, then append the rest) and checks `is_relative_to`.
- `WriteFileTool(workspace, protected_roots)`: `protected_roots` are plain absolute paths passed in by composition (tooling cannot import safety); after resolving, a target equal to or under a root is refused.
- Size limit: named constant `MAX_FILE_BYTES` (1 MiB), a constructor argument.
- Writes use write-to-temp-then-rename in the same directory so a failed write never leaves a half file.
- `Settings.workspace_dir: Path = Path("./workspace")`; composition creates it, builds both tools and registers them. `WRITE_TOOLS` already contains `write_file`, so the Gate also denies protected-path writes.
- Glossary: add **Workspace** [tooling]. ADR only if a decision contradicts an existing one (none expected).

## Testing Decisions

- Through `ReadFileTool.run` / `WriteFileTool.run` on `tmp_path`, including symlink and `..` escape cases; one wiring test through `build_app` that the registry lists both tools with the right Risk levels.
- Prior art: `tests/unit/test_tooling_registry.py`, `tests/unit/test_tool_runner.py`, `tests/unit/test_safety_protected_paths.py`.
- `make check` passes; `june.tooling` coverage at least 80%.

## Out of Scope

Directory listing, delete, edit/patch tools, binary files, sandbox escape suite (SHIP-344), `manage_skill`.

## Further Notes

Linear: SHIP-339. Stacked on SHIP-338 (PR #25).
