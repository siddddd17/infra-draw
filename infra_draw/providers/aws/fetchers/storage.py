"""Storage fetcher – S3 buckets."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from infra_draw.core.config import InfraDrawConfig
from infra_draw.core.provider import ResourceFetcher
from infra_draw.utils.tags import filter_resources

logger = logging.getLogger(__name__)


class StorageFetcher(ResourceFetcher):
    """Discover S3 buckets (region-filtered when possible)."""

    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def resource_types(self) -> List[str]:
        return ["s3"]

    def fetch(self, config: InfraDrawConfig) -> Dict[str, List[Dict[str, Any]]]:
        if not self._w(config, "s3"):
            return {}
        return {"s3": self._s3_buckets(config)}

    def _s3_buckets(self, cfg: InfraDrawConfig) -> List[Dict[str, Any]]:
        try:
            s3 = self._session.client("s3")
            buckets = s3.list_buckets().get("Buckets", [])
            enriched: List[Dict[str, Any]] = []

            target_regions = set(cfg.regions)

            for bucket in buckets:
                name = bucket["Name"]
                try:
                    loc = s3.get_bucket_location(Bucket=name)
                    region = loc.get("LocationConstraint") or "us-east-1"
                except Exception:
                    region = "unknown"

                if not cfg.all_regions and region not in target_regions:
                    continue

                try:
                    tag_resp = s3.get_bucket_tagging(Bucket=name)
                    tags = tag_resp.get("TagSet", [])
                except Exception:
                    tags = []

                bucket["Tags"] = tags
                bucket["_region"] = region
                enriched.append(bucket)

            enriched = filter_resources(enriched, cfg.exclude_tags)
            logger.debug("S3: found %d buckets", len(enriched))
            return enriched
        except Exception as exc:
            logger.warning("S3 list_buckets failed: %s", exc)
            return []

    @staticmethod
    def _w(cfg: InfraDrawConfig, rtype: str) -> bool:
        return not cfg.resource_types or rtype in cfg.resource_types
