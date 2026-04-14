"""High-level orchestrator: fetches resources (in parallel) then builds diagrams."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from infra_draw.core.config import InfraDrawConfig
from infra_draw.core.provider import CloudProvider, ResourceFetcher
from infra_draw.utils.progress import progress_bar

logger = logging.getLogger(__name__)


def _run_fetcher(fetcher: ResourceFetcher, config: InfraDrawConfig) -> Dict[str, List[Dict[str, Any]]]:
    name = type(fetcher).__name__
    logger.debug("Running %s …", name)
    return fetcher.fetch(config)


def fetch_all(
    fetchers: List[ResourceFetcher],
    config: InfraDrawConfig,
) -> Dict[str, List[Dict[str, Any]]]:
    """Run every fetcher in parallel via a thread-pool, merge results."""
    merged: Dict[str, List[Dict[str, Any]]] = {}
    futures = {}

    with ThreadPoolExecutor(max_workers=config.max_workers) as pool:
        for f in fetchers:
            futures[pool.submit(_run_fetcher, f, config)] = type(f).__name__

        for fut in progress_bar(
            as_completed(futures),
            desc="Fetching resources",
            total=len(futures),
        ):
            name = futures[fut]
            try:
                result = fut.result()
                for rtype, items in result.items():
                    merged.setdefault(rtype, []).extend(items)
            except Exception as exc:
                logger.warning("Fetcher %s failed: %s", name, exc)

    for rtype, items in merged.items():
        logger.info("  %-15s %d", rtype, len(items))
    return merged


def generate_diagrams(
    provider: CloudProvider,
    config: InfraDrawConfig,
) -> List[str]:
    """End-to-end: discover regions → fetch → build diagrams. Returns file paths."""
    regions = provider.list_regions(config)
    builder = provider.get_diagram_builder()
    output_files: List[str] = []

    for region in regions:
        region_config = InfraDrawConfig(
            provider=config.provider,
            regions=[region],
            all_regions=False,
            profile=config.profile,
            resource_types=config.resource_types,
            exclude_tags=config.exclude_tags,
            output_dir=config.output_dir,
            output_format=config.output_format,
            per_vpc=config.per_vpc,
            show_details=config.show_details,
            verbose=config.verbose,
            dry_run=config.dry_run,
            max_workers=config.max_workers,
        )

        fetchers = provider.get_fetchers(region_config)
        resources = fetch_all(fetchers, region_config)

        if not any(resources.values()):
            logger.warning("No resources found in %s – skipping diagram", region)
            continue

        if config.per_vpc:
            vpc_ids = {v["VpcId"] for v in resources.get("vpc", [])}
            for vid in vpc_ids:
                path = builder.build(resources, region_config, region=region, vpc_id=vid)
                output_files.append(path)
        else:
            path = builder.build(resources, region_config, region=region)
            output_files.append(path)

    return output_files
