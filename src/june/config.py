"""Settings loaded from JUNE_-prefixed environment variables; the only environment reader."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from june.shared import ConfigError


class Settings(BaseSettings):
    """Application settings, read from the environment and an optional .env file."""

    model_config = SettingsConfigDict(
        env_prefix="JUNE_", env_file=".env", extra="ignore", frozen=True
    )

    persona_path: Path = Path("persona/SOUL.md")
    data_dir: Path = Path("./data")
    log_level: str = "INFO"
    llm_provider: Literal["mock", "openai"] = "mock"
    llm_model: str = "mock"
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    llm_max_retries: int = Field(default=2, ge=0, le=10)

    @model_validator(mode="after")
    def _require_credentials_for_real_provider(self) -> Self:
        if self.llm_provider == "mock":
            return self
        if self.llm_api_key is None or not self.llm_api_key.get_secret_value().strip():
            raise ValueError(f"JUNE_LLM_API_KEY is required when llm_provider={self.llm_provider}")
        if not self.llm_model.strip():
            raise ValueError(f"JUNE_LLM_MODEL is required when llm_provider={self.llm_provider}")
        return self


def load_settings() -> Settings:
    """Load settings, reporting invalid values as a `ConfigError`."""
    try:
        return Settings()
    except ValidationError as exc:
        problems = "; ".join(_describe_problem(err["loc"], err["msg"]) for err in exc.errors())
        raise ConfigError(f"invalid configuration: {problems}") from exc


def _describe_problem(location: tuple[int | str, ...], message: str) -> str:
    """Render one validation problem; model-level errors have no field location."""
    if not location:
        return message.removeprefix("Value error, ")
    return f"{'.'.join(str(part) for part in location)}: {message}"
