"""Tests for the saved-config persistence layer and setup wizard helpers."""

from __future__ import annotations

import configparser
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infra_draw.core import saved_config
from infra_draw.cli.setup_wizard import (
    SetupWizard,
    _get_profile_region,
    _list_aws_profiles,
    _write_aws_profile,
)


# ======================================================================
# Saved config persistence
# ======================================================================

class TestSavedConfig:
    def test_save_and_load(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".infra-draw"
        config_file = config_dir / "config.json"
        monkeypatch.setattr(saved_config, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(saved_config, "CONFIG_FILE", config_file)

        assert saved_config.load() is None

        saved_config.save({"provider": "aws", "profile": "prod", "region": "eu-west-1"})
        result = saved_config.load()
        assert result is not None
        assert result["provider"] == "aws"
        assert result["profile"] == "prod"
        assert result["region"] == "eu-west-1"

    def test_clear(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".infra-draw"
        config_file = config_dir / "config.json"
        monkeypatch.setattr(saved_config, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(saved_config, "CONFIG_FILE", config_file)

        saved_config.save({"provider": "aws", "profile": "test"})
        assert saved_config.load() is not None

        saved_config.clear()
        assert saved_config.load() is None

    def test_clear_nonexistent(self, tmp_path, monkeypatch):
        config_file = tmp_path / ".infra-draw" / "config.json"
        monkeypatch.setattr(saved_config, "CONFIG_FILE", config_file)
        saved_config.clear()  # should not raise

    def test_load_corrupt_file(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".infra-draw"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text("not json at all")
        monkeypatch.setattr(saved_config, "CONFIG_FILE", config_file)

        assert saved_config.load() is None

    def test_load_empty_dict(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".infra-draw"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text("{}")
        monkeypatch.setattr(saved_config, "CONFIG_FILE", config_file)

        assert saved_config.load() is None

    def test_get_profile(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".infra-draw"
        config_file = config_dir / "config.json"
        monkeypatch.setattr(saved_config, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(saved_config, "CONFIG_FILE", config_file)

        assert saved_config.get_profile() is None

        saved_config.save({"provider": "aws", "profile": "dev"})
        assert saved_config.get_profile() == "dev"

    def test_get_region(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".infra-draw"
        config_file = config_dir / "config.json"
        monkeypatch.setattr(saved_config, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(saved_config, "CONFIG_FILE", config_file)

        assert saved_config.get_region() is None

        saved_config.save({"provider": "aws", "profile": "dev", "region": "ap-southeast-1"})
        assert saved_config.get_region() == "ap-southeast-1"


# ======================================================================
# AWS profile helpers
# ======================================================================

class TestAWSProfileHelpers:
    def test_write_and_read_profile(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        _write_aws_profile("myprof", "AKIAXXXXXXXX", "secret123", "us-west-2", "json")

        cred_path = tmp_path / ".aws" / "credentials"
        assert cred_path.exists()
        cp = configparser.ConfigParser()
        cp.read(str(cred_path))
        assert cp["myprof"]["aws_access_key_id"] == "AKIAXXXXXXXX"
        assert cp["myprof"]["aws_secret_access_key"] == "secret123"

        cfg_path = tmp_path / ".aws" / "config"
        assert cfg_path.exists()
        cp2 = configparser.ConfigParser()
        cp2.read(str(cfg_path))
        assert cp2["profile myprof"]["region"] == "us-west-2"

    def test_write_default_profile(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_aws_profile("default", "AKIAXXXXXXXX", "secret", "us-east-1", "json")

        cfg_path = tmp_path / ".aws" / "config"
        cp = configparser.ConfigParser()
        cp.read(str(cfg_path))
        assert "default" in cp.sections()
        assert cp["default"]["region"] == "us-east-1"

    def test_get_profile_region_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_aws_profile("staging", "AKIA", "sec", "eu-west-1", "json")

        region = _get_profile_region("staging")
        assert region == "eu-west-1"

    def test_get_profile_region_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert _get_profile_region("nonexistent") == "us-east-1"

    def test_list_profiles_from_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        _write_aws_profile("alpha", "AK", "SK", "us-east-1", "json")
        _write_aws_profile("beta", "AK2", "SK2", "eu-west-1", "json")

        with patch("infra_draw.cli.setup_wizard.shutil.which", return_value=None):
            profiles = _list_aws_profiles()
        assert "alpha" in profiles
        assert "beta" in profiles


# ======================================================================
# Wizard class (unit-level)
# ======================================================================

class TestSetupWizardUnit:
    def test_choose_provider_aws(self, monkeypatch):
        console = MagicMock()
        wizard = SetupWizard(console)

        monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **kw: "1")
        result = wizard._choose_provider()
        assert result == "aws"

    def test_verify_profile_success(self, monkeypatch):
        console = MagicMock()
        wizard = SetupWizard(console)

        monkeypatch.setattr(
            "infra_draw.cli.setup_wizard._test_aws_credentials",
            lambda p: "123456789012",
        )
        profile, region, account = wizard._verify_profile("myprof", "us-east-1")
        assert profile == "myprof"
        assert region == "us-east-1"
        assert account == "123456789012"

    def test_verify_profile_failure_then_abort(self, monkeypatch):
        console = MagicMock()
        wizard = SetupWizard(console)

        monkeypatch.setattr(
            "infra_draw.cli.setup_wizard._test_aws_credentials",
            lambda p: None,
        )
        monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *a, **kw: False)

        profile, region, account = wizard._verify_profile("bad", "us-east-1")
        assert profile is None


# ======================================================================
# CLI integration – setup command is registered
# ======================================================================

class TestCLISetupCommand:
    def test_setup_in_help(self):
        from click.testing import CliRunner
        from infra_draw.cli.main import cli

        result = CliRunner().invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "setup" in result.output

    def test_setup_help(self):
        from click.testing import CliRunner
        from infra_draw.cli.main import cli

        result = CliRunner().invoke(cli, ["setup", "--help"])
        assert result.exit_code == 0
        assert "--reset" in result.output


# ======================================================================
# Config fallback
# ======================================================================

class TestConfigFallback:
    def test_from_cli_uses_saved_profile(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".infra-draw"
        config_file = config_dir / "config.json"
        monkeypatch.setattr(saved_config, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(saved_config, "CONFIG_FILE", config_file)

        saved_config.save({"provider": "aws", "profile": "saved-prof", "region": "ap-south-1"})

        monkeypatch.delenv("AWS_PROFILE", raising=False)

        from infra_draw.core.config import InfraDrawConfig
        cfg = InfraDrawConfig.from_cli(
            provider="aws",
            region=None,
            all_regions=False,
            resources=[],
            output_dir="output",
            format="png",
            per_vpc=False,
            show_details=False,
            exclude_tags=[],
            profile=None,
            verbose=False,
            dry_run=False,
        )
        assert cfg.profile == "saved-prof"
        assert cfg.regions == ["ap-south-1"]

    def test_explicit_profile_overrides_saved(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".infra-draw"
        config_file = config_dir / "config.json"
        monkeypatch.setattr(saved_config, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(saved_config, "CONFIG_FILE", config_file)

        saved_config.save({"provider": "aws", "profile": "saved-prof"})

        monkeypatch.delenv("AWS_PROFILE", raising=False)

        from infra_draw.core.config import InfraDrawConfig
        cfg = InfraDrawConfig.from_cli(profile="explicit-prof")
        assert cfg.profile == "explicit-prof"
