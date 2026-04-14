"""Canonical infrastructure graph model.

Provider-agnostic intermediate representation that all exporters consume.
Built once from cloud resources, then serialised into any output format.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class GraphNode:
    """A single cloud resource rendered as a graph vertex."""

    id: str
    label: str
    resource_type: str
    aws_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    cluster_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d = {k: v for k, v in d.items() if v is not None}
        return d


@dataclass
class GraphEdge:
    """A directed relationship between two nodes."""

    id: str
    source: str
    target: str
    label: str = ""
    edge_type: str = "association"
    style: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GraphCluster:
    """A visual grouping container (VPC, region, account …)."""

    id: str
    label: str
    cluster_type: str
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d = {k: v for k, v in d.items() if v is not None}
        return d


@dataclass
class InfraGraph:
    """Complete infrastructure topology ready for export."""

    title: str
    provider: str
    region: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    clusters: List[GraphCluster] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "provider": self.provider,
            "region": self.region,
            "generated_at": self.generated_at,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "clusters": [c.to_dict() for c in self.clusters],
        }

    def nodes_in_cluster(self, cluster_id: str) -> List[GraphNode]:
        return [n for n in self.nodes if n.cluster_id == cluster_id]

    def standalone_nodes(self) -> List[GraphNode]:
        return [n for n in self.nodes if n.cluster_id is None]

    def edges_for_node(self, node_id: str) -> List[GraphEdge]:
        return [e for e in self.edges if e.source == node_id or e.target == node_id]
