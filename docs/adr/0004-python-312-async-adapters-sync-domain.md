# ADR 0004: Python 3.12; async adapters and loop, synchronous domain

- Status: accepted

## Context
The agent waits on network calls, so async fits I/O. Domain rules are pure and gain nothing from async.

## Decision
Python 3.12. The loop and adapters are async. Domain code is synchronous and may not import asyncio, which is a contract.

## Consequences
Domain stays trivially testable. Callers await at the edges.

## Alternatives considered
Everything async (infects pure code); everything sync (blocks on I/O or needs threads).
