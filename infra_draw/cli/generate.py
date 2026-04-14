"""``infra-draw generate`` command – the main workhorse."""

from __future__ import annotations

import sys
import time

import click
from rich.console import Console

from infra_draw.core.config import InfraDrawConfig
from infra_draw.core.exceptions import (
    CredentialsError,
    DiagramError,
    GraphvizMissingError,
    InfraDrawError,
    PermissionError_,
    ProviderError,
)
from infra_draw.utils import logging as log_util
from infra_draw.utils.graphviz_check import ensure_graphviz

console = Console()


@click.command()
@click.pass_context
def generate(ctx: click.Context) -> None:
    """Discover cloud resources and generate architecture diagrams."""
    opts = ctx.obj
    verbose = bool(opts.get("verbose", False))
    log_util.setup(verbose=verbose)

    # --- pre-flight checks -------------------------------------------
    try:
        gv_version = ensure_graphviz()
        if verbose:
            console.print(f"[dim]Graphviz: {gv_version}[/dim]")
    except GraphvizMissingError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    # --- build config -------------------------------------------------
    config = InfraDrawConfig.from_cli(**opts)

    # Flatten comma-separated --resources into a single list
    flat: list[str] = []
    for entry in config.resource_types:
        flat.extend(t.strip() for t in entry.split(",") if t.strip())
    config.resource_types = flat

    # --- resolve provider ---------------------------------------------
    try:
        import infra_draw.providers  # noqa: F401 – trigger registration
        from infra_draw.core.provider import ProviderFactory

        provider = ProviderFactory.get(config.provider, config)
    except ProviderError as exc:
        console.print(f"[bold red]Provider error:[/bold red] {exc}")
        sys.exit(1)

    # --- validate credentials ----------------------------------------
    try:
        console.print("[cyan]Validating credentials …[/cyan]")
        provider.validate_credentials(config)
    except CredentialsError as exc:
        console.print(f"[bold red]Credentials error:[/bold red]\n{exc}")
        sys.exit(1)
    except PermissionError_ as exc:
        console.print(f"[bold red]Permission error:[/bold red]\n{exc}")
        sys.exit(1)

    # --- discover regions if --all-regions ----------------------------
    if config.all_regions:
        config.regions = provider.list_regions(config)
        console.print(f"[cyan]Scanning {len(config.regions)} region(s): {', '.join(config.regions)}[/cyan]")
    else:
        console.print(f"[cyan]Region(s): {', '.join(config.regions)}[/cyan]")

    # --- fetch & build ------------------------------------------------
    t0 = time.monotonic()
    try:
        from infra_draw.diagram.builder import generate_diagrams

        if config.dry_run:
            from infra_draw.diagram.builder import fetch_all

            fetchers = provider.get_fetchers(config)
            resources = fetch_all(fetchers, config)
            console.print("[yellow]Dry run – diagrams not generated.[/yellow]")
            total = sum(len(v) for v in resources.values())
            console.print(f"[green]Discovered {total} resource(s).[/green]")
            return

        files = generate_diagrams(provider, config)
    except InfraDrawError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        if verbose:
            console.print_exception()
        sys.exit(1)

    elapsed = time.monotonic() - t0
    console.print()
    if files:
        console.print(f"[bold green]Done![/bold green]  {len(files)} diagram(s) generated in {elapsed:.1f}s:")
        for f in files:
            console.print(f"  [link=file://{f}]{f}[/link]")
    else:
        console.print("[yellow]No diagrams generated (no resources found).[/yellow]")
