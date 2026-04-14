"""Persistent user config stored at ``~/.infra-draw/config.json``.

Remembers the last-used provider, profile, region, and account so that
``infra-draw`` (no arguments) can skip the setup wizard on subsequent runs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".infra-draw"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load() -> Optional[Dict[str, Any]]:
    """Return the saved config dict, or *None* if absent / corrupt."""
    if not CONFIG_FILE.exists():
        return None
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("provider"):
            return data
        return None
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("Could not read saved config: %s", exc)
        return None


def save(data: Dict[str, Any]) -> None:
    """Write *data* to the persistent config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    logger.debug("Saved config → %s", CONFIG_FILE)


def clear() -> None:
    """Remove the saved config so the next run triggers setup."""
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
        logger.debug("Cleared saved config")


def get_profile() -> Optional[str]:
    cfg = load()
    return cfg.get("profile") if cfg else None


def get_region() -> Optional[str]:
    cfg = load()
    return cfg.get("region") if cfg else None
