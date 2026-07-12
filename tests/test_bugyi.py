"""Behavioral tests for the packaged bugyi.sh library."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from basher.engine import packaged_library


def run_bugyi(command: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Source the real packaged library and run a bash command."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    logger = fake_bin / "logger"
    logger.write_text("#!/bin/bash\ncat >/dev/null\n")
    logger.chmod(0o755)
    env = {
        **os.environ,
        "DISABLE_LOG_COLOR": "true",
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    return subprocess.run(
        ["bash", "-c", 'source "$1" && eval "$2"', "bugyi-test", packaged_library(), command],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_pyprintf_uses_python_style_formatting(tmp_path: Path) -> None:
    result = run_bugyi('pyprintf "{0} {1} {0}" "foo" "bar"', tmp_path)

    assert result.returncode == 0
    assert result.stdout == "foo bar foo"


def test_log_info_includes_level_and_message(tmp_path: Path) -> None:
    result = run_bugyi('log::info "foo bar baz"', tmp_path)

    assert result.returncode == 0
    assert "foo bar baz" in result.stderr
    assert "INFO" in result.stderr


def test_die_honors_explicit_exit_code_and_printf_arguments(tmp_path: Path) -> None:
    result = run_bugyi("die -x 5 'foo bar %s' 'baz'", tmp_path)

    assert result.returncode == 5
    assert "foo bar baz" in result.stderr
    assert "ERROR" in result.stderr
