"""Filesystem engine for vendoring shell artifacts."""

from __future__ import annotations

import os
import re
import shutil
import stat
from dataclasses import dataclass, field
from datetime import date
from importlib import metadata, resources
from pathlib import Path

from basher import __version__
from basher.provenance import display_source, insert_provenance, make_provenance, parse_provenance

BUGYI_SOURCE = "https://github.com/bbugyi200/basher"
HOME_BUGYI_SOURCE_LINE = "source ~/lib/bugyi.sh"


class BasherError(Exception):
    """A user-facing vendoring error."""


@dataclass(slots=True)
class OperationResult:
    """A summary of filesystem changes performed by an operation."""

    written: list[Path] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)
    rewritten: list[Path] = field(default_factory=list)


def _package_version() -> str:
    """Return the installed basher distribution version."""
    try:
        return metadata.version("basher")
    except metadata.PackageNotFoundError:
        return __version__


def packaged_library() -> Path:
    """Return the filesystem path to the packaged bugyi.sh library."""
    return Path(str(resources.files("basher").joinpath("data/bugyi.sh"))).resolve()


def _vendored_basename(source: Path, *, chezmoi_root: Path | None = None) -> str:
    """Strip chezmoi's executable_ attribute prefix when appropriate."""
    source = source.expanduser().resolve()
    configured_root = os.environ.get("CHEZMOI_SOURCE_ROOT")
    root = (chezmoi_root or Path(configured_root or "~/.local/share/chezmoi")).expanduser()
    try:
        source.relative_to(root.resolve())
    except (FileNotFoundError, ValueError):
        return source.name
    if source.name.startswith("executable_") and len(source.name) > len("executable_"):
        return source.name.removeprefix("executable_")
    return source.name


def vendor_script(
    source: Path,
    project: Path,
    *,
    tools_dir: str = "tools",
    lib_dir: str = "lib",
    no_lib: bool = False,
    suffix: str | None = None,
) -> OperationResult:
    """Vendor a script and, when referenced, the packaged bugyi.sh library."""
    source, project = _validate_source_and_project(source, project)
    content = _read_required_text(source)
    script_name = _vendored_basename(source)
    script_suffix = suffix or date.today().strftime("%y%m%d")
    destination_dir = (project / tools_dir).resolve()
    destination = destination_dir / f"{script_name}-{script_suffix}"
    _refuse_self_copy(source, destination)

    stale_scripts = _stale_scripts(destination_dir, source.name, script_name)
    bundle_library = HOME_BUGYI_SOURCE_LINE in content and not no_lib
    library_destination = (project / lib_dir).resolve() / f"bugyi-{suffix or _package_version()}.sh"
    stale_libraries = _stale_libraries(library_destination.parent) if bundle_library else []
    _validate_removals([*stale_scripts, *stale_libraries])

    result = OperationResult()
    replacements: list[tuple[str, str]] = []
    _remove_stale(stale_scripts, destination.name, result, replacements)
    if bundle_library:
        _remove_stale(stale_libraries, library_destination.name, result, replacements)
        _write_library(library_destination, result)
        relative_lib = Path(os.path.relpath(library_destination.parent, destination_dir)).as_posix()
        new_source = (
            f'source "$(dirname "${{BASH_SOURCE[0]}}")/{relative_lib}/{library_destination.name}"'
        )
        content = content.replace(HOME_BUGYI_SOURCE_LINE, new_source)

    destination_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    destination.write_text(
        insert_provenance(
            content,
            make_provenance(display_source(source), version=_package_version()),
        )
    )
    destination.chmod(stat.S_IMODE(source.stat().st_mode) | 0o111)
    result.written.append(destination)
    result.rewritten.extend(_rewrite_references(project, replacements))
    return result


def vendor_library(
    project: Path,
    *,
    lib_dir: str = "lib",
    suffix: str | None = None,
) -> OperationResult:
    """Vendor or refresh the packaged bugyi.sh library in a project."""
    project = _validate_project(project)
    destination_dir = (project / lib_dir).resolve()
    destination = destination_dir / f"bugyi-{suffix or _package_version()}.sh"
    _refuse_self_copy(packaged_library(), destination)
    stale = _stale_libraries(destination_dir)
    _validate_removals(stale)
    result = OperationResult()
    replacements: list[tuple[str, str]] = []
    _remove_stale(stale, destination.name, result, replacements)
    _write_library(destination, result)
    result.rewritten.extend(_rewrite_references(project, replacements))
    return result


def export_library(destination_dir: Path) -> OperationResult:
    """Export an unversioned, provenance-bearing bugyi.sh library."""
    destination_dir = destination_dir.expanduser().resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "bugyi.sh"
    _refuse_self_copy(packaged_library(), destination)
    _write_library(destination, OperationResult())
    return OperationResult(written=[destination])


def _write_library(destination: Path, result: OperationResult) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = packaged_library()
    content = _read_required_text(source)
    shutil.copy2(source, destination)
    destination.write_text(
        insert_provenance(
            content,
            make_provenance(BUGYI_SOURCE, version=_package_version()),
        )
    )
    result.written.append(destination)


def _validate_source_and_project(source: Path, project: Path) -> tuple[Path, Path]:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise BasherError(f"SCRIPT does not exist or is not a file: {source}")
    return source, _validate_project(project)


def _validate_project(project: Path) -> Path:
    project = project.expanduser().resolve()
    if not project.is_dir():
        raise BasherError(f"PROJECT does not exist or is not a directory: {project}")
    return project


def _refuse_self_copy(source: Path, destination: Path) -> None:
    if source.resolve() == destination.resolve():
        raise BasherError(f"Refusing to vendor a file onto itself: {source}")


def _read_required_text(path: Path) -> str:
    try:
        return path.read_text()
    except UnicodeDecodeError as error:
        raise BasherError(f"Expected a text file, but found binary data: {path}") from error


def _stale_scripts(destination_dir: Path, source_name: str, vendored_name: str) -> list[Path]:
    if not destination_dir.is_dir():
        return []
    basenames = {source_name, vendored_name}
    return sorted(
        path
        for path in destination_dir.iterdir()
        if path.is_file()
        and any(re.fullmatch(rf"{re.escape(name)}-\d{{6}}", path.name) for name in basenames)
    )


def _stale_libraries(destination_dir: Path) -> list[Path]:
    if not destination_dir.is_dir():
        return []
    return sorted(
        path
        for path in destination_dir.iterdir()
        if path.is_file() and re.fullmatch(r"bugyi[_-].*\.sh", path.name)
    )


def _validate_removals(paths: list[Path]) -> None:
    for path in paths:
        content = _read_required_text(path)
        if parse_provenance(content) is None:
            raise BasherError(
                f"Refusing to remove {path}: no recognized provenance line (use --force in phase 2)"
            )


def _remove_stale(
    stale: list[Path],
    replacement_name: str,
    result: OperationResult,
    replacements: list[tuple[str, str]],
) -> None:
    for path in stale:
        replacements.append((path.name, replacement_name))
        path.unlink()
        result.removed.append(path)


def _rewrite_references(project: Path, replacements: list[tuple[str, str]]) -> list[Path]:
    rewritten: list[Path] = []
    for path in project.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        try:
            original = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        updated = original
        for old_name, new_name in replacements:
            if old_name != new_name:
                updated = updated.replace(old_name, new_name)
        if updated != original:
            path.write_text(updated)
            rewritten.append(path)
    return rewritten
