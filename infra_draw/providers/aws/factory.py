"""AWS provider factory – wires fetchers + builder and registers with ProviderFactory."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

from infra_draw.core.config import InfraDrawConfig
from infra_draw.core.exceptions import CredentialsError, PermissionError_
from infra_draw.core.provider import CloudProvider, DiagramBuilder, GraphBuilder, ProviderFactory, ResourceFetcher
from infra_draw.providers.aws.diagram_builder import AWSDiagramBuilder
from infra_draw.providers.aws.graph_builder import AWSGraphBuilder
from infra_draw.providers.aws.fetchers.compute import ComputeFetcher
from infra_draw.providers.aws.fetchers.database import DatabaseFetcher
from infra_draw.providers.aws.fetchers.network import NetworkFetcher
from infra_draw.providers.aws.fetchers.security import SecurityFetcher
from infra_draw.providers.aws.fetchers.storage import StorageFetcher

logger = logging.getLogger(__name__)


@ProviderFactory.register
class AWSProvider(CloudProvider):
    """Complete AWS implementation."""

    @property
    def name(self) -> str:
        return "aws"

    def _session(self, config: InfraDrawConfig) -> boto3.Session:
        kwargs: Dict[str, Any] = {}
        if config.profile:
            kwargs["profile_name"] = config.profile
        return boto3.Session(**kwargs)

    # ------------------------------------------------------------------
    def validate_credentials(self, config: InfraDrawConfig) -> None:
        try:
            sess = self._session(config)
            sts = sess.client("sts")
            identity = sts.get_caller_identity()
            logger.info(
                "Authenticated as %s (account %s)",
                identity["Arn"],
                identity["Account"],
            )
        except NoCredentialsError:
            raise CredentialsError(
                "No AWS credentials found.\n"
                "  • Run `aws configure`\n"
                "  • Or export AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY\n"
                "  • Or pass --profile <name>"
            )
        except PartialCredentialsError:
            raise CredentialsError("Incomplete AWS credentials – check your config.")
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("AccessDenied", "UnauthorizedOperation"):
                raise PermissionError_(f"STS GetCallerIdentity denied: {exc}")
            raise CredentialsError(f"AWS credential check failed: {exc}")

    # ------------------------------------------------------------------
    def list_regions(self, config: InfraDrawConfig) -> List[str]:
        if not config.all_regions:
            return list(config.regions)
        try:
            sess = self._session(config)
            ec2 = sess.client("ec2", region_name=config.regions[0] if config.regions else "us-east-1")
            resp = ec2.describe_regions(Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required", "opted-in"]}])
            regions = [r["RegionName"] for r in resp.get("Regions", [])]
            logger.info("Discovered %d enabled regions", len(regions))
            return regions
        except Exception as exc:
            logger.warning("Could not list regions, falling back to config: %s", exc)
            return list(config.regions)

    # ------------------------------------------------------------------
    def get_fetchers(self, config: InfraDrawConfig) -> List[ResourceFetcher]:
        sess = self._session(config)
        return [
            ComputeFetcher(sess),
            NetworkFetcher(sess),
            DatabaseFetcher(sess),
            StorageFetcher(sess),
            SecurityFetcher(sess),
        ]

    def get_diagram_builder(self) -> DiagramBuilder:
        return AWSDiagramBuilder()

    def get_graph_builder(self) -> GraphBuilder:
        return AWSGraphBuilder()
