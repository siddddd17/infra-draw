"""Runtime configuration carried through every layer via a single dataclass."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class InfraDrawConfig:
    """Immutable-ish bag of settings built once from CLI flags + env vars."""

    provider: str = "aws"
    regions: List[str] = field(default_factory=lambda: ["us-east-1"])
    all_regions: bool = False
    profile: Optional[str] = None

    resource_types: List[str] = field(default_factory=list)
    exclude_tags: Dict[str, str] = field(default_factory=dict)

    output_dir: Path = field(default_factory=lambda: Path("output"))
    output_format: str = "drawio"
    per_vpc: bool = False
    show_details: bool = False

    verbose: bool = False
    dry_run: bool = False

    max_workers: int = 10

    @classmethod
    def from_cli(cls, **kwargs: object) -> "InfraDrawConfig":
        """Build config from Click option dict, falling back to env vars and saved config."""
        from infra_draw.core.saved_config import get_profile, get_region

        regions_raw: str = str(
            kwargs.get("region")
            or os.getenv("INFRA_DRAW_REGION")
            or get_region()
            or "us-east-1"
        )
        regions = [r.strip() for r in regions_raw.split(",") if r.strip()]

        exclude_tags: Dict[str, str] = {}
        for pair in (kwargs.get("exclude_tags") or []):
            if "=" in pair:
                k, v = pair.split("=", 1)
                exclude_tags[k.strip()] = v.strip()

        profile = (
            kwargs.get("profile")
            or os.getenv("AWS_PROFILE")
            or get_profile()
        )

        return cls(
            provider=str(kwargs.get("provider", os.getenv("INFRA_DRAW_PROVIDER", "aws"))),
            regions=regions,
            all_regions=bool(kwargs.get("all_regions", False)),
            profile=profile,  # type: ignore[arg-type]
            resource_types=list(kwargs.get("resources") or []),
            exclude_tags=exclude_tags,
            output_dir=Path(str(kwargs.get("output_dir", os.getenv("INFRA_DRAW_OUTPUT", "output")))),
            output_format=str(kwargs.get("format", "drawio")),
            per_vpc=bool(kwargs.get("per_vpc", False)),
            show_details=bool(kwargs.get("show_details", False)),
            verbose=bool(kwargs.get("verbose", False)),
            dry_run=bool(kwargs.get("dry_run", False)),
            max_workers=int(kwargs.get("max_workers", os.getenv("INFRA_DRAW_WORKERS", "10"))),
        )

    IMAGE_FORMATS = {"png", "svg", "pdf"}
    DATA_FORMATS = {"json", "drawio", "mermaid", "plantuml", "terraform", "raw"}
    RAW_FORMATS = {"raw"}

    @property
    def is_data_format(self) -> bool:
        return self.output_format in self.DATA_FORMATS

    @property
    def is_raw_format(self) -> bool:
        return self.output_format in self.RAW_FORMATS

    @property
    def available_resource_types(self) -> Set[str]:
        return {
            "ec2", "lambda", "vpc", "subnet", "routetable", "igw", "natgw",
            "alb", "nlb", "vpc_peering", "tgw", "rds", "dynamodb", "s3", "iam",
        }
