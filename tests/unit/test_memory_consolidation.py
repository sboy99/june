import asyncio
from datetime import UTC, datetime

import pytest

from june.memory import (
    Consolidate,
    ConsolidationResult,
    FactCandidate,
    RememberConversation,
    RememberEpisode,
    RememberFact,
    TranscriptTurn,
)
from june.memory.adapters.hashing_embedder import HashingEmbedder
from june.memory.adapters.sqlite_index import SqliteVectorIndex
from june.memory.domain import EpisodeStatus, Fact
from june.memory.ports import SearchFilter
from june.shared import DomainError, FixedClock, PermanentAdapterError, TransientAdapterError

pytestmark = pytest.mark.unit

NOW = datetime(2026, 6, 1, tzinfo=UTC)
PENDING = SearchFilter(kind="episode", episode_status=EpisodeStatus.PENDING)
FACTS = SearchFilter(kind="fact")


class CountingIds:
    def __init__(self):
        self.count = 0

    def new_id(self):
        self.count += 1
        return f"id{self.count}"


class FakeSummarizer:
    def __init__(self, candidates=(), summary="they chatted", error=None, delay=0.0):
        self.candidates = list(candidates)
        self.summary = summary
        self.error = error
        self.delay = delay
        self.summarize_calls = []
        self.distill_calls = 0

    async def summarize(self, turns):
        self.summarize_calls.append(list(turns))
        if self.error:
            raise self.error
        return self.summary

    async def distill(self, episodes):
        self.distill_calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.candidates


class SpyEmbedder(HashingEmbedder):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def embed(self, texts):
        self.calls += 1
        return await super().embed(texts)


@pytest.fixture
async def index():
    adapter = SqliteVectorIndex(":memory:")
    yield adapter
    adapter.close()


@pytest.fixture
def embedder():
    return SpyEmbedder()


@pytest.fixture
def ids():
    return CountingIds()


@pytest.fixture
def remember_fact(index, embedder, ids):
    return RememberFact(index, embedder, FixedClock(NOW), ids)


@pytest.fixture
def remember_episode(index, embedder, ids):
    return RememberEpisode(index, embedder, FixedClock(NOW), ids)


def consolidator(index, summarizer, remember_fact):
    return Consolidate(index, summarizer, remember_fact)


async def test_conversation_is_summarized_into_a_pending_episode(remember_episode, index):
    summarizer = FakeSummarizer(summary="talked about hiking")
    use_case = RememberConversation(summarizer, remember_episode)
    turns = [TranscriptTurn("user", "hi"), TranscriptTurn("assistant", "hello")]

    episode = await use_case.execute("u1", turns)

    assert episode.summary == "talked about hiking"
    assert episode.status is EpisodeStatus.PENDING
    assert summarizer.summarize_calls == [turns]
    assert len(await index.list("u1", PENDING)) == 1


async def test_empty_conversation_is_rejected_before_any_call(remember_episode, embedder):
    summarizer = FakeSummarizer()
    use_case = RememberConversation(summarizer, remember_episode)

    with pytest.raises(DomainError):
        await use_case.execute("u1", [])

    assert summarizer.summarize_calls == []
    assert embedder.calls == 0


def test_tool_activity_is_not_a_transcript_turn():
    with pytest.raises(DomainError):
        TranscriptTurn("tool", "ls output")  # type: ignore[arg-type]


async def test_consolidation_stores_candidates_as_facts_and_marks_episodes(
    index, remember_fact, remember_episode
):
    await remember_episode.execute("u1", "likes tea")
    await remember_episode.execute("u1", "lives in Oslo")
    candidates = [FactCandidate("likes tea"), FactCandidate("lives in Oslo", "city")]
    summarizer = FakeSummarizer(candidates)

    result = await consolidator(index, summarizer, remember_fact).execute("u1")

    assert result == ConsolidationResult(episodes_consolidated=2, facts_stored=2, facts_skipped=0)
    facts = [e.item for e in await index.list("u1", FACTS)]
    assert {f.text for f in facts} == {"likes tea", "lives in Oslo"}
    assert all(f.source == "consolidation" for f in facts)
    assert await index.list("u1", PENDING) == []
    episodes = await index.list("u1", SearchFilter(kind="episode"))
    assert all(e.item.status is EpisodeStatus.CONSOLIDATED for e in episodes)


async def test_consolidated_episodes_keep_their_vectors(index, remember_fact, remember_episode):
    await remember_episode.execute("u1", "likes tea")
    [before] = await index.list("u1", PENDING)

    await consolidator(index, FakeSummarizer(), remember_fact).execute("u1")

    [after] = await index.list("u1", SearchFilter(kind="episode"))
    assert after.vector == before.vector
    assert after.embedder == before.embedder


async def test_second_run_is_a_noop(index, remember_fact, remember_episode, embedder):
    await remember_episode.execute("u1", "likes tea")
    summarizer = FakeSummarizer([FactCandidate("likes tea")])
    use_case = consolidator(index, summarizer, remember_fact)
    await use_case.execute("u1")
    embed_calls = embedder.calls

    result = await use_case.execute("u1")

    assert result == ConsolidationResult(0, 0, 0)
    assert summarizer.distill_calls == 1
    assert embedder.calls == embed_calls


async def test_summarizer_failure_leaves_episodes_pending(index, remember_fact, remember_episode):
    await remember_episode.execute("u1", "likes tea")
    error = TransientAdapterError("boom")
    use_case = consolidator(index, FakeSummarizer(error=error), remember_fact)

    with pytest.raises(TransientAdapterError) as raised:
        await use_case.execute("u1")

    assert raised.value is error
    assert len(await index.list("u1", PENDING)) == 1
    assert await index.list("u1", FACTS) == []


async def test_permanent_summarizer_failure_passes_through(index, remember_fact, remember_episode):
    await remember_episode.execute("u1", "likes tea")
    use_case = consolidator(index, FakeSummarizer(error=PermanentAdapterError("no")), remember_fact)

    with pytest.raises(PermanentAdapterError):
        await use_case.execute("u1")


async def test_failure_while_storing_facts_leaves_episodes_pending_and_rerun_dedupes(
    index, remember_episode, embedder, ids
):
    await remember_episode.execute("u1", "likes tea")
    summarizer = FakeSummarizer([FactCandidate("likes tea"), FactCandidate("lives in Oslo")])

    class FlakyRememberFact(RememberFact):
        failing = True

        async def execute(self, user_id, text, source, profile_key=None):
            if self.failing and text == "lives in Oslo":
                raise TransientAdapterError("down")
            return await super().execute(user_id, text, source, profile_key)

    flaky = FlakyRememberFact(index, embedder, FixedClock(NOW), ids)
    use_case = consolidator(index, summarizer, flaky)

    with pytest.raises(TransientAdapterError):
        await use_case.execute("u1")
    assert len(await index.list("u1", PENDING)) == 1

    flaky.failing = False
    result = await use_case.execute("u1")

    assert result == ConsolidationResult(episodes_consolidated=1, facts_stored=1, facts_skipped=1)
    texts = sorted(e.item.text for e in await index.list("u1", FACTS))
    assert texts == ["likes tea", "lives in Oslo"]


@pytest.mark.parametrize(
    "secret",
    ["api_key=abc123def", "my token: s3cr3tvalue", "use sk-abcdef123456", "Bearer abc.def.ghi"],
)
async def test_secret_candidates_are_never_stored(index, remember_fact, remember_episode, secret):
    await remember_episode.execute("u1", "something")
    summarizer = FakeSummarizer([FactCandidate(secret), FactCandidate("likes tea")])

    result = await consolidator(index, summarizer, remember_fact).execute("u1")

    assert result == ConsolidationResult(episodes_consolidated=1, facts_stored=1, facts_skipped=1)
    texts = [e.item.text for e in await index.list("u1", FACTS)]
    assert texts == ["likes tea"]


async def test_existing_fact_counts_as_skipped(index, remember_fact, remember_episode):
    await remember_fact.execute("u1", "Likes  Tea", "chat")
    await remember_episode.execute("u1", "tea talk")
    summarizer = FakeSummarizer([FactCandidate("likes tea")])

    result = await consolidator(index, summarizer, remember_fact).execute("u1")

    assert result == ConsolidationResult(episodes_consolidated=1, facts_stored=0, facts_skipped=1)
    assert len(await index.list("u1", FACTS)) == 1


async def test_profile_key_candidate_supersedes_old_fact(index, remember_fact, remember_episode):
    old = await remember_fact.execute("u1", "lives in Oslo", "chat", "city")
    await remember_episode.execute("u1", "moved")
    summarizer = FakeSummarizer([FactCandidate("lives in Rome", "city")])

    await consolidator(index, summarizer, remember_fact).execute("u1")

    stored = await index.get("u1", old.id)
    assert isinstance(stored.item, Fact) and not stored.item.is_active


async def test_only_the_given_users_episodes_are_consolidated(
    index, remember_fact, remember_episode
):
    await remember_episode.execute("u1", "one")
    await remember_episode.execute("u2", "two")

    await consolidator(index, FakeSummarizer(), remember_fact).execute("u1")

    assert len(await index.list("u2", PENDING)) == 1


async def test_concurrent_runs_for_one_user_are_serialized(index, remember_fact, remember_episode):
    await remember_episode.execute("u1", "likes tea")
    summarizer = FakeSummarizer([FactCandidate("likes tea")], delay=0.05)
    use_case = consolidator(index, summarizer, remember_fact)

    first, second = await asyncio.gather(use_case.execute("u1"), use_case.execute("u1"))

    assert summarizer.distill_calls == 1
    assert sorted([first.episodes_consolidated, second.episodes_consolidated]) == [0, 1]
    assert len(await index.list("u1", FACTS)) == 1


async def test_different_users_do_not_block_each_other(index, remember_fact, remember_episode):
    await remember_episode.execute("u1", "a")
    await remember_episode.execute("u2", "b")
    summarizer = FakeSummarizer(delay=0.05)
    use_case = consolidator(index, summarizer, remember_fact)

    await asyncio.gather(use_case.execute("u1"), use_case.execute("u2"))

    assert summarizer.distill_calls == 2


async def test_blank_user_id_is_rejected(index, remember_fact):
    with pytest.raises(DomainError):
        await consolidator(index, FakeSummarizer(), remember_fact).execute("  ")
