"""Regression tests ported from chezmoi's pyvendor bashunit suite."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from basher.engine import vendor_script
from basher.provenance import make_provenance


@pytest.fixture
def chezmoi_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "home/.local/share/chezmoi"
    monkeypatch.setenv("CHEZMOI_SOURCE_ROOT", str(root))
    return root


def make_script(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#!/bin/bash\nprintf "hello from %s\\n" "$(basename "$0")"\n')
    path.chmod(0o755)


def old_vendored_script(path: Path) -> None:
    path.write_text(
        f"#!/bin/bash\n{make_provenance('~/bin/tool', version='0.0.1', today=date(2026, 1, 1))}\n"
    )


def test_chezmoi_executable_prefix_is_stripped(chezmoi_root: Path, tmp_path: Path) -> None:
    source = chezmoi_root / "home/bin/executable_foo"
    make_script(source)
    project = tmp_path / "project"
    project.mkdir()

    vendor_script(source, project)

    suffix = f"{date.today():%y%m%d}"
    assert (project / "tools" / f"foo-{suffix}").is_file()
    assert not (project / "tools" / f"executable_foo-{suffix}").exists()


def test_prefix_cleanup_updates_all_old_references(chezmoi_root: Path, tmp_path: Path) -> None:
    source = chezmoi_root / "home/bin/executable_foo"
    make_script(source)
    project = tmp_path / "project"
    tools = project / "tools"
    tools.mkdir(parents=True)
    old_prefixed = tools / "executable_foo-260101"
    old_unprefixed = tools / "foo-260102"
    old_vendored_script(old_prefixed)
    old_vendored_script(old_unprefixed)
    readme = project / "README.md"
    readme.write_text(f"tools/{old_prefixed.name}\ntools/{old_unprefixed.name}\n")

    vendor_script(source, project)

    current = f"foo-{date.today():%y%m%d}"
    assert not old_prefixed.exists()
    assert not old_unprefixed.exists()
    assert (tools / current).is_file()
    assert readme.read_text() == f"tools/{current}\ntools/{current}\n"


def test_other_sources_preserve_their_basenames(chezmoi_root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside/executable_bar"
    make_script(outside)
    outside_project = tmp_path / "outside-project"
    outside_project.mkdir()
    inside = chezmoi_root / "home/bin/baz"
    make_script(inside)
    inside_project = tmp_path / "inside-project"
    inside_project.mkdir()

    vendor_script(outside, outside_project)
    vendor_script(inside, inside_project)

    suffix = f"{date.today():%y%m%d}"
    assert (outside_project / "tools" / f"executable_bar-{suffix}").is_file()
    assert not (outside_project / "tools" / f"bar-{suffix}").exists()
    assert (inside_project / "tools" / f"baz-{suffix}").is_file()
