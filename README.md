# june

A modular AI agent built as a hexagonal modular monolith. Phase 0 is an empty, bootable skeleton with architecture rules enforced by tooling.

## Quickstart
```
uv sync
python -m june      # june 0.1.0 ready (persona: <n> chars)
make check
```
Configuration comes from `JUNE_*` environment variables (see `.env.example`).

## Docs
- [Architecture](docs/ARCHITECTURE.md)
- [Glossary](docs/GLOSSARY.md)
- [Decision records](docs/adr/)
- [Contributing](CONTRIBUTING.md)
