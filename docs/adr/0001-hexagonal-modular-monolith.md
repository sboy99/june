# ADR 0001: Hexagonal modular monolith

- Status: accepted

## Context
june will grow memory, tools, safety and several LLM providers. We want to swap vendors and test core logic without them.

## Decision
One deployable package. Each module owns its logic and declares ports; adapters implement ports and are wired only in the composition root. Dependencies point inward and are enforced by import-linter.

## Consequences
Vendors are replaceable and core logic is testable without I/O. Cross-module needs between same-level modules require a port, which adds a little ceremony.

## Alternatives considered
Microservices (too much operational weight for one developer); a layer-first monolith (boundaries erode silently).
