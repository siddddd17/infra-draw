"""Click group, ASCII banner, and top-level options."""

from __future__ import annotations

import click
from rich.console import Console

from infra_draw import __version__

console = Console()

BANNER = r"""
[bold cyan]
  _____        __               _____
 |_   _|      / _|             |  __ \
   | |  _ __ | |_ _ __ __ _   | |  | |_ __ __ ___      __
   | | | '_ \|  _| '__/ _` |  | |  | | '__/ _` \ \ /\ / /
  _| |_| | | | | | | | (_| |  | |__| | | | (_| |\ V  V /
 |_____|_| |_|_| |_|  \__,_|  |_____/|_|  \__,_| \_/\_/
[/bold cyan]
[dim]  infra-draw — turn cloud infrastructure into diagrams[/dim]
"""


def show_banner() -> None:
    console.print(BANNER)


@click.group(invoke_without_command=True)
@click.option("--provider", "-p", default="aws", type=click.Choice(["aws", "azure", "gcp"]), help="Cloud provider.")
@click.option("--region", "-r", default="us-east-1", help="Comma-separated region(s).")
@click.option("--all-regions", is_flag=True, help="Scan every enabled region.")
@click.option(
    "--resources",
    multiple=True,
    help="Resource types to include (e.g. ec2,vpc). Omit for all.",
)
@click.option("--output-dir", "-o", default="output", help="Directory for generated files.")
@click.option("--format", "-f", "fmt", default="png", type=click.Choice(["png", "svg", "pdf"]), help="Image format.")
@click.option("--per-vpc", is_flag=True, help="One diagram per VPC.")
@click.option("--show-details", is_flag=True, help="Show IPs, instance types, etc.")
@click.option("--exclude-tags", multiple=True, help="key=value pairs to exclude.")
@click.option("--profile", default=None, help="AWS CLI profile name.")
@click.option("--verbose", "-v", is_flag=True, help="Debug logging.")
@click.option("--dry-run", is_flag=True, help="Fetch but don't generate diagrams.")
@click.pass_context
def cli(ctx: click.Context, **kwargs: object) -> None:
    """infra-draw – turn cloud infrastructure into diagrams."""
    ctx.ensure_object(dict)
    ctx.obj.update(kwargs)

    if ctx.invoked_subcommand is None:
        show_banner()
        click.echo(ctx.get_help())


# Register sub-commands ------------------------------------------------
from infra_draw.cli.generate import generate  # noqa: E402
from infra_draw.cli.shell import shell  # noqa: E402
from infra_draw.cli.version import version  # noqa: E402

cli.add_command(generate)
cli.add_command(shell)
cli.add_command(version)
