"""Centralised logging bootstrap.

Call ``setup()`` once from the CLI layer; every other module just uses
``logging.getLogger(__name__)``.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def setup(*, verbose: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s" if verbose else "%(message)s"

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    for noisy in ("boto3", "botocore", "urllib3", "s3transfer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
