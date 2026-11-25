"""Settings loaded from JUNE_-prefixed environment variables; the only environment reader."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from the environment and an optional .env file."""

    model_config = SettingsConfigDict(env_prefix="JUNE_", env_file=".env", extra="ignore")

    persona_path: Path = Path("persona/SOUL.md")
    data_dir: Path = Path("./data")
    log_level: str = "INFO"
    llm_provider: str = "mock"
