import os
import subprocess
import sys
from pathlib import Path

import pytest

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
