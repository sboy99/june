# 01: Implement settings for model providers

Status: ready-for-agent
Blocked by: none

Implement the whole spec at `.scratch/settings-for-model-providers/spec.md` (SHIP-312). It is one small, cohesive change, so it is a single ticket.

Done when: `make check` passes, invalid values fail at startup with a one-line `ConfigError`, a planted API key never appears in `repr` or error text, and `.env.example` lists every setting.
