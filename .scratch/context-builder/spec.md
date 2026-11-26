# Context builder (SHIP-326, P3.2)

Status: ready-for-agent
Source: Linear SHIP-326, milestone "Phase 3: Conversation and runtime"
Branch: `contactsagarbera/ship-326-p32-context-builder` (stacked on SHIP-325)

## Problem Statement

The runtime has no way to turn a persona, a user's profile, recalled memories, skills and history into the messages a Chat model sees. Without one fixed, tested assembly, prompt order drifts and recalled memory text (which came from earlier conversations) can be mistaken for instructions.

## Solution

A pure `ContextBuilder` in `june.runtime`. It is built once with the persona text and, per request, turns the user message plus already-fetched inputs into an ordered tuple of `Message`s: one system message (persona, user profile, recalled memories wrapped as untrusted, skills index with the best-matching skill loaded), then trimmed history, then the new user message. It does no I/O; the persona text is passed in.

## User Stories

1. As the runtime, I want the persona text to open the system message, so it outranks everything after it.
2. As the runtime, I want the user profile (active Facts with a Profile key) rendered as `key: text` lines after the persona.
3. As the runtime, I want recalled memories rendered after the profile, in the order given (best first).
4. As the runtime, I want every recalled memory wrapped in an `untrusted_memory` block with a standing note that its content is data, never instructions.
5. As the runtime, I want a memory that contains the closing tag to be unable to break out of its block.
6. As the runtime, I want an index of all skills (name and description) in the system message, ordered by name.
7. As the runtime, I want the one skill whose name and description best match the user message loaded in full (name, description, numbered steps), and none loaded when nothing matches.
8. As the runtime, I want matching to be deterministic: more shared words wins, ties go to the lower name.
9. As the runtime, I want history rendered as alternating user and assistant messages, oldest first, then the new user message last.
10. As the runtime, I want history trimmed from the oldest end to fit a character budget, never splitting a turn.
11. As the runtime, I want the newest turn always kept if it alone fits the budget, and an empty history when even it does not.
12. As the runtime, I want sections with no content omitted, not rendered as empty headings.
13. As the runtime, I want the same inputs to give the same output.
14. As the runtime, I want a blank persona or a blank user message rejected with `DomainError`, and a non-positive history budget rejected.
15. As an architect, I want the runtime to read no files and import no adapters, so the persona stays read-only text (ADR 0005) and all five import contracts pass.
16. As a maintainer, I want `build_app` to expose a `context_builder` built from the persona, and new terms in the glossary.

## Implementation Decisions

- `ContextBuilder(persona, history_char_budget=DEFAULT)`; `build(user_message, *, profile=(), memories=(), skills=(), history=()) -> tuple[Message, ...]`. No state between calls.
- Inputs are domain values the runtime may import from lower layers: `Fact`, `Skill` and `RecalledMemory` from memory, `Turn` from conversation. `Fact`, `Episode` and `Skill` are re-exported from `june.memory`.
- Section order is fixed: persona, user profile, recalled memories, skills index, loaded skill. Each section after the persona has a plain heading.
- Memories: a `Fact` renders its text, an `Episode` its summary. Profile facts are rendered plainly (they are the user's own stated attributes); only recalled memories are wrapped.
- Escaping: the literal closing tag inside memory text is neutralised so a block cannot be closed early.
- Skill match: lowercase word tokens of three or more characters; score is the count of tokens shared between the message and `name + description`; best score above zero wins; ties by name.
- Trimming counts characters of user message plus reply per turn; the constant default budget is named in code.
- No ADR: follows ADR 0005 (persona passed in) and 0001.

## Testing Decisions

- Test only the returned messages through the public `june.runtime` API with real `Fact`, `Episode`, `Skill`, `Turn` values. No assertions on private helpers.
- Cover every story above. Prior art: `tests/unit/test_memory_consolidation.py` for style.
- `make check` passes; coverage of `june.runtime` at least 80%.

## Out of Scope

- Fetching memories, skills or history (the loop's caller does), token-accurate counting, embedding-based skill matching, summarising dropped history, the loop itself (P3.3).

## Further Notes

- Linear: SHIP-326.
