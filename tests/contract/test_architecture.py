import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

pytestmark = pytest.mark.contract


@pytest.fixture
def project_copy(tmp_path: Path) -> Path:
    """A throwaway copy of the source tree and contract config, safe to violate."""
    shutil.copytree(
        REPO_ROOT / "src", tmp_path / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copy(REPO_ROOT / ".importlinter", tmp_path / ".importlinter")
    return tmp_path


def lint_imports(project: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(project / "src")}
    return subprocess.run(
        [str(Path(sys.executable).parent / "lint-imports"), "--config", ".importlinter"],
        capture_output=True,
        text=True,
        cwd=project,
        env=env,
        check=False,
    )


def test_clean_tree_satisfies_all_contracts(project_copy: Path):
    result = lint_imports(project_copy)

    assert result.returncode == 0, result.stdout + result.stderr


def test_vendor_sdk_import_in_memory_domain_is_rejected(project_copy: Path):
    offender = project_copy / "src" / "june" / "memory" / "domain" / "bad.py"
    offender.write_text("import anthropic\n", encoding="utf-8")

    result = lint_imports(project_copy)

    assert result.returncode != 0
    assert "june.memory.domain.bad" in result.stdout


def test_same_level_cross_module_import_is_rejected(project_copy: Path):
    offender = project_copy / "src" / "june" / "memory" / "bad.py"
    offender.write_text("from june import llm\n", encoding="utf-8")

    result = lint_imports(project_copy)

    assert result.returncode != 0
    assert "june.memory.bad" in result.stdout
