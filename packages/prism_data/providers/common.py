"""Shared HTTP and result helpers for provider adapters."""

from __future__ import annotations

from datetime import datetime
import json
import os
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import requests

from prism_data.contracts import DatasetStatus, ProviderResult, ProviderRole
from prism_data.utils import hash_payload


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def request_json_http(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: Any | None = None,
    timeout: int | float = 10,
    retries: int = 1,
    proxy_url: str | None = None,
) -> tuple[Any, str, str, str]:
    request_headers = {**DEFAULT_HEADERS, **(headers or {})}
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    params_hash = params_hash_from_url(url, {"method": method.upper(), "json": json_body})
    last_error: Exception | None = None
    for _ in range(retries + 1):
        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=request_headers,
                json=json_body,
                timeout=timeout,
                proxies=proxies,
            )
            response.raise_for_status()
            text = response.text
            if not text.strip():
                raise ValueError("empty response")
            return json.loads(text), redact_endpoint(url), params_hash, hash_payload(text)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(str(last_error) if last_error else "request failed")


def redact_endpoint(url: str) -> str:
    split = urlsplit(url)
    return f"{split.scheme}://{split.netloc}{split.path}"


def params_hash_from_url(url: str, extra: dict[str, Any] | None = None) -> str:
    split = urlsplit(url)
    payload: dict[str, Any] = dict(parse_qsl(split.query, keep_blank_values=True))
    if extra:
        payload.update(extra)
    return hash_payload(payload)


class BaseProvider:
    provider_name = "base"

    def __init__(self, *, timeout: int = 10, retries: int = 1, proxy_url: str | None = None):
        self.timeout = timeout
        self.retries = retries
        self.proxy_url = proxy_url or ""
        self.session = requests.Session()

    def _proxies(self) -> dict[str, str] | None:
        if not self.proxy_url:
            return None
        return {"http": self.proxy_url, "https": self.proxy_url}

    def _request_text(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        retries: int | None = None,
        encoding: str = "utf-8",
        referer: str | None = None,
        use_proxy: bool = False,
    ) -> tuple[str, str, str, str]:
        request_headers = {**DEFAULT_HEADERS, **(headers or {})}
        if referer:
            request_headers["Referer"] = referer
        last_error: Exception | None = None
        for _ in range((retries if retries is not None else self.retries) + 1):
            try:
                response = self.session.get(
                    url,
                    headers=request_headers,
                    timeout=timeout or self.timeout,
                    proxies=self._proxies() if use_proxy else None,
                )
                response.raise_for_status()
                text = response.content.decode(encoding, errors="replace")
                if not text.strip():
                    raise ValueError("empty response")
                return (
                    text,
                    redact_endpoint(url),
                    params_hash_from_url(url),
                    hash_payload(text),
                )
            except Exception as exc:
                last_error = exc
        raise RuntimeError(str(last_error) if last_error else "request failed")

    def _request_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        retries: int | None = None,
        referer: str | None = None,
        use_proxy: bool = False,
    ) -> tuple[Any, str, str, str]:
        text, endpoint, params_hash, payload_hash = self._request_text(
            url,
            headers=headers,
            timeout=timeout,
            retries=retries,
            referer=referer,
            use_proxy=use_proxy,
        )
        return json.loads(text), endpoint, params_hash, payload_hash

    def _ok(
        self,
        *,
        data: Any,
        dataset: str,
        trade_date: str,
        endpoint: str,
        params_hash: str,
        payload_hash: str,
        ttl_seconds: int,
        asof: datetime | None = None,
        quality_flags: list[str] | None = None,
        live_small_allowed: bool = True,
    ) -> ProviderResult:
        row_count = len(data) if isinstance(data, (list, tuple, set, dict)) else int(data is not None)
        return ProviderResult(
            status=DatasetStatus.OK,
            data=data,
            provider=self.provider_name,
            provider_role=ProviderRole.PRIMARY,
            dataset=dataset,
            trade_date=trade_date,
            fetched_at=datetime.now(),
            asof=asof,
            ttl_seconds=ttl_seconds,
            source_endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash or hash_payload(data),
            row_count=row_count,
            quality_flags=list(quality_flags or []),
            live_small_allowed=live_small_allowed,
        )

    def _error(
        self,
        *,
        dataset: str,
        trade_date: str,
        error: str,
        endpoint: str = "redacted",
        params_hash: str = "",
        payload_hash: str = "",
        quality_flags: list[str] | None = None,
    ) -> ProviderResult:
        return ProviderResult(
            status=DatasetStatus.FAILED,
            data=None,
            provider=self.provider_name,
            provider_role=ProviderRole.PRIMARY,
            dataset=dataset,
            trade_date=trade_date,
            fetched_at=datetime.now(),
            ttl_seconds=0,
            error=error,
            source_endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            row_count=0,
            quality_flags=list(quality_flags or ["fetch_failed"]),
            live_small_allowed=False,
        )


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def eastmoney_proxy_url() -> str:
    return (
        os.environ.get("OPENCLAW_EASTMONEY_PROXY")
        or os.environ.get("EASTMONEY_PROXY_URL")
        or os.environ.get("PRISM_PROXY_URL")
        or ""
    ).strip()


__all__ = [
    "BaseProvider",
    "DEFAULT_HEADERS",
    "eastmoney_proxy_url",
    "params_hash_from_url",
    "redact_endpoint",
    "request_json_http",
    "today_str",
]
