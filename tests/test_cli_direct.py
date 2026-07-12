"""In-process CLI tests that complement the subprocess smoke suite."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from basher import __version__
from basher.cli import main


@pytest.fixture(autouse=True)
def isolated_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


def test_cat_path_and_export_commands(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main(["--color", "never", "cat"]) == 0
    library_text = capsys.readouterr().out
    assert "BUGYI_VERSION" in library_text

    assert main(["--color", "never", "path"]) == 0
    library_path = Path(capsys.readouterr().out.strip())
    assert library_path.read_text() == library_text

    destination = tmp_path / "export"
    assert main(["--color", "never", "export", str(destination)]) == 0
    assert "Vendored" in capsys.readouterr().out
    assert (destination / "bugyi.sh").is_file()


def test_vendor_status_update_and_quiet_json(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = tmp_path / "tool"
    source.write_text("#!/bin/bash\nprintf one\n")

    assert (
        main(
            [
                "--color",
                "never",
                "--verbose",
                "vendor",
                "--no-lib",
                str(source),
                str(project),
            ]
        )
        == 0
    )
    vendor_output = capsys.readouterr().out
    assert "Project:" in vendor_output
    assert "Vendored" in vendor_output

    assert main(["--color", "never", "status", str(project), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"project", "stale", "artifacts"}
    assert payload["project"] == str(project)
    assert payload["stale"] is False
    assert len(payload["artifacts"]) == 1
    assert set(payload["artifacts"][0]) == {
        "artifact",
        "kind",
        "source",
        "vendored_date",
        "vendored_version",
        "latest",
        "state",
        "legacy",
    }

    assert main(["--quiet", "status", str(project), "--json"]) == 0
    assert capsys.readouterr().out == ""

    source.write_text("#!/bin/bash\nprintf two\n")
    assert main(["--color", "never", "status", str(project)]) == 3
    assert "stale" in capsys.readouterr().out
    assert main(["--color", "never", "update", str(project)]) == 0
    assert "Vendored" in capsys.readouterr().out


def test_library_command_dry_run_and_already_current(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    assert main(["--color", "never", "lib", "--dry-run", str(project)]) == 0
    preview = capsys.readouterr().out
    assert "Would write" in preview
    assert not (project / "lib").exists()

    assert main(["--color", "never", "lib", str(project)]) == 0
    assert "Vendored" in capsys.readouterr().out
    assert main(["--color", "never", "lib", str(project)]) == 0
    assert "Already up to date" in capsys.readouterr().out


def test_empty_status_and_user_facing_errors(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    assert main(["--color", "never", "status", str(project)]) == 0
    assert "No vendored artifacts found" in capsys.readouterr().out

    assert main(["--color", "never", "vendor", str(tmp_path / "missing"), str(project)]) == 1
    assert "Error:" in capsys.readouterr().out

    (project / ".basher.toml").write_text('color = "invalid"\n')
    assert main(["status", str(project)]) == 1
    assert "must be one of" in capsys.readouterr().out


def test_version_parser_action(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--version"])

    assert error.value.code == 0
    assert capsys.readouterr().out.strip() == f"basher {__version__}"


def test_status_json_date_and_version_types(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = tmp_path / "tool"
    source.write_text("#!/bin/bash\n")
    assert main(["vendor", "--no-lib", str(source), str(project)]) == 0
    capsys.readouterr()

    assert main(["status", str(project), "--json"]) == 0
    artifact = json.loads(capsys.readouterr().out)["artifacts"][0]
    assert artifact["vendored_date"] == date.today().isoformat()
    assert artifact["vendored_version"] == __version__
