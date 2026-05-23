"""Unified external data ingress for Prism."""

from .data_capability_matrix import (
    DataCapabilityEntry,
    build_data_capability_matrix,
    build_dataset_capability,
    data_capability_matrix_as_dict,
)
from .gateway import DataGateway, GatewayResult
from .manifest import DataManifest, build_pipeline_manifest, load_manifest_file, write_sidecar_manifest
from .repositories import DatasetRepository

__version__ = "0.2.0"

__all__ = [
    "DataCapabilityEntry",
    "DataGateway",
    "DataManifest",
    "DatasetRepository",
    "GatewayResult",
    "build_data_capability_matrix",
    "build_dataset_capability",
    "build_pipeline_manifest",
    "data_capability_matrix_as_dict",
    "load_manifest_file",
    "write_sidecar_manifest",
]
