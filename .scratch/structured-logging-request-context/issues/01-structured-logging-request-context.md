# 01: Implement structured logging with request context

Status: ready-for-agent
Blocked by: none

Implement the whole spec at `.scratch/structured-logging-request-context/spec.md` (SHIP-311). It is small and cohesive, so it is a single ticket.

Done when: `make check` passes, a test plants a secret and the log output is redacted, and every Testing Decisions bullet in the spec is covered.
