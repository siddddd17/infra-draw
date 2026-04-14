"""Export package – format registry and convenience helpers."""

from __future__ import annotations

from typing import Dict, Type

from infra_draw.export.graph import InfraGraph

IMAGE_FORMATS = {"png", "svg", "pdf"}
DATA_FORMATS = {"json", "drawio", "mermaid", "plantuml", "terraform"}
ALL_FORMATS = IMAGE_FORMATS | DATA_FORMATS


class Exporter:
    """Base class for all data-format exporters."""

    format_id: str = ""
    file_extension: str = ""

    def export(self, graph: InfraGraph, output_path: str) -> str:
        """Write *graph* to disk, return the final file path."""
        raise NotImplementedError


_REGISTRY: Dict[str, Type[Exporter]] = {}


def register_exporter(cls: Type[Exporter]) -> Type[Exporter]:
    _REGISTRY[cls.format_id] = cls
    return cls


def get_exporter(fmt: str) -> Exporter:
    if fmt not in _REGISTRY:
        raise KeyError(f"No exporter registered for format '{fmt}'")
    return _REGISTRY[fmt]()


def available_data_formats() -> list[str]:
    return sorted(_REGISTRY.keys())


def is_data_format(fmt: str) -> bool:
    return fmt in DATA_FORMATS
