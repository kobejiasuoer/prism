from __future__ import annotations

import ast
from pathlib import Path

from quant.free_sources.canonical_mapping import all_provider_mappings, mappings_for_provider
from quant.free_sources.manifest import FreeSourceProvider


FS2_SOURCE_FILES = [
    Path("packages/quant/free_sources/provider_contracts.py"),
    Path("packages/quant/free_sources/canonical_mapping.py"),
]

FORBIDDEN_PROVIDER_OR_NETWORK_IMPORTS = {
    "akshare",
    "baostock",
    "curl_cffi",
    "httpx",
    "requests",
    "socket",
    "urllib",
}

FORBIDDEN_PRODUCTION_IMPORTS = {
    "apps",
    "stock_analyzer",
    "stock_screener",
}

FORBIDDEN_OUTPUT_OR_RAW_TERMS = {
    "data/quant",
    ".prism-private",
    "raw_archive",
    "raw_response",
    "rows",
    "records",
    "ohlcv_rows",
    "prices",
    "formal_label",
    "formal_excess_return",
    "formal_adjusted_return",
    "execution_realistic_return",
}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_fs2_modules_have_no_provider_or_network_imports() -> None:
    for source_file in FS2_SOURCE_FILES:
        assert imported_roots(source_file).isdisjoint(FORBIDDEN_PROVIDER_OR_NETWORK_IMPORTS)


def test_fs2_modules_have_no_production_page_or_ml_imports() -> None:
    for source_file in FS2_SOURCE_FILES:
        assert imported_roots(source_file).isdisjoint(FORBIDDEN_PRODUCTION_IMPORTS)


def test_fs2_modules_do_not_reference_output_or_raw_archive_terms() -> None:
    for source_file in FS2_SOURCE_FILES:
        text = source_file.read_text(encoding="utf-8")
        assert all(term not in text for term in FORBIDDEN_OUTPUT_OR_RAW_TERMS)


def test_provider_packages_are_not_imported_for_mapping_access() -> None:
    assert mappings_for_provider(FreeSourceProvider.BAOSTOCK)
    assert mappings_for_provider(FreeSourceProvider.AKSHARE)
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in FS2_SOURCE_FILES)
    assert "import baostock" not in source_text
    assert "import akshare" not in source_text


def test_mapping_access_does_not_write_data_quant() -> None:
    data_quant = Path("data/quant")
    before = sorted(path.relative_to(data_quant) for path in data_quant.rglob("*")) if data_quant.exists() else []
    assert all_provider_mappings()
    after = sorted(path.relative_to(data_quant) for path in data_quant.rglob("*")) if data_quant.exists() else []
    assert after == before


def test_no_disallowed_fs2_runtime_files_exist() -> None:
    disallowed = [
        Path("packages/quant/free_sources/baostock_adapter.py"),
        Path("packages/quant/free_sources/akshare_adapter.py"),
        Path("packages/quant/free_sources/run_field_poc.py"),
        Path("packages/quant/free_sources/report_generator.py"),
    ]
    assert not any(path.exists() for path in disallowed)
