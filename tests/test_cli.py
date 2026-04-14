"""CLI smoke tests using Click's test runner."""

from __future__ import annotations

from click.testing import CliRunner

from infra_draw.cli.main import cli


class TestCLI:
    def test_no_args_shows_banner(self):
        result = CliRunner().invoke(cli, [])
        assert result.exit_code == 0
        assert "Infra" in result.output or "infra-draw" in result.output.lower()

    def test_version_command(self):
        result = CliRunner().invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "1.0.0" in result.output

    def test_help_flag(self):
        result = CliRunner().invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "generate" in result.output
        assert "shell" in result.output
        assert "version" in result.output

    def test_generate_help(self):
        result = CliRunner().invoke(cli, ["generate", "--help"])
        assert result.exit_code == 0
        assert "Discover cloud resources" in result.output
