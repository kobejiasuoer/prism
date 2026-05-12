"""Unified external data ingress for Prism."""

from .gateway import DataGateway, GatewayResult
from .manifest import DataManifest, build_pipeline_manifest, load_manifest_file, write_sidecar_manifest
from .repositories import DatasetRepository

__version__ = "0.2.0"

__all__ = [
    "DataGateway",
    "DataManifest",
    "DatasetRepository",
    "GatewayResult",
    "build_pipeline_manifest",
    "load_manifest_file",
    "write_sidecar_manifest",
]
