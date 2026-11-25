# ADR 0003: Context-first folders, not layer-first

- Status: accepted

## Context
We can group code by technical layer (all ports together) or by feature area.

## Decision
Folders are named for what they do (memory, safety, llm). Layers appear inside a module only when needed.

## Consequences
Related code sits together and ownership is clear. Shared technical concerns live in shared/ and must stay small.

## Alternatives considered
Layer-first (controllers, services, repositories): scatters one feature across the tree.
