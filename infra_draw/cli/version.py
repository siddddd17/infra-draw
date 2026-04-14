"""``infra-draw version`` command."""

from __future__ import annotations

import click
from rich.console import Console

from infra_draw import __version__

console = Console()


@click.command()
def version() -> None:
    """Show the infra-draw version."""
    console.print(f"[bold]infra-draw[/bold] {__version__}")
