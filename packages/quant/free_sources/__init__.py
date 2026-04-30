"""Non-production free-source metadata contracts.

This package intentionally contains schema, contract, and redaction helpers
only. It must not import provider SDKs or perform network calls.
"""

from .contracts import BLOCKED_CAPABILITIES, FIELD_CONTRACTS
from .manifest import (
    AdapterLayer,
    HashMethod,
    ManifestStatus,
    ManifestValidationError,
    PitAsOfStatus,
    ProviderRole,
    FreeSourceProvider,
    REQUIRED_MANIFEST_FIELDS,
    validate_manifest,
)

__all__ = [
    "AdapterLayer",
    "BLOCKED_CAPABILITIES",
    "FIELD_CONTRACTS",
    "FreeSourceProvider",
    "HashMethod",
    "ManifestStatus",
    "ManifestValidationError",
    "PitAsOfStatus",
    "ProviderRole",
    "REQUIRED_MANIFEST_FIELDS",
    "validate_manifest",
]
