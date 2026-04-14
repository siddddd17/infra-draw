"""Interactive setup wizard – guides first-time users through provider
configuration, credential setup, and their first diagram generation.
"""

from __future__ import annotations

import configparser
import logging
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Tuple

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from infra_draw.core import saved_config

logger = logging.getLogger(__name__)

AWS_DOCS_URL = "https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"


# ======================================================================
# AWS CLI installation helpers (one per OS)
# ======================================================================

def _run_quiet(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, capturing output.  Never raises on failure."""
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kwargs)


def _install_aws_cli_macos(console: Console) -> bool:
    if shutil.which("brew"):
        console.print("[cyan]Installing via Homebrew …[/cyan]")
        result = subprocess.run(["brew", "install", "awscli"], check=False)
        if result.returncode == 0:
            console.print("[green]AWS CLI installed successfully.[/green]")
            return True
        console.print("[red]Homebrew installation failed.[/red]")
    else:
        console.print("[yellow]Homebrew not found.[/yellow]")
    console.print(
        "Install manually:\n"
        "  1. Install Homebrew → [link]https://brew.sh[/link]\n"
        "  2. Run: [bold]brew install awscli[/bold]\n"
        f"  Or download directly → [link]{AWS_DOCS_URL}[/link]"
    )
    return False


def _install_aws_cli_linux(console: Console) -> bool:
    console.print("[cyan]Downloading AWS CLI v2 installer …[/cyan]")
    cmds = [
        'curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip',
        "unzip -qo /tmp/awscliv2.zip -d /tmp/aws-cli-install",
        "sudo /tmp/aws-cli-install/aws/install --update",
    ]
    for cmd in cmds:
        console.print(f"  [dim]$ {cmd}[/dim]")
        result = subprocess.run(cmd, shell=True, check=False)
        if result.returncode != 0:
            console.print(f"[red]Command failed (exit {result.returncode}).[/red]")
            console.print(f"Install manually → [link]{AWS_DOCS_URL}[/link]")
            return False
    console.print("[green]AWS CLI installed successfully.[/green]")
    return True


def _install_aws_cli_windows(console: Console) -> bool:
    if shutil.which("winget"):
        console.print("[cyan]Installing via winget …[/cyan]")
        result = subprocess.run(
            ["winget", "install", "--id", "Amazon.AWSCLI", "-e", "--accept-source-agreements"],
            check=False,
        )
        if result.returncode == 0:
            console.print("[green]AWS CLI installed successfully.[/green]")
            return True
        console.print("[red]winget installation failed.[/red]")
    console.print(
        "Install manually:\n"
        f"  Download the MSI → [link]{AWS_DOCS_URL}[/link]\n"
        "  Or run: [bold]winget install --id Amazon.AWSCLI[/bold]"
    )
    return False


# ======================================================================
# AWS profile helpers
# ======================================================================

def _list_aws_profiles() -> List[str]:
    """Return sorted list of configured AWS profile names."""
    profiles: set[str] = set()

    if shutil.which("aws"):
        result = _run_quiet(["aws", "configure", "list-profiles"])
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                name = line.strip()
                if name:
                    profiles.add(name)

    # Fallback: parse files directly
    if not profiles:
        for path in (Path.home() / ".aws" / "credentials", Path.home() / ".aws" / "config"):
            if not path.exists():
                continue
            cp = configparser.ConfigParser()
            cp.read(str(path))
            for section in cp.sections():
                profiles.add(section.removeprefix("profile ").strip())

    return sorted(profiles)


def _write_aws_profile(
    name: str,
    access_key: str,
    secret_key: str,
    region: str,
    output_fmt: str,
) -> None:
    """Write a new profile to ``~/.aws/credentials`` and ``~/.aws/config``."""
    aws_dir = Path.home() / ".aws"
    aws_dir.mkdir(parents=True, exist_ok=True)

    cred_path = aws_dir / "credentials"
    cp = configparser.ConfigParser()
    if cred_path.exists():
        cp.read(str(cred_path))
    cp[name] = {
        "aws_access_key_id": access_key,
        "aws_secret_access_key": secret_key,
    }
    with open(cred_path, "w") as fh:
        cp.write(fh)
    if platform.system() != "Windows":
        cred_path.chmod(0o600)

    cfg_path = aws_dir / "config"
    cp2 = configparser.ConfigParser()
    if cfg_path.exists():
        cp2.read(str(cfg_path))
    section = name if name == "default" else f"profile {name}"
    cp2[section] = {"region": region, "output": output_fmt}
    with open(cfg_path, "w") as fh:
        cp2.write(fh)


def _get_profile_region(profile: str) -> str:
    """Read the default region for *profile* from ``~/.aws/config``."""
    cfg_path = Path.home() / ".aws" / "config"
    if not cfg_path.exists():
        return "us-east-1"
    cp = configparser.ConfigParser()
    cp.read(str(cfg_path))
    section = profile if profile == "default" else f"profile {profile}"
    return cp.get(section, "region", fallback="us-east-1")


def _test_aws_credentials(profile: str) -> Optional[str]:
    """Validate *profile* via STS.  Returns account ID on success, else None."""
    try:
        import boto3
        session = boto3.Session(profile_name=profile)
        identity = session.client("sts").get_caller_identity()
        return identity["Account"]
    except Exception as exc:
        logger.debug("Credential test failed for %s: %s", profile, exc)
        return None


# ======================================================================
# The wizard itself
# ======================================================================

class SetupWizard:
    """Interactive first-run wizard."""

    def __init__(self, console: Console) -> None:
        self.console = console

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def run(self, *, reset: bool = False) -> None:
        if reset:
            saved_config.clear()
            self.console.print("[dim]Saved configuration cleared.[/dim]\n")

        provider = self._choose_provider()
        if provider == "aws":
            self._aws_flow()

    # ------------------------------------------------------------------
    # Provider selection
    # ------------------------------------------------------------------
    def _choose_provider(self) -> str:
        self.console.print("\n[bold]Choose your cloud provider:[/bold]\n")
        self.console.print("  [cyan]1.[/cyan] AWS")
        self.console.print("  [dim]2. GCP  (coming soon)[/dim]")
        self.console.print("  [dim]3. Azure (coming soon)[/dim]")

        choice = Prompt.ask("\nEnter selection", choices=["1", "2", "3"], default="1")
        if choice in ("2", "3"):
            name = "GCP" if choice == "2" else "Azure"
            self.console.print(f"\n[yellow]{name} support is coming soon. Please choose another provider.[/yellow]")
            return self._choose_provider()
        return "aws"

    # ------------------------------------------------------------------
    # Full AWS setup flow
    # ------------------------------------------------------------------
    def _aws_flow(self) -> None:
        self._check_aws_cli()
        profile, region, account_id = self._select_profile()
        if not profile:
            return

        os.environ["AWS_PROFILE"] = profile
        saved_config.save({
            "provider": "aws",
            "profile": profile,
            "region": region,
            "account_id": account_id,
        })
        self.console.print(
            f"\n[bold green]Now using profile: {profile} (account {account_id})[/bold green]"
        )
        self._action_menu(profile, region)

    # ------------------------------------------------------------------
    # Step A – AWS CLI check
    # ------------------------------------------------------------------
    def _check_aws_cli(self) -> None:
        self.console.print("\n[cyan]Checking AWS CLI installation …[/cyan]")

        if shutil.which("aws"):
            result = _run_quiet(["aws", "--version"])
            version = (result.stdout.strip() or result.stderr.strip()).split("\n")[0]
            self.console.print(f"[green]AWS CLI found:[/green] {version}")
            return

        self.console.print("[yellow]AWS CLI is not installed on your system.[/yellow]")
        if not Confirm.ask("Do you want infra-draw to install it for you?", default=True):
            self.console.print("[dim]Skipping — some features may require the AWS CLI.[/dim]")
            return

        system = platform.system()
        self.console.print(f"[cyan]Detected OS: {system}[/cyan]")
        installers = {
            "Darwin": _install_aws_cli_macos,
            "Linux": _install_aws_cli_linux,
            "Windows": _install_aws_cli_windows,
        }
        installer = installers.get(system)
        if installer:
            installer(self.console)
        else:
            self.console.print(f"[red]Unsupported OS ({system}). Install manually → [link]{AWS_DOCS_URL}[/link][/red]")

        if shutil.which("aws"):
            ver = _run_quiet(["aws", "--version"])
            self.console.print(f"[green]Verified:[/green] {(ver.stdout or ver.stderr).strip().splitlines()[0]}")
        else:
            self.console.print("[yellow]AWS CLI still not found on PATH. You may need to restart your terminal.[/yellow]")

    # ------------------------------------------------------------------
    # Step B / C / D – Profile selection or creation
    # ------------------------------------------------------------------
    def _select_profile(self) -> Tuple[Optional[str], str, str]:
        """Guide the user through picking or creating an AWS profile.

        Returns ``(profile, region, account_id)`` or ``(None, "", "")``
        on abort.
        """
        profiles = _list_aws_profiles()

        if profiles:
            self.console.print("\n[bold]Available AWS profiles:[/bold]\n")
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column("#", style="cyan", justify="right")
            table.add_column("Profile")
            for idx, name in enumerate(profiles, 1):
                table.add_row(str(idx), name)
            self.console.print(table)

            raw = Prompt.ask(
                "\nSelect a profile (enter number), or type [bold]new[/bold] to create one",
            )
            if raw.lower() == "new":
                return self._create_profile()

            try:
                idx = int(raw) - 1
                if 0 <= idx < len(profiles):
                    profile = profiles[idx]
                else:
                    raise ValueError
            except ValueError:
                self.console.print("[red]Invalid selection.[/red]")
                return self._select_profile()

            region = _get_profile_region(profile)
            return self._verify_profile(profile, region)
        else:
            self.console.print("\n[yellow]No AWS profiles found.[/yellow]")
            if Confirm.ask("Create a new profile now?", default=True):
                return self._create_profile()
            self.console.print("[dim]Cannot continue without a profile.[/dim]")
            return None, "", ""

    def _create_profile(self) -> Tuple[Optional[str], str, str]:
        self.console.print()
        name = Prompt.ask("Enter profile name", default="default")
        access_key = Prompt.ask("Enter AWS Access Key ID")
        secret_key = Prompt.ask("Enter AWS Secret Access Key", password=True)
        region = Prompt.ask("Default region", default="us-east-1")
        output_fmt = Prompt.ask(
            "Output format",
            choices=["json", "table", "text"],
            default="json",
        )

        self.console.print("\n[cyan]Writing profile …[/cyan]")
        _write_aws_profile(name, access_key, secret_key, region, output_fmt)
        self.console.print(f"[green]Profile [bold]{name}[/bold] saved to ~/.aws/[/green]")

        return self._verify_profile(name, region)

    def _verify_profile(self, profile: str, region: str) -> Tuple[Optional[str], str, str]:
        """Test credentials and return ``(profile, region, account_id)``."""
        self.console.print("\n[cyan]Testing credentials …[/cyan]")
        account_id = _test_aws_credentials(profile)
        if account_id:
            self.console.print(f"[green]Success! Account ID: {account_id}[/green]")
            return profile, region, account_id

        self.console.print("[red]Credential test failed.[/red]")
        if Confirm.ask("Try a different profile?", default=True):
            return self._select_profile()
        return None, "", ""

    # ------------------------------------------------------------------
    # Step E – Action menu
    # ------------------------------------------------------------------
    def _action_menu(self, profile: str, region: str) -> None:
        while True:
            self.console.print("\n[bold]What would you like to do?[/bold]\n")
            self.console.print(f"  [cyan]1.[/cyan] Generate a diagram (all resources in {region})")
            self.console.print("  [cyan]2.[/cyan] Generate a diagram with custom options")
            self.console.print("  [cyan]3.[/cyan] View discovered resources (dry run)")
            self.console.print("  [cyan]4.[/cyan] Change profile / provider")
            self.console.print("  [cyan]5.[/cyan] Exit")

            choice = Prompt.ask("\nEnter selection", choices=["1", "2", "3", "4", "5"])

            if choice == "1":
                self._run_generate(profile=profile, region=region)
            elif choice == "2":
                self._run_generate_custom(profile=profile, default_region=region)
            elif choice == "3":
                self._run_generate(profile=profile, region=region, dry_run=True)
            elif choice == "4":
                return self.run()
            else:
                self.console.print("[dim]Bye![/dim]")
                return

    # ------------------------------------------------------------------
    # Generate helpers (reuse internal engine, not CLI)
    # ------------------------------------------------------------------
    def _run_generate(
        self,
        *,
        profile: str,
        region: str,
        fmt: str = "png",
        resources: Optional[List[str]] = None,
        per_vpc: bool = False,
        show_details: bool = False,
        dry_run: bool = False,
        output_dir: str = "output",
    ) -> None:
        from infra_draw.core.config import InfraDrawConfig
        from infra_draw.core.exceptions import InfraDrawError

        config = InfraDrawConfig(
            provider="aws",
            regions=[region],
            profile=profile,
            resource_types=resources or [],
            per_vpc=per_vpc,
            show_details=show_details,
            output_format=fmt,
            output_dir=Path(output_dir),
            dry_run=dry_run,
        )

        if not config.is_data_format:
            from infra_draw.utils.graphviz_check import ensure_graphviz
            from infra_draw.core.exceptions import GraphvizMissingError
            try:
                ensure_graphviz()
            except GraphvizMissingError as exc:
                self.console.print(f"[bold red]Error:[/bold red] {exc}")
                return

        try:
            import infra_draw.providers  # noqa: F401
            from infra_draw.core.provider import ProviderFactory
            provider = ProviderFactory.get("aws", config)

            if dry_run:
                from infra_draw.diagram.builder import fetch_all
                fetchers = provider.get_fetchers(config)
                result = fetch_all(fetchers, config)
                total = sum(len(v) for v in result.values())
                self.console.print(f"\n[green]Discovered {total} resource(s).[/green]")

                table = Table(title="Resources")
                table.add_column("Type", style="cyan")
                table.add_column("Count", justify="right")
                for rtype, items in sorted(result.items()):
                    table.add_row(rtype, str(len(items)))
                self.console.print(table)
                return

            t0 = time.monotonic()
            if config.is_data_format:
                from infra_draw.diagram.builder import generate_exports
                files = generate_exports(provider, config)
            else:
                from infra_draw.diagram.builder import generate_diagrams
                files = generate_diagrams(provider, config)
            elapsed = time.monotonic() - t0

            label = "export(s)" if config.is_data_format else "diagram(s)"
            if files:
                self.console.print(
                    f"\n[bold green]Done![/bold green]  {len(files)} {label} generated in {elapsed:.1f}s:"
                )
                for f in files:
                    self.console.print(f"  [link=file://{f}]{f}[/link]")
            else:
                self.console.print(f"[yellow]No {label} generated (no resources found).[/yellow]")

        except InfraDrawError as exc:
            self.console.print(f"[bold red]Error:[/bold red] {exc}")
        except Exception as exc:
            self.console.print(f"[bold red]Unexpected error:[/bold red] {exc}")

    def _run_generate_custom(self, *, profile: str, default_region: str) -> None:
        self.console.print()
        region = Prompt.ask("Region", default=default_region)
        res_raw = Prompt.ask("Resource types (comma-separated, or [bold]all[/bold])", default="all")
        resources = (
            [r.strip() for r in res_raw.split(",") if r.strip()]
            if res_raw.lower() != "all"
            else []
        )
        per_vpc = Confirm.ask("Generate per-VPC diagrams?", default=False)
        show_details = Confirm.ask("Show details (IPs, instance types)?", default=False)
        fmt = Prompt.ask(
            "Output format",
            choices=["png", "svg", "pdf", "json", "drawio", "mermaid", "plantuml", "terraform"],
            default="png",
        )
        output_dir = Prompt.ask("Output directory", default="output")

        self._run_generate(
            profile=profile,
            region=region,
            fmt=fmt,
            resources=resources,
            per_vpc=per_vpc,
            show_details=show_details,
            output_dir=output_dir,
        )


# ======================================================================
# Resumption helper (called from main.py when saved config exists)
# ======================================================================

def resume_from_saved(console: Console) -> None:
    """Check for a saved config and either resume or launch the wizard."""
    saved = saved_config.load()
    wizard = SetupWizard(console)

    if saved and saved.get("profile"):
        profile = saved["profile"]
        region = saved.get("region", "us-east-1")
        account = saved.get("account_id", "")

        label = f"[bold]{profile}[/bold]"
        if account:
            label += f" (account {account})"

        if Confirm.ask(f"Use saved profile {label}?", default=True):
            os.environ["AWS_PROFILE"] = profile
            wizard._action_menu(profile, region)
            return

    wizard.run()
