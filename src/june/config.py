"""Settings loaded from JUNE_-prefixed environment variables; the only environment reader."""

from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from june.shared import ConfigError


class Settings(BaseSettings):
    """Application settings, read from the environment and an optional .env file."""

    model_config = SettingsConfigDict(env_prefix="JUNE_", env_file=".env", extra="ignore")

    persona_path: Path = Path("persona/SOUL.md")
    data_dir: Path = Path("./data")
    log_level: str = "INFO"
    llm_provider: str = "mock"


def load_settings() -> Settings:
    """Load settings, reporting invalid values as a `ConfigError`."""
    try:
        return Settings()
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise ConfigError(f"invalid configuration: {problems}") from exc
