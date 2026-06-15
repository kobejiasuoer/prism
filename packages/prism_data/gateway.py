"""Unified data gateway with persistence, manifests, and fallback handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from .contracts import DatasetStatus, ProviderResult, ProviderRole
from .manifest import get_dataset_definition, manifest_from_provider_result
from .repositories import DatasetRepository
from .utils import hash_payload


@dataclass
class GatewayResult:
    dataset: str
    request_key: str
    data: Any
    manifest: dict[str, Any]
    data_path: str | None
    manifest_path: str
    provider_result: ProviderResult
    attempt_manifests: list[str] = field(default_factory=list)


class DataGateway:
    def __init__(self, providers: dict[str, Any], repository: DatasetRepository):
        self.providers = providers
        self.repository = repository

    def fetch_quote(self, code: str, *, trade_date: str, dataset: str = "quotes.snapshot", key: str | None = None, allow_fallback: bool = True, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=key or code,
                method_name="fetch_quote",
                primary_args=(code,),
                method_kwargs=kwargs,
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=key or code,
            method_name="fetch_quote",
            primary_args=(code,),
            allow_fallback=allow_fallback,
            method_kwargs=kwargs,
        )

    def fetch_quotes_batch(self, codes: list[str], *, trade_date: str, dataset: str = "quotes.batch", key: str | None = None, allow_fallback: bool = True, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        request_key = key or f"batch-{hash_payload(sorted(codes))[:12]}"
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=request_key,
                method_name="fetch_quotes_batch",
                primary_args=(codes,),
                method_kwargs=kwargs,
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=request_key,
            method_name="fetch_quotes_batch",
            primary_args=(codes,),
            allow_fallback=allow_fallback,
            method_kwargs=kwargs,
        )

    def fetch_kline(self, code: str, *, trade_date: str, period: str = "daily", count: int = 120, dataset: str = "bars.daily", key: str | None = None, allow_fallback: bool = True, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=key or code,
                method_name="fetch_kline",
                primary_args=(code,),
                method_kwargs={"period": period, "count": count, "trade_date": trade_date, **kwargs},
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=key or code,
            method_name="fetch_kline",
            primary_args=(code,),
            allow_fallback=allow_fallback,
            method_kwargs={"period": period, "count": count, "trade_date": trade_date, **kwargs},
        )

    def fetch_trade_calendar(self, *, trade_date: str, exchange: str = "SSE", start_date: str | None = None, end_date: str | None = None, dataset: str = "trade_calendar", key: str | None = None, allow_fallback: bool = True, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        request_key = key or f"{exchange}-{start_date or trade_date}-{end_date or trade_date}"
        method_kwargs = {"exchange": exchange, "start_date": start_date or trade_date, "end_date": end_date or trade_date, "trade_date": trade_date, **kwargs}
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=request_key,
                method_name="fetch_trade_calendar",
                primary_args=(),
                method_kwargs=method_kwargs,
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=request_key,
            method_name="fetch_trade_calendar",
            primary_args=(),
            allow_fallback=allow_fallback,
            method_kwargs=method_kwargs,
        )

    def fetch_index_daily(self, symbol: str, *, trade_date: str, start_date: str | None = None, end_date: str | None = None, dataset: str = "benchmark.index_daily", key: str | None = None, allow_fallback: bool = True, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        request_key = key or f"{symbol}-{start_date or ''}-{end_date or trade_date}"
        method_kwargs = {"start_date": start_date, "end_date": end_date or trade_date, "trade_date": trade_date, **kwargs}
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=request_key,
                method_name="fetch_index_daily",
                primary_args=(symbol,),
                method_kwargs=method_kwargs,
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=request_key,
            method_name="fetch_index_daily",
            primary_args=(symbol,),
            allow_fallback=allow_fallback,
            method_kwargs=method_kwargs,
        )

    def fetch_adjustment_factor(self, code: str, *, trade_date: str, start_date: str | None = None, end_date: str | None = None, dataset: str = "adjustment.factor", key: str | None = None, allow_fallback: bool = False, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        request_key = key or f"{code}-{start_date or ''}-{end_date or trade_date}"
        method_kwargs = {"start_date": start_date, "end_date": end_date or trade_date, "trade_date": trade_date, **kwargs}
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=request_key,
                method_name="fetch_adjustment_factor",
                primary_args=(code,),
                method_kwargs=method_kwargs,
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=request_key,
            method_name="fetch_adjustment_factor",
            primary_args=(code,),
            allow_fallback=allow_fallback,
            method_kwargs=method_kwargs,
        )

    def fetch_price_limit(self, *, trade_date: str, code: str | None = None, dataset: str = "price_limit.daily", key: str | None = None, allow_fallback: bool = False, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        request_key = key or (f"{trade_date}-{code}" if code else trade_date)
        method_kwargs = {"code": code, **kwargs}
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=request_key,
                method_name="fetch_price_limit",
                primary_args=(trade_date,),
                method_kwargs=method_kwargs,
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=request_key,
            method_name="fetch_price_limit",
            primary_args=(trade_date,),
            allow_fallback=allow_fallback,
            method_kwargs=method_kwargs,
        )

    def fetch_execution_flags(self, *, trade_date: str, codes: list[str] | None = None, dataset: str = "execution.flags", key: str | None = None, allow_fallback: bool = False, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        normalized_codes = list(codes or [])
        request_key = key or f"{trade_date}-execution-{hash_payload(sorted(normalized_codes))[:12] if normalized_codes else 'market'}"
        method_kwargs = {"codes": normalized_codes, **kwargs}
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=request_key,
                method_name="fetch_execution_flags",
                primary_args=(trade_date,),
                method_kwargs=method_kwargs,
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=request_key,
            method_name="fetch_execution_flags",
            primary_args=(trade_date,),
            allow_fallback=allow_fallback,
            method_kwargs=method_kwargs,
        )

    def fetch_capital_flow(self, code: str, *, trade_date: str, dataset: str = "capital_flow.daily", key: str | None = None, allow_fallback: bool = True, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=key or code,
                method_name="fetch_capital_flow",
                primary_args=(code,),
                method_kwargs={"trade_date": trade_date, **kwargs},
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=key or code,
            method_name="fetch_capital_flow",
            primary_args=(code,),
            allow_fallback=allow_fallback,
            method_kwargs={"trade_date": trade_date, **kwargs},
        )

    def fetch_capital_flow_batch(self, codes: list[str], *, trade_date: str, dataset: str = "capital_flow.batch", key: str | None = None, allow_fallback: bool = False, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        request_key = key or f"capital-batch-{hash_payload(sorted(codes))[:12]}"
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=request_key,
                method_name="fetch_capital_flow_batch",
                primary_args=(codes,),
                method_kwargs={"trade_date": trade_date, **kwargs},
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=request_key,
            method_name="fetch_capital_flow_batch",
            primary_args=(codes,),
            allow_fallback=allow_fallback,
            method_kwargs={"trade_date": trade_date, **kwargs},
        )

    def fetch_fundamentals(self, code: str, *, trade_date: str, dataset: str = "fundamentals.snapshot", key: str | None = None, allow_fallback: bool = True, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=key or code,
                method_name="fetch_fundamentals",
                primary_args=(code,),
                method_kwargs={"trade_date": trade_date, **kwargs},
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=key or code,
            method_name="fetch_fundamentals",
            primary_args=(code,),
            allow_fallback=allow_fallback,
            method_kwargs={"trade_date": trade_date, **kwargs},
        )

    def fetch_fundamentals_batch(self, codes: list[str], *, trade_date: str, dataset: str = "fundamentals.batch", key: str | None = None, allow_fallback: bool = False, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        request_key = key or f"fundamentals-batch-{hash_payload(sorted(codes))[:12]}"
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=request_key,
                method_name="fetch_fundamentals_batch",
                primary_args=(codes,),
                method_kwargs={"trade_date": trade_date, **kwargs},
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=request_key,
            method_name="fetch_fundamentals_batch",
            primary_args=(codes,),
            allow_fallback=allow_fallback,
            method_kwargs={"trade_date": trade_date, **kwargs},
        )

    def fetch_announcements(self, code: str, *, trade_date: str, start_date: str | None = None, end_date: str | None = None, dataset: str = "announcements.latest", key: str | None = None, allow_fallback: bool = False, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=key or code,
                method_name="fetch_announcements",
                primary_args=(code,),
                method_kwargs={"start_date": start_date, "end_date": end_date, **kwargs},
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=key or code,
            method_name="fetch_announcements",
            primary_args=(code,),
            allow_fallback=allow_fallback,
            method_kwargs={"start_date": start_date, "end_date": end_date, **kwargs},
        )

    def fetch_news(self, code: str, *, trade_date: str, count: int = 10, dataset: str = "news.latest", key: str | None = None, allow_fallback: bool = False, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=key or code,
                method_name="fetch_news",
                primary_args=(code,),
                method_kwargs={"count": count, **kwargs},
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=key or code,
            method_name="fetch_news",
            primary_args=(code,),
            allow_fallback=allow_fallback,
            method_kwargs={"count": count, **kwargs},
        )

    def search_stock(self, query: str, *, trade_date: str, dataset: str = "stock.search", key: str | None = None, allow_fallback: bool = False, provider_name: str | None = None, **kwargs: Any) -> GatewayResult:
        if provider_name:
            return self._run_single_provider(
                provider_name=provider_name,
                dataset=dataset,
                trade_date=trade_date,
                request_key=key or f"search-{hash_payload(query)[:12]}",
                method_name="search_stock",
                primary_args=(query,),
                method_kwargs=kwargs,
            )
        return self._run(
            dataset=dataset,
            trade_date=trade_date,
            request_key=key or f"search-{hash_payload(query)[:12]}",
            method_name="search_stock",
            primary_args=(query,),
            allow_fallback=allow_fallback,
            method_kwargs=kwargs,
        )

    def fetch_market_pool(self, node: str, *, trade_date: str, pages: int = 3, dataset: str = "quotes.pool", key: str | None = None, provider_name: str = "sina", **kwargs: Any) -> GatewayResult:
        return self._run_single_provider(
            provider_name=provider_name,
            dataset=dataset,
            trade_date=trade_date,
            request_key=key or node,
            method_name="fetch_market_pool",
            primary_args=(node,),
            method_kwargs={"pages": pages, **kwargs},
        )

    def fetch_index_constituents(self, symbol: str, *, trade_date: str, source: str = "csindex", dataset: str = "index.constituents", key: str | None = None, provider_name: str = "akshare", **kwargs: Any) -> GatewayResult:
        return self._run_single_provider(
            provider_name=provider_name,
            dataset=dataset,
            trade_date=trade_date,
            request_key=key or f"{symbol}-{source}",
            method_name="fetch_index_constituents",
            primary_args=(symbol,),
            method_kwargs={"source": source, **kwargs},
        )

    def fetch_sector_snapshot(self, sector_code: str, *, trade_date: str, dataset: str = "sector.snapshot", key: str | None = None, provider_name: str = "eastmoney", **kwargs: Any) -> GatewayResult:
        return self._run_single_provider(
            provider_name=provider_name,
            dataset=dataset,
            trade_date=trade_date,
            request_key=key or sector_code,
            method_name="fetch_sector_snapshot",
            primary_args=(sector_code,),
            method_kwargs=kwargs,
        )

    def _run(
        self,
        *,
        dataset: str,
        trade_date: str,
        request_key: str,
        method_name: str,
        primary_args: tuple[Any, ...],
        allow_fallback: bool,
        method_kwargs: dict[str, Any],
    ) -> GatewayResult:
        definition = get_dataset_definition(dataset)
        if definition is None:
            error_result = self._error_result(dataset=dataset, trade_date=trade_date, request_key=request_key, provider="none", provider_role=ProviderRole.PRIMARY, error=f"unknown dataset: {dataset}")
            return self._finalize(
                request_key=request_key,
                expected_trade_date=trade_date,
                result=error_result,
                attempt_manifest_paths=[],
            )

        provider_names = [definition.primary_provider]
        if allow_fallback:
            provider_names.extend(definition.fallback_providers)

        attempt_manifest_paths: list[str] = []
        last_result: ProviderResult | None = None
        for index, provider_name in enumerate(provider_names):
            role = ProviderRole.PRIMARY if index == 0 else ProviderRole.FALLBACK
            provider = self.providers.get(provider_name)
            if provider is None:
                result = self._error_result(
                    dataset=dataset,
                    trade_date=trade_date,
                    request_key=request_key,
                    provider=provider_name,
                    provider_role=role,
                    error=f"provider unavailable: {provider_name}",
                )
            else:
                result = self._invoke_provider(
                    provider_name=provider_name,
                    provider_role=role,
                    provider=provider,
                    dataset=dataset,
                    trade_date=trade_date,
                    request_key=request_key,
                    method_name=method_name,
                    args=primary_args,
                    kwargs=method_kwargs,
                )
            attempt_key = f"{request_key}__{provider_name}__{role.value}"
            attempt_manifest = self._manifest_for_result(
                result=result,
                expected_trade_date=trade_date,
                live_small_allowed=self._effective_live_small_allowed(result, trade_date),
            )
            attempt_path = self.repository.save_manifest(dataset, trade_date, attempt_key, attempt_manifest)
            attempt_manifest_paths.append(str(attempt_path.resolve()))
            last_result = result
            if result.status == DatasetStatus.OK:
                return self._finalize(
                    request_key=request_key,
                    expected_trade_date=trade_date,
                    result=result,
                    attempt_manifest_paths=attempt_manifest_paths,
                )

        return self._finalize(
            request_key=request_key,
            expected_trade_date=trade_date,
            result=last_result or self._error_result(dataset=dataset, trade_date=trade_date, request_key=request_key, provider="none", provider_role=ProviderRole.PRIMARY, error="all providers failed"),
            attempt_manifest_paths=attempt_manifest_paths,
        )

    def _run_single_provider(
        self,
        *,
        provider_name: str,
        dataset: str,
        trade_date: str,
        request_key: str,
        method_name: str,
        primary_args: tuple[Any, ...],
        method_kwargs: dict[str, Any],
    ) -> GatewayResult:
        provider = self.providers.get(provider_name)
        if provider is None:
            result = self._error_result(
                dataset=dataset,
                trade_date=trade_date,
                request_key=request_key,
                provider=provider_name,
                provider_role=ProviderRole.PRIMARY,
                error=f"provider unavailable: {provider_name}",
            )
        else:
            result = self._invoke_provider(
                provider_name=provider_name,
                provider_role=ProviderRole.PRIMARY,
                provider=provider,
                dataset=dataset,
                trade_date=trade_date,
                request_key=request_key,
                method_name=method_name,
                args=primary_args,
                kwargs=method_kwargs,
            )
        return self._finalize(
            request_key=request_key,
            expected_trade_date=trade_date,
            result=result,
            attempt_manifest_paths=[],
        )

    def _invoke_provider(
        self,
        *,
        provider_name: str,
        provider_role: ProviderRole,
        provider: Any,
        dataset: str,
        trade_date: str,
        request_key: str,
        method_name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> ProviderResult:
        try:
            fetcher: Callable[..., ProviderResult] = getattr(provider, method_name)
            result = fetcher(*args, **kwargs)
        except Exception as exc:
            return self._error_result(
                dataset=dataset,
                trade_date=trade_date,
                request_key=request_key,
                provider=provider_name,
                provider_role=provider_role,
                error=str(exc),
            )
        result.dataset = dataset
        result.trade_date = str(result.trade_date or trade_date)
        result.provider = provider_name
        result.provider_role = provider_role
        result.request_key = request_key
        if not result.payload_hash:
            result.payload_hash = hash_payload(result.data)
        if not result.row_count:
            result.row_count = self._row_count(result.data)
        result.ttl_seconds = self._effective_ttl_seconds(result.dataset, result.ttl_seconds)
        return result

    def _manifest_for_result(
        self,
        *,
        result: ProviderResult,
        expected_trade_date: str,
        live_small_allowed: bool,
        data_path: str | None = None,
        manifest_path: str | None = None,
    ) -> dict[str, Any]:
        return manifest_from_provider_result(
            result,
            expected_trade_date=expected_trade_date,
            live_small_allowed=live_small_allowed,
            data_path=data_path,
            manifest_path=manifest_path,
        )

    def _finalize(
        self,
        *,
        request_key: str,
        expected_trade_date: str,
        result: ProviderResult,
        attempt_manifest_paths: list[str],
    ) -> GatewayResult:
        live_small_allowed = self._effective_live_small_allowed(result, expected_trade_date)
        manifest = self._manifest_for_result(
            result=result,
            expected_trade_date=expected_trade_date,
            live_small_allowed=live_small_allowed,
        )
        data_path: str | None = None
        display_key = self._display_request_key_for_non_authority_result(
            result=result,
            manifest=manifest,
            expected_trade_date=expected_trade_date,
            request_key=request_key,
        )
        manifest_formal_ready = self._manifest_is_formal_ready(manifest, expected_trade_date)
        existing_formal_ready = self._existing_manifest_is_formal_ready(
            dataset=result.dataset,
            trade_date=expected_trade_date,
            request_key=request_key,
        )
        if result.status == DatasetStatus.OK and result.data is not None:
            if (display_key or existing_formal_ready) and not manifest_formal_ready:
                display_key = display_key or f"{request_key}__{result.provider}__display"
                display_manifest = dict(manifest)
                display_manifest["request_key"] = display_key
                if existing_formal_ready:
                    display_manifest["preserved_existing_formal_manifest"] = True
                    display_manifest["preserved_formal_request_key"] = request_key
                else:
                    display_manifest["isolated_non_authority_result"] = True
                    display_manifest["formal_request_key"] = request_key
                data_file, manifest_file = self.repository.save_dataset(
                    result.dataset,
                    expected_trade_date,
                    display_key,
                    result.data,
                    display_manifest,
                )
                data_path = str(data_file.resolve())
                manifest_path = str(manifest_file.resolve())
                manifest = display_manifest
                manifest["data_path"] = data_path
                manifest["manifest_path"] = manifest_path
                return GatewayResult(
                    dataset=result.dataset,
                    request_key=request_key,
                    data=result.data,
                    manifest=manifest,
                    data_path=data_path,
                    manifest_path=manifest_path,
                    provider_result=result,
                    attempt_manifests=attempt_manifest_paths,
                )
            data_file, manifest_file = self.repository.save_dataset(
                result.dataset,
                expected_trade_date,
                request_key,
                result.data,
                manifest,
            )
            data_path = str(data_file.resolve())
            manifest_path = str(manifest_file.resolve())
            manifest["data_path"] = data_path
            manifest["manifest_path"] = manifest_path
        else:
            if existing_formal_ready:
                manifest_path = str(
                    self.repository.dataset_paths(result.dataset, expected_trade_date, request_key)[1].resolve()
                )
                manifest["manifest_path"] = manifest_path
                manifest["preserved_existing_formal_manifest"] = True
            elif display_key:
                display_manifest = dict(manifest)
                display_manifest["request_key"] = display_key
                display_manifest["isolated_non_authority_result"] = True
                display_manifest["formal_request_key"] = request_key
                manifest_file = self.repository.save_manifest(
                    result.dataset,
                    expected_trade_date,
                    display_key,
                    display_manifest,
                )
                manifest_path = str(manifest_file.resolve())
                manifest = display_manifest
                manifest["manifest_path"] = manifest_path
            else:
                manifest_file = self.repository.save_manifest(result.dataset, expected_trade_date, request_key, manifest)
                manifest_path = str(manifest_file.resolve())
                manifest["manifest_path"] = manifest_path
        return GatewayResult(
            dataset=result.dataset,
            request_key=request_key,
            data=result.data,
            manifest=manifest,
            data_path=data_path,
            manifest_path=manifest_path,
            provider_result=result,
            attempt_manifests=attempt_manifest_paths,
        )

    def _existing_manifest_is_formal_ready(
        self,
        *,
        dataset: str,
        trade_date: str,
        request_key: str,
    ) -> bool:
        existing = self.repository.load_manifest(dataset, trade_date, request_key)
        if not existing:
            return False
        return self._manifest_is_formal_ready(existing, trade_date)

    @staticmethod
    def _manifest_is_formal_ready(manifest: dict[str, Any], trade_date: str) -> bool:
        return (
            str(manifest.get("status") or "").lower() == DatasetStatus.OK.value
            and str(manifest.get("trade_date") or "") == trade_date
            and bool(manifest.get("source_authority_ready"))
            and bool(manifest.get("formal_decision_allowed"))
            and bool(manifest.get("payload_hash"))
        )

    @staticmethod
    def _display_request_key_for_non_authority_result(
        *,
        result: ProviderResult,
        manifest: dict[str, Any],
        expected_trade_date: str,
        request_key: str,
    ) -> str:
        if DataGateway._manifest_is_formal_ready(manifest, expected_trade_date):
            return ""
        definition = get_dataset_definition(result.dataset)
        if definition is None or definition.source_lane not in {"authoritative_daily", "execution"}:
            return ""
        target = (
            definition.target_authority_provider
            or definition.authority_provider
            or definition.primary_provider
            or ""
        )
        if not target or str(result.provider or "") == str(target):
            return ""
        return f"{request_key}__{result.provider}__display"

    def _effective_live_small_allowed(self, result: ProviderResult, expected_trade_date: str) -> bool:
        if result.provider_role == ProviderRole.FALLBACK and not bool(result.extra.get("allow_live_small_fallback")):
            return False
        if result.status != DatasetStatus.OK:
            return False
        if str(result.trade_date or "") != expected_trade_date:
            return False
        return bool(result.live_small_allowed)

    def _effective_ttl_seconds(self, dataset: str, provider_ttl: int) -> int:
        definition = get_dataset_definition(dataset)
        if definition is None:
            return int(provider_ttl or 0)
        registry_ttl = int(definition.ttl_intraday or provider_ttl or 0)
        if provider_ttl:
            return min(int(provider_ttl), registry_ttl)
        return registry_ttl

    @staticmethod
    def _row_count(data: Any) -> int:
        if data is None:
            return 0
        if isinstance(data, (list, tuple, set)):
            return len(data)
        if isinstance(data, dict):
            return len(data)
        return 1

    @staticmethod
    def _error_result(
        *,
        dataset: str,
        trade_date: str,
        request_key: str,
        provider: str,
        provider_role: ProviderRole,
        error: str,
    ) -> ProviderResult:
        return ProviderResult(
            status=DatasetStatus.FAILED,
            data=None,
            provider=provider,
            provider_role=provider_role,
            dataset=dataset,
            trade_date=trade_date,
            fetched_at=datetime.now(),
            ttl_seconds=0,
            error=error,
            live_small_allowed=False,
            request_key=request_key,
            quality_flags=["fetch_failed"],
        )


__all__ = ["DataGateway", "GatewayResult"]
