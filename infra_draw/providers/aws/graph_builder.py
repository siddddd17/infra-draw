"""Build a canonical InfraGraph from AWS resource dicts.

Mirrors the topology extraction logic in ``AWSDiagramBuilder._render`` so that
every data-format exporter sees exactly the same nodes, edges, and clusters
that the image renderer would produce.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from infra_draw.core.config import InfraDrawConfig
from infra_draw.export.graph import GraphCluster, GraphEdge, GraphNode, InfraGraph
from infra_draw.utils.tags import get_name_tag

logger = logging.getLogger(__name__)

RESOURCE_TYPE_TO_AWS_TYPE = {
    "vpc": "AWS::EC2::VPC",
    "subnet": "AWS::EC2::Subnet",
    "igw": "AWS::EC2::InternetGateway",
    "natgw": "AWS::EC2::NatGateway",
    "routetable": "AWS::EC2::RouteTable",
    "ec2": "AWS::EC2::Instance",
    "lambda": "AWS::Lambda::Function",
    "alb": "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "nlb": "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "rds": "AWS::RDS::DBInstance",
    "dynamodb": "AWS::DynamoDB::Table",
    "s3": "AWS::S3::Bucket",
    "iam": "AWS::IAM::Role",
    "vpc_peering": "AWS::EC2::VPCPeeringConnection",
    "tgw": "AWS::EC2::TransitGateway",
}

TERRAFORM_TYPE_MAP = {
    "vpc": "aws_vpc",
    "subnet": "aws_subnet",
    "igw": "aws_internet_gateway",
    "natgw": "aws_nat_gateway",
    "routetable": "aws_route_table",
    "ec2": "aws_instance",
    "lambda": "aws_lambda_function",
    "alb": "aws_lb",
    "nlb": "aws_lb",
    "rds": "aws_db_instance",
    "dynamodb": "aws_dynamodb_table",
    "s3": "aws_s3_bucket",
    "iam": "aws_iam_role",
    "vpc_peering": "aws_vpc_peering_connection",
    "tgw": "aws_ec2_transit_gateway",
}

ID_KEY_MAP = {
    "vpc": "VpcId",
    "subnet": "SubnetId",
    "igw": "InternetGatewayId",
    "natgw": "NatGatewayId",
    "routetable": "RouteTableId",
    "ec2": "InstanceId",
    "lambda": "FunctionName",
    "alb": "LoadBalancerName",
    "nlb": "LoadBalancerName",
    "rds": "DBInstanceIdentifier",
    "dynamodb": "TableName",
    "s3": "Name",
    "iam": "RoleName",
    "vpc_peering": "VpcPeeringConnectionId",
    "tgw": "TransitGatewayId",
}


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


def _tags_dict(resource: Dict[str, Any]) -> Dict[str, str]:
    return {t["Key"]: t.get("Value", "") for t in (resource.get("Tags") or [])}


def _node_id(resource_type: str, resource: Dict[str, Any]) -> str:
    """Stable unique identifier for a resource node."""
    id_key = ID_KEY_MAP.get(resource_type, "")
    raw = resource.get(id_key, "")
    if raw:
        return raw
    return f"{resource_type}-{id(resource)}"


def _make_node(
    resource_type: str,
    resource: Dict[str, Any],
    label: str,
    cluster_id: Optional[str] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> GraphNode:
    meta: Dict[str, Any] = {
        "region": resource.get("_region", ""),
        "tags": _tags_dict(resource),
    }
    if extra_meta:
        meta.update(extra_meta)
    return GraphNode(
        id=_node_id(resource_type, resource),
        label=label,
        resource_type=resource_type,
        aws_type=RESOURCE_TYPE_TO_AWS_TYPE.get(resource_type, ""),
        metadata=meta,
        cluster_id=cluster_id,
    )


class AWSGraphBuilder:
    """Convert fetched AWS resources into an ``InfraGraph``."""

    def build(
        self,
        resources: Dict[str, List[Dict[str, Any]]],
        config: InfraDrawConfig,
        *,
        region: str = "",
        vpc_id: str | None = None,
    ) -> InfraGraph:
        region_label = region or ", ".join(config.regions)
        title = f"AWS – {region_label}"
        if vpc_id:
            title += f" – {vpc_id}"

        graph = InfraGraph(title=title, provider="aws", region=region_label)
        self._populate(graph, resources, config, vpc_id)
        return graph

    def _populate(
        self,
        graph: InfraGraph,
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
        edge_counter = 0

        def _eid(src: str, tgt: str, etype: str) -> str:
            nonlocal edge_counter
            edge_counter += 1
            return f"e{edge_counter}-{etype}"

        for vpc in vpcs:
            vid = vpc["VpcId"]
            if target_vpc and vid != target_vpc:
                continue

            cidr = vpc.get("CidrBlock", "")
            vpc_label = _label(vpc, "VpcId", detail, cidr)

            graph.clusters.append(GraphCluster(
                id=vid,
                label=f"VPC {vpc_label}",
                cluster_type="vpc",
                metadata={"cidr_block": cidr, "tags": _tags_dict(vpc)},
            ))

            # VPC as a node too (for Terraform mapping / JSON export)
            graph.nodes.append(_make_node(
                "vpc", vpc, vpc_label,
                cluster_id=vid,
                extra_meta={"cidr_block": cidr, "vpc_id": vid},
            ))

            # IGWs attached to this VPC
            attached_igws = [
                i for i in igws
                if any(a.get("VpcId") == vid for a in i.get("Attachments", []))
            ]
            igw_node_ids: List[str] = []
            for igw in attached_igws:
                node = _make_node("igw", igw, _label(igw, "InternetGatewayId", detail), cluster_id=vid)
                graph.nodes.append(node)
                igw_node_ids.append(node.id)

            # NAT Gateways in this VPC
            vpc_nats = [n for n in nats if n.get("VpcId") == vid]
            nat_node_ids: List[str] = []
            for nat in vpc_nats:
                node = _make_node("natgw", nat, _label(nat, "NatGatewayId", detail), cluster_id=vid)
                graph.nodes.append(node)
                nat_node_ids.append(node.id)

            # Subnets
            vpc_subnets = [s for s in subnets if s.get("VpcId") == vid]
            for sn in vpc_subnets:
                is_pub = _is_public_subnet(sn, rts)
                sn_label = _label(sn, "SubnetId", detail, sn.get("CidrBlock", ""))
                sn_id = sn["SubnetId"]

                sn_node = _make_node(
                    "subnet", sn, sn_label,
                    cluster_id=vid,
                    extra_meta={
                        "subnet_type": "public" if is_pub else "private",
                        "cidr_block": sn.get("CidrBlock", ""),
                        "vpc_id": vid,
                    },
                )
                graph.nodes.append(sn_node)

                # EC2 instances in this subnet
                for inst in ec2s:
                    if inst.get("SubnetId") == sn_id:
                        extra = f"{inst.get('InstanceType', '')}\n{inst.get('PrivateIpAddress', '')}"
                        ec2_node = _make_node(
                            "ec2", inst, _label(inst, "InstanceId", detail, extra),
                            cluster_id=vid,
                            extra_meta={
                                "instance_type": inst.get("InstanceType", ""),
                                "private_ip": inst.get("PrivateIpAddress", ""),
                                "subnet_id": sn_id,
                                "vpc_id": vid,
                            },
                        )
                        graph.nodes.append(ec2_node)
                        graph.edges.append(GraphEdge(
                            id=_eid(ec2_node.id, sn_id, "ec2-subnet"),
                            source=ec2_node.id,
                            target=sn_id,
                            edge_type="placement",
                            style={"color": "gray"},
                        ))

                # Lambda functions in this subnet
                for fn in lambdas:
                    fn_subnets = (fn.get("VpcConfig") or {}).get("SubnetIds", [])
                    if sn_id in fn_subnets:
                        fn_name = fn.get("FunctionName", "?")
                        lam_node = _make_node(
                            "lambda", fn,
                            _label(fn, "FunctionName", detail, fn.get("Runtime", "")),
                            cluster_id=vid,
                            extra_meta={
                                "runtime": fn.get("Runtime", ""),
                                "subnet_id": sn_id,
                                "vpc_id": vid,
                            },
                        )
                        graph.nodes.append(lam_node)
                        graph.edges.append(GraphEdge(
                            id=_eid(fn_name, sn_id, "lambda-subnet"),
                            source=fn_name,
                            target=sn_id,
                            edge_type="placement",
                            style={"color": "orange"},
                        ))

                # Route table associations
                for rt in rts:
                    for assoc in rt.get("Associations", []):
                        if assoc.get("SubnetId") == sn_id:
                            rt_id = rt["RouteTableId"]
                            rt_label = _label(rt, "RouteTableId", detail)

                            if not any(n.id == rt_id for n in graph.nodes):
                                graph.nodes.append(_make_node(
                                    "routetable", rt, rt_label, cluster_id=vid,
                                ))

                            graph.edges.append(GraphEdge(
                                id=_eid(sn_id, rt_id, "subnet-rt"),
                                source=sn_id,
                                target=rt_id,
                                edge_type="route_association",
                                style={"color": "blue", "style": "dashed"},
                            ))

                            for route in rt.get("Routes", []):
                                gw = route.get("GatewayId", "")
                                if gw.startswith("igw-"):
                                    for ig_id in igw_node_ids:
                                        graph.edges.append(GraphEdge(
                                            id=_eid(rt_id, ig_id, "rt-igw"),
                                            source=rt_id,
                                            target=ig_id,
                                            edge_type="route",
                                            style={"color": "green"},
                                        ))
                                nat_id = route.get("NatGatewayId", "")
                                if nat_id and nat_id in nat_node_ids:
                                    graph.edges.append(GraphEdge(
                                        id=_eid(rt_id, nat_id, "rt-nat"),
                                        source=rt_id,
                                        target=nat_id,
                                        edge_type="route",
                                        style={"color": "purple"},
                                    ))

            # ALBs in this VPC
            vpc_subnet_ids = {s.get("SubnetId") for s in vpc_subnets}
            for lb in albs:
                lb_azs = {a.get("SubnetId") for a in lb.get("AvailabilityZones", [])}
                if lb_azs & vpc_subnet_ids:
                    graph.nodes.append(_make_node(
                        "alb", lb,
                        _label(lb, "LoadBalancerName", detail, lb.get("DNSName", "")),
                        cluster_id=vid,
                        extra_meta={"dns_name": lb.get("DNSName", ""), "vpc_id": vid},
                    ))

            # NLBs in this VPC
            for lb in nlbs:
                lb_azs = {a.get("SubnetId") for a in lb.get("AvailabilityZones", [])}
                if lb_azs & vpc_subnet_ids:
                    graph.nodes.append(_make_node(
                        "nlb", lb,
                        _label(lb, "LoadBalancerName", detail, lb.get("DNSName", "")),
                        cluster_id=vid,
                        extra_meta={"dns_name": lb.get("DNSName", ""), "vpc_id": vid},
                    ))

            # RDS in this VPC
            for db in rdss:
                db_subnets = {
                    s["SubnetIdentifier"]
                    for s in (db.get("DBSubnetGroup") or {}).get("Subnets", [])
                }
                if db_subnets & vpc_subnet_ids:
                    extra = f"{db.get('Engine', '')} {db.get('DBInstanceClass', '')}"
                    graph.nodes.append(_make_node(
                        "rds", db,
                        _label(db, "DBInstanceIdentifier", detail, extra),
                        cluster_id=vid,
                        extra_meta={
                            "engine": db.get("Engine", ""),
                            "instance_class": db.get("DBInstanceClass", ""),
                            "vpc_id": vid,
                        },
                    ))

        # --- resources outside VPC clusters ---------------------------
        for pc in peerings:
            graph.nodes.append(_make_node(
                "vpc_peering", pc,
                pc.get("VpcPeeringConnectionId", "peering"),
            ))

        for tg in tgws:
            graph.nodes.append(_make_node(
                "tgw", tg, _label(tg, "TransitGatewayId", detail),
            ))

        for tbl in dynamos:
            graph.nodes.append(_make_node(
                "dynamodb", tbl, tbl.get("TableName", "table"),
                extra_meta={"table_arn": tbl.get("TableArn", "")},
            ))

        for bkt in s3s:
            graph.nodes.append(_make_node("s3", bkt, bkt.get("Name", "bucket")))

        for role in iam_roles[:10]:
            graph.nodes.append(_make_node(
                "iam", role, role.get("RoleName", "role"),
                extra_meta={"arn": role.get("Arn", "")},
            ))
