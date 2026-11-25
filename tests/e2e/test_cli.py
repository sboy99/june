from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_boots_and_reports_persona_length(run_june, tmp_path: Path):
    persona = tmp_path / "SOUL.md"
    persona.write_text("x" * 42, encoding="utf-8")

    result = run_june(JUNE_PERSONA_PATH=str(persona))

    assert result.returncode == 0
    assert result.stdout.strip() == "june 0.1.0 ready (persona: 42 chars)"


def test_fails_fast_with_one_line_error_when_persona_is_missing(run_june, tmp_path: Path):
    missing = tmp_path / "nope" / "SOUL.md"

    result = run_june(JUNE_PERSONA_PATH=str(missing))

    assert result.returncode != 0
    assert result.stdout == ""
    assert str(missing) in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert "Traceback" not in result.stderr


def test_fails_fast_when_persona_is_empty(run_june, tmp_path: Path):
    persona = tmp_path / "SOUL.md"
    persona.write_text("  \n", encoding="utf-8")

    result = run_june(JUNE_PERSONA_PATH=str(persona))

    assert result.returncode != 0
    assert str(persona) in result.stderr
    assert "Traceback" not in result.stderr


def test_default_persona_path_is_resolved_relative_to_working_directory(run_june, tmp_path: Path):
    (tmp_path / "persona").mkdir()
    (tmp_path / "persona" / "SOUL.md").write_text("hello", encoding="utf-8")

    result = run_june()

    assert result.returncode == 0
    assert "persona: 5 chars" in result.stdout
