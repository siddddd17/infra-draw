"""Draw.io (diagrams.net) XML exporter.

Generates ``.drawio`` files that can be opened directly in the Draw.io
desktop or web editor.  Uses basic styled shapes with AWS-category colours
so the output renders without custom stencil packs.
"""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Dict, List, Tuple
from xml.etree.ElementTree import Element, SubElement, tostring

from infra_draw.export import Exporter, register_exporter
from infra_draw.export.graph import GraphCluster, GraphNode, InfraGraph

logger = logging.getLogger(__name__)

# Layout constants
NODE_W, NODE_H = 120, 60
PAD = 20
COL_GAP = 30
ROW_GAP = 40
CLUSTER_HEADER = 30

AWS_COLORS: Dict[str, Tuple[str, str]] = {
    "ec2":         ("#ED7100", "#FFFFFF"),
    "lambda":      ("#ED7100", "#FFFFFF"),
    "vpc":         ("#8C4FFF", "#FFFFFF"),
    "subnet":      ("#8C4FFF", "#FFFFFF"),
    "igw":         ("#8C4FFF", "#FFFFFF"),
    "natgw":       ("#8C4FFF", "#FFFFFF"),
    "routetable":  ("#8C4FFF", "#FFFFFF"),
    "alb":         ("#8C4FFF", "#FFFFFF"),
    "nlb":         ("#8C4FFF", "#FFFFFF"),
    "rds":         ("#C925D1", "#FFFFFF"),
    "dynamodb":    ("#C925D1", "#FFFFFF"),
    "s3":          ("#3F8624", "#FFFFFF"),
    "iam":         ("#DD344C", "#FFFFFF"),
    "vpc_peering": ("#8C4FFF", "#FFFFFF"),
    "tgw":         ("#8C4FFF", "#FFFFFF"),
}

EDGE_HEX: Dict[str, str] = {
    "gray": "#666666",
    "blue": "#1168BD",
    "green": "#248814",
    "purple": "#7B2D8E",
    "orange": "#ED7100",
}


def _node_style(resource_type: str) -> str:
    fill, font = AWS_COLORS.get(resource_type, ("#E8E8E8", "#000000"))
    return (
        f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};"
        f"fontColor={font};strokeColor=#232F3E;fontSize=11;"
    )


def _cluster_style() -> str:
    return (
        "swimlane;startSize=30;fillColor=#232F3E;fontColor=#FFFFFF;"
        "strokeColor=#232F3E;rounded=1;fontSize=12;html=1;"
        "collapsible=0;whiteSpace=wrap;"
    )


def _edge_style(edge_meta: Dict[str, str]) -> str:
    color = EDGE_HEX.get(edge_meta.get("color", ""), "#666666")
    dashed = "1" if edge_meta.get("style") == "dashed" else "0"
    return (
        f"edgeStyle=orthogonalEdgeStyle;rounded=1;strokeColor={color};"
        f"dashed={dashed};exitX=0.5;exitY=1;entryX=0.5;entryY=0;"
    )


class _LayoutEngine:
    """Simple grid layout that places nodes in rows within clusters."""

    def __init__(self) -> None:
        self._cluster_bounds: Dict[str, Tuple[float, float, float, float]] = {}
        self._node_positions: Dict[str, Tuple[float, float]] = {}
        self._next_y: float = PAD

    def layout(self, graph: InfraGraph) -> None:
        for cluster in graph.clusters:
            nodes = graph.nodes_in_cluster(cluster.id)
            self._layout_cluster(cluster, nodes)

        standalone = graph.standalone_nodes()
        if standalone:
            self._layout_standalone(standalone)

    def _layout_cluster(self, cluster: GraphCluster, nodes: List[GraphNode]) -> None:
        if not nodes:
            return
        cols = max(3, int(len(nodes) ** 0.5) + 1)
        rows = (len(nodes) + cols - 1) // cols

        inner_w = cols * NODE_W + (cols - 1) * COL_GAP
        inner_h = rows * NODE_H + (rows - 1) * ROW_GAP
        cw = inner_w + 2 * PAD
        ch = inner_h + 2 * PAD + CLUSTER_HEADER

        cx, cy = PAD, self._next_y
        self._cluster_bounds[cluster.id] = (cx, cy, cw, ch)

        for idx, node in enumerate(nodes):
            col = idx % cols
            row = idx // cols
            nx = cx + PAD + col * (NODE_W + COL_GAP)
            ny = cy + CLUSTER_HEADER + PAD + row * (NODE_H + ROW_GAP)
            self._node_positions[node.id] = (nx, ny)

        self._next_y = cy + ch + PAD

    def _layout_standalone(self, nodes: List[GraphNode]) -> None:
        cols = max(4, int(len(nodes) ** 0.5) + 1)
        for idx, node in enumerate(nodes):
            col = idx % cols
            row = idx // cols
            nx = PAD + col * (NODE_W + COL_GAP)
            ny = self._next_y + row * (NODE_H + ROW_GAP)
            self._node_positions[node.id] = (nx, ny)

    def cluster_geom(self, cluster_id: str) -> Tuple[float, float, float, float]:
        return self._cluster_bounds.get(cluster_id, (0, 0, 200, 100))

    def node_pos(self, node_id: str) -> Tuple[float, float]:
        return self._node_positions.get(node_id, (0, 0))


def _build_xml(graph: InfraGraph) -> bytes:
    layout = _LayoutEngine()
    layout.layout(graph)

    mxfile = Element("mxfile")
    diagram = SubElement(mxfile, "diagram", name=graph.title)
    model = SubElement(diagram, "mxGraphModel", {
        "dx": "1200", "dy": "800", "grid": "1", "gridSize": "10",
        "guides": "1", "tooltips": "1", "connect": "1", "arrows": "1",
        "fold": "1", "page": "1", "pageScale": "1", "math": "0",
    })
    root = SubElement(model, "root")
    SubElement(root, "mxCell", id="0")
    SubElement(root, "mxCell", id="1", parent="0")

    cell_counter = 2
    cluster_cell_map: Dict[str, str] = {}
    node_cell_map: Dict[str, str] = {}

    def _next_id() -> str:
        nonlocal cell_counter
        cid = str(cell_counter)
        cell_counter += 1
        return cid

    # Clusters
    for cluster in graph.clusters:
        cid = _next_id()
        cluster_cell_map[cluster.id] = cid
        cx, cy, cw, ch = layout.cluster_geom(cluster.id)
        cell = SubElement(root, "mxCell", {
            "id": cid, "value": html.escape(cluster.label),
            "style": _cluster_style(), "vertex": "1", "parent": "1",
        })
        SubElement(cell, "mxGeometry", {
            "x": str(int(cx)), "y": str(int(cy)),
            "width": str(int(cw)), "height": str(int(ch)),
            "as": "geometry",
        })

    # Nodes
    for node in graph.nodes:
        nid = _next_id()
        parent = cluster_cell_map.get(node.cluster_id, "1") if node.cluster_id else "1"
        nx, ny = layout.node_pos(node.id)

        if node.cluster_id:
            cx, cy, _, _ = layout.cluster_geom(node.cluster_id)
            nx -= cx
            ny -= cy

        cell = SubElement(root, "mxCell", {
            "id": nid, "value": html.escape(node.label.replace("\n", "<br/>")),
            "style": _node_style(node.resource_type),
            "vertex": "1", "parent": parent,
        })
        SubElement(cell, "mxGeometry", {
            "x": str(int(nx)), "y": str(int(ny)),
            "width": str(NODE_W), "height": str(NODE_H),
            "as": "geometry",
        })
        node_cell_map[node.id] = nid

    # Edges
    for edge in graph.edges:
        eid = _next_id()
        src = node_cell_map.get(edge.source, "")
        tgt = node_cell_map.get(edge.target, "")
        if not src or not tgt:
            logger.debug("Skipping Draw.io edge %s due to missing endpoint", edge.id)
            continue
        if src == tgt:
            logger.debug("Skipping Draw.io self-referencing edge %s", edge.id)
            continue
        cell = SubElement(root, "mxCell", {
            "id": eid,
            "value": html.escape(edge.label) if edge.label else "",
            "style": _edge_style(edge.style),
            "edge": "1", "parent": "1",
            "source": src, "target": tgt,
        })
        SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})

    return tostring(mxfile, encoding="unicode", xml_declaration=True).encode("utf-8")


@register_exporter
class DrawioExporter(Exporter):
    format_id = "drawio"
    file_extension = ".drawio"

    def export(self, graph: InfraGraph, output_path: str) -> str:
        xml_bytes = _build_xml(graph)

        dest = f"{output_path}{self.file_extension}"
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(xml_bytes)
        return dest
