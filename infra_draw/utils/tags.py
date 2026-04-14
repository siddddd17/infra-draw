"""Helpers for AWS-style tag filtering."""

from __future__ import annotations

from typing import Any, Dict, List


def get_name_tag(resource: Dict[str, Any], fallback: str = "") -> str:
    """Extract the ``Name`` tag value, falling back to *fallback*."""
    for tag in resource.get("Tags") or []:
        if tag.get("Key") == "Name":
            return tag.get("Value", fallback)
    return fallback


def matches_exclude_tags(resource: Dict[str, Any], exclude: Dict[str, str]) -> bool:
    """Return ``True`` if *resource* has **any** of the *exclude* key=value pairs."""
    if not exclude:
        return False
    tags = {t["Key"]: t.get("Value", "") for t in (resource.get("Tags") or [])}
    return any(tags.get(k) == v for k, v in exclude.items())


def filter_resources(
    resources: List[Dict[str, Any]],
    exclude: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Return resources that do **not** match *exclude* tags."""
    if not exclude:
        return resources
    return [r for r in resources if not matches_exclude_tags(r, exclude)]
