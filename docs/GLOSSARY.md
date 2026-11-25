# Glossary

One definition per term. The owning module is in brackets. A new concept needs an entry in the same PR.

- **Session** [conversation]: one continuous interaction between a user and the agent, identified by an id.
- **Turn** [conversation]: one user message and the agent's complete reply.
- **Step** [runtime]: one iteration of the agent loop inside a turn (think, then optionally act).
- **Episode** [memory]: a stored summary of something that happened, kept for later recall.
- **Fact** [memory]: a small, durable statement about the user or the world.
- **Skill** [memory]: a reusable procedure the agent has learned and can replay.
- **Persona** [persona/SOUL.md]: the agent's identity, tone and values, loaded at startup and read-only to the agent.
- **Gate** [safety]: a check that must pass before an action runs.
- **Port** [each module's `ports.py`]: a `typing.Protocol` describing what a module needs from the outside.
- **Adapter** [each module's `adapters/`]: a concrete implementation of a port that talks to a vendor, a database or the file system.
- **Consolidation** [memory]: turning working memory and recent episodes into durable facts and skills.
- **Working memory** [runtime]: the context the loop holds for the current turn.
- **Budget** [runtime]: limits on steps, tokens or time for a turn.
- **Risk level** [safety]: the classified danger of an action, which decides which gates apply.
