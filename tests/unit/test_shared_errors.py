import pytest

from june.shared import (
    AdapterError,
    AgentError,
    BudgetExceeded,
    ConfigError,
    DomainError,
    PermanentAdapterError,
    PersonaNotFound,
    SafetyDenied,
    ToolError,
    TransientAdapterError,
)
from june.shared import errors as errors_module

pytestmark = pytest.mark.unit

AGENT_ERROR_CHILDREN = [
    ConfigError,
    PersonaNotFound,
    DomainError,
    AdapterError,
    SafetyDenied,
    BudgetExceeded,
    ToolError,
]


def _all_subclasses(root: type) -> set[type]:
    found: set[type] = set()
    for child in root.__subclasses__():
        found.add(child)
        found |= _all_subclasses(child)
    return found


@pytest.mark.parametrize("error_type", AGENT_ERROR_CHILDREN)
def test_every_direct_child_is_an_agent_error(error_type):
    assert issubclass(error_type, AgentError)


@pytest.mark.parametrize("error_type", [TransientAdapterError, PermanentAdapterError])
def test_transient_and_permanent_adapter_errors_are_adapter_errors(error_type):
    assert issubclass(error_type, AdapterError)


def test_transient_adapter_error_is_retryable_by_default():
    assert TransientAdapterError("timeout").retryable is True


@pytest.mark.parametrize(
    "error_type",
    [
        AgentError,
        ConfigError,
        PersonaNotFound,
        DomainError,
        AdapterError,
        PermanentAdapterError,
        SafetyDenied,
        BudgetExceeded,
        ToolError,
    ],
)
def test_all_other_errors_are_not_retryable_by_default(error_type):
    assert error_type("boom").retryable is False


def test_retryable_can_be_overridden_per_instance():
    assert ToolError("flaky", retryable=True).retryable is True
    assert TransientAdapterError("fatal", retryable=False).retryable is False


@pytest.mark.parametrize("error_type", [SafetyDenied, BudgetExceeded])
def test_safety_and_budget_errors_reject_a_retryable_override(error_type):
    with pytest.raises(ValueError):
        error_type("nope", retryable=True)


def test_codes_are_stable_snake_case_literals():
    assert ConfigError("x").code == "config_error"
    assert PersonaNotFound("x").code == "persona_not_found"
    assert TransientAdapterError("x").code == "adapter_transient"
    assert PermanentAdapterError("x").code == "adapter_permanent"


def test_codes_are_unique_across_the_whole_hierarchy():
    classes = {
        cls for cls in _all_subclasses(AgentError) if cls.__module__ == errors_module.__name__
    } | {AgentError}

    codes = [cls.code for cls in classes]

    assert len(codes) == len(set(codes))


def test_str_is_the_plain_message():
    assert str(PersonaNotFound("persona file empty: /x")) == "persona file empty: /x"


def test_cause_chaining_with_raise_from_is_preserved():
    original = TimeoutError("vendor timed out")

    with pytest.raises(TransientAdapterError) as caught:
        try:
            raise original
        except TimeoutError as exc:
            raise TransientAdapterError("llm timeout") from exc

    assert caught.value.__cause__ is original


def test_cause_argument_sets_the_exception_cause():
    original = ValueError("bad key")

    error = PermanentAdapterError("rejected", cause=original)

    assert error.__cause__ is original
