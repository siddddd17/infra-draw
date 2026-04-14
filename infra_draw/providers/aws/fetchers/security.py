"""Security fetcher – IAM roles and policies (lightweight)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from infra_draw.core.config import InfraDrawConfig
from infra_draw.core.provider import ResourceFetcher

logger = logging.getLogger(__name__)


class SecurityFetcher(ResourceFetcher):
    """Discover IAM roles (global, not region-scoped)."""

    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def resource_types(self) -> List[str]:
        return ["iam"]

    def fetch(self, config: InfraDrawConfig) -> Dict[str, List[Dict[str, Any]]]:
        if not self._w(config, "iam"):
            return {}
        return {"iam": self._iam_roles()}

    def _iam_roles(self) -> List[Dict[str, Any]]:
        try:
            iam = self._session.client("iam")
            paginator = iam.get_paginator("list_roles")
            roles: List[Dict[str, Any]] = []
            for page in paginator.paginate():
                roles.extend(page.get("Roles", []))
            # Attach inline + managed policy counts
            for role in roles:
                role_name = role["RoleName"]
                try:
                    attached = iam.list_attached_role_policies(RoleName=role_name)
                    role["_attached_policies"] = [
                        p["PolicyName"] for p in attached.get("AttachedPolicies", [])
                    ]
                except Exception:
                    role["_attached_policies"] = []
                role["_region"] = "global"
            logger.debug("IAM: found %d roles", len(roles))
            return roles
        except Exception as exc:
            logger.warning("IAM list_roles failed: %s", exc)
            return []

    @staticmethod
    def _w(cfg: InfraDrawConfig, rtype: str) -> bool:
        return not cfg.resource_types or rtype in cfg.resource_types
