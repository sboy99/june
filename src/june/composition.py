"""Composition root: the only place where the application is wired together."""

from dataclasses import dataclass

from june.config import Settings
from june.shared import PersonaNotFound


@dataclass(frozen=True)
class App:
    """The wired application."""

    settings: Settings
    soul: str


def load_persona(settings: Settings) -> str:
    """Read the persona text from the configured path."""
    path = settings.persona_path
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PersonaNotFound(f"persona file not found or unreadable: {path}") from exc
    if not text.strip():
        raise PersonaNotFound(f"persona file is empty: {path}")
    return text


def build_app(settings: Settings) -> App:
    """Build the application from explicit settings."""
    return App(settings=settings, soul=load_persona(settings))
