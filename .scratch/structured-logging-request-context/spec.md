# Structured logging with request context (SHIP-311)

Status: ready-for-agent

## Problem Statement

Every module in june will emit logs, but today `observability` only offers a bare `get_logger`. Output is unstructured text, so a single turn cannot be followed across modules. Nothing ties a log line to the trace, session or user that caused it. Nothing stops a secret (API key, token, password) or a full prompt or tool output from landing in a log file. Operators cannot safely turn logging on in production, and developers cannot trust log output in tests.

## Solution

`june.observability` provides structured JSON logging on top of stdlib `logging`. One call configures it from the `log_level` setting. Every log line is a single JSON object carrying the current `trace_id`, `session_id` and `user_id`, which are held in context variables and set by whichever layer starts a request. A redaction filter masks secrets in every line before it is written. Prompts and tool output are logged as a size and a hash only, unless the level is DEBUG, when the full text is included. Modules keep using `get_logger(name)` and need no other change.

## User Stories

1. As an operator, I want every log line to be one JSON object, so that I can ship and query logs with standard tools.
2. As an operator, I want each line to carry timestamp, level, logger name and message, so that I can read a line on its own.
3. As an operator, I want extra structured fields passed with a log call to appear as JSON keys, so that I can filter on them.
4. As an operator, I want exception details on error lines to be included in the JSON, so that one line holds the whole failure.
5. As an operator, I want logs to go to stderr, so that stdout stays clean for program output.
6. As an operator, I want the log level controlled by the existing `log_level` setting, so that I tune verbosity without code changes.
7. As an operator, I want an invalid log level reported as a `ConfigError`, so that startup fails clearly instead of silently logging nothing.
8. As an operator, I want `trace_id` on every line, so that I can follow one request across modules.
9. As an operator, I want `session_id` on every line, so that I can group all turns of one conversation.
10. As an operator, I want `user_id` on every line, so that I can find everything one user triggered.
11. As an operator, I want lines logged outside any request to omit or null the context fields rather than fail, so that startup and shutdown logs still work.
12. As a runtime author, I want to bind `trace_id`, `session_id` and `user_id` for the duration of a block of code, so that every log call inside is tagged without passing ids around.
13. As a runtime author, I want the previous context restored when the block exits, even on error, so that context never leaks between requests.
14. As a runtime author, I want context to propagate into async tasks started inside the block, so that concurrent work stays attributed to the right request.
15. As a runtime author, I want two concurrent requests to keep separate context, so that one request never logs another's ids.
16. As a runtime author, I want a way to generate a fresh `trace_id` using the shared id generator, so that ids are consistent and testable.
17. As a security reviewer, I want secrets masked in the message, so that a secret interpolated into text never reaches the output.
18. As a security reviewer, I want secrets masked in structured extra fields, so that a secret passed as a field never reaches the output.
19. As a security reviewer, I want values under sensitive key names (for example api_key, token, password, secret, authorization) masked regardless of content, so that I do not rely on pattern matching alone.
20. As a security reviewer, I want common secret shapes in free text (bearer tokens, `sk-` style API keys) masked, so that leaks through message strings are caught.
21. As a security reviewer, I want redaction applied to nested fields and to exception text, so that secrets cannot hide in structure.
22. As a security reviewer, I want redaction to run on the final output of every handler, so that no code path bypasses it.
23. As a security reviewer, I want redaction to be safe when a value cannot be inspected, so that a bad value never crashes logging or leaks.
24. As a security reviewer, I want the redaction marker to be constant and obvious, so that masked values are recognisable in logs.
25. As a privacy-minded operator, I want prompts logged as size and hash only at INFO and above, so that user content does not sit in log files.
26. As a privacy-minded operator, I want tool output logged as size and hash only at INFO and above, so that tool results do not sit in log files.
27. As a developer debugging locally, I want full prompt and tool output text included when the level is DEBUG, so that I can see exactly what happened.
28. As a developer debugging locally, I want the DEBUG text to still pass through secret redaction, so that debugging never leaks secrets.
29. As an operator, I want the hash to be stable for identical content, so that I can tell whether two prompts were the same without reading them.
30. As an operator, I want the hash to be non-reversible and truncated, so that the log value is short and does not expose content.
31. As a module author, I want a single helper to log a prompt or tool output safely, so that I never hand-roll size and hash logic.
32. As a module author, I want `get_logger` to keep working unchanged, so that existing callers need no edits.
33. As a test author, I want logging configuration to be re-runnable without duplicating handlers, so that tests and repeated boots do not double every line.
34. As a test author, I want to direct output to a supplied stream, so that tests capture and parse JSON lines.
35. As a test author, I want to plant a secret and assert it is absent from captured output, so that redaction is proven by test.
36. As a CLI user, I want startup to configure logging before the app is built, so that startup failures are logged consistently.
37. As a CLI user, I want the one-line stderr error and non-zero exit for failures to be unchanged, so that user-visible behaviour does not regress.
38. As an architect, I want `observability` to import only the standard library and `june.shared`, so that the layer contracts keep passing.
39. As a maintainer, I want the new vocabulary in the glossary, so that code and docs use the same terms.

## Implementation Decisions

- **Module**: all work lives in `observability`, plus a small wiring change at startup. `get_logger(name)` is retained as-is.
- **Format**: a JSON formatter on stdlib `logging`, no third-party logging dependency. Each line is one JSON object with at least timestamp (UTC, ISO 8601), level, logger, message, `trace_id`, `session_id`, `user_id`, plus any extra fields and exception text. The timestamp may come from the shared clock where practical, otherwise from the log record; keep it timezone-aware UTC.
- **Configuration**: one public function configures the root `june` logger tree with a single stderr handler, the JSON formatter, the context filter and the redaction filter. It accepts a level and an optional output stream (for tests). It is idempotent: calling it again replaces its own handler rather than adding another. The level comes from the existing `log_level` setting; an unrecognised level raises `ConfigError`.
- **Request context**: three context variables (`trace_id`, `session_id`, `user_id`), default none. Exposed through a context manager that binds any subset of the three and restores prior values on exit, including on exception. Because they are context variables, they propagate into tasks created inside the block and stay isolated between concurrent requests. A helper creates a new `trace_id` via the shared `IdGenerator`. A filter copies the current values onto every record, so ids appear without call-site changes. Outside a request the fields are null.
- **Redaction filter**: masks by key name and by value pattern. Sensitive key names (case-insensitive, substring match) include api key, token, password, secret, authorization, cookie. Value patterns cover bearer tokens and common API key prefixes. Applied to the formatted message, extra fields (recursively through dicts and lists) and exception text. The marker is a single constant string. Redaction must never raise; on an uninspectable value it replaces the value with the marker. The filter lives on the handler so it covers all output, not only loggers that opted in.
- **Content logging**: one helper takes a label and text and returns structured fields: `size` (characters or bytes, pick one and document it) and `hash` (truncated SHA-256 hex). At DEBUG it also returns the full text. The helper decides based on the effective logger level, so callers do not branch. Full text is still subject to redaction.
- **Settings**: `log_level` already exists. No new settings. A DEBUG-text switch separate from level is intentionally not added.
- **Startup**: the CLI configures logging first, then builds the app. Error output and exit codes are unchanged.
- **Layering**: `observability` sits in the lowest layer beside `shared`. It may import `june.shared` and the standard library only. No change to `.importlinter` is expected. No vendor SDKs.
- **Immutability**: context binding returns restored state rather than mutating shared objects; helpers return new dicts.
- **Glossary**: add entries for Trace id, Session id, User id (or a single Request context entry), Redaction, and Content digest (size plus hash), owned by `observability`, in the same PR.
- **ADR**: none required; no existing ADR is contradicted. Note the choice of stdlib `logging` over a third-party library in the PR.

## Testing Decisions

- A good test drives the public `june.observability` API, captures the real output stream, parses each line as JSON, and asserts on observable content. It must not inspect private attributes, formatter internals or handler classes.
- Single seam: configure logging to an in-memory stream, log through `get_logger`, and assert on the parsed JSON lines. The existing CLI e2e tests remain as the regression check for startup output.
- Tests to write:
  - Output: each line is valid JSON with timestamp, level, logger, message and the three context fields; extra fields appear as keys; exceptions are included.
  - Context: ids bound in a block appear on lines inside it and not after; restored on exception; propagate into an async task; two concurrent tasks keep separate ids; null outside a request.
  - Redaction (the ticket's done condition): plant a secret in the message, in an extra field, under a sensitive key, in a nested structure and in exception text, and assert it is absent from the output while the marker is present. Include a secret logged at DEBUG.
  - Content logging: at INFO the output has size and hash and not the text; at DEBUG it has the text (redacted); identical input gives an identical hash; hash is not the raw content.
  - Configuration: calling configure twice yields one line per log call; an invalid level raises `ConfigError`.
  - CLI e2e: a failing start still prints one stderr error line without traceback; JSON log lines, if any, go to stderr and not stdout.
- Prior art: `tests/e2e/test_cli.py` for behavioural style and markers, `tests/unit/test_shared_*.py` for unit style, `tests/contract/test_architecture.py` for the architecture check. Follow Arrange-Act-Assert and descriptive names; use the existing `FixedClock` and fake id generator where determinism is needed.
- Done when: `make check` passes, a test plants a secret and the log output is redacted, and coverage on `observability` meets the repo's 80% minimum.

## Out of Scope

- Log shipping, rotation, files or any sink other than stderr.
- Metrics, tracing spans or OpenTelemetry export.
- Deciding where `trace_id`, `session_id` and `user_id` are created in a real request; the runtime and interface layers bind them in later tickets. This spec only provides the mechanism.
- Redacting data that is not logged (for example stored memory or persisted transcripts).
- Per-module log level overrides.
- Async or queue-based log handlers.
- Changes to `.importlinter` contracts.

## Further Notes

- Linear: SHIP-311, project June, milestone "Phase 1: LLM and shared". Branch: `contactsagarbera/ship-311-p12-structured-logging-with`.
- Depends on the shared id generator and clock from SHIP-310 (merged).
- Redaction by pattern is best effort. Key-name masking and size-and-hash logging are the primary defences; callers should still avoid logging secrets.
- Seams proposed: one primary seam (unit tests against `june.observability` with a captured stream) and the existing CLI e2e seam. Please confirm these match expectations.
