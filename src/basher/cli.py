"""Command-line interface for basher."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from collections.abc import Sequence

from basher import __version__
from basher.config import Settings, discover_project
from basher.engine import (
    BasherError,
    export_library,
    packaged_library,
    vendor_library,
    vendor_script,
)
from basher.render import make_console, render_result


def _build_parser() -> argparse.ArgumentParser:
    """Build the basher argument parser."""
    defaults = Settings()
    parser = argparse.ArgumentParser(
        prog="basher",
        description="Vendor shell scripts and the bugyi.sh library.",
    )
    parser.add_argument("--version", action="version", version=f"basher {__version__}")
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("-v", "--verbose", action="count", default=0)
    verbosity.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    commands = parser.add_subparsers(dest="command", required=True)

    vendor = commands.add_parser("vendor", help="Vendor a script into a project")
    vendor.add_argument("script", type=Path)
    vendor.add_argument("project", type=Path, nargs="?")
    vendor.add_argument("-t", "--tools-dir", default=defaults.tools_dir)
    vendor.add_argument("-l", "--lib-dir", default=defaults.lib_dir)
    vendor.add_argument("--no-lib", action="store_true")
    vendor.add_argument("--suffix")

    library = commands.add_parser("lib", help="Vendor or refresh bugyi.sh")
    library.add_argument("project", type=Path, nargs="?")
    library.add_argument("-l", "--lib-dir", default=defaults.lib_dir)
    library.add_argument("--suffix")

    commands.add_parser("cat", help="Print the packaged bugyi.sh")
    commands.add_parser("path", help="Print the packaged bugyi.sh path")

    export = commands.add_parser("export", help="Export unversioned bugyi.sh")
    export.add_argument("destination", type=Path, nargs="?", default=Path("~/lib"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return a process exit code."""
    args = _build_parser().parse_args(argv)
    console = make_console(quiet=args.quiet, color=args.color)
    try:
        if args.command == "cat":
            sys.stdout.write(packaged_library().read_text())
        elif args.command == "path":
            print(packaged_library())
        elif args.command == "export":
            render_result(console, export_library(args.destination))
        elif args.command == "lib":
            project = args.project or discover_project()
            render_result(
                console,
                vendor_library(project, lib_dir=args.lib_dir, suffix=args.suffix),
            )
        elif args.command == "vendor":
            project = args.project or discover_project()
            render_result(
                console,
                vendor_script(
                    args.script,
                    project,
                    tools_dir=args.tools_dir,
                    lib_dir=args.lib_dir,
                    no_lib=args.no_lib,
                    suffix=args.suffix,
                ),
            )
    except (BasherError, OSError) as error:
        console.print(f"[red]Error:[/red] {error}", style="red")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
