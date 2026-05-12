"""Runtime helpers for the Prism data ingress singleton."""

from __future__ import annotations

import os

from .gateway import DataGateway
from .providers import AkshareProvider, EastmoneyProvider, SinaProvider, THSProvider
from .repositories import DatasetRepository
from .utils import default_dataset_repository_root


_GATEWAY: DataGateway | None = None


def get_dataset_repository() -> DatasetRepository:
    root = os.environ.get("PRISM_DATASET_REPOSITORY_ROOT", "").strip()
    return DatasetRepository(root or default_dataset_repository_root())


def get_data_gateway() -> DataGateway:
    global _GATEWAY
    if _GATEWAY is not None:
        return _GATEWAY
    repository = get_dataset_repository()
    providers = {
        "sina": SinaProvider(),
        "eastmoney": EastmoneyProvider(),
        "akshare": AkshareProvider(),
        "ths": THSProvider(),
    }
    _GATEWAY = DataGateway(providers=providers, repository=repository)
    return _GATEWAY


__all__ = ["get_data_gateway", "get_dataset_repository"]
