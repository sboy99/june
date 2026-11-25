import asyncio

import pytest

from june.observability import get_logger, new_trace_id, request_context

pytestmark = pytest.mark.unit


def test_bound_ids_appear_inside_the_block_and_not_after(log_output):
    _, lines = log_output
    logger = get_logger("june.ctx")

    with request_context(trace_id="t1", session_id="s1", user_id="u1"):
        logger.info("inside")
    logger.info("after")

    inside, after = lines()
    assert (inside["trace_id"], inside["session_id"], inside["user_id"]) == ("t1", "s1", "u1")
    assert after["trace_id"] is None


def test_binding_a_subset_keeps_outer_values_for_the_rest(log_output):
    _, lines = log_output

    with request_context(trace_id="t1", session_id="s1"), request_context(trace_id="t2"):
        get_logger("june.ctx").info("nested")

    (line,) = lines()
    assert line["trace_id"] == "t2"
    assert line["session_id"] == "s1"


def test_previous_context_is_restored_when_the_block_raises(log_output):
    _, lines = log_output

    with request_context(trace_id="outer"):
        with pytest.raises(RuntimeError), request_context(trace_id="inner"):
            raise RuntimeError("x")
        get_logger("june.ctx").info("back")

    assert lines()[0]["trace_id"] == "outer"


async def test_context_propagates_into_tasks_started_inside_the_block(log_output):
    _, lines = log_output

    async def work() -> None:
        get_logger("june.ctx").info("in task")

    with request_context(trace_id="t1"):
        await asyncio.create_task(work())

    assert lines()[0]["trace_id"] == "t1"


async def test_concurrent_requests_keep_separate_context(log_output):
    _, lines = log_output

    async def request(trace_id: str) -> None:
        with request_context(trace_id=trace_id):
            await asyncio.sleep(0)
            get_logger("june.ctx").info(trace_id)
            await asyncio.sleep(0)
            get_logger("june.ctx").info(trace_id)

    await asyncio.gather(request("a"), request("b"))

    assert all(line["trace_id"] == line["message"] for line in lines())
    assert len(lines()) == 4


def test_new_trace_id_uses_the_given_generator():
    class FakeIds:
        def new_id(self) -> str:
            return "fixed"

    assert new_trace_id(FakeIds()) == "fixed"


def test_new_trace_id_defaults_to_a_fresh_shared_id():
    assert new_trace_id() != new_trace_id()
