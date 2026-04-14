"""Terraform reference mapping – resource-to-IaC bridge.

Produces a mapping from each discovered resource to its Terraform resource
type and the import identifier that ``terraform import`` expects.  Available
both as standalone export and embedded inside the JSON export.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from infra_draw import __version__
from infra_draw.export import Exporter, register_exporter
from infra_draw.export.graph import GraphNode, InfraGraph

_TF_TYPE_MAP: Dict[str, str] = {
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

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_]")


def _safe_tf_name(raw: str) -> str:
    """Turn an arbitrary resource id/name into a Terraform-safe identifier."""
    name = _SAFE_NAME_RE.sub("_", raw).strip("_")
    if name and name[0].isdigit():
        name = f"r_{name}"
    return name or "unnamed"


def _import_id(node: GraphNode) -> str:
    """Best-effort import identifier for ``terraform import``."""
    meta = node.metadata
    if node.resource_type == "iam":
        return meta.get("arn") or node.id
    if node.resource_type == "dynamodb":
        return node.id
    if node.resource_type == "s3":
        return node.id
    if node.resource_type == "lambda":
        return node.id
    return node.id


def _resource_entry(node: GraphNode) -> Dict[str, Any]:
    tf_type = _TF_TYPE_MAP.get(node.resource_type, "")
    if not tf_type:
        return {}
    import_id = _import_id(node)
    suggested_name = _safe_tf_name(node.id)
    return {
        "resource_id": node.id,
        "resource_type": node.resource_type,
        "terraform_type": tf_type,
        "terraform_name": suggested_name,
        "import_id": import_id,
        "label": node.label,
        "region": node.metadata.get("region", ""),
    }


def terraform_mapping(graph: InfraGraph) -> Dict[str, Any]:
    """Return the full Terraform mapping dict (embeddable in JSON export)."""
    resources: List[Dict[str, Any]] = []
    import_commands: List[str] = []

    for node in graph.nodes:
        entry = _resource_entry(node)
        if not entry:
            continue
        resources.append(entry)
        import_commands.append(
            f"terraform import {entry['terraform_type']}.{entry['terraform_name']} {entry['import_id']}"
        )

    return {
        "resources": resources,
        "import_commands": import_commands,
    }


@register_exporter
class TerraformExporter(Exporter):
    """Standalone Terraform mapping export (``terraform`` format)."""

    format_id = "terraform"
    file_extension = ".tf.json"

    def export(self, graph: InfraGraph, output_path: str) -> str:
        mapping = terraform_mapping(graph)
        payload = {
            "version": "1.0",
            "generator": "infra-draw",
            "generator_version": __version__,
            "generated_at": graph.generated_at,
            "provider": graph.provider,
            "region": graph.region,
            **mapping,
        }

        dest = f"{output_path}{self.file_extension}"
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        return dest
