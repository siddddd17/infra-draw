"""Mermaid diagram exporter."""

from __future__ import annotations

import re
from pathlib import Path

from infra_draw.export import Exporter, register_exporter
from infra_draw.export.graph import InfraGraph

_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9_]")

RESOURCE_ICONS = {
    "ec2": "fa:fa-server",
    "lambda": "fa:fa-bolt",
    "vpc": "fa:fa-cloud",
    "subnet": "fa:fa-network-wired",
    "igw": "fa:fa-globe",
    "natgw": "fa:fa-exchange-alt",
    "routetable": "fa:fa-route",
    "alb": "fa:fa-balance-scale",
    "nlb": "fa:fa-balance-scale",
    "rds": "fa:fa-database",
    "dynamodb": "fa:fa-database",
    "s3": "fa:fa-archive",
    "iam": "fa:fa-user-shield",
    "vpc_peering": "fa:fa-link",
    "tgw": "fa:fa-project-diagram",
}


def _safe_id(raw: str) -> str:
    sanitized = _SANITIZE_RE.sub("_", raw).strip("_")
    if sanitized and sanitized[0].isdigit():
        sanitized = f"n_{sanitized}"
    return sanitized or "node"


def _escape_label(text: str) -> str:
    return text.replace('"', "'").replace("\n", "<br/>")


@register_exporter
class MermaidExporter(Exporter):
    format_id = "mermaid"
    file_extension = ".mmd"

    def export(self, graph: InfraGraph, output_path: str) -> str:
        lines = [f"---", f"title: {graph.title}", f"---", "graph TB"]

        cluster_ids = {c.id for c in graph.clusters}
        rendered_node_ids: set[str] = set()

        for cluster in graph.clusters:
            safe_cid = _safe_id(cluster.id)
            label = _escape_label(cluster.label)
            lines.append(f'    subgraph {safe_cid} ["{label}"]')

            for node in graph.nodes_in_cluster(cluster.id):
                safe_nid = _safe_id(node.id)
                rendered_node_ids.add(node.id)
                icon = RESOURCE_ICONS.get(node.resource_type, "")
                node_label = _escape_label(node.label)
                if icon:
                    lines.append(f'        {safe_nid}["{icon} {node_label}"]')
                else:
                    lines.append(f'        {safe_nid}["{node_label}"]')

            lines.append("    end")

        standalone = graph.standalone_nodes()
        if standalone:
            for node in standalone:
                safe_nid = _safe_id(node.id)
                rendered_node_ids.add(node.id)
                icon = RESOURCE_ICONS.get(node.resource_type, "")
                node_label = _escape_label(node.label)
                if icon:
                    lines.append(f'    {safe_nid}["{icon} {node_label}"]')
                else:
                    lines.append(f'    {safe_nid}["{node_label}"]')

        lines.append("")

        for edge in graph.edges:
            src = _safe_id(edge.source)
            tgt = _safe_id(edge.target)
            if edge.label:
                label = _escape_label(edge.label)
                lines.append(f'    {src} -->|"{label}"| {tgt}')
            else:
                style_hint = edge.style.get("style", "")
                if style_hint == "dashed":
                    lines.append(f"    {src} -.-> {tgt}")
                else:
                    lines.append(f"    {src} --> {tgt}")

        # Style classes per resource type
        styles = self._style_defs(graph)
        if styles:
            lines.append("")
            lines.extend(styles)

        content = "\n".join(lines) + "\n"

        dest = f"{output_path}{self.file_extension}"
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(content)
        return dest

    @staticmethod
    def _style_defs(graph: InfraGraph) -> list[str]:
        color_map = {
            "ec2": "#ED7100",
            "lambda": "#ED7100",
            "vpc": "#8C4FFF",
            "subnet": "#8C4FFF",
            "igw": "#8C4FFF",
            "natgw": "#8C4FFF",
            "routetable": "#8C4FFF",
            "alb": "#8C4FFF",
            "nlb": "#8C4FFF",
            "rds": "#C925D1",
            "dynamodb": "#C925D1",
            "s3": "#3F8624",
            "iam": "#DD344C",
            "vpc_peering": "#8C4FFF",
            "tgw": "#8C4FFF",
        }
        type_to_nodes: dict[str, list[str]] = {}
        for node in graph.nodes:
            rt = node.resource_type
            if rt in color_map:
                type_to_nodes.setdefault(rt, []).append(_safe_id(node.id))

        lines: list[str] = []
        for rt, node_ids in type_to_nodes.items():
            color = color_map[rt]
            class_name = f"cls_{rt}"
            lines.append(f"    classDef {class_name} fill:{color},stroke:#232F3E,color:#fff")
            lines.append(f"    class {','.join(node_ids)} {class_name}")
        return lines
