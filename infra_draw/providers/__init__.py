"""Cloud provider implementations.

Importing this package auto-registers every provider that ships with
infra-draw so that ``ProviderFactory.get(name)`` works immediately.
"""

import infra_draw.providers.aws  # noqa: F401 – registers AWSProvider
import infra_draw.providers.azure  # noqa: F401
import infra_draw.providers.gcp  # noqa: F401
