# Contributing

## Setup
`uv sync`, then `make check`. Python 3.12.

## Conventions
- Domain code uses frozen dataclasses and plain functions; pydantic only at edges.
- Ports are `typing.Protocol`; adapters never subclass them.
- Absolute imports, no `import *`, no relative imports across packages.
- A module's `__init__.py` is its public API; do not reach into another module's subfolders.
- Names come from `docs/GLOSSARY.md`; a new concept adds an entry in the same PR.
- Soft limits: files under 300 lines, functions under 40. Exceeding one needs a reason in review.

## Add an adapter
Implement the port in the module's `adapters/`, register it in `composition.py`, add tests.

## Add a module
Create the package with a docstring, `__all__` and `ports.py`, add it to the layers contract in `.importlinter`, and add glossary terms.

## ADR process
Copy `docs/adr/0000-template.md`, keep it to one page, and open a PR.

## PR checklist
- [ ] `make check` passes
- [ ] Tests cover new behavior through the CLI or architecture seams
- [ ] Glossary and ADRs updated if needed
