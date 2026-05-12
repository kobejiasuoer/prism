"""Eastmoney provider adapter."""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any
from urllib.parse import quote

from prism_data.contracts import ProviderResult
from prism_data.providers.common import BaseProvider, eastmoney_proxy_url, today_str
from prism_data.utils import digits_code, eastmoney_secid, normalize_code


_EM_ULIST_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids={secids}&fields={fields}"
_EM_CAPITAL_HISTORY_URL = (
    "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get?"
    "secid={secid}&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56&lmt={limit}"
)
_EM_CAPITAL_KLINE_URL = (
    "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?"
    "secid={secid}&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57,f58&klt=101&fqt=1&lmt={limit}"
)
_EM_FUNDAMENTALS_URL = (
    "https://push2.eastmoney.com/api/qt/stock/get?"
    "secid={secid}&fields=f43,f57,f58,f116,f117,f127,f128,f163,f167,f168,f169,f170,f173,f186"
)
_EM_SECTOR_URL = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get?"
    "secid=90.{sector_code}&fields1=f1,f2,f3,f4,f5,f6"
    "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20990101&lmt=1"
)
_EM_ANNOUNCEMENTS_URL = (
    "https://np-anotice-stock.eastmoney.com/api/security/ann?"
    "sr=-1&page_size={count}&page_index=1&ann_type=A&client_source=web&stock_list={code}"
)
_EM_NEWS_URL = (
    "https://search-api-web.eastmoney.com/search/jsonp"
    "?cb=jQuery&param=%7B%22uid%22%3A%22%22%2C%22keyword%22%3A%22{keyword}%22"
    "%2C%22type%22%3A%5B%22cmsArticleWebOld%22%5D%2C%22client%22%3A%22web%22"
    "%2C%22clientType%22%3A%22web%22%2C%22clientVersion%22%3A%22curr%22"
    "%2C%22param%22%3A%7B%22cmsArticleWebOld%22%3A%7B%22searchScope%22%3A%22default%22"
    "%2C%22sort%22%3A%22default%22%2C%22pageIndex%22%3A1%2C%22pageSize%22%3A{count}"
    "%2C%22preTag%22%3A%22%22%2C%22postTag%22%3A%22%22%7D%7D%7D"
)


class EastmoneyProvider(BaseProvider):
    provider_name = "eastmoney"

    def __init__(self, **kwargs: Any):
        super().__init__(proxy_url=eastmoney_proxy_url(), **kwargs)

    def fetch_quote(self, code: str, **kwargs: Any) -> ProviderResult:
        batch = self.fetch_quotes_batch([code], **kwargs)
        if batch.status.value != "ok":
            return batch
        rows = list(batch.data or [])
        if not rows:
            return self._error(dataset="quotes.snapshot", trade_date=today_str(), error=f"quote missing for {code}")
        item = dict(rows[0])
        return self._ok(
            data=item,
            dataset="quotes.snapshot",
            trade_date=item.get("trade_date") or today_str(),
            endpoint=batch.source_endpoint,
            params_hash=batch.params_hash,
            payload_hash=batch.payload_hash,
            ttl_seconds=900,
            asof=batch.asof,
        )

    def fetch_quotes_batch(self, codes: list[str], **kwargs: Any) -> ProviderResult:
        secids = ",".join(eastmoney_secid(code) for code in codes)
        url = _EM_ULIST_URL.format(secids=secids, fields="f12,f14,f2,f3,f17,f15,f16,f5,f6,f8,f9,f20,f18")
        try:
            data, endpoint, params_hash, payload_hash = self._request_json(
                url,
                referer="https://data.eastmoney.com",
                use_proxy=bool(self.proxy_url),
            )
            diff = ((data or {}).get("data") or {}).get("diff", [])
            rows = []
            for item in diff or []:
                raw_code = str(item.get("f12") or "").strip()
                if len(raw_code) != 6 or not raw_code.isdigit():
                    continue
                symbol = normalize_code(raw_code)
                prev_close = float(item.get("f18") or 0)
                price = float(item.get("f2") or 0)
                rows.append(
                    {
                        "code": raw_code,
                        "symbol": symbol,
                        "name": item.get("f14") or raw_code,
                        "price": price,
                        "change": round(price - prev_close, 4),
                        "change_pct": float(item.get("f3") or 0),
                        "open": float(item.get("f17") or 0),
                        "high": float(item.get("f15") or 0),
                        "low": float(item.get("f16") or 0),
                        "volume": float(item.get("f5") or 0) * 100,
                        "amount": float(item.get("f6") or 0),
                        "turnover": float(item.get("f8") or 0),
                        "pe_ttm": float(item.get("f9") or 0) if item.get("f9") not in (None, "", "-") else None,
                        "mktcap": float(item.get("f20") or 0) if item.get("f20") not in (None, "", "-") else None,
                        "prev_close": prev_close,
                        "trade_date": today_str(),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
            if not rows:
                return self._error(dataset="quotes.batch", trade_date=today_str(), error="empty eastmoney quotes", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
            return self._ok(
                data=rows,
                dataset="quotes.batch",
                trade_date=today_str(),
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                ttl_seconds=900,
                asof=datetime.now(),
            )
        except Exception as exc:
            return self._error(dataset="quotes.batch", trade_date=today_str(), error=str(exc))

    def fetch_kline(self, code: str, period: str = "daily", count: int = 120, **kwargs: Any) -> ProviderResult:
        return self._error(dataset="bars.daily", trade_date=today_str(), error="eastmoney kline not primary in this pipeline")

    def fetch_capital_flow(self, code: str, trade_date: str | None = None, **kwargs: Any) -> ProviderResult:
        target_date = trade_date or today_str()
        secid = eastmoney_secid(code)
        mode = str(kwargs.get("mode") or "history").strip().lower()
        limit = int(kwargs.get("count") or kwargs.get("limit") or 5)
        if mode == "snapshot":
            batch = self.fetch_capital_flow_batch([code], **kwargs)
            if batch.status.value != "ok":
                return batch
            item = ((batch.data or {}).get(digits_code(code)) or {})
            if not item:
                return self._error(dataset="capital_flow.daily", trade_date=target_date, error=f"capital flow snapshot missing for {code}")
            return self._ok(
                data=[item],
                dataset="capital_flow.daily",
                trade_date=item.get("date") or target_date,
                endpoint=batch.source_endpoint,
                params_hash=batch.params_hash,
                payload_hash=batch.payload_hash,
                ttl_seconds=900,
                asof=datetime.now(),
            )
        url = _EM_CAPITAL_HISTORY_URL.format(secid=secid, limit=limit)
        try:
            data, endpoint, params_hash, payload_hash = self._request_json(
                url,
                referer="https://data.eastmoney.com",
                use_proxy=bool(self.proxy_url),
            )
            klines = ((data or {}).get("data") or {}).get("klines", [])
            rows = []
            for item in klines or []:
                parts = str(item).split(",")
                if len(parts) < 6:
                    continue
                rows.append(
                    {
                        "date": parts[0],
                        "trade_date": parts[0],
                        "code": digits_code(code),
                        "main_net": round(float(parts[1]) / 10000, 2),
                        "main_net_wan": round(float(parts[1]) / 10000, 2),
                        "main_net_yi": round(float(parts[1]) / 1e8, 2),
                        "super_large": round(float(parts[2]) / 10000, 2),
                        "super_large_wan": round(float(parts[2]) / 10000, 2),
                        "super_large_yi": round(float(parts[2]) / 1e8, 2),
                        "mid_large_net": round(float(parts[3]) / 10000, 2),
                        "retail_net": round(float(parts[4]) / 10000, 2),
                        "small_net": round(float(parts[5]) / 10000, 2),
                        "unit": "wan_yuan",
                    }
                )
            if not rows:
                return self._error(dataset="capital_flow.daily", trade_date=target_date, error=f"empty capital flow history for {code}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
            return self._ok(
                data=rows,
                dataset="capital_flow.daily",
                trade_date=rows[-1]["trade_date"] or target_date,
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                ttl_seconds=1800,
                asof=datetime.now(),
            )
        except Exception as exc:
            return self._error(dataset="capital_flow.daily", trade_date=target_date, error=str(exc))

    def fetch_capital_flow_batch(self, codes: list[str], **kwargs: Any) -> ProviderResult:
        secids = ",".join(eastmoney_secid(code) for code in codes)
        url = _EM_ULIST_URL.format(secids=secids, fields="f12,f62,f66")
        try:
            data, endpoint, params_hash, payload_hash = self._request_json(
                url,
                referer="https://data.eastmoney.com",
                use_proxy=bool(self.proxy_url),
            )
            diff = ((data or {}).get("data") or {}).get("diff", [])
            rows: dict[str, dict[str, Any]] = {}
            trade_date = today_str()
            for item in diff or []:
                raw_code = str(item.get("f12") or "").strip()
                if len(raw_code) != 6 or not raw_code.isdigit():
                    continue
                main_raw = item.get("f62")
                super_raw = item.get("f66")
                if main_raw in (None, "-", "") and super_raw in (None, "-", ""):
                    continue
                rows[raw_code] = {
                    "date": trade_date,
                    "trade_date": trade_date,
                    "code": raw_code,
                    "main_net": round(float(main_raw or 0) / 10000, 2),
                    "main_net_wan": round(float(main_raw or 0) / 10000, 2),
                    "main_net_yi": round(float(main_raw or 0) / 1e8, 2),
                    "super_large": round(float(super_raw or 0) / 10000, 2),
                    "super_large_wan": round(float(super_raw or 0) / 10000, 2),
                    "super_large_yi": round(float(super_raw or 0) / 1e8, 2),
                    "unit": "wan_yuan",
                }
            return self._ok(
                data=rows,
                dataset="capital_flow.batch",
                trade_date=trade_date,
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                ttl_seconds=900,
                asof=datetime.now(),
            )
        except Exception as exc:
            return self._error(dataset="capital_flow.batch", trade_date=today_str(), error=str(exc))

    def fetch_fundamentals(self, code: str, **kwargs: Any) -> ProviderResult:
        secid = eastmoney_secid(code)
        url = _EM_FUNDAMENTALS_URL.format(secid=secid)
        try:
            data, endpoint, params_hash, payload_hash = self._request_json(
                url,
                referer="https://data.eastmoney.com",
                use_proxy=bool(self.proxy_url),
            )
            row = (data or {}).get("data") or {}
            if not row:
                return self._error(dataset="fundamentals.snapshot", trade_date=today_str(), error=f"empty fundamentals for {code}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
            result = {
                "code": digits_code(code),
                "symbol": normalize_code(code),
                "name": row.get("f58") or digits_code(code),
                "price": float(row.get("f43") or 0) / 100 if row.get("f43") not in (None, "", "-") else None,
                "pe": float(row.get("f167") or 0) / 10 if row.get("f167") not in (None, "", "-") else None,
                "pe_ttm": float(row.get("f163") or 0) / 100 if row.get("f163") not in (None, "", "-") else (float(row.get("f167") or 0) / 10 if row.get("f167") not in (None, "", "-") else None),
                "pb": float(row.get("f168") or 0) / 100 if row.get("f168") not in (None, "", "-") else None,
                "roe": float(row.get("f169") or 0) / 100 if row.get("f169") not in (None, "", "-") else None,
                "margin": float(row.get("f170") or 0) / 100 if row.get("f170") not in (None, "", "-") else None,
                "gross_margin": float(row.get("f186") or 0) if row.get("f186") not in (None, "", "-") else None,
                "total_mv": float(row.get("f116") or 0) / 1e8 if row.get("f116") not in (None, "", "-") else None,
                "total_mv_yi": float(row.get("f116") or 0) / 1e8 if row.get("f116") not in (None, "", "-") else None,
                "circ_mv_yi": float(row.get("f117") or 0) / 1e8 if row.get("f117") not in (None, "", "-") else None,
                "industry": row.get("f127") or None,
                "concept": row.get("f128") or None,
                "trade_date": today_str(),
            }
            return self._ok(
                data=result,
                dataset="fundamentals.snapshot",
                trade_date=today_str(),
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                ttl_seconds=43200,
                asof=datetime.now(),
            )
        except Exception as exc:
            return self._error(dataset="fundamentals.snapshot", trade_date=today_str(), error=str(exc))

    def fetch_fundamentals_batch(self, codes: list[str], **kwargs: Any) -> ProviderResult:
        secids = ",".join(eastmoney_secid(code) for code in codes)
        url = _EM_ULIST_URL.format(secids=secids, fields="f12,f2,f9,f20")
        try:
            data, endpoint, params_hash, payload_hash = self._request_json(
                url,
                referer="https://data.eastmoney.com",
                use_proxy=bool(self.proxy_url),
            )
            diff = ((data or {}).get("data") or {}).get("diff", [])
            rows: dict[str, dict[str, Any]] = {}
            for item in diff or []:
                raw_code = str(item.get("f12") or "").strip()
                if len(raw_code) != 6 or not raw_code.isdigit():
                    continue
                rows[raw_code] = {
                    "code": raw_code,
                    "price": float(item.get("f2") or 0) if item.get("f2") not in (None, "", "-") else None,
                    "pe": float(item.get("f9") or 0) if item.get("f9") not in (None, "", "-") else None,
                    "pe_ttm": float(item.get("f9") or 0) if item.get("f9") not in (None, "", "-") else None,
                    "total_mv": float(item.get("f20") or 0) / 1e8 if item.get("f20") not in (None, "", "-") else None,
                    "total_mv_yi": float(item.get("f20") or 0) / 1e8 if item.get("f20") not in (None, "", "-") else None,
                    "trade_date": today_str(),
                }
            return self._ok(
                data=rows,
                dataset="fundamentals.batch",
                trade_date=today_str(),
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                ttl_seconds=43200,
                asof=datetime.now(),
            )
        except Exception as exc:
            return self._error(dataset="fundamentals.batch", trade_date=today_str(), error=str(exc))

    def fetch_announcements(self, code: str, start_date: str | None = None, end_date: str | None = None, **kwargs: Any) -> ProviderResult:
        count = int(kwargs.get("count") or 5)
        url = _EM_ANNOUNCEMENTS_URL.format(count=count, code=digits_code(code))
        try:
            data, endpoint, params_hash, payload_hash = self._request_json(
                url,
                referer="https://data.eastmoney.com",
                use_proxy=bool(self.proxy_url),
            )
            items = ((data or {}).get("data") or {}).get("list", [])
            output = []
            latest_trade_date = today_str()
            for item in items[:count]:
                notice_date = str(item.get("notice_date") or "")[:10]
                if notice_date:
                    latest_trade_date = max(latest_trade_date, notice_date)
                title = str(item.get("title") or "")
                clean_title = re.sub(r"^[\w\u4e00-\u9fff]+[:：]", "", title).strip()
                output.append(
                    {
                        "date": notice_date,
                        "publish_date": notice_date,
                        "title": clean_title or title,
                        "source": item.get("source") or "东方财富",
                    }
                )
            return self._ok(
                data=output,
                dataset="announcements.latest",
                trade_date=latest_trade_date,
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                ttl_seconds=14400,
                asof=datetime.now(),
            )
        except Exception as exc:
            return self._error(dataset="announcements.latest", trade_date=today_str(), error=str(exc))

    def fetch_news(self, code: str, count: int = 10, **kwargs: Any) -> ProviderResult:
        name = str(kwargs.get("name") or "").strip()
        keyword = quote(f"{name}{digits_code(code)}" if name else digits_code(code))
        url = _EM_NEWS_URL.format(keyword=keyword, count=count)
        try:
            text, endpoint, params_hash, payload_hash = self._request_text(
                url,
                referer="https://so.eastmoney.com",
                use_proxy=bool(self.proxy_url),
            )
            match = re.search(r"jQuery\((.*)\)", text, re.S)
            if not match:
                return self._error(dataset="news.latest", trade_date=today_str(), error=f"eastmoney news parse failed for {code}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
            data = json.loads(match.group(1))
            items = (((data or {}).get("result") or {}).get("cmsArticleWebOld") or [])[:count]
            output = []
            latest_trade_date = today_str()
            for item in items:
                publish_date = str(item.get("date") or "")[:10]
                if publish_date:
                    latest_trade_date = max(latest_trade_date, publish_date)
                output.append(
                    {
                        "date": publish_date,
                        "publish_date": publish_date,
                        "title": item.get("title") or "",
                        "content": str(item.get("content") or "")[:150],
                        "source": item.get("mediaName") or "",
                    }
                )
            return self._ok(
                data=output,
                dataset="news.latest",
                trade_date=latest_trade_date,
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                ttl_seconds=14400,
                asof=datetime.now(),
            )
        except Exception as exc:
            return self._error(dataset="news.latest", trade_date=today_str(), error=str(exc))

    def search_stock(self, query: str, **kwargs: Any) -> ProviderResult:
        return self._error(dataset="stock.search", trade_date=today_str(), error=f"eastmoney search unsupported for {query}")

    def fetch_market_pool(self, node: str, **kwargs: Any) -> ProviderResult:
        return self._error(dataset="quotes.pool", trade_date=today_str(), error=f"eastmoney market pool unsupported for {node}")

    def fetch_index_constituents(self, symbol: str, **kwargs: Any) -> ProviderResult:
        return self._error(dataset="index.constituents", trade_date=today_str(), error=f"eastmoney index constituents unsupported for {symbol}")

    def fetch_sector_snapshot(self, sector_code: str, **kwargs: Any) -> ProviderResult:
        url = _EM_SECTOR_URL.format(sector_code=str(sector_code or "").strip())
        try:
            data, endpoint, params_hash, payload_hash = self._request_json(
                url,
                referer="https://data.eastmoney.com",
                use_proxy=bool(self.proxy_url),
            )
            payload = (data or {}).get("data") or {}
            klines = payload.get("klines") or []
            if not klines:
                return self._error(dataset="sector.snapshot", trade_date=today_str(), error=f"empty sector snapshot for {sector_code}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
            parts = str(klines[0]).split(",")
            if len(parts) < 8:
                return self._error(dataset="sector.snapshot", trade_date=today_str(), error=f"invalid sector snapshot for {sector_code}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
            row = {
                "sector_code": str(sector_code or "").strip(),
                "name": payload.get("name") or "",
                "trade_date": parts[0],
                "change_pct": round(float(parts[7] or 0), 2),
            }
            return self._ok(
                data=row,
                dataset="sector.snapshot",
                trade_date=str(row.get("trade_date") or today_str()),
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                ttl_seconds=1800,
                asof=datetime.now(),
            )
        except Exception as exc:
            return self._error(dataset="sector.snapshot", trade_date=today_str(), error=str(exc))


__all__ = ["EastmoneyProvider"]
