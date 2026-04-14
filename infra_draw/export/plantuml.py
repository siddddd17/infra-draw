"""PlantUML exporter using AWS stdlib icons."""

from __future__ import annotations

import re
from pathlib import Path

from infra_draw.export import Exporter, register_exporter
from infra_draw.export.graph import InfraGraph

_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9_]")

PLANTUML_INCLUDES = {
    "ec2": "<awslib/Compute/EC2>",
    "lambda": "<awslib/Compute/Lambda>",
    "vpc": "<awslib/NetworkingContentDelivery/VPC>",
    "subnet": "<awslib/NetworkingContentDelivery/VPCSubnet>",
    "igw": "<awslib/NetworkingContentDelivery/VPCInternetGateway>",
    "natgw": "<awslib/NetworkingContentDelivery/VPCNATGateway>",
    "routetable": "<awslib/NetworkingContentDelivery/VPCRouter>",
    "alb": "<awslib/NetworkingContentDelivery/ElasticLoadBalancing>",
    "nlb": "<awslib/NetworkingContentDelivery/ElasticLoadBalancing>",
    "rds": "<awslib/Database/RDS>",
    "dynamodb": "<awslib/Database/DynamoDB>",
    "s3": "<awslib/Storage/SimpleStorageService>",
    "iam": "<awslib/SecurityIdentityCompliance/IAMIdentityCenter>",
    "vpc_peering": "<awslib/NetworkingContentDelivery/VPCPeering>",
    "tgw": "<awslib/NetworkingContentDelivery/TransitGateway>",
}

PLANTUML_MACROS = {
    "ec2": "EC2",
    "lambda": "Lambda",
    "vpc": "VPC",
    "subnet": "VPCSubnet",
    "igw": "VPCInternetGateway",
    "natgw": "VPCNATGateway",
    "routetable": "VPCRouter",
    "alb": "ElasticLoadBalancing",
    "nlb": "ElasticLoadBalancing",
    "rds": "RDS",
    "dynamodb": "DynamoDB",
    "s3": "SimpleStorageService",
    "iam": "IAMIdentityCenter",
    "vpc_peering": "VPCPeering",
    "tgw": "TransitGateway",
}

EDGE_STYLE_MAP = {
    "green": "#248814",
    "blue": "#1168BD",
    "purple": "#7B2D8E",
    "orange": "#ED7100",
    "gray": "#666666",
}


def _safe_id(raw: str) -> str:
    sanitized = _SANITIZE_RE.sub("_", raw).strip("_")
    if sanitized and sanitized[0].isdigit():
        sanitized = f"n_{sanitized}"
    return sanitized or "node"


def _escape_label(text: str) -> str:
    return text.replace('"', "'").replace("\n", "\\n")


@register_exporter
class PlantUMLExporter(Exporter):
    format_id = "plantuml"
    file_extension = ".puml"

    def export(self, graph: InfraGraph, output_path: str) -> str:
        lines = ["@startuml", f"' {graph.title}", ""]

        # Collect needed includes
        needed = set()
        for node in graph.nodes:
            inc = PLANTUML_INCLUDES.get(node.resource_type)
            if inc:
                needed.add(inc)

        lines.append("!include <awslib/AWSCommon>")
        for inc in sorted(needed):
            lines.append(f"!include {inc}")

        lines.extend([
            "",
            "skinparam backgroundColor #FEFEFE",
            "skinparam packageStyle rectangle",
            "",
        ])

        for cluster in graph.clusters:
            label = _escape_label(cluster.label)
            safe_cid = _safe_id(cluster.id)
            lines.append(f'package "{label}" as {safe_cid} {{')

            for node in graph.nodes_in_cluster(cluster.id):
                safe_nid = _safe_id(node.id)
                nlabel = _escape_label(node.label)
                macro = PLANTUML_MACROS.get(node.resource_type)
                if macro:
                    lines.append(f'    {macro}({safe_nid}, "{nlabel}", "")')
                else:
                    lines.append(f'    component "{nlabel}" as {safe_nid}')

            lines.append("}")
            lines.append("")

        for node in graph.standalone_nodes():
            safe_nid = _safe_id(node.id)
            nlabel = _escape_label(node.label)
            macro = PLANTUML_MACROS.get(node.resource_type)
            if macro:
                lines.append(f'{macro}({safe_nid}, "{nlabel}", "")')
            else:
                lines.append(f'component "{nlabel}" as {safe_nid}')

        if graph.standalone_nodes():
            lines.append("")

        for edge in graph.edges:
            src = _safe_id(edge.source)
            tgt = _safe_id(edge.target)
            color = EDGE_STYLE_MAP.get(edge.style.get("color", ""), "#666666")
            is_dashed = edge.style.get("style") == "dashed"
            arrow = "..>" if is_dashed else "-->"
            if edge.label:
                label = _escape_label(edge.label)
                lines.append(f'{src} {arrow} {tgt} {color} : {label}')
            else:
                lines.append(f"{src} {arrow} {tgt} {color}")

        lines.extend(["", "@enduml", ""])
        content = "\n".join(lines)

        dest = f"{output_path}{self.file_extension}"
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(content)
        return dest
