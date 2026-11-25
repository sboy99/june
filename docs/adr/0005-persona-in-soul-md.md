# ADR 0005: Persona lives in persona/SOUL.md, read-only to the agent

- Status: accepted

## Context
The persona shapes every response. If the agent could edit it, behavior would drift unreviewed.

## Decision
The persona is one markdown file loaded at startup and passed to the runtime as text. It changes only through git review. A missing or empty file stops startup.

## Consequences
Persona changes are reviewed and versioned, so evals can log the version. Startup fails fast without it.

## Alternatives considered
Persona in config or a database (harder to review); agent-editable persona (unsafe drift).
