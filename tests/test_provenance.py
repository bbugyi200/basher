"""Focused tests for the provenance contract."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from basher.provenance import (
    display_source,
    insert_provenance,
    make_provenance,
    parse_provenance,
    remove_provenance,
)


def test_current_provenance_round_trip_with_and_without_shebang() -> None:
    provenance = make_provenance("~/bin/my tool", version="1.2.3", today=date(2026, 7, 12))
    expected = (
        "# Vendored by basher v1.2.3 from ~/bin/my tool on 2026-07-12. "
        "Run 'basher update' to refresh."
    )
    assert provenance == expected

    with_shebang = insert_provenance("#!/bin/bash\nprintf ok\n", provenance)
    without_shebang = insert_provenance("printf ok\n", provenance)
    assert with_shebang.splitlines()[1] == provenance
    assert without_shebang.splitlines()[0] == provenance
    assert remove_provenance(with_shebang) == "#!/bin/bash\nprintf ok\n"
    assert remove_provenance(without_shebang) == "printf ok\n"

    parsed = parse_provenance(with_shebang)
    assert parsed is not None
    assert parsed.source == "~/bin/my tool"
    assert parsed.vendored_on == date(2026, 7, 12)
    assert parsed.version == "1.2.3"
    assert not parsed.legacy


def test_legacy_provenance_and_unrecognized_content() -> None:
    legacy_line = "# Vendored from https://github.com/bbugyi200/dotfiles via pyvendor on 2026-02-21"
    content = f"#!/bin/bash\n{legacy_line}\nprintf ok\n"

    parsed = parse_provenance(content)
    assert parsed is not None
    assert parsed.source == "https://github.com/bbugyi200/dotfiles"
    assert parsed.vendored_on == date(2026, 2, 21)
    assert parsed.version is None
    assert parsed.legacy
    assert remove_provenance(content) == "#!/bin/bash\nprintf ok\n"
    assert parse_provenance("#!/bin/bash\n# not provenance\n") is None
    assert remove_provenance("plain text\n") == "plain text\n"


def test_display_source_abbreviates_only_paths_below_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    inside = tmp_path / "bin/tool"
    outside = Path("/opt/example/tool")

    assert display_source(inside) == "~/bin/tool"
    assert display_source(outside) == str(outside)
