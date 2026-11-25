# ADR 0002: DDD-lite: domain layer only in memory

- Status: accepted

## Context
Memory has real business rules (what to keep, merge, forget). Other modules are mostly orchestration or glue.

## Decision
Only memory gets domain, application and adapters layers. Other modules stay flat until rules spread, then we widen them.

## Consequences
Less structure to maintain now. A module may need restructuring later; the contracts make that safe.

## Alternatives considered
Full DDD everywhere (speculative); no domain layer at all (rules would leak into adapters).
