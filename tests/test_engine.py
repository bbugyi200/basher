"""Focused engine tests for vendoring, cleanup, status, and updates."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from basher import __version__
from basher.engine import (
    BUGYI_SOURCE,
    BasherError,
    OperationResult,
    export_library,
    inspect_project,
    packaged_library,
    update_project,
    vendor_library,
    vendor_script,
)
from basher.provenance import insert_provenance, make_provenance, parse_provenance


def test_provenance_parses_current_and_legacy_formats() -> None:
    current = make_provenance("~/bin/tool", version="0.1.0", today=date(2026, 7, 12))
    parsed = parse_provenance(f"#!/bin/bash\n{current}\n")
    assert parsed is not None
    assert parsed.source == "~/bin/tool"
    assert parsed.version == "0.1.0"
    assert not parsed.legacy

    legacy = parse_provenance(
        "# Vendored from https://github.com/bbugyi200/dotfiles via pyvendor on 2026-02-21"
    )
    assert legacy is not None
    assert legacy.legacy
    assert legacy.version is None


def test_library_refresh_rewrites_literal_references(tmp_path: Path) -> None:
    project = tmp_path / "project"
    library_dir = project / "lib"
    library_dir.mkdir(parents=True)
    old_name = "bugyi-260221.sh"
    (library_dir / old_name).write_text(
        "#!/bin/bash\n"
        "# Vendored from https://github.com/bbugyi200/dotfiles via pyvendor on 2026-02-21\n"
    )
    readme = project / "README.md"
    readme.write_text(f"source lib/{old_name}\n")

    result = vendor_library(project, suffix="0.1.0")
    assert (library_dir / "bugyi-0.1.0.sh").is_file()
    assert old_name not in readme.read_text()
    assert readme in result.rewritten


def test_cleanup_refuses_unknown_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    tools = project / "tools"
    tools.mkdir(parents=True)
    source = tmp_path / "tool"
    source.write_text("#!/bin/bash\n")
    (tools / "tool-260101").write_text("#!/bin/bash\n")

    with pytest.raises(BasherError, match="no recognized provenance"):
        vendor_script(source, project)


def test_update_migrates_legacy_library_and_skips_legacy_script(tmp_path: Path) -> None:
    project = tmp_path / "project"
    library_dir = project / "lib"
    tools_dir = project / "tools"
    library_dir.mkdir(parents=True)
    tools_dir.mkdir()
    provenance = (
        "# Vendored from https://github.com/bbugyi200/dotfiles via pyvendor on 2026-02-21\n"
    )
    old_library = library_dir / "bugyi-260221.sh"
    old_library.write_text(f"#!/bin/bash\n{provenance}")
    legacy_script = tools_dir / "pyscripts-260619"
    legacy_script.write_text(f"#!/usr/bin/env python3\n{provenance}")
    reference = project / "README.md"
    reference.write_text(f"source lib/{old_library.name}\n")

    result = update_project(project)

    assert not old_library.exists()
    current_name = f"bugyi-{__version__}.sh"
    assert (library_dir / current_name).is_file()
    assert current_name in reference.read_text()
    assert legacy_script.is_file()
    assert any("re-vendor manually" in warning for warning in result.warnings)


def test_status_understands_custom_suffix(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = tmp_path / "tool"
    source.write_text("#!/bin/bash\nsource ~/lib/bugyi.sh\n")

    vendor_script(source, project, suffix="snapshot")

    statuses = inspect_project(project)
    assert len(statuses) == 2
    assert all(status.state == "current" for status in statuses)


def test_cleanup_rewrites_literal_names_and_skips_binary_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    tools = project / "tools"
    tools.mkdir(parents=True)
    source = tmp_path / "tool[1]"
    source.write_text("#!/bin/bash\n")
    old_name = "tool[1]-260101"
    old = tools / old_name
    old.write_text(
        insert_provenance("#!/bin/bash\n", make_provenance(str(source), version="0.0.1"))
    )
    reference = project / "reference.txt"
    reference.write_text(f"exact={old_name}\nregex-lookalike=tool1-260101\n")
    binary = project / "binary.dat"
    binary.write_bytes(b"\xff" + old_name.encode())

    result = vendor_script(source, project, suffix="260202")

    assert reference.read_text() == "exact=tool[1]-260202\nregex-lookalike=tool1-260101\n"
    assert binary.read_bytes() == b"\xff" + old_name.encode()
    assert reference in result.rewritten
    assert binary not in result.rewritten


def test_dry_run_previews_cleanup_without_writing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    tools = project / "tools"
    tools.mkdir(parents=True)
    source = tmp_path / "tool"
    source.write_text("#!/bin/bash\nprintf new\n")
    old = tools / "tool-260101"
    old.write_text(insert_provenance("#!/bin/bash\nprintf old\n", make_provenance(str(source))))
    reference = project / "README.md"
    reference.write_text(f"run {old.name}\n")
    before = {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}

    result = vendor_script(source, project, suffix="260202", dry_run=True)

    assert result.dry_run
    assert old in result.removed
    assert tools / "tool-260202" in result.written
    assert reference in result.rewritten
    assert all(diff.text for diff in result.diffs)
    assert {path: path.read_bytes() for path in project.rglob("*") if path.is_file()} == before


def test_export_is_unversioned_idempotent_and_has_provenance(tmp_path: Path) -> None:
    destination_dir = tmp_path / "export"

    first = export_library(destination_dir)
    exported = destination_dir / "bugyi.sh"
    second = export_library(destination_dir)

    assert first.written == [exported]
    assert not second.changed
    assert (
        exported.read_text()
        .splitlines()[1]
        .startswith(f"# Vendored by basher v{__version__} from {BUGYI_SOURCE}")
    )
    assert "BUGYI_VERSION" in exported.read_text()


def test_operation_result_merge_deduplicates_every_field(tmp_path: Path) -> None:
    path = tmp_path / "file"
    left = OperationResult(written=[path], warnings=["warning"])
    right = OperationResult(
        written=[path],
        removed=[path],
        rewritten=[path],
        warnings=["warning"],
        dry_run=True,
    )

    left.merge(right)
    left.merge(right)

    assert left.written == [path]
    assert left.removed == [path]
    assert left.rewritten == [path]
    assert left.warnings == ["warning"]
    assert left.dry_run


def test_status_reports_missing_source_and_ignores_non_artifacts(tmp_path: Path) -> None:
    project = tmp_path / "project"
    tools = project / "tools"
    tools.mkdir(parents=True)
    missing = tmp_path / "missing"
    artifact = tools / "tool-260101"
    artifact.write_text(insert_provenance("#!/bin/bash\n", make_provenance(str(missing))))
    (tools / "ordinary").write_text("not vendored\n")
    (tools / "binary").write_bytes(b"\xff\xfe")

    statuses = inspect_project(project)

    assert len(statuses) == 1
    assert statuses[0].path == artifact
    assert statuses[0].state == "missing source"
    assert statuses[0].latest == "unavailable"
    assert statuses[0].stale


def test_update_warns_when_current_script_source_disappears(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = tmp_path / "tool"
    source.write_text("#!/bin/bash\n")
    vendor_script(source, project)
    source.unlink()

    result = update_project(project)

    assert any("source is unavailable" in warning for warning in result.warnings)


def test_validation_rejects_bad_paths_binary_sources_and_self_copy(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    binary = tmp_path / "binary"
    binary.write_bytes(b"\xff\xfe")

    with pytest.raises(BasherError, match="Expected a text file"):
        vendor_script(binary, project)
    with pytest.raises(BasherError, match="SCRIPT does not exist"):
        vendor_script(tmp_path / "missing", project)
    with pytest.raises(BasherError, match="PROJECT does not exist"):
        vendor_library(tmp_path / "missing-project")

    library = packaged_library()
    with pytest.raises(BasherError, match="onto itself"):
        export_library(library.parent)


def test_vendor_is_idempotent_and_restores_executable_mode(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = tmp_path / "tool"
    source.write_text("#!/bin/bash\n")
    source.chmod(0o600)

    first = vendor_script(source, project)
    second = vendor_script(source, project)

    assert first.changed
    assert not second.changed
    assert first.written[0].stat().st_mode & 0o111
