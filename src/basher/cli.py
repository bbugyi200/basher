"""Command-line interface for basher."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from rich.console import Console

from basher import __version__
from basher.config import ConfigError, discover_project, load_settings
from basher.engine import (
    BasherError,
    export_library,
    inspect_project,
    packaged_library,
    update_project,
    vendor_library,
    vendor_script,
)
from basher.render import make_console, render_result, render_status


def _build_parser() -> argparse.ArgumentParser:
    """Build the basher argument parser."""
    parser = argparse.ArgumentParser(
        prog="basher",
        description="Vendor shell scripts and the bugyi.sh library.",
    )
    parser.add_argument("--version", action="version", version=f"basher {__version__}")
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("-v", "--verbose", action="count", default=0)
    verbosity.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--color", choices=("auto", "always", "never"), default=None)
    commands = parser.add_subparsers(dest="command", required=True)

    vendor = commands.add_parser("vendor", help="Vendor a script into a project")
    vendor.add_argument("script", type=Path)
    vendor.add_argument("project", type=Path, nargs="?")
    _add_directory_options(vendor, tools=True, library=True)
    vendor.add_argument("--no-lib", action="store_true")
    vendor.add_argument("--suffix")
    _add_mutation_options(vendor)

    library = commands.add_parser("lib", help="Vendor or refresh bugyi.sh")
    library.add_argument("project", type=Path, nargs="?")
    _add_directory_options(library, library=True)
    library.add_argument("--suffix")
    _add_mutation_options(library)

    update = commands.add_parser("update", help="Refresh all vendored artifacts")
    update.add_argument("project", type=Path, nargs="?")
    _add_directory_options(update, tools=True, library=True)
    _add_mutation_options(update)

    status = commands.add_parser("status", help="Show vendored artifact freshness")
    status.add_argument("project", type=Path, nargs="?")
    _add_directory_options(status, tools=True, library=True)
    status.add_argument("--json", action="store_true", dest="as_json")

    commands.add_parser("cat", help="Print the packaged bugyi.sh")
    commands.add_parser("path", help="Print the packaged bugyi.sh path")

    export = commands.add_parser("export", help="Export unversioned bugyi.sh")
    export.add_argument("destination", type=Path, nargs="?", default=Path("~/lib"))
    return parser


def _add_directory_options(
    parser: argparse.ArgumentParser, *, tools: bool = False, library: bool = False
) -> None:
    if tools:
        parser.add_argument("-t", "--tools-dir", default=None)
    if library:
        parser.add_argument("-l", "--lib-dir", default=None)


def _add_mutation_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-n", "--dry-run", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replacing files without recognized provenance",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return a process exit code."""
    args = _build_parser().parse_args(argv)
    project_argument = getattr(args, "project", None)
    project = (project_argument or discover_project()).expanduser().resolve()

    try:
        settings = load_settings(
            project,
            tools_dir=getattr(args, "tools_dir", None),
            lib_dir=getattr(args, "lib_dir", None),
            color=args.color,
        )
    except ConfigError as error:
        make_console(quiet=False, color=args.color or "auto").print(
            f"[red]Error:[/red] {error}", style="red"
        )
        return 1

    console = make_console(quiet=args.quiet, color=settings.color)
    error_console = make_console(quiet=False, color=settings.color)
    try:
        if args.command == "cat":
            sys.stdout.write(packaged_library().read_text())
        elif args.command == "path":
            print(packaged_library())
        elif args.command == "export":
            render_result(console, export_library(args.destination))
        elif args.command == "status":
            artifacts = inspect_project(
                project, tools_dir=settings.tools_dir, lib_dir=settings.lib_dir
            )
            if args.as_json:
                payload = {
                    "project": str(project),
                    "stale": any(artifact.stale for artifact in artifacts),
                    "artifacts": [artifact.as_dict(project) for artifact in artifacts],
                }
                if not args.quiet:
                    print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                render_status(console, artifacts, project)
            return 3 if any(artifact.stale for artifact in artifacts) else 0
        elif args.command == "update":
            _render_debug(console, args.verbose, project, settings.tools_dir, settings.lib_dir)
            render_result(
                console,
                update_project(
                    project,
                    tools_dir=settings.tools_dir,
                    lib_dir=settings.lib_dir,
                    dry_run=args.dry_run,
                    force=args.force,
                ),
            )
        elif args.command == "lib":
            _render_debug(console, args.verbose, project, settings.tools_dir, settings.lib_dir)
            render_result(
                console,
                vendor_library(
                    project,
                    lib_dir=settings.lib_dir,
                    suffix=args.suffix,
                    dry_run=args.dry_run,
                    force=args.force,
                ),
            )
        elif args.command == "vendor":
            _render_debug(console, args.verbose, project, settings.tools_dir, settings.lib_dir)
            render_result(
                console,
                vendor_script(
                    args.script,
                    project,
                    tools_dir=settings.tools_dir,
                    lib_dir=settings.lib_dir,
                    no_lib=args.no_lib,
                    suffix=args.suffix,
                    dry_run=args.dry_run,
                    force=args.force,
                ),
            )
    except (BasherError, OSError) as error:
        error_console.print(f"[red]Error:[/red] {error}", style="red")
        return 1
    return 0


def _render_debug(
    console: Console, verbose: int, project: Path, tools_dir: str, lib_dir: str
) -> None:
    if verbose:
        console.print(
            f"Project: {project}\nTools directory: {tools_dir}\nLibrary directory: {lib_dir}",
            style="dim",
        )


if __name__ == "__main__":
    raise SystemExit(main())
