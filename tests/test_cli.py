"""Smoke tests for the phase-1 command surface."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from basher import __version__


def run_basher(
    *args: object, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run basher through its real module entry point."""
    command = [sys.executable, "-m", "basher", *(str(arg) for arg in args)]
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)


def test_version_and_usage_exit_codes(tmp_path: Path) -> None:
    version = run_basher("--version")
    assert version.returncode == 0
    assert version.stdout.strip() == f"basher {__version__}"

    missing_command = run_basher()
    assert missing_command.returncode == 2

    missing_script = run_basher("vendor", tmp_path / "missing", tmp_path)
    assert missing_script.returncode == 1
    assert "does not exist" in missing_script.stdout


def test_cat_path_and_export(tmp_path: Path) -> None:
    path_result = run_basher("path")
    assert path_result.returncode == 0
    library = Path(path_result.stdout.strip())
    assert library.is_file()

    cat_result = run_basher("cat")
    assert cat_result.returncode == 0
    assert cat_result.stdout == library.read_text()
    syntax = subprocess.run(
        ["bash", "-n"], input=cat_result.stdout, capture_output=True, text=True, check=False
    )
    assert syntax.returncode == 0

    destination = tmp_path / "exported"
    export_result = run_basher("export", destination)
    assert export_result.returncode == 0
    exported = destination / "bugyi.sh"
    assert exported.is_file()
    assert "Vendored by basher" in exported.read_text()
    assert "BUGYI_VERSION" in exported.read_text()


def test_vendor_bundles_library_and_strips_chezmoi_prefix(tmp_path: Path) -> None:
    chezmoi_root = tmp_path / "chezmoi"
    source = chezmoi_root / "home/bin/executable_hello"
    source.parent.mkdir(parents=True)
    source.write_text('#!/bin/bash\nsource ~/lib/bugyi.sh\nprintf "hello\\n"\n')
    # Chezmoi's source file is not executable; the executable_ attribute is
    # materialized only after applying the dotfiles.
    source.chmod(0o644)
    project = tmp_path / "project"
    project.mkdir()

    env = os.environ.copy()
    env["CHEZMOI_SOURCE_ROOT"] = str(chezmoi_root)
    result = run_basher("vendor", source, project, env=env)
    assert result.returncode == 0, result.stdout + result.stderr

    script = project / "tools" / f"hello-{date.today():%y%m%d}"
    library = project / "lib" / f"bugyi-{__version__}.sh"
    assert script.is_file()
    assert library.is_file()
    assert os.access(script, os.X_OK)
    script_content = script.read_text()
    assert script_content.splitlines()[1].startswith(f"# Vendored by basher v{__version__}")
    assert f'../lib/{library.name}"' in script_content
    assert "source ~/lib/bugyi.sh" not in script_content


def test_vendor_defaults_to_enclosing_git_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    nested = project / "nested"
    nested.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", project], check=True)
    source = tmp_path / "outside-script"
    source.write_text("#!/bin/bash\nprintf ok\\n\n")
    source.chmod(0o755)

    result = run_basher("vendor", "--no-lib", source, cwd=nested)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / "tools" / f"outside-script-{date.today():%y%m%d}").is_file()
