"""Shared helpers that concrete providers can reuse."""

from __future__ import annotations

from typing import Any, Dict, List


def group_by_key(items: List[Dict[str, Any]], key: str) -> Dict[str, List[Dict[str, Any]]]:
    """Group a flat list of dicts by the value at *key*."""
    result: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        bucket = item.get(key, "__none__")
        result.setdefault(bucket, []).append(item)
    return result
