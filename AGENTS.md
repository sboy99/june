# june

A modular AI agent built as a hexagonal modular monolith. Architecture rules are enforced by tooling (`make arch`, `make check`).

## Project context

- **Architecture**: `docs/ARCHITECTURE.md`. Module map, layer order, the five import-linter contracts (`.importlinter`), and the request flow. Read it before adding or moving code across modules.
- **Glossary**: `docs/GLOSSARY.md`. One definition per term, with the owning module. Use these terms in code, tests, issues and docs. A new concept needs a glossary entry in the same PR.
- **ADRs**: `docs/adr/` (template: `0000-template.md`). Read those touching the area you are changing. If your change contradicts an ADR, say so explicitly rather than overriding it silently. Add a new ADR for significant decisions.

## Commands

- `uv sync`: install dependencies
- `python -m june`: run the app
- `make check`: full checks; `make arch`: architecture contracts only

## Agent skills

### Issue tracker

Issues and specs are local markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `docs/GLOSSARY.md` + `docs/adr/`. See `docs/agents/domain.md`.

## Linear status workflow

Keep the Linear issue status in step with the work. Update it yourself, without asking.

- After writing the spec for an issue (`.scratch/<feature>/spec.md`): set the issue to **In Progress**.
- After committing the implementation or creating its PR: set the issue to **In Review**. Do this for every issue the commit or PR covers.
