"""JSON exporter – canonical graph plus embedded Terraform mapping."""

from __future__ import annotations

import json
from pathlib import Path

from infra_draw import __version__
from infra_draw.export import Exporter, register_exporter
from infra_draw.export.graph import InfraGraph
from infra_draw.export.terraform import terraform_mapping


@register_exporter
class JSONExporter(Exporter):
    format_id = "json"
    file_extension = ".json"

    def export(self, graph: InfraGraph, output_path: str) -> str:
        payload = {
            "version": "1.0",
            "generator": "infra-draw",
            "generator_version": __version__,
            "generated_at": graph.generated_at,
            "provider": graph.provider,
            "region": graph.region,
            "title": graph.title,
            "graph": graph.to_dict(),
            "terraform": terraform_mapping(graph),
        }

        dest = f"{output_path}{self.file_extension}"
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        return dest
