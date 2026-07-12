"""Write and parse basher provenance comments."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from basher import __version__

_BASHER_PATTERN = re.compile(
    r"^# Vendored by basher v(?P<version>\S+) from (?P<source>.+) "
    r"on (?P<date>\d{4}-\d{2}-\d{2})\. Run 'basher update' to refresh\.$"
)
_LEGACY_PATTERN = re.compile(
    r"^# Vendored from https://github\.com/bbugyi200/dotfiles via pyvendor "
    r"on (?P<date>\d{4}-\d{2}-\d{2})$"
)


@dataclass(frozen=True, slots=True)
class Provenance:
    """Parsed provenance attached to a vendored artifact."""

    source: str
    vendored_on: date
    version: str | None
    legacy: bool = False


def make_provenance(source: str, *, version: str = __version__, today: date | None = None) -> str:
    """Return the machine-readable provenance comment for an artifact."""
    vendored_on = today or date.today()
    return (
        f"# Vendored by basher v{version} from {source} on {vendored_on.isoformat()}. "
        "Run 'basher update' to refresh."
    )


def insert_provenance(content: str, provenance: str) -> str:
    """Insert provenance after a shebang, or at the start of a shebang-less file."""
    lines = content.splitlines(keepends=True)
    comment = f"{provenance}\n"
    if lines and lines[0].startswith("#!"):
        lines.insert(1, comment)
    else:
        lines.insert(0, comment)
    return "".join(lines)


def parse_provenance(content: str) -> Provenance | None:
    """Parse basher v2 or legacy pyvendor provenance from file content."""
    for line in content.splitlines()[:5]:
        match = _BASHER_PATTERN.fullmatch(line)
        if match:
            return Provenance(
                source=match.group("source"),
                vendored_on=date.fromisoformat(match.group("date")),
                version=match.group("version"),
            )
        legacy_match = _LEGACY_PATTERN.fullmatch(line)
        if legacy_match:
            return Provenance(
                source="https://github.com/bbugyi200/dotfiles",
                vendored_on=date.fromisoformat(legacy_match.group("date")),
                version=None,
                legacy=True,
            )
    return None


def remove_provenance(content: str) -> str:
    """Remove a recognized provenance line while preserving all other text."""
    lines = content.splitlines(keepends=True)
    for index, line in enumerate(lines[:5]):
        if _BASHER_PATTERN.fullmatch(line.rstrip("\r\n")) or _LEGACY_PATTERN.fullmatch(
            line.rstrip("\r\n")
        ):
            del lines[index]
            break
    return "".join(lines)


def display_source(path: Path) -> str:
    """Render an absolute source path with the current home abbreviated."""
    absolute = path.expanduser().resolve()
    home = Path.home().resolve()
    try:
        relative = absolute.relative_to(home)
    except ValueError:
        return str(absolute)
    return str(Path("~") / relative)
