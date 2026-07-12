"""Tests for layered basher configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from basher.config import ConfigError, discover_project, load_settings


def test_config_precedence(tmp_path: Path) -> None:
    config_home = tmp_path / "config"
    user_config = config_home / "basher/config.toml"
    user_config.parent.mkdir(parents=True)
    user_config.write_text('tools_dir = "user-tools"\nlib_dir = "user-lib"\ncolor = "auto"\n')

    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[tool.basher]\ntools_dir = "project-tools"\ncolor = "never"\n'
    )
    (project / ".basher.toml").write_text('lib_dir = "dot-lib"\n')

    settings = load_settings(
        project,
        tools_dir="cli-tools",
        color="always",
        environ={
            "XDG_CONFIG_HOME": str(config_home),
            "BASHER_TOOLS_DIR": "environment-tools",
            "BASHER_LIB_DIR": "environment-lib",
        },
    )

    assert settings.tools_dir == "cli-tools"
    assert settings.lib_dir == "environment-lib"
    assert settings.color == "always"


def test_no_color_is_overridden_by_explicit_color(tmp_path: Path) -> None:
    settings = load_settings(tmp_path, environ={"NO_COLOR": ""})
    assert settings.color == "never"

    settings = load_settings(tmp_path, color="always", environ={"NO_COLOR": ""})
    assert settings.color == "always"


@pytest.mark.parametrize(
    ("layers", "expected"),
    [
        ((), "tools"),
        (("user",), "user-tools"),
        (("user", "pyproject"), "project-tools"),
        (("user", "pyproject", "dotfile"), "dotfile-tools"),
        (("user", "pyproject", "dotfile", "environment"), "environment-tools"),
        (("user", "pyproject", "dotfile", "environment", "cli"), "cli-tools"),
    ],
)
def test_tools_directory_precedence_matrix(
    tmp_path: Path, layers: tuple[str, ...], expected: str
) -> None:
    config_home = tmp_path / "config"
    project = tmp_path / "project"
    project.mkdir()
    environ = {"XDG_CONFIG_HOME": str(config_home)}
    cli_value = None
    if "user" in layers:
        user = config_home / "basher/config.toml"
        user.parent.mkdir(parents=True)
        user.write_text('tools_dir = "user-tools"\n')
    if "pyproject" in layers:
        (project / "pyproject.toml").write_text('[tool.basher]\ntools_dir = "project-tools"\n')
    if "dotfile" in layers:
        (project / ".basher.toml").write_text('tools_dir = "dotfile-tools"\n')
    if "environment" in layers:
        environ["BASHER_TOOLS_DIR"] = "environment-tools"
    if "cli" in layers:
        cli_value = "cli-tools"

    assert load_settings(project, tools_dir=cli_value, environ=environ).tools_dir == expected


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ('unknown = "value"\n', "Unknown basher configuration"),
        ("tools_dir = 42\n", "must be a string"),
        ('color = "sometimes"\n', "must be one of"),
        ('tools_dir = "/absolute"\n', "non-empty relative path"),
        ('lib_dir = "../outside"\n', "non-empty relative path"),
        ('tools_dir = ""\n', "non-empty relative path"),
        ("not valid toml =\n", "Cannot read configuration"),
    ],
)
def test_invalid_configuration_is_rejected(tmp_path: Path, content: str, message: str) -> None:
    (tmp_path / ".basher.toml").write_text(content)

    with pytest.raises(ConfigError, match=message):
        load_settings(tmp_path, environ={"XDG_CONFIG_HOME": str(tmp_path / "missing")})


def test_nested_dotfile_table_and_environment_color(tmp_path: Path) -> None:
    (tmp_path / ".basher.toml").write_text(
        '[tool.basher]\ntools_dir = "nested-tools"\nlib_dir = "nested-lib"\n'
    )

    settings = load_settings(
        tmp_path,
        environ={"XDG_CONFIG_HOME": str(tmp_path / "missing"), "BASHER_COLOR": "never"},
    )

    assert settings.tools_dir == "nested-tools"
    assert settings.lib_dir == "nested-lib"
    assert settings.color == "never"


def test_discover_project_finds_git_root_or_falls_back(tmp_path: Path) -> None:
    project = tmp_path / "project"
    nested = project / "one/two"
    nested.mkdir(parents=True)
    import subprocess

    subprocess.run(["git", "init", "-q", project], check=True)

    assert discover_project(nested) == project.resolve()
    outside = tmp_path / "outside"
    outside.mkdir()
    assert discover_project(outside) == outside.resolve()
