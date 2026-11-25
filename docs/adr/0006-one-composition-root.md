# ADR 0006: One composition root, no DI container

- Status: accepted

## Context
Something must construct adapters and hand them to modules.

## Decision
composition.py exposes one function, build_app(settings), with explicit arguments. No container, no globals, no service locator.

## Consequences
All wiring is visible in one file. It can grow long, in which case we split helpers but keep a single entry point.

## Alternatives considered
A DI container (hidden wiring, magic); module-level singletons (global state).
