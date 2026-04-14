"""Pre-flight check for the Graphviz ``dot`` binary."""

from __future__ import annotations

import shutil
import subprocess

from infra_draw.core.exceptions import GraphvizMissingError


def ensure_graphviz() -> str:
    """Return the Graphviz version string, or raise ``GraphvizMissingError``."""
    dot = shutil.which("dot")
    if dot is None:
        raise GraphvizMissingError(
            "Graphviz is not installed or 'dot' is not on your PATH.\n"
            "  macOS:   brew install graphviz\n"
            "  Ubuntu:  sudo apt-get install graphviz\n"
            "  Windows: choco install graphviz\n"
            "  Or visit https://graphviz.org/download/"
        )
    result = subprocess.run([dot, "-V"], capture_output=True, text=True)  # noqa: S603
    version = (result.stderr or result.stdout).strip()
    return version
