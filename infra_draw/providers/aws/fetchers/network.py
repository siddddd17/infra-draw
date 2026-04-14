"""Network fetcher – VPC ecosystem resources."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from infra_draw.core.config import InfraDrawConfig
from infra_draw.core.provider import ResourceFetcher
from infra_draw.utils.tags import filter_resources

logger = logging.getLogger(__name__)


class NetworkFetcher(ResourceFetcher):
    """VPC, Subnet, Route Table, IGW, NAT GW, ELB, Peering, Transit Gateway."""

    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def resource_types(self) -> List[str]:
        return ["vpc", "subnet", "routetable", "igw", "natgw", "alb", "nlb", "vpc_peering", "tgw"]

    def fetch(self, config: InfraDrawConfig) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = {}
        for region in config.regions:
            for rtype, items in self._fetch_region(region, config).items():
                result.setdefault(rtype, []).extend(items)
        return result

    def _fetch_region(self, region: str, cfg: InfraDrawConfig) -> Dict[str, List[Dict[str, Any]]]:
        ec2 = self._session.client("ec2", region_name=region)
        elbv2 = self._session.client("elbv2", region_name=region)
        out: Dict[str, List[Dict[str, Any]]] = {}

        if self._w(cfg, "vpc"):
            out["vpc"] = self._vpcs(ec2, region, cfg)
        if self._w(cfg, "subnet"):
            out["subnet"] = self._subnets(ec2, region, cfg)
        if self._w(cfg, "routetable"):
            out["routetable"] = self._route_tables(ec2, region, cfg)
        if self._w(cfg, "igw"):
            out["igw"] = self._igws(ec2, region, cfg)
        if self._w(cfg, "natgw"):
            out["natgw"] = self._nat_gws(ec2, region, cfg)
        if self._w(cfg, "alb") or self._w(cfg, "nlb"):
            out.update(self._load_balancers(elbv2, region, cfg))
        if self._w(cfg, "vpc_peering"):
            out["vpc_peering"] = self._peerings(ec2, region, cfg)
        if self._w(cfg, "tgw"):
            out["tgw"] = self._tgws(ec2, region, cfg)
        return out

    # ---- individual fetchers -----------------------------------------
    def _vpcs(self, ec2: Any, region: str, cfg: InfraDrawConfig) -> List[Dict[str, Any]]:
        try:
            pages = ec2.get_paginator("describe_vpcs").paginate()
            vpcs = [v for p in pages for v in p.get("Vpcs", [])]
            for v in vpcs:
                v["_region"] = region
            return filter_resources(vpcs, cfg.exclude_tags)
        except Exception as e:
            logger.warning("VPC fetch failed in %s: %s", region, e)
            return []

    def _subnets(self, ec2: Any, region: str, cfg: InfraDrawConfig) -> List[Dict[str, Any]]:
        try:
            pages = ec2.get_paginator("describe_subnets").paginate()
            items = [s for p in pages for s in p.get("Subnets", [])]
            for s in items:
                s["_region"] = region
            return filter_resources(items, cfg.exclude_tags)
        except Exception as e:
            logger.warning("Subnet fetch failed in %s: %s", region, e)
            return []

    def _route_tables(self, ec2: Any, region: str, cfg: InfraDrawConfig) -> List[Dict[str, Any]]:
        try:
            pages = ec2.get_paginator("describe_route_tables").paginate()
            items = [rt for p in pages for rt in p.get("RouteTables", [])]
            for rt in items:
                rt["_region"] = region
            return filter_resources(items, cfg.exclude_tags)
        except Exception as e:
            logger.warning("RouteTable fetch failed in %s: %s", region, e)
            return []

    def _igws(self, ec2: Any, region: str, cfg: InfraDrawConfig) -> List[Dict[str, Any]]:
        try:
            pages = ec2.get_paginator("describe_internet_gateways").paginate()
            items = [i for p in pages for i in p.get("InternetGateways", [])]
            for i in items:
                i["_region"] = region
            return filter_resources(items, cfg.exclude_tags)
        except Exception as e:
            logger.warning("IGW fetch failed in %s: %s", region, e)
            return []

    def _nat_gws(self, ec2: Any, region: str, cfg: InfraDrawConfig) -> List[Dict[str, Any]]:
        try:
            pages = ec2.get_paginator("describe_nat_gateways").paginate()
            items = [n for p in pages for n in p.get("NatGateways", [])]
            for n in items:
                n["_region"] = region
            return filter_resources(items, cfg.exclude_tags)
        except Exception as e:
            logger.warning("NAT GW fetch failed in %s: %s", region, e)
            return []

    def _load_balancers(self, elbv2: Any, region: str, cfg: InfraDrawConfig) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {"alb": [], "nlb": []}
        try:
            pages = elbv2.get_paginator("describe_load_balancers").paginate()
            for page in pages:
                for lb in page.get("LoadBalancers", []):
                    lb["_region"] = region
                    lb_type = lb.get("Type", "application")
                    if lb_type == "application" and self._w(cfg, "alb"):
                        out["alb"].append(lb)
                    elif lb_type == "network" and self._w(cfg, "nlb"):
                        out["nlb"].append(lb)
        except Exception as e:
            logger.warning("ELBv2 fetch failed in %s: %s", region, e)
        return out

    def _peerings(self, ec2: Any, region: str, cfg: InfraDrawConfig) -> List[Dict[str, Any]]:
        try:
            resp = ec2.describe_vpc_peering_connections()
            items = resp.get("VpcPeeringConnections", [])
            for i in items:
                i["_region"] = region
            return filter_resources(items, cfg.exclude_tags)
        except Exception as e:
            logger.warning("VPC Peering fetch failed in %s: %s", region, e)
            return []

    def _tgws(self, ec2: Any, region: str, cfg: InfraDrawConfig) -> List[Dict[str, Any]]:
        try:
            pages = ec2.get_paginator("describe_transit_gateways").paginate()
            items = [t for p in pages for t in p.get("TransitGateways", [])]
            for t in items:
                t["_region"] = region
            return filter_resources(items, cfg.exclude_tags)
        except Exception as e:
            logger.warning("Transit GW fetch failed in %s: %s", region, e)
            return []

    @staticmethod
    def _w(cfg: InfraDrawConfig, rtype: str) -> bool:
        return not cfg.resource_types or rtype in cfg.resource_types
