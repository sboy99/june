# End-to-end chat on the mock LLM (SHIP-330, P3.6)

Status: ready-for-agent
Source: Linear SHIP-330, milestone "Phase 3: Conversation and runtime"
Branch: `contactsagarbera/ship-330-p36-end-to-end-chat-tests-on-the` (stacked on SHIP-329)

## Problem Statement

The Context builder, Agent loop, Session store, Recall and Session closer exist but nothing joins them. There is no way to hold a conversation, and no proof that what is said in one Session shapes the next.

## Solution

`june.runtime` gains a `ChatService`, wired in `build_app` as `App.chat_service`. It starts Sessions, answers a user message (recall, build context, run the loop, save the Turn) and ends Sessions through the Session closer. End-to-end tests drive it on the mock Chat model, the hashing Embedder and real SQLite stores, and show a working agent with memory and no tools: Session 1 is remembered and appears as untrusted memory in Session 2.

## User Stories

1. As a user, I want `start_session(user_id)` to give me a new, saved, empty Session.
2. As a user, I want `chat(session, message)` to return the agent's reply and the updated Session.
3. As a user, I want each answered message saved as a Turn, so history survives a restart.
4. As a user, I want earlier Turns of the Session in the prompt, so the agent follows the conversation.
5. As a user, I want memories relevant to my message recalled and shown to the model as untrusted memory.
6. As a user, I want my profile Facts (Facts with a Profile key) in the prompt.
7. As a user, I want the Skills index in the prompt.
8. As a user, I want a run that ends without an answer (model error, a budget limit) to return its stop reason and no reply, and the Session left unchanged.
9. As a user, I want a truncated reply kept as the Turn's reply.
10. As a user, I want `end_session(session)` to return at once and the Session stored as an Episode in the background.
11. As a user, I want a later Session to recall what an earlier one said.
12. As an operator, I want every log line of a chat call to carry the trace, session and user ids.
13. As an operator, I want a blank message rejected with `DomainError` before any model call.
14. As a maintainer, I want `App` to expose `chat_service`, the Session closer and an offline extractive Summarizer, and the glossary to describe the new terms.

## Implementation Decisions

- `ChatService(sessions, context_builder, agent_loop, recall, index, skills, clock, ids, closer)`; async `start_session`, async `chat`, sync `end_session` delegating to the closer, async `drain` delegating too.
- `ChatReply` is frozen: `reply`, `session`, `stop` (a `LoopStop`), `error_code`. On any stop other than `answered`/`truncated` the returned session is the input session and nothing is saved.
- Recall uses a fixed limit of 5 and a minimum similarity of 0.1, as constants. Profile Facts come from active Facts in the index that have a Profile key.
- Only the final reply is stored in the Turn; tool messages from the loop are not.
- Each `chat` call binds a request context (new trace id, session id, user id).
- The default Summarizer is an offline, deterministic `ExtractiveSummarizer` in the memory adapters: `summarize` returns the transcript as `role: text` lines cut to a length limit, `distill` returns no candidates. A model-backed Summarizer is a later issue; consolidation therefore marks Episodes consolidated without making Facts for now.
- `build_app` wires `RememberConversation`, `Consolidate`, `SessionCloser` and `ChatService`.

## Testing Decisions

- End-to-end through `build_app` with `llm_provider=mock`, hashing embedder and a temp data dir: assert on replies, saved Sessions, the prompts the mock recorded, and the index contents. A scripted-Summarizer variant proves Facts reach the profile section.
- A unit-level test per story where the e2e does not reach it (error stop, blank message, log ids).
- Prior art: `tests/unit/test_composition.py`, `tests/unit/test_runtime_loop.py`.
- `make check` passes; `june.runtime` coverage at least 80%.

## Out of Scope

- A CLI chat command, tools, safety Gates, a model-backed Summarizer, streaming, multi-user auth.

## Further Notes

- Linear: SHIP-330. This is the Phase 3 exit check: a working agent with memory, no tools.
