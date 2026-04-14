"""Abstract provider interface and factory.

Every cloud backend (AWS, Azure, GCP …) implements ``CloudProvider`` and
registers itself with ``ProviderFactory``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Type

from infra_draw.core.config import InfraDrawConfig
from infra_draw.core.exceptions import ProviderError


class ResourceFetcher(ABC):
    """Fetches one *category* of resources (compute, network …)."""

    @property
    @abstractmethod
    def resource_types(self) -> List[str]:
        """Canonical resource-type names this fetcher can return."""

    @abstractmethod
    def fetch(self, config: InfraDrawConfig) -> Dict[str, List[Dict[str, Any]]]:
        """Return ``{resource_type: [resource_dict, …]}``."""


class DiagramBuilder(ABC):
    """Turns fetched resource dicts into ``diagrams`` graph objects."""

    @abstractmethod
    def build(
        self,
        resources: Dict[str, List[Dict[str, Any]]],
        config: InfraDrawConfig,
        *,
        region: str = "",
        vpc_id: str | None = None,
    ) -> str:
        """Return the path of the generated image file."""


class CloudProvider(ABC):
    """Facade that wires up fetchers + builder for one cloud."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def get_fetchers(self, config: InfraDrawConfig) -> List[ResourceFetcher]: ...

    @abstractmethod
    def get_diagram_builder(self) -> DiagramBuilder: ...

    @abstractmethod
    def list_regions(self, config: InfraDrawConfig) -> List[str]:
        """Return list of enabled/available regions."""

    @abstractmethod
    def validate_credentials(self, config: InfraDrawConfig) -> None:
        """Raise ``CredentialsError`` if creds are bad."""


class ProviderFactory:
    """Registry of cloud providers keyed by lowercase name."""

    _registry: Dict[str, Type[CloudProvider]] = {}

    @classmethod
    def register(cls, provider_cls: Type[CloudProvider]) -> Type[CloudProvider]:
        name = provider_cls.__name__.replace("Provider", "").lower()
        if not name:
            name = "unknown"
        cls._registry[name] = provider_cls
        return provider_cls

    @classmethod
    def get(cls, name: str, config: InfraDrawConfig) -> CloudProvider:
        key = name.lower()
        if key not in cls._registry:
            raise ProviderError(
                f"Unknown provider '{name}'. Available: {', '.join(sorted(cls._registry))}"
            )
        return cls._registry[key]()

    @classmethod
    def available(cls) -> List[str]:
        return sorted(cls._registry)
