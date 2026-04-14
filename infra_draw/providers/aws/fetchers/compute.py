"""Compute fetcher – EC2 instances and Lambda functions."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from infra_draw.core.config import InfraDrawConfig
from infra_draw.core.provider import ResourceFetcher
from infra_draw.utils.tags import filter_resources

logger = logging.getLogger(__name__)


class ComputeFetcher(ResourceFetcher):
    """Discover EC2 instances and Lambda functions."""

    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def resource_types(self) -> List[str]:
        return ["ec2", "lambda"]

    # ------------------------------------------------------------------
    def fetch(self, config: InfraDrawConfig) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = {}
        for region in config.regions:
            result.update(self._fetch_region(region, config))
        return result

    def _fetch_region(self, region: str, config: InfraDrawConfig) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}

        if self._want(config, "ec2"):
            out["ec2"] = out.get("ec2", []) + self._ec2_instances(region, config)
        if self._want(config, "lambda"):
            out["lambda"] = out.get("lambda", []) + self._lambda_functions(region, config)
        return out

    # --- EC2 ----------------------------------------------------------
    def _ec2_instances(self, region: str, config: InfraDrawConfig) -> List[Dict[str, Any]]:
        try:
            ec2 = self._session.client("ec2", region_name=region)
            paginator = ec2.get_paginator("describe_instances")
            instances: List[Dict[str, Any]] = []
            for page in paginator.paginate():
                for res in page.get("Reservations", []):
                    instances.extend(res.get("Instances", []))
            instances = filter_resources(instances, config.exclude_tags)
            for inst in instances:
                inst["_region"] = region
            logger.debug("EC2: found %d instances in %s", len(instances), region)
            return instances
        except Exception as exc:
            logger.warning("EC2 describe_instances failed in %s: %s", region, exc)
            return []

    # --- Lambda -------------------------------------------------------
    def _lambda_functions(self, region: str, config: InfraDrawConfig) -> List[Dict[str, Any]]:
        try:
            lam = self._session.client("lambda", region_name=region)
            paginator = lam.get_paginator("list_functions")
            funcs: List[Dict[str, Any]] = []
            for page in paginator.paginate():
                funcs.extend(page.get("Functions", []))
            # Lambda functions expose Tags as a top-level dict, normalise to list
            for fn in funcs:
                raw_tags = fn.get("Tags") or {}
                if isinstance(raw_tags, dict):
                    fn["Tags"] = [{"Key": k, "Value": v} for k, v in raw_tags.items()]
                fn["_region"] = region
            funcs = filter_resources(funcs, config.exclude_tags)
            logger.debug("Lambda: found %d functions in %s", len(funcs), region)
            return funcs
        except Exception as exc:
            logger.warning("Lambda list_functions failed in %s: %s", region, exc)
            return []

    # ------------------------------------------------------------------
    @staticmethod
    def _want(config: InfraDrawConfig, rtype: str) -> bool:
        return not config.resource_types or rtype in config.resource_types
