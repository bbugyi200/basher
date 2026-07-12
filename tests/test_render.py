"""Tests for Rich-backed terminal rendering."""

from __future__ import annotations

from datetime import date
from io import StringIO
from pathlib import Path

from rich.console import Console

from basher.engine import ArtifactStatus, OperationResult
from basher.render import make_console, render_result, render_status


def test_make_console_color_and_quiet_modes() -> None:
    assert make_console(color="always")._force_terminal is True
    assert make_console(color="never")._force_terminal is False
    assert make_console(color="auto")._force_terminal is None
    assert make_console(quiet=True).quiet


def test_render_result_includes_every_operation_kind(tmp_path: Path) -> None:
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=120)
    result = OperationResult(
        written=[tmp_path / "written"],
        removed=[tmp_path / "removed"],
        rewritten=[tmp_path / "rewritten"],
        warnings=["manual action needed"],
        dry_run=True,
    )

    render_result(console, result)

    rendered = output.getvalue()
    assert "Warning: manual action needed" in rendered
    assert "Would remove" in rendered
    assert "Would write" in rendered
    assert "Would update references in" in rendered


def test_render_result_reports_noop() -> None:
    output = StringIO()
    render_result(Console(file=output, force_terminal=False), OperationResult())
    assert "Already up to date" in output.getvalue()


def test_render_status_handles_relative_and_external_paths(tmp_path: Path) -> None:
    output = StringIO()
    project = tmp_path / "project"
    project.mkdir()
    artifacts = [
        ArtifactStatus(
            path=project / "tools/current",
            kind="script",
            source="~/bin/current",
            vendored_date=date(2026, 7, 12),
            vendored_version="0.1.0",
            latest="2026-07-12",
            state="current",
            legacy=False,
        ),
        ArtifactStatus(
            path=tmp_path / "external",
            kind="library",
            source="https://example.com",
            vendored_date=date(2026, 2, 21),
            vendored_version=None,
            latest="0.1.0",
            state="stale",
            legacy=True,
        ),
    ]

    render_status(Console(file=output, force_terminal=False, width=160), artifacts, project)

    rendered = output.getvalue()
    assert "tools/current" in rendered
    assert str(tmp_path / "external") in rendered
    assert "2026-02-21" in rendered
    assert "current" in rendered
    assert "stale" in rendered
