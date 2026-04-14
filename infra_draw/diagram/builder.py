"""High-level orchestrator: fetches resources (in parallel) then builds diagrams or data exports."""

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


def _region_config(config: InfraDrawConfig, region: str) -> InfraDrawConfig:
    """Clone the top-level config scoped to a single region."""
    return InfraDrawConfig(
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


def generate_diagrams(
    provider: CloudProvider,
    config: InfraDrawConfig,
) -> List[str]:
    """End-to-end: discover regions -> fetch -> build image diagrams. Returns file paths."""
    regions = provider.list_regions(config)
    builder = provider.get_diagram_builder()
    output_files: List[str] = []

    for region in regions:
        rcfg = _region_config(config, region)
        fetchers = provider.get_fetchers(rcfg)
        resources = fetch_all(fetchers, rcfg)

        if not any(resources.values()):
            logger.warning("No resources found in %s – skipping diagram", region)
            continue

        if config.per_vpc:
            vpc_ids = {v["VpcId"] for v in resources.get("vpc", [])}
            for vid in vpc_ids:
                path = builder.build(resources, rcfg, region=region, vpc_id=vid)
                output_files.append(path)
        else:
            path = builder.build(resources, rcfg, region=region)
            output_files.append(path)

    return output_files


def generate_exports(
    provider: CloudProvider,
    config: InfraDrawConfig,
) -> List[str]:
    """End-to-end: discover regions -> fetch -> export to data format. Returns file paths."""
    import infra_draw.export.json_export  # noqa: F401 – register exporters
    import infra_draw.export.drawio  # noqa: F401
    import infra_draw.export.mermaid  # noqa: F401
    import infra_draw.export.plantuml  # noqa: F401
    import infra_draw.export.terraform  # noqa: F401
    from infra_draw.export import get_exporter

    regions = provider.list_regions(config)
    graph_builder = provider.get_graph_builder()
    exporter = get_exporter(config.output_format)
    output_files: List[str] = []

    for region in regions:
        rcfg = _region_config(config, region)
        fetchers = provider.get_fetchers(rcfg)
        resources = fetch_all(fetchers, rcfg)

        if not any(resources.values()):
            logger.warning("No resources found in %s – skipping export", region)
            continue

        if config.per_vpc:
            vpc_ids = {v["VpcId"] for v in resources.get("vpc", [])}
            for vid in vpc_ids:
                graph = graph_builder.build(resources, rcfg, region=region, vpc_id=vid)
                safe_name = graph.title.replace(" ", "_").replace("–", "-")
                path = str(config.output_dir / safe_name)
                output_files.append(exporter.export(graph, path))
        else:
            graph = graph_builder.build(resources, rcfg, region=region)
            safe_name = graph.title.replace(" ", "_").replace("–", "-")
            path = str(config.output_dir / safe_name)
            output_files.append(exporter.export(graph, path))

    return output_files
