"""Thin wrapper around tqdm so callers don't import it directly."""

from __future__ import annotations

from typing import Iterable, TypeVar

from tqdm import tqdm

T = TypeVar("T")


def progress_bar(
    iterable: Iterable[T],
    *,
    desc: str = "",
    total: int | None = None,
    disable: bool = False,
) -> Iterable[T]:
    return tqdm(
        iterable,
        desc=desc,
        total=total,
        disable=disable,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        colour="cyan",
    )
