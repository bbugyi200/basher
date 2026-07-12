"""Rich-backed terminal rendering for basher commands."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from basher.engine import OperationResult


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
    """Render filesystem changes made by the engine."""
    for path in result.removed:
        console.print(f"[yellow]−[/yellow] Removed {_pretty(path)}")
    for path in result.written:
        console.print(f"[green]✓[/green] Vendored {_pretty(path)}")
    for path in result.rewritten:
        console.print(f"[cyan]↻[/cyan] Updated references in {_pretty(path)}")


def _pretty(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)
