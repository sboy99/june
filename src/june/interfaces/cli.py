"""Command-line entry point: boots the app, reports readiness and exits."""

import sys
from importlib.metadata import version

from june.composition import build_app
from june.config import load_settings
from june.observability import configure_logging
from june.shared import AgentError


def main() -> int:
    """Boot the application and print a readiness line."""
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        app = build_app(settings)
    except AgentError as exc:
        print(f"june: error: {exc}", file=sys.stderr)
        return 1
    print(f"june {version('june')} ready (persona: {len(app.soul)} chars)")
    return 0
