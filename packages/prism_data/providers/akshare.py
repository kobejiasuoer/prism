"""AkShare provider adapter used for fallback and index constituents."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from prism_data.providers.common import BaseProvider, today_str
from prism_data.utils import digits_code, normalize_code


class AkshareProvider(BaseProvider):
    provider_name = "akshare"

    def _load_module(self):
        import akshare as ak  # type: ignore

        return ak

    def fetch_quote(self, code: str, **kwargs: Any):
        return self._error(dataset="quotes.snapshot", trade_date=today_str(), error="akshare quote unsupported")

    def fetch_quotes_batch(self, codes: list[str], **kwargs: Any):
        return self._error(dataset="quotes.batch", trade_date=today_str(), error="akshare quote batch unsupported")

    def fetch_kline(self, code: str, period: str = "daily", count: int = 120, **kwargs: Any):
        try:
            ak = self._load_module()
            symbol = digits_code(code)
            adjust = str(kwargs.get("adjust") or "qfq")
            frame = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust=adjust)
            if frame is None or frame.empty:
                return self._error(dataset="bars.daily", trade_date=today_str(), error=f"akshare empty kline for {symbol}")
            tail = frame.tail(count)
            rows = []
            for record in tail.to_dict(orient="records"):
                trade_date = str(record.get("日期") or "")[:10]
                rows.append(
                    {
                        "code": normalize_code(symbol),
                        "trade_date": trade_date,
                        "day": trade_date,
                        "open": float(record.get("开盘") or 0),
                        "high": float(record.get("最高") or 0),
                        "low": float(record.get("最低") or 0),
                        "close": float(record.get("收盘") or 0),
                        "volume": float(record.get("成交量") or 0),
                        "amount": float(record.get("成交额") or 0),
                        "change_pct": float(record.get("涨跌幅") or 0),
                    }
                )
            return self._ok(
                data=rows,
                dataset="bars.daily",
                trade_date=rows[-1]["trade_date"] if rows else today_str(),
                endpoint="akshare://stock_zh_a_hist",
                params_hash="",
                payload_hash="",
                ttl_seconds=3600,
                asof=datetime.now(),
            )
        except Exception as exc:
            return self._error(dataset="bars.daily", trade_date=today_str(), error=str(exc))

    def fetch_capital_flow(self, code: str, trade_date: str | None = None, **kwargs: Any):
        return self._error(dataset="capital_flow.daily", trade_date=trade_date or today_str(), error="akshare capital flow unsupported")

    def fetch_capital_flow_batch(self, codes: list[str], **kwargs: Any):
        return self._error(dataset="capital_flow.batch", trade_date=today_str(), error="akshare capital flow batch unsupported")

    def fetch_fundamentals(self, code: str, **kwargs: Any):
        return self._error(dataset="fundamentals.snapshot", trade_date=today_str(), error="akshare fundamentals unsupported")

    def fetch_fundamentals_batch(self, codes: list[str], **kwargs: Any):
        return self._error(dataset="fundamentals.batch", trade_date=today_str(), error="akshare fundamentals batch unsupported")

    def fetch_announcements(self, code: str, start_date: str | None = None, end_date: str | None = None, **kwargs: Any):
        return self._error(dataset="announcements.latest", trade_date=today_str(), error="akshare announcements unsupported")

    def fetch_news(self, code: str, count: int = 10, **kwargs: Any):
        return self._error(dataset="news.latest", trade_date=today_str(), error="akshare news unsupported")

    def search_stock(self, query: str, **kwargs: Any):
        return self._error(dataset="stock.search", trade_date=today_str(), error="akshare search unsupported")

    def fetch_market_pool(self, node: str, **kwargs: Any):
        return self._error(dataset="quotes.pool", trade_date=today_str(), error=f"akshare market pool unsupported for {node}")

    def fetch_index_constituents(self, symbol: str, **kwargs: Any):
        source = str(kwargs.get("source") or "csindex").strip().lower()
        try:
            ak = self._load_module()
            if source == "sina":
                frame = ak.index_stock_cons_sina(symbol=symbol)
            else:
                frame = ak.index_stock_cons_csindex(symbol=symbol)
            if frame is None or frame.empty:
                return self._error(dataset="index.constituents", trade_date=today_str(), error=f"akshare empty index constituents for {symbol}")
            rows = []
            for record in frame.to_dict(orient="records"):
                code = str(record.get("成分券代码") or record.get("code") or "").strip()
                if code.isdigit():
                    code = code.zfill(6)
                if len(code) != 6 or not code.isdigit():
                    continue
                rows.append(
                    {
                        "code": code,
                        "symbol": normalize_code(code),
                        "name": str(record.get("成分券名称") or record.get("name") or "").strip(),
                    }
                )
            return self._ok(
                data=rows,
                dataset="index.constituents",
                trade_date=today_str(),
                endpoint=f"akshare://index_stock_cons_{source}",
                params_hash="",
                payload_hash="",
                ttl_seconds=86400,
                asof=datetime.now(),
            )
        except Exception as exc:
            return self._error(dataset="index.constituents", trade_date=today_str(), error=str(exc))

    def fetch_sector_snapshot(self, sector_code: str, **kwargs: Any):
        return self._error(dataset="sector.snapshot", trade_date=today_str(), error=f"akshare sector snapshot unsupported for {sector_code}")


__all__ = ["AkshareProvider"]
