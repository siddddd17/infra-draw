"""Database fetcher – RDS and DynamoDB."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from infra_draw.core.config import InfraDrawConfig
from infra_draw.core.provider import ResourceFetcher
from infra_draw.utils.tags import filter_resources

logger = logging.getLogger(__name__)


class DatabaseFetcher(ResourceFetcher):
    """Discover RDS instances/clusters and DynamoDB tables."""

    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def resource_types(self) -> List[str]:
        return ["rds", "dynamodb"]

    def fetch(self, config: InfraDrawConfig) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = {}
        for region in config.regions:
            for rtype, items in self._fetch_region(region, config).items():
                result.setdefault(rtype, []).extend(items)
        return result

    def _fetch_region(self, region: str, cfg: InfraDrawConfig) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        if self._w(cfg, "rds"):
            out["rds"] = self._rds(region, cfg)
        if self._w(cfg, "dynamodb"):
            out["dynamodb"] = self._dynamodb(region, cfg)
        return out

    # ---- RDS ---------------------------------------------------------
    def _rds(self, region: str, cfg: InfraDrawConfig) -> List[Dict[str, Any]]:
        try:
            rds = self._session.client("rds", region_name=region)
            paginator = rds.get_paginator("describe_db_instances")
            instances: List[Dict[str, Any]] = []
            for page in paginator.paginate():
                instances.extend(page.get("DBInstances", []))
            # RDS TagList → normalise to Tags
            for inst in instances:
                inst.setdefault("Tags", inst.pop("TagList", []))
                inst["_region"] = region
            instances = filter_resources(instances, cfg.exclude_tags)
            logger.debug("RDS: found %d instances in %s", len(instances), region)
            return instances
        except Exception as exc:
            logger.warning("RDS describe_db_instances failed in %s: %s", region, exc)
            return []

    # ---- DynamoDB ----------------------------------------------------
    def _dynamodb(self, region: str, cfg: InfraDrawConfig) -> List[Dict[str, Any]]:
        try:
            ddb = self._session.client("dynamodb", region_name=region)
            paginator = ddb.get_paginator("list_tables")
            names: List[str] = []
            for page in paginator.paginate():
                names.extend(page.get("TableNames", []))

            tables: List[Dict[str, Any]] = []
            for name in names:
                try:
                    desc = ddb.describe_table(TableName=name)["Table"]
                    arn = desc.get("TableArn", "")
                    tags_resp = ddb.list_tags_of_resource(ResourceArn=arn) if arn else {}
                    desc["Tags"] = [
                        {"Key": t["Key"], "Value": t["Value"]}
                        for t in tags_resp.get("Tags", [])
                    ]
                    desc["_region"] = region
                    tables.append(desc)
                except Exception as inner:
                    logger.warning("DynamoDB describe_table(%s) failed: %s", name, inner)

            tables = filter_resources(tables, cfg.exclude_tags)
            logger.debug("DynamoDB: found %d tables in %s", len(tables), region)
            return tables
        except Exception as exc:
            logger.warning("DynamoDB list_tables failed in %s: %s", region, exc)
            return []

    @staticmethod
    def _w(cfg: InfraDrawConfig, rtype: str) -> bool:
        return not cfg.resource_types or rtype in cfg.resource_types
