"""Focused smoke tests for cleanup and provenance support."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from basher.engine import BasherError, vendor_library, vendor_script
from basher.provenance import make_provenance, parse_provenance


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
