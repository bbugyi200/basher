"""Filesystem engine for vendoring shell artifacts."""

from __future__ import annotations

import difflib
import os
import re
import stat
from dataclasses import dataclass, field
from datetime import date
from importlib import metadata, resources
from pathlib import Path

from basher import __version__
from basher.provenance import (
    Provenance,
    display_source,
    insert_provenance,
    make_provenance,
    parse_provenance,
    remove_provenance,
)

BUGYI_SOURCE = "https://github.com/bbugyi200/basher"
HOME_BUGYI_SOURCE_LINE = "source ~/lib/bugyi.sh"


class BasherError(Exception):
    """A user-facing vendoring error."""


@dataclass(frozen=True, slots=True)
class _FileDiff:
    """A unified diff generated for a planned or applied change."""

    path: Path
    text: str


@dataclass(slots=True)
class OperationResult:
    """A summary of filesystem changes performed by an operation."""

    written: list[Path] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)
    rewritten: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    diffs: list[_FileDiff] = field(default_factory=list)
    dry_run: bool = False

    @property
    def changed(self) -> bool:
        """Whether the operation contains filesystem changes."""
        return bool(self.written or self.removed or self.rewritten)

    def merge(self, other: OperationResult) -> None:
        """Merge another result without repeating paths or messages."""
        for path in other.written:
            if path not in self.written:
                self.written.append(path)
        for removed_path in other.removed:
            if removed_path not in self.removed:
                self.removed.append(removed_path)
        for rewritten_path in other.rewritten:
            if rewritten_path not in self.rewritten:
                self.rewritten.append(rewritten_path)
        for warning in other.warnings:
            if warning not in self.warnings:
                self.warnings.append(warning)
        for diff in other.diffs:
            if diff not in self.diffs:
                self.diffs.append(diff)
        self.dry_run = self.dry_run or other.dry_run


@dataclass(frozen=True, slots=True)
class ArtifactStatus:
    """The freshness of one discovered vendored artifact."""

    path: Path
    kind: str
    source: str
    vendored_date: date
    vendored_version: str | None
    latest: str
    state: str
    legacy: bool

    @property
    def stale(self) -> bool:
        return self.state != "current"

    def as_dict(self, project: Path) -> dict[str, object]:
        """Return the stable machine-readable status representation."""
        try:
            artifact = str(self.path.relative_to(project))
        except ValueError:
            artifact = str(self.path)
        return {
            "artifact": artifact,
            "kind": self.kind,
            "source": self.source,
            "vendored_date": self.vendored_date.isoformat(),
            "vendored_version": self.vendored_version,
            "latest": self.latest,
            "state": self.state,
            "legacy": self.legacy,
        }


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
    dry_run: bool = False,
    force: bool = False,
) -> OperationResult:
    """Vendor a script and, when referenced, the packaged bugyi.sh library."""
    source, project = _validate_source_and_project(source, project)
    content = _read_required_text(source)
    script_name = _vendored_basename(source)
    script_suffix = suffix or date.today().strftime("%y%m%d")
    destination_dir = (project / tools_dir).resolve()
    destination = destination_dir / f"{script_name}-{script_suffix}"
    _refuse_self_copy(source, destination)

    stale_scripts = _include_existing(
        _stale_scripts(destination_dir, source.name, script_name), destination
    )
    bundle_library = HOME_BUGYI_SOURCE_LINE in content and not no_lib
    library_destination = (project / lib_dir).resolve() / f"bugyi-{suffix or _package_version()}.sh"
    stale_libraries = (
        _include_existing(_stale_libraries(library_destination.parent), library_destination)
        if bundle_library
        else []
    )
    _validate_removals([*stale_scripts, *stale_libraries], force=force)

    replacements: list[tuple[str, str]] = []
    removals: list[Path] = []
    for path in stale_scripts:
        if path != destination:
            removals.append(path)
            replacements.append((path.name, destination.name))

    writes: dict[Path, tuple[str, int]] = {}
    if bundle_library:
        for path in stale_libraries:
            if path != library_destination:
                removals.append(path)
                replacements.append((path.name, library_destination.name))
        if not _library_is_current(library_destination):
            writes[library_destination] = _library_write()
        relative_lib = Path(os.path.relpath(library_destination.parent, destination_dir)).as_posix()
        new_source = (
            f'source "$(dirname "${{BASH_SOURCE[0]}}")/{relative_lib}/{library_destination.name}"'
        )
        content = content.replace(HOME_BUGYI_SOURCE_LINE, new_source)

    desired_script = insert_provenance(
        content,
        make_provenance(display_source(source), version=_package_version()),
    )
    desired_mode = stat.S_IMODE(source.stat().st_mode) | 0o111
    if not _matches(destination, desired_script, desired_mode):
        writes[destination] = (desired_script, desired_mode)

    return _execute_changes(
        project,
        writes=writes,
        removals=removals,
        replacements=replacements,
        dry_run=dry_run,
    )


def vendor_library(
    project: Path,
    *,
    lib_dir: str = "lib",
    suffix: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> OperationResult:
    """Vendor or refresh the packaged bugyi.sh library in a project."""
    project = _validate_project(project)
    destination_dir = (project / lib_dir).resolve()
    destination = destination_dir / f"bugyi-{suffix or _package_version()}.sh"
    _refuse_self_copy(packaged_library(), destination)
    stale = _include_existing(_stale_libraries(destination_dir), destination)
    _validate_removals(stale, force=force)

    removals = [path for path in stale if path != destination]
    replacements = [(path.name, destination.name) for path in removals]
    writes = {} if _library_is_current(destination) else {destination: _library_write()}
    return _execute_changes(
        project,
        writes=writes,
        removals=removals,
        replacements=replacements,
        dry_run=dry_run,
    )


def export_library(destination_dir: Path) -> OperationResult:
    """Export an unversioned, provenance-bearing bugyi.sh library."""
    destination_dir = destination_dir.expanduser().resolve()
    destination = destination_dir / "bugyi.sh"
    _refuse_self_copy(packaged_library(), destination)
    content, mode = _library_write()
    if _matches(destination, content, mode):
        return OperationResult()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination.write_text(content)
    destination.chmod(mode)
    return OperationResult(written=[destination])


def inspect_project(
    project: Path, *, tools_dir: str = "tools", lib_dir: str = "lib"
) -> list[ArtifactStatus]:
    """Discover vendored artifacts and report their freshness."""
    project = _validate_project(project)
    candidates: set[Path] = set()
    for directory in ((project / tools_dir).resolve(), (project / lib_dir).resolve()):
        if directory.is_dir():
            candidates.update(path for path in directory.iterdir() if path.is_file())

    artifacts: list[ArtifactStatus] = []
    for path in sorted(candidates):
        try:
            content = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        provenance = parse_provenance(content)
        if provenance is None:
            continue
        is_library = bool(re.fullmatch(r"bugyi[_-].*\.sh", path.name))
        artifacts.append(
            _library_status(path, provenance)
            if is_library
            else _script_status(path, provenance, project=project, lib_dir=lib_dir)
        )
    return artifacts


def update_project(
    project: Path,
    *,
    tools_dir: str = "tools",
    lib_dir: str = "lib",
    dry_run: bool = False,
    force: bool = False,
) -> OperationResult:
    """Refresh every stale artifact that has enough provenance to update."""
    project = _validate_project(project)
    statuses = inspect_project(project, tools_dir=tools_dir, lib_dir=lib_dir)
    result = OperationResult(dry_run=dry_run)

    if any(item.kind == "library" and item.stale for item in statuses):
        result.merge(vendor_library(project, lib_dir=lib_dir, dry_run=dry_run, force=force))

    for item in statuses:
        if item.kind != "script" or not item.stale:
            continue
        if item.legacy:
            result.warnings.append(f"{item.path}: legacy script — re-vendor manually")
            continue
        source = Path(item.source).expanduser()
        if not source.is_file():
            result.warnings.append(f"{item.path}: source is unavailable: {item.source}")
            continue
        try:
            no_lib = HOME_BUGYI_SOURCE_LINE in remove_provenance(item.path.read_text())
        except (OSError, UnicodeDecodeError):
            no_lib = False
        result.merge(
            vendor_script(
                source,
                project,
                tools_dir=tools_dir,
                lib_dir=lib_dir,
                no_lib=no_lib,
                dry_run=dry_run,
                force=force,
            )
        )
    return result


def _library_write() -> tuple[str, int]:
    source = packaged_library()
    content = insert_provenance(
        _read_required_text(source),
        make_provenance(BUGYI_SOURCE, version=_package_version()),
    )
    return content, stat.S_IMODE(source.stat().st_mode)


def _library_is_current(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        content = path.read_text()
    except (OSError, UnicodeDecodeError):
        return False
    provenance = parse_provenance(content)
    return bool(
        provenance
        and not provenance.legacy
        and provenance.source == BUGYI_SOURCE
        and provenance.version == _package_version()
        and remove_provenance(content) == _read_required_text(packaged_library())
    )


def _library_status(path: Path, provenance: Provenance) -> ArtifactStatus:
    current = _library_is_current(path)
    return ArtifactStatus(
        path=path,
        kind="library",
        source=BUGYI_SOURCE,
        vendored_date=provenance.vendored_on,
        vendored_version=provenance.version,
        latest=_package_version(),
        state="current" if current else "stale",
        legacy=provenance.legacy,
    )


def _script_status(
    path: Path, provenance: Provenance, *, project: Path, lib_dir: str
) -> ArtifactStatus:
    if provenance.legacy:
        return ArtifactStatus(
            path=path,
            kind="script",
            source=provenance.source,
            vendored_date=provenance.vendored_on,
            vendored_version=None,
            latest="manual",
            state="legacy",
            legacy=True,
        )

    source = Path(provenance.source).expanduser()
    if not source.is_file():
        return ArtifactStatus(
            path=path,
            kind="script",
            source=provenance.source,
            vendored_date=provenance.vendored_on,
            vendored_version=provenance.version,
            latest="unavailable",
            state="missing source",
            legacy=False,
        )

    source_content = _read_required_text(source)
    actual = remove_provenance(_read_required_text(path))
    expected = source_content
    if HOME_BUGYI_SOURCE_LINE in source_content and HOME_BUGYI_SOURCE_LINE not in actual:
        library_dir = (project / lib_dir).resolve()
        library = next(
            (
                candidate
                for candidate in _stale_libraries(library_dir)
                if _library_is_current(candidate)
            ),
            library_dir / f"bugyi-{_package_version()}.sh",
        )
        relative_lib = Path(os.path.relpath(library.parent, path.parent)).as_posix()
        replacement = f'source "$(dirname "${{BASH_SOURCE[0]}}")/{relative_lib}/{library.name}"'
        expected = expected.replace(HOME_BUGYI_SOURCE_LINE, replacement)
    current = actual == expected and os.access(path, os.X_OK)
    latest = date.fromtimestamp(source.stat().st_mtime).isoformat()
    return ArtifactStatus(
        path=path,
        kind="script",
        source=provenance.source,
        vendored_date=provenance.vendored_on,
        vendored_version=provenance.version,
        latest=latest,
        state="current" if current else "stale",
        legacy=False,
    )


def _execute_changes(
    project: Path,
    *,
    writes: dict[Path, tuple[str, int]],
    removals: list[Path],
    replacements: list[tuple[str, str]],
    dry_run: bool,
) -> OperationResult:
    """Apply or preview an operation after computing literal reference rewrites."""
    removals = list(dict.fromkeys(removals))
    planned_writes = dict(writes)
    rewritten_contents: dict[Path, str] = {}

    candidates = [
        path
        for path in project.rglob("*")
        if path.is_file() and not path.is_symlink() and ".git" not in path.parts
    ]
    for path in candidates:
        if path in removals:
            continue
        if path in planned_writes:
            original = planned_writes[path][0]
        else:
            try:
                original = path.read_text()
            except (OSError, UnicodeDecodeError):
                continue
        updated = _replace_literals(original, replacements)
        if updated == original:
            continue
        if path in planned_writes:
            planned_writes[path] = (updated, planned_writes[path][1])
        else:
            rewritten_contents[path] = updated

    result = OperationResult(dry_run=dry_run)
    result.removed.extend(removals)
    result.rewritten.extend(sorted(rewritten_contents))
    for path, (content, mode) in planned_writes.items():
        if not _matches(path, content, mode):
            result.written.append(path)

    for path in result.removed:
        result.diffs.append(_FileDiff(path, _unified_diff(path, _safe_text(path), "")))
    for path in result.written:
        result.diffs.append(
            _FileDiff(path, _unified_diff(path, _safe_text(path), planned_writes[path][0]))
        )
    for path in result.rewritten:
        result.diffs.append(
            _FileDiff(path, _unified_diff(path, _safe_text(path), rewritten_contents[path]))
        )

    if dry_run:
        return result

    for path in removals:
        path.unlink()
    for path in result.written:
        content, mode = planned_writes[path]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(mode)
    for path, content in rewritten_contents.items():
        path.write_text(content)
    return result


def _replace_literals(content: str, replacements: list[tuple[str, str]]) -> str:
    for old_name, new_name in replacements:
        if old_name != new_name:
            content = content.replace(old_name, new_name)
    return content


def _unified_diff(path: Path, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=str(path) if before else "/dev/null",
            tofile=str(path) if after else "/dev/null",
        )
    )


def _safe_text(path: Path) -> str:
    try:
        return path.read_text()
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return ""


def _matches(path: Path, content: str, mode: int) -> bool:
    if not path.is_file():
        return False
    try:
        return path.read_text() == content and stat.S_IMODE(path.stat().st_mode) == mode
    except (OSError, UnicodeDecodeError):
        return False


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


def _include_existing(paths: list[Path], destination: Path) -> list[Path]:
    if destination.is_file() and destination not in paths:
        return sorted([*paths, destination])
    return paths


def _validate_removals(paths: list[Path], *, force: bool) -> None:
    if force:
        return
    for path in paths:
        content = _read_required_text(path)
        if parse_provenance(content) is None:
            raise BasherError(
                f"Refusing to remove or replace {path}: no recognized provenance line "
                "(pass --force to confirm)"
            )
