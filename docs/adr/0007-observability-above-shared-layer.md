# ADR 0007: Observability sits above shared in the layer contract

- Status: accepted

## Context
The "Module layers" contract in `.importlinter` originally listed `june.observability | june.shared` as one independent level, so the two could not import each other. The structured-logging work (SHIP-311) needs observability to import shared: `ConfigError` for invalid log levels, and `IdGenerator`/`UuidGenerator` for trace ids. The spec for that work said the contract would not change, but that is not achievable.

## Decision
Split the level into two: `june.observability` above `june.shared`. Observability may import shared; shared never imports observability. The other four contracts are unchanged.

## Consequences
Observability can reuse shared errors and id generation without duplicating them. Shared stays a leaf, so it cannot log through observability; it raises errors and lets callers log. The rule is enforced by `make arch`.

## Alternatives considered
- Keep them independent and duplicate `ConfigError` and id generation in observability: rejected, it splits one error hierarchy in two.
- Move logging config out of observability: rejected, it is the module's purpose.
