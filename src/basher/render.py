"""Rich-backed terminal rendering for basher commands."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from basher.engine import ArtifactStatus, OperationResult


def make_console(*, quiet: bool = False, color: str = "auto") -> Console:
    """Create a console that respects quiet and explicit color modes."""
    force_terminal: bool | None
    if color == "always":
        force_terminal = True
    elif color == "never":
        force_terminal = False
    else:
        force_terminal = None
    return Console(quiet=quiet, force_terminal=force_terminal)


def render_result(console: Console, result: OperationResult) -> None:
    """Render filesystem changes made by or planned for the engine."""
    prefix = "Would " if result.dry_run else ""
    for warning in result.warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")
    for path in result.removed:
        console.print(f"[yellow]−[/yellow] {prefix}remove {_pretty(path)}")
    for path in result.written:
        verb = "write" if result.dry_run else "Vendored"
        console.print(f"[green]✓[/green] {prefix}{verb} {_pretty(path)}")
    for path in result.rewritten:
        verb = "update references in" if result.dry_run else "Updated references in"
        console.print(f"[cyan]↻[/cyan] {prefix}{verb} {_pretty(path)}")
    if not result.changed and not result.warnings:
        console.print("[green]✓[/green] Already up to date")
    if result.dry_run:
        for diff in result.diffs:
            if diff.text:
                console.print(Syntax(diff.text, "diff", theme="ansi_dark", word_wrap=False))


def render_status(console: Console, artifacts: list[ArtifactStatus], project: Path) -> None:
    """Render a project status table."""
    table = Table(title=f"Vendored artifacts in {_pretty(project)}")
    table.add_column("Artifact")
    table.add_column("Kind")
    table.add_column("Vendored")
    table.add_column("Latest")
    table.add_column("State")
    for artifact in artifacts:
        vendored = artifact.vendored_version or artifact.vendored_date.isoformat()
        state_style = "green" if artifact.state == "current" else "yellow"
        try:
            shown_path = artifact.path.relative_to(project)
        except ValueError:
            shown_path = artifact.path
        table.add_row(
            str(shown_path),
            artifact.kind,
            vendored,
            artifact.latest,
            f"[{state_style}]{artifact.state}[/{state_style}]",
        )
    console.print(table)
    if not artifacts:
        console.print("No vendored artifacts found.", style="dim")


def _pretty(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)
