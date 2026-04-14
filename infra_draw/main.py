"""Package entry-point wired to ``pyproject.toml [project.scripts]``."""

from infra_draw.cli.main import cli


def entrypoint() -> None:
    cli(standalone_mode=True)
