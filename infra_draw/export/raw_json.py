"""Raw JSON exporter.

Dumps the unfiltered boto3 resource data returned by every fetcher, grouped
by region and resource type.  Useful for downstream analysis, auditing,
importing into other tools, or feeding LLMs for architecture
summarisation.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from infra_draw import __version__
from infra_draw.core.config import InfraDrawConfig

logger = logging.getLogger(__name__)


def _json_default(value: Any) -> Any:
    """JSON fallback that handles datetimes and unknown boto3 values."""
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def export_raw(
    config: InfraDrawConfig,
    regions_data: Dict[str, Dict[str, List[Dict[str, Any]]]],
    account_id: str | None = None,
) -> str:
    """Write a single aggregated raw-JSON file, return its path."""
    config.output_dir.mkdir(parents=True, exist_ok=True)

    total = sum(
        len(items)
        for by_type in regions_data.values()
        for items in by_type.values()
    )

    payload: Dict[str, Any] = {
        "version": "1.0",
        "generator": "infra-draw",
        "generator_version": __version__,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "provider": config.provider,
        "account_id": account_id,
        "profile": config.profile,
        "region_count": len(regions_data),
        "total_resources": total,
        "regions": regions_data,
    }

    filename = f"{config.provider}-raw-all-regions.json"
    dest = config.output_dir / filename
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=_json_default, sort_keys=True)

    logger.info("Raw export saved → %s", dest)
    return str(dest)
