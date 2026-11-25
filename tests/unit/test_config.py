import pytest

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
