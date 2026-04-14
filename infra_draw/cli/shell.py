"""``infra-draw shell`` – interactive REPL with prompt_toolkit."""

from __future__ import annotations

import shlex
import sys
from typing import Any, Dict, List, Optional

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.table import Table

from infra_draw import __version__
from infra_draw.cli.main import show_banner
from infra_draw.core.config import InfraDrawConfig
from infra_draw.core.exceptions import InfraDrawError, ProviderError
from infra_draw.utils import logging as log_util

console = Console()

COMMANDS = [
    "generate",
    "set",
    "show",
    "list",
    "help",
    "exit",
    "quit",
]

SET_TARGETS = ["provider", "region", "format", "output-dir", "profile", "per-vpc", "show-details", "verbose"]
LIST_TARGETS = ["resources", "providers", "regions"]


def _build_completer() -> WordCompleter:
    words = list(COMMANDS)
    for t in SET_TARGETS:
        words.append(f"set {t}")
    for t in LIST_TARGETS:
        words.append(f"list {t}")
    return WordCompleter(words, sentence=True)


class ShellState:
    """Mutable session state for the interactive shell."""

    def __init__(self, initial: Dict[str, Any]) -> None:
        self.provider: str = str(initial.get("provider", "aws"))
        self.region: str = str(initial.get("region", "us-east-1"))
        self.profile: Optional[str] = initial.get("profile")  # type: ignore[assignment]
        self.output_dir: str = str(initial.get("output_dir", "output"))
        self.fmt: str = str(initial.get("fmt", "png"))
        self.per_vpc: bool = bool(initial.get("per_vpc", False))
        self.show_details: bool = bool(initial.get("show_details", False))
        self.verbose: bool = bool(initial.get("verbose", False))
        self.exclude_tags: list = list(initial.get("exclude_tags", []))
        self.resources: list = list(initial.get("resources", []))
        self._last_resources: Dict[str, List[Dict[str, Any]]] = {}

    def to_cli_kwargs(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "region": self.region,
            "profile": self.profile,
            "output_dir": self.output_dir,
            "fmt": self.fmt,
            "per_vpc": self.per_vpc,
            "show_details": self.show_details,
            "verbose": self.verbose,
            "exclude_tags": self.exclude_tags,
            "resources": self.resources,
            "all_regions": False,
            "dry_run": False,
        }


def _print_help() -> None:
    table = Table(title="Shell Commands", show_lines=True)
    table.add_column("Command", style="cyan")
    table.add_column("Description")
    table.add_row("generate", "Fetch resources and create diagrams with current settings")
    table.add_row("set provider <aws|azure|gcp>", "Change cloud provider")
    table.add_row("set region <name>", "Change target region")
    table.add_row("set format <png|svg|pdf|json|drawio|mermaid|plantuml|terraform>", "Change output format")
    table.add_row("set output-dir <path>", "Change output directory")
    table.add_row("set profile <name>", "Change AWS CLI profile")
    table.add_row("set per-vpc <on|off>", "Toggle per-VPC diagrams")
    table.add_row("set show-details <on|off>", "Toggle detail labels")
    table.add_row("set verbose <on|off>", "Toggle debug logging")
    table.add_row("show", "Display current settings")
    table.add_row("list resources", "Show last-discovered resources")
    table.add_row("list providers", "Show available providers")
    table.add_row("list regions", "Show available regions")
    table.add_row("help", "Show this table")
    table.add_row("exit / quit", "Leave the shell")
    console.print(table)


def _show_settings(state: ShellState) -> None:
    table = Table(title="Current Settings")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    table.add_row("provider", state.provider)
    table.add_row("region", state.region)
    table.add_row("profile", state.profile or "(default)")
    table.add_row("output-dir", state.output_dir)
    table.add_row("format", state.fmt)
    table.add_row("per-vpc", "on" if state.per_vpc else "off")
    table.add_row("show-details", "on" if state.show_details else "off")
    table.add_row("verbose", "on" if state.verbose else "off")
    table.add_row("exclude-tags", ", ".join(state.exclude_tags) or "(none)")
    table.add_row("resources", ", ".join(state.resources) or "(all)")
    console.print(table)


def _handle_set(state: ShellState, parts: List[str]) -> None:
    if len(parts) < 3:
        console.print("[yellow]Usage: set <key> <value>[/yellow]")
        return
    key, value = parts[1], " ".join(parts[2:])
    if key == "provider":
        if value not in ("aws", "azure", "gcp"):
            console.print("[red]Valid providers: aws, azure, gcp[/red]")
            return
        state.provider = value
    elif key == "region":
        state.region = value
    elif key == "format":
        valid = ("png", "svg", "pdf", "json", "drawio", "mermaid", "plantuml", "terraform")
        if value not in valid:
            console.print(f"[red]Valid formats: {', '.join(valid)}[/red]")
            return
        state.fmt = value
    elif key in ("output-dir", "output_dir"):
        state.output_dir = value
    elif key == "profile":
        state.profile = value
    elif key == "per-vpc":
        state.per_vpc = value.lower() in ("on", "true", "1", "yes")
    elif key == "show-details":
        state.show_details = value.lower() in ("on", "true", "1", "yes")
    elif key == "verbose":
        state.verbose = value.lower() in ("on", "true", "1", "yes")
        log_util.setup(verbose=state.verbose)
    else:
        console.print(f"[red]Unknown setting: {key}[/red]")
        return
    console.print(f"[green]{key} → {value}[/green]")


def _handle_list(state: ShellState, parts: List[str]) -> None:
    target = parts[1] if len(parts) > 1 else ""
    if target == "resources":
        if not state._last_resources:
            console.print("[yellow]No resources cached. Run 'generate' first.[/yellow]")
            return
        table = Table(title="Discovered Resources")
        table.add_column("Type", style="cyan")
        table.add_column("Count", justify="right")
        for rtype, items in sorted(state._last_resources.items()):
            table.add_row(rtype, str(len(items)))
        console.print(table)
    elif target == "providers":
        import infra_draw.providers  # noqa: F401
        from infra_draw.core.provider import ProviderFactory
        console.print(f"[cyan]Available providers:[/cyan] {', '.join(ProviderFactory.available())}")
    elif target == "regions":
        console.print("[cyan]Specify a provider first, then use 'generate --all-regions' to discover.[/cyan]")
    else:
        console.print("[yellow]Usage: list resources | list providers | list regions[/yellow]")


def _handle_generate(state: ShellState) -> None:
    import time
    from infra_draw.core.config import InfraDrawConfig
    from infra_draw.utils.graphviz_check import ensure_graphviz

    config = InfraDrawConfig.from_cli(**state.to_cli_kwargs())

    if not config.is_data_format:
        try:
            ensure_graphviz()
        except Exception as exc:
            console.print(f"[bold red]{exc}[/bold red]")
            return

    flat: list[str] = []
    for entry in config.resource_types:
        flat.extend(t.strip() for t in entry.split(",") if t.strip())
    config.resource_types = flat

    try:
        import infra_draw.providers  # noqa: F401
        from infra_draw.core.provider import ProviderFactory
        from infra_draw.diagram.builder import fetch_all, generate_diagrams, generate_exports

        provider = ProviderFactory.get(config.provider, config)
        console.print("[cyan]Validating credentials …[/cyan]")
        provider.validate_credentials(config)

        t0 = time.monotonic()
        if config.is_data_format:
            files = generate_exports(provider, config)
        else:
            files = generate_diagrams(provider, config)

        # Cache fetched resources for `list resources`
        fetchers = provider.get_fetchers(config)
        state._last_resources = fetch_all(fetchers, config)

        label = "export(s)" if config.is_data_format else "diagram(s)"
        elapsed = time.monotonic() - t0
        if files:
            console.print(f"[bold green]Done![/bold green]  {len(files)} {label} in {elapsed:.1f}s")
            for f in files:
                console.print(f"  {f}")
        else:
            console.print("[yellow]No resources found.[/yellow]")
    except InfraDrawError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
    except Exception as exc:
        console.print(f"[bold red]Unexpected: {exc}[/bold red]")
        if state.verbose:
            console.print_exception()


@click.command()
@click.pass_context
def shell(ctx: click.Context) -> None:
    """Launch an interactive infra-draw session."""
    log_util.setup(verbose=bool(ctx.obj.get("verbose", False)))
    show_banner()
    console.print(f"[dim]infra-draw {__version__} – type 'help' for commands, 'exit' to quit[/dim]\n")

    state = ShellState(ctx.obj)
    session: PromptSession = PromptSession(
        history=InMemoryHistory(),
        completer=_build_completer(),
    )

    while True:
        try:
            line = session.prompt("infra-draw> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye![/dim]")
            break

        if not line:
            continue

        try:
            parts = shlex.split(line)
        except ValueError:
            parts = line.split()

        cmd = parts[0].lower()

        if cmd in ("exit", "quit"):
            console.print("[dim]Bye![/dim]")
            break
        elif cmd == "help":
            _print_help()
        elif cmd == "show":
            _show_settings(state)
        elif cmd == "set":
            _handle_set(state, parts)
        elif cmd == "list":
            _handle_list(state, parts)
        elif cmd == "generate":
            _handle_generate(state)
        else:
            console.print(f"[red]Unknown command: {cmd}[/red] – type 'help'")
