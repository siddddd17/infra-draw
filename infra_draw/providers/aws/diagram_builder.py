"""AWS-specific diagram builder using the ``diagrams`` library."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import EC2, Lambda as LambdaFn
from diagrams.aws.database import RDS, Dynamodb
from diagrams.aws.network import (
    ALB,
    NLB,
    InternetGateway,
    NATGateway,
    RouteTable,
    TransitGateway,
    VPC as VPCIcon,
    VPCPeering,
    PrivateSubnet,
    PublicSubnet,
)
from diagrams.aws.security import IAMRole
from diagrams.aws.storage import S3

from infra_draw.core.config import InfraDrawConfig
from infra_draw.core.provider import DiagramBuilder
from infra_draw.utils.tags import get_name_tag

logger = logging.getLogger(__name__)


def _label(resource: Dict[str, Any], id_key: str, show_details: bool, extra: str = "") -> str:
    name = get_name_tag(resource, resource.get(id_key, "?"))
    if show_details and extra:
        return f"{name}\n{extra}"
    return name


def _is_public_subnet(subnet: Dict[str, Any], route_tables: List[Dict[str, Any]]) -> bool:
    sid = subnet.get("SubnetId")
    for rt in route_tables:
        if any(a.get("SubnetId") == sid for a in rt.get("Associations", [])):
            if any(r.get("GatewayId", "").startswith("igw-") for r in rt.get("Routes", [])):
                return True
    return False


class AWSDiagramBuilder(DiagramBuilder):
    """Create ``diagrams`` graphs from AWS resource dicts."""

    def build(
        self,
        resources: Dict[str, List[Dict[str, Any]]],
        config: InfraDrawConfig,
        *,
        region: str = "",
        vpc_id: str | None = None,
    ) -> str:
        region_label = region or ", ".join(config.regions)
        title = f"AWS – {region_label}"
        if vpc_id:
            title += f" – {vpc_id}"

        config.output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = title.replace(" ", "_").replace("–", "-")
        filepath = str(config.output_dir / safe_name)

        fmt = config.output_format
        graph_attr = {"fontsize": "14", "bgcolor": "white", "pad": "0.5"}

        with Diagram(
            title,
            show=False,
            direction="TB",
            filename=filepath,
            outformat=fmt,
            graph_attr=graph_attr,
        ):
            self._render(resources, config, vpc_id)

        output_file = f"{filepath}.{fmt}"
        logger.info("Diagram saved → %s", output_file)
        return output_file

    # ------------------------------------------------------------------
    def _render(
        self,
        res: Dict[str, List[Dict[str, Any]]],
        cfg: InfraDrawConfig,
        target_vpc: Optional[str],
    ) -> None:
        vpcs = res.get("vpc", [])
        subnets = res.get("subnet", [])
        rts = res.get("routetable", [])
        igws = res.get("igw", [])
        nats = res.get("natgw", [])
        ec2s = res.get("ec2", [])
        lambdas = res.get("lambda", [])
        albs = res.get("alb", [])
        nlbs = res.get("nlb", [])
        rdss = res.get("rds", [])
        dynamos = res.get("dynamodb", [])
        peerings = res.get("vpc_peering", [])
        tgws = res.get("tgw", [])
        s3s = res.get("s3", [])
        iam_roles = res.get("iam", [])

        detail = cfg.show_details

        # --- per-VPC clusters -----------------------------------------
        vpc_nodes: Dict[str, Any] = {}
        for vpc in vpcs:
            vid = vpc["VpcId"]
            if target_vpc and vid != target_vpc:
                continue
            cidr = vpc.get("CidrBlock", "")
            label = _label(vpc, "VpcId", detail, cidr)
            with Cluster(f"VPC {label}"):
                # IGW for this VPC
                attached_igws = [
                    i for i in igws
                    if any(a.get("VpcId") == vid for a in i.get("Attachments", []))
                ]
                igw_nodes = [
                    InternetGateway(_label(i, "InternetGatewayId", detail))
                    for i in attached_igws
                ]

                # NAT Gateways
                vpc_nats = [n for n in nats if n.get("VpcId") == vid]
                nat_nodes = [NATGateway(_label(n, "NatGatewayId", detail)) for n in vpc_nats]

                # Subnets
                vpc_subnets = [s for s in subnets if s.get("VpcId") == vid]
                for sn in vpc_subnets:
                    is_pub = _is_public_subnet(sn, rts)
                    sn_label = _label(sn, "SubnetId", detail, sn.get("CidrBlock", ""))
                    SubnetCls = PublicSubnet if is_pub else PrivateSubnet
                    sn_node = SubnetCls(sn_label)

                    # EC2 in this subnet
                    for inst in ec2s:
                        if inst.get("SubnetId") == sn.get("SubnetId"):
                            extra = f"{inst.get('InstanceType', '')}\n{inst.get('PrivateIpAddress', '')}"
                            node = EC2(_label(inst, "InstanceId", detail, extra))
                            node >> Edge(color="gray") >> sn_node

                    # Lambda in this subnet
                    for fn in lambdas:
                        fn_subnets = [s for s in (fn.get("VpcConfig") or {}).get("SubnetIds", [])]
                        if sn.get("SubnetId") in fn_subnets:
                            node = LambdaFn(_label(fn, "FunctionName", detail, fn.get("Runtime", "")))
                            node >> Edge(color="orange") >> sn_node

                    # Route Table → subnet associations
                    for rt in rts:
                        for assoc in rt.get("Associations", []):
                            if assoc.get("SubnetId") == sn.get("SubnetId"):
                                rt_node = RouteTable(_label(rt, "RouteTableId", detail))
                                sn_node >> Edge(color="blue", style="dashed") >> rt_node
                                for route in rt.get("Routes", []):
                                    gw = route.get("GatewayId", "")
                                    if gw.startswith("igw-"):
                                        for ig in igw_nodes:
                                            rt_node >> Edge(color="green") >> ig
                                    nat_id = route.get("NatGatewayId", "")
                                    if nat_id:
                                        for nn in nat_nodes:
                                            rt_node >> Edge(color="purple") >> nn

                # ALB / NLB
                for lb in albs:
                    lb_azs = {a.get("SubnetId") for a in lb.get("AvailabilityZones", [])}
                    if lb_azs & {s.get("SubnetId") for s in vpc_subnets}:
                        ALB(_label(lb, "LoadBalancerName", detail, lb.get("DNSName", "")))

                for lb in nlbs:
                    lb_azs = {a.get("SubnetId") for a in lb.get("AvailabilityZones", [])}
                    if lb_azs & {s.get("SubnetId") for s in vpc_subnets}:
                        NLB(_label(lb, "LoadBalancerName", detail, lb.get("DNSName", "")))

                # RDS
                for db in rdss:
                    db_subnets = {
                        s["SubnetIdentifier"]
                        for s in (db.get("DBSubnetGroup") or {}).get("Subnets", [])
                    }
                    if db_subnets & {s.get("SubnetId") for s in vpc_subnets}:
                        extra = f"{db.get('Engine', '')} {db.get('DBInstanceClass', '')}"
                        RDS(_label(db, "DBInstanceIdentifier", detail, extra))

                vpc_nodes[vid] = True

        # --- VPC Peering / TGW (outside VPC clusters) -----------------
        for pc in peerings:
            VPCPeering(pc.get("VpcPeeringConnectionId", "peering"))

        for tg in tgws:
            TransitGateway(_label(tg, "TransitGatewayId", detail))

        # --- DynamoDB (global-ish) ------------------------------------
        for tbl in dynamos:
            Dynamodb(tbl.get("TableName", "table"))

        # --- S3 -------------------------------------------------------
        for bkt in s3s:
            S3(bkt.get("Name", "bucket"))

        # --- IAM (sample up to 10) ------------------------------------
        for role in iam_roles[:10]:
            IAMRole(role.get("RoleName", "role"))
