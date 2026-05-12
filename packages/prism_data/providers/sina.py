"""Sina provider adapter."""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any
from urllib.parse import quote

from prism_data.contracts import ProviderResult
from prism_data.providers.common import BaseProvider, today_str
from prism_data.utils import digits_code, normalize_code, sina_symbol


_SINA_QUOTE_URL = "https://hq.sinajs.cn/list={symbols}"
_SINA_KLINE_URL = (
    "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={count}"
)
_SINA_SUGGEST_URL = "https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15&key={query}"
_SINA_NODE_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "Market_Center.getHQNodeData?page={page}&num=100&sort=changepercent&asc=0&node={node}&symbol="
)


class SinaProvider(BaseProvider):
    provider_name = "sina"

    def fetch_quote(self, code: str, **kwargs: Any) -> ProviderResult:
        batch = self.fetch_quotes_batch([code], **kwargs)
        if batch.status.value != "ok":
            return batch
        data = list(batch.data or [])
        if not data:
            return self._error(dataset="quotes.snapshot", trade_date=today_str(), error=f"quote missing for {code}")
        item = dict(data[0])
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
        symbols = ",".join(sina_symbol(code) for code in codes)
        url = _SINA_QUOTE_URL.format(symbols=symbols)
        try:
            text, endpoint, params_hash, payload_hash = self._request_text(
                url,
                referer="https://finance.sina.com.cn",
                encoding="gbk",
            )
            rows = []
            asof: datetime | None = None
            for line in text.splitlines():
                match = re.match(r'var hq_str_(\w+)="(.*)";', line.strip())
                if not match:
                    continue
                symbol, payload = match.groups()
                fields = payload.split(",")
                if len(fields) < 32 or not fields[0]:
                    continue
                quote_time = None
                if fields[30] and fields[31]:
                    try:
                        quote_time = datetime.strptime(
                            f"{fields[30]} {fields[31]}",
                            "%Y-%m-%d %H:%M:%S",
                        )
                    except ValueError:
                        quote_time = None
                if quote_time and (asof is None or quote_time > asof):
                    asof = quote_time
                prev_close = float(fields[2] or 0)
                price = float(fields[3] or 0)
                rows.append(
                    {
                        "code": symbol,
                        "name": fields[0],
                        "open": float(fields[1] or 0),
                        "prev_close": prev_close,
                        "price": price,
                        "change": round(price - prev_close, 4),
                        "change_pct": round(((price - prev_close) / prev_close) * 100, 2) if prev_close else 0.0,
                        "high": float(fields[4] or 0),
                        "low": float(fields[5] or 0),
                        "volume": int(float(fields[8] or 0)),
                        "amount": float(fields[9] or 0),
                        "buy1_vol": int(float(fields[10] or 0)),
                        "buy1_price": float(fields[11] or 0),
                        "sell1_vol": int(float(fields[20] or 0)),
                        "sell1_price": float(fields[21] or 0),
                        "trade_date": fields[30] or today_str(),
                        "timestamp": f"{fields[30]} {fields[31]}".strip(),
                    }
                )
            if not rows:
                return self._error(dataset="quotes.batch", trade_date=today_str(), error="empty sina quotes", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
            trade_date = max((item.get("trade_date") or today_str()) for item in rows)
            return self._ok(
                data=rows,
                dataset="quotes.batch",
                trade_date=trade_date,
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                ttl_seconds=900,
                asof=asof,
            )
        except Exception as exc:
            return self._error(dataset="quotes.batch", trade_date=today_str(), error=str(exc))

    def fetch_kline(self, code: str, period: str = "daily", count: int = 120, **kwargs: Any) -> ProviderResult:
        symbol = sina_symbol(code)
        url = _SINA_KLINE_URL.format(symbol=symbol, count=count)
        try:
            text, endpoint, params_hash, payload_hash = self._request_text(
                url,
                referer="https://finance.sina.com.cn",
            )
            normalized_text = text.strip()
            if normalized_text == "null":
                return self._error(dataset="bars.daily", trade_date=today_str(), error=f"kline missing for {symbol}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
            try:
                rows = json.loads(normalized_text)
            except json.JSONDecodeError:
                fixed = re.sub(r"(\w+):", r'"\1":', normalized_text)
                rows = json.loads(fixed)
            output = []
            for row in rows or []:
                trade_date = str(row.get("day") or row.get("date") or "")[:10]
                output.append(
                    {
                        "code": symbol,
                        "trade_date": trade_date,
                        "day": trade_date,
                        "open": float(row.get("open") or 0),
                        "high": float(row.get("high") or 0),
                        "low": float(row.get("low") or 0),
                        "close": float(row.get("close") or 0),
                        "volume": float(row.get("volume") or 0),
                    }
                )
            if not output:
                return self._error(dataset="bars.daily", trade_date=today_str(), error=f"empty kline for {symbol}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
            trade_date = output[-1]["trade_date"] or today_str()
            asof = datetime.strptime(trade_date, "%Y-%m-%d") if trade_date else None
            return self._ok(
                data=output,
                dataset="bars.daily",
                trade_date=trade_date,
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                ttl_seconds=3600,
                asof=asof,
            )
        except Exception as exc:
            return self._error(dataset="bars.daily", trade_date=today_str(), error=str(exc))

    def fetch_capital_flow(self, code: str, trade_date: str | None = None, **kwargs: Any) -> ProviderResult:
        return self._error(dataset="capital_flow.daily", trade_date=trade_date or today_str(), error="sina capital flow unsupported")

    def fetch_capital_flow_batch(self, codes: list[str], **kwargs: Any) -> ProviderResult:
        return self._error(dataset="capital_flow.batch", trade_date=today_str(), error="sina capital flow batch unsupported")

    def fetch_fundamentals(self, code: str, **kwargs: Any) -> ProviderResult:
        return self._error(dataset="fundamentals.snapshot", trade_date=today_str(), error="sina fundamentals unsupported")

    def fetch_fundamentals_batch(self, codes: list[str], **kwargs: Any) -> ProviderResult:
        return self._error(dataset="fundamentals.batch", trade_date=today_str(), error="sina fundamentals batch unsupported")

    def fetch_announcements(self, code: str, start_date: str | None = None, end_date: str | None = None, **kwargs: Any) -> ProviderResult:
        return self._error(dataset="announcements.latest", trade_date=today_str(), error="sina announcements unsupported")

    def fetch_news(self, code: str, count: int = 10, **kwargs: Any) -> ProviderResult:
        return self._error(dataset="news.latest", trade_date=today_str(), error="sina news unsupported")

    def search_stock(self, query: str, **kwargs: Any) -> ProviderResult:
        url = _SINA_SUGGEST_URL.format(query=quote(str(query or "").strip()))
        try:
            text, endpoint, params_hash, payload_hash = self._request_text(
                url,
                referer="https://finance.sina.com.cn",
                encoding="gbk",
                timeout=kwargs.get("timeout") or self.timeout,
                retries=int(kwargs.get("retries") if kwargs.get("retries") is not None else 0),
            )
            match = re.search(r'"(.*)"', text, re.S)
            items = []
            seen: set[str] = set()
            if match:
                for row in str(match.group(1) or "").split(";"):
                    fields = [field.strip() for field in row.split(",")]
                    if len(fields) < 4:
                        continue
                    name, _type_code, raw_code, symbol = fields[:4]
                    if len(raw_code) != 6 or not raw_code.isdigit() or raw_code in seen:
                        continue
                    seen.add(raw_code)
                    items.append(
                        {
                            "code": raw_code,
                            "name": name or raw_code,
                            "market": symbol[:2],
                            "sina": symbol,
                            "type": "stock",
                        }
                    )
            return self._ok(
                data=items,
                dataset="stock.search",
                trade_date=today_str(),
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                ttl_seconds=86400,
            )
        except Exception as exc:
            return self._error(dataset="stock.search", trade_date=today_str(), error=str(exc))

    def fetch_market_pool(self, node: str, **kwargs: Any) -> ProviderResult:
        pages = int(kwargs.get("pages") or 3)
        aggregated: list[dict[str, Any]] = []
        payload_hashes: list[str] = []
        endpoint = ""
        params_hash = ""
        for page in range(1, pages + 1):
            url = _SINA_NODE_URL.format(page=page, node=node)
            try:
                text, endpoint, params_hash, page_hash = self._request_text(
                    url,
                    referer="https://finance.sina.com.cn",
                )
                payload_hashes.append(page_hash)
                rows = json.loads(text)
            except Exception:
                continue
            for item in rows or []:
                raw_code = str(item.get("code") or "").strip()
                if len(raw_code) != 6 or not raw_code.isdigit():
                    continue
                symbol = normalize_code(raw_code)
                aggregated.append(
                    {
                        "code": raw_code,
                        "name": item.get("name", ""),
                        "symbol": symbol,
                        "price": float(item.get("trade") or 0),
                        "prev": float(item.get("settlement") or 0),
                        "open": float(item.get("open") or 0),
                        "high": float(item.get("high") or 0),
                        "low": float(item.get("low") or 0),
                        "change_pct": float(item.get("changepercent") or 0),
                        "volume": float(item.get("volume") or 0),
                        "amount": float(item.get("amount") or 0),
                        "pe": float(item.get("per") or 0),
                        "pb": float(item.get("pb") or 0),
                        "mktcap": float(item.get("mktcap") or 0),
                        "turnover": float(item.get("turnoverratio") or 0),
                        "source_pool": node,
                    }
                )
        if not aggregated:
            return self._error(dataset="quotes.pool", trade_date=today_str(), error=f"empty market pool for {node}")
        payload_hash = ",".join(payload_hashes)[:1024]
        return self._ok(
            data=aggregated,
            dataset="quotes.pool",
            trade_date=today_str(),
            endpoint=endpoint or "redacted",
            params_hash=params_hash,
            payload_hash=payload_hash,
            ttl_seconds=900,
        )

    def fetch_index_constituents(self, symbol: str, **kwargs: Any) -> ProviderResult:
        return self._error(dataset="index.constituents", trade_date=today_str(), error=f"sina index constituents unsupported for {symbol}")

    def fetch_sector_snapshot(self, sector_code: str, **kwargs: Any) -> ProviderResult:
        return self._error(dataset="sector.snapshot", trade_date=today_str(), error=f"sina sector snapshot unsupported for {sector_code}")


__all__ = ["SinaProvider"]
