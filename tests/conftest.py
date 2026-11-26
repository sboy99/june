import io
import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from june.observability import configure_logging

LogLines = Callable[[], list[dict[str, Any]]]

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def run_june(tmp_path: Path):
    """Run `python -m june` as a subprocess with an isolated environment."""

    def _run(**env_overrides: str) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("JUNE_")}
        env.update(env_overrides)
        return subprocess.run(
            [sys.executable, "-m", "june"],
            capture_output=True,
            text=True,
            env=env,
            cwd=tmp_path,
            check=False,
        )

    return _run


@pytest.fixture
def log_output() -> Iterator[tuple[io.StringIO, LogLines]]:
    """Configure june logging into memory; yield the stream and a JSON-line parser."""
    stream = io.StringIO()
    configure_logging("DEBUG", stream=stream)

    def lines() -> list[dict[str, Any]]:
        return [json.loads(line) for line in stream.getvalue().splitlines()]

    yield stream, lines
    june_logger = logging.getLogger("june")
    june_logger.handlers.clear()
    june_logger.setLevel(logging.NOTSET)
