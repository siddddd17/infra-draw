"""Azure provider stub – ready for extension."""

from __future__ import annotations

from typing import Any, Dict, List

from infra_draw.core.config import InfraDrawConfig
from infra_draw.core.exceptions import ProviderError
from infra_draw.core.provider import CloudProvider, DiagramBuilder, ProviderFactory, ResourceFetcher


@ProviderFactory.register
class AzureProvider(CloudProvider):
    @property
    def name(self) -> str:
        return "azure"

    def validate_credentials(self, config: InfraDrawConfig) -> None:
        raise ProviderError("Azure provider is not yet implemented. Contributions welcome!")

    def list_regions(self, config: InfraDrawConfig) -> List[str]:
        raise ProviderError("Azure provider is not yet implemented.")

    def get_fetchers(self, config: InfraDrawConfig) -> List[ResourceFetcher]:
        raise ProviderError("Azure provider is not yet implemented.")

    def get_diagram_builder(self) -> DiagramBuilder:
        raise ProviderError("Azure provider is not yet implemented.")
