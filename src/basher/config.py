"""Layered configuration and project discovery for basher."""

from __future__ import annotations

import os
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

_KEYS = frozenset({"tools_dir", "lib_dir", "color"})
_COLORS = frozenset({"auto", "always", "never"})


class ConfigError(ValueError):
    """A user-facing configuration error."""


@dataclass(frozen=True, slots=True)
class _Settings:
    """Effective basher settings."""

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


def load_settings(
    project: Path,
    *,
    tools_dir: str | None = None,
    lib_dir: str | None = None,
    color: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> _Settings:
    """Load settings in documented precedence order.

    Precedence is defaults, user TOML, project ``pyproject.toml``, project
    ``.basher.toml``, environment, then explicit CLI values.
    """
    project = project.expanduser().resolve()
    env = os.environ if environ is None else environ
    settings = _Settings()

    config_home = Path(env.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    settings = _apply(settings, _read_config(config_home / "basher/config.toml"))
    settings = _apply(settings, _read_pyproject(project / "pyproject.toml"))
    settings = _apply(settings, _read_config(project / ".basher.toml"))

    environment_values: dict[str, str] = {}
    for key, variable in (
        ("tools_dir", "BASHER_TOOLS_DIR"),
        ("lib_dir", "BASHER_LIB_DIR"),
        ("color", "BASHER_COLOR"),
    ):
        if variable in env:
            environment_values[key] = env[variable]
    if "NO_COLOR" in env and "color" not in environment_values:
        environment_values["color"] = "never"
    settings = _apply(settings, environment_values)

    cli_values = {
        key: value
        for key, value in {"tools_dir": tools_dir, "lib_dir": lib_dir, "color": color}.items()
        if value is not None
    }
    return _apply(settings, cli_values)


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as stream:
            return tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Cannot read configuration {path}: {error}") from error


def _read_config(path: Path) -> dict[str, Any]:
    data = _read_toml(path)
    # Accept [tool.basher] too, while keeping the documented top-level form.
    tool = data.get("tool")
    if isinstance(tool, dict) and isinstance(tool.get("basher"), dict):
        nested = tool["basher"]
        return {**{key: value for key, value in data.items() if key != "tool"}, **nested}
    return data


def _read_pyproject(path: Path) -> dict[str, Any]:
    data = _read_toml(path)
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return {}
    basher = tool.get("basher")
    return basher if isinstance(basher, dict) else {}


def _apply(settings: _Settings, values: Mapping[str, Any]) -> _Settings:
    unknown = set(values) - _KEYS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigError(f"Unknown basher configuration key(s): {names}")

    updates: dict[str, str] = {}
    for key, value in values.items():
        if not isinstance(value, str):
            raise ConfigError(f"Configuration value {key!r} must be a string")
        if key == "color":
            if value not in _COLORS:
                choices = ", ".join(sorted(_COLORS))
                raise ConfigError(f"Configuration value 'color' must be one of: {choices}")
        else:
            _validate_directory(key, value)
        updates[key] = value
    return replace(settings, **updates)


def _validate_directory(key: str, value: str) -> None:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ConfigError(f"Configuration value {key!r} must be a non-empty relative path")
