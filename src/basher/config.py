"""Built-in settings and project discovery.

Layered TOML and environment configuration is intentionally added in phase 2.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Settings used by the phase-1 command set."""

    tools_dir: str = "tools"
    lib_dir: str = "lib"
    color: str = "auto"


def discover_project(start: Path | None = None) -> Path:
    """Find the enclosing Git root, falling back to the starting directory."""
    cwd = (start or Path.cwd()).expanduser().resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip()).resolve()
    return cwd
