from pathlib import Path

import pytest
from pydantic import ValidationError

from june import config
from june.shared import ConfigError

pytestmark = pytest.mark.unit


def test_invalid_settings_are_reported_as_a_config_error(monkeypatch):
    class StrictSettings(config.Settings):
        max_steps: int = 1

    monkeypatch.setattr(config, "Settings", StrictSettings)
    monkeypatch.setenv("JUNE_MAX_STEPS", "not-a-number")

    with pytest.raises(ConfigError) as caught:
        config.load_settings()

    assert "max_steps" in str(caught.value)
    assert len(str(caught.value).splitlines()) == 1


def test_valid_settings_load(monkeypatch):
    monkeypatch.setenv("JUNE_LOG_LEVEL", "DEBUG")

    assert config.load_settings().log_level == "DEBUG"


PLANTED_KEY = "sk-planted-secret-1234567890"
SETTING_ENV_VARS = (
    "JUNE_LLM_PROVIDER",
    "JUNE_LLM_MODEL",
    "JUNE_LLM_API_KEY",
    "JUNE_LLM_BASE_URL",
    "JUNE_LLM_TIMEOUT_SECONDS",
    "JUNE_LLM_MAX_RETRIES",
)


@pytest.fixture(autouse=True)
def clean_model_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in SETTING_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_use_the_mock_provider_without_a_key():
    settings = config.load_settings()

    assert settings.llm_provider == "mock"
    assert settings.llm_api_key is None
    assert settings.llm_timeout_seconds == 30
    assert settings.llm_max_retries == 2


@pytest.mark.parametrize(
    ("name", "value", "field"),
    [
        ("JUNE_LLM_PROVIDER", "anthropc", "llm_provider"),
        ("JUNE_LLM_TIMEOUT_SECONDS", "0", "llm_timeout_seconds"),
        ("JUNE_LLM_TIMEOUT_SECONDS", "abc", "llm_timeout_seconds"),
        ("JUNE_LLM_MAX_RETRIES", "-1", "llm_max_retries"),
        ("JUNE_LLM_MAX_RETRIES", "11", "llm_max_retries"),
    ],
)
def test_invalid_model_setting_fails_with_one_line_naming_it(monkeypatch, name, value, field):
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigError) as caught:
        config.load_settings()

    assert field in str(caught.value)
    assert len(str(caught.value).splitlines()) == 1


def test_openai_without_api_key_fails_at_startup(monkeypatch):
    monkeypatch.setenv("JUNE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("JUNE_LLM_MODEL", "gpt-4o-mini")

    with pytest.raises(ConfigError) as caught:
        config.load_settings()

    assert "JUNE_LLM_API_KEY" in str(caught.value)
    assert len(str(caught.value).splitlines()) == 1


def test_openai_with_blank_model_fails_at_startup(monkeypatch):
    monkeypatch.setenv("JUNE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("JUNE_LLM_API_KEY", PLANTED_KEY)
    monkeypatch.setenv("JUNE_LLM_MODEL", "  ")

    with pytest.raises(ConfigError) as caught:
        config.load_settings()

    assert "JUNE_LLM_MODEL" in str(caught.value)
    assert PLANTED_KEY not in str(caught.value)


def test_openai_with_key_and_model_loads(monkeypatch):
    monkeypatch.setenv("JUNE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("JUNE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("JUNE_LLM_API_KEY", PLANTED_KEY)

    settings = config.load_settings()

    assert settings.llm_api_key.get_secret_value() == PLANTED_KEY


def test_api_key_never_appears_in_repr_or_str(monkeypatch):
    monkeypatch.setenv("JUNE_LLM_API_KEY", PLANTED_KEY)

    settings = config.load_settings()

    assert PLANTED_KEY not in repr(settings)
    assert PLANTED_KEY not in str(settings)


def test_api_key_never_appears_in_validation_errors(monkeypatch):
    monkeypatch.setenv("JUNE_LLM_API_KEY", PLANTED_KEY)
    monkeypatch.setenv("JUNE_LLM_MAX_RETRIES", "99")

    with pytest.raises(ConfigError) as caught:
        config.load_settings()

    assert PLANTED_KEY not in str(caught.value)


def test_settings_are_immutable():
    settings = config.load_settings()

    with pytest.raises(ValidationError):
        settings.llm_model = "other"


def test_env_example_lists_every_setting():
    example = (Path(__file__).parents[2] / ".env.example").read_text()
    listed = {line.split("=", 1)[0] for line in example.splitlines() if "=" in line}

    expected = {f"JUNE_{name.upper()}" for name in config.Settings.model_fields}

    assert expected <= listed
