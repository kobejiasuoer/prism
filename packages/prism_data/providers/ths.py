"""THS HTML provider adapter used for explicit fallback provenance."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from prism_data.providers.common import BaseProvider, today_str
from prism_data.utils import digits_code


_THS_STOCK_PAGE = "https://stockpage.10jqka.com.cn/{code}/"


class THSProvider(BaseProvider):
    provider_name = "ths"

    def fetch_quote(self, code: str, **kwargs: Any):
        return self._error(dataset="quotes.snapshot", trade_date=today_str(), error="ths quote unsupported")

    def fetch_quotes_batch(self, codes: list[str], **kwargs: Any):
        return self._error(dataset="quotes.batch", trade_date=today_str(), error="ths quote batch unsupported")

    def fetch_kline(self, code: str, period: str = "daily", count: int = 120, **kwargs: Any):
        return self._error(dataset="bars.daily", trade_date=today_str(), error="ths kline unsupported")

    def fetch_capital_flow(self, code: str, trade_date: str | None = None, **kwargs: Any):
        target_date = trade_date or today_str()
        url = _THS_STOCK_PAGE.format(code=digits_code(code))
        try:
            text, endpoint, params_hash, payload_hash = self._request_text(url, headers={"Accept": "text/html"})
            inflow_match = re.search(r"总流入[：:](\s*<[^>]*>)*(\d[\d.]*)", text)
            outflow_match = re.search(r"总流出[：:](\s*<[^>]*>)*(\d[\d.]*)", text)
            net_match = re.search(r"净[\s]*额[：:](\s*<[^>]*>)*(-?\d[\d.]*)", text)
            net_yuan: float | None = None
            if net_match:
                net_yuan = float(net_match.group(2)) * 10000
            elif inflow_match and outflow_match:
                net_yuan = (float(inflow_match.group(2)) - float(outflow_match.group(2))) * 10000
            if net_yuan is None:
                return self._error(dataset="capital_flow.daily", trade_date=target_date, error=f"ths capital flow parse failed for {code}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
            row = {
                "date": target_date,
                "trade_date": target_date,
                "code": digits_code(code),
                "main_net": round(net_yuan / 10000, 2),
                "main_net_wan": round(net_yuan / 10000, 2),
                "main_net_yi": round(net_yuan / 1e8, 2),
                "super_large": 0.0,
                "super_large_wan": 0.0,
                "super_large_yi": 0.0,
                "unit": "wan_yuan",
            }
            return self._ok(
                data=[row],
                dataset="capital_flow.daily",
                trade_date=target_date,
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                ttl_seconds=1800,
                asof=datetime.now(),
                quality_flags=["ths_html_fallback"],
                live_small_allowed=False,
            )
        except Exception as exc:
            return self._error(dataset="capital_flow.daily", trade_date=target_date, error=str(exc))

    def fetch_capital_flow_batch(self, codes: list[str], **kwargs: Any):
        return self._error(dataset="capital_flow.batch", trade_date=today_str(), error="ths capital flow batch unsupported")

    def fetch_fundamentals(self, code: str, **kwargs: Any):
        url = _THS_STOCK_PAGE.format(code=digits_code(code))
        try:
            text, endpoint, params_hash, payload_hash = self._request_text(url, headers={"Accept": "text/html"})
            result: dict[str, Any] = {"code": digits_code(code), "trade_date": today_str()}
            pe_match = re.search(r"市盈率(?:TTM)?[：:]\s*</dt>\s*<dd>([\d.-]+)", text)
            pb_match = re.search(r"市净率[：:]\s*</dt>\s*<dd>([\d.-]+)", text)
            eps_match = re.search(r"每股收益[：:]\s*</dt>\s*<dd>([\d.-]+)元", text)
            profit_match = re.search(r"净利润[：:]\s*</dt>\s*<dd>([\d.-]+)亿元", text)
            rev_match = re.search(r"营业收入[：:]\s*</dt>\s*<dd>([\d.-]+)亿元", text)
            shares_match = re.search(r"总股本[：:]\s*</dt>\s*<dd>([\d.]+)亿", text)
            bvps_match = re.search(r"每股净资产[：:]\s*</dt>\s*<dd>([\d.]+)元", text)
            if pe_match:
                result["pe_ttm"] = float(pe_match.group(1))
                result["pe"] = float(pe_match.group(1))
            if pb_match:
                result["pb"] = float(pb_match.group(1))
            if eps_match:
                result["eps"] = float(eps_match.group(1))
            if profit_match:
                result["net_profit"] = float(profit_match.group(1))
            if rev_match:
                result["revenue"] = float(rev_match.group(1))
            if shares_match:
                result["total_shares_yi"] = float(shares_match.group(1))
            if bvps_match:
                result["bvps"] = float(bvps_match.group(1))
            if not any(key in result for key in ("pe_ttm", "pb", "net_profit", "revenue")):
                return self._error(dataset="fundamentals.snapshot", trade_date=today_str(), error=f"ths fundamentals parse failed for {code}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
            return self._ok(
                data=result,
                dataset="fundamentals.snapshot",
                trade_date=today_str(),
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                ttl_seconds=43200,
                asof=datetime.now(),
                quality_flags=["ths_html_fallback"],
                live_small_allowed=False,
            )
        except Exception as exc:
            return self._error(dataset="fundamentals.snapshot", trade_date=today_str(), error=str(exc))

    def fetch_fundamentals_batch(self, codes: list[str], **kwargs: Any):
        return self._error(dataset="fundamentals.batch", trade_date=today_str(), error="ths fundamentals batch unsupported")

    def fetch_announcements(self, code: str, start_date: str | None = None, end_date: str | None = None, **kwargs: Any):
        return self._error(dataset="announcements.latest", trade_date=today_str(), error="ths announcements unsupported")

    def fetch_news(self, code: str, count: int = 10, **kwargs: Any):
        return self._error(dataset="news.latest", trade_date=today_str(), error="ths news unsupported")

    def search_stock(self, query: str, **kwargs: Any):
        return self._error(dataset="stock.search", trade_date=today_str(), error="ths search unsupported")

    def fetch_market_pool(self, node: str, **kwargs: Any):
        return self._error(dataset="quotes.pool", trade_date=today_str(), error=f"ths market pool unsupported for {node}")

    def fetch_index_constituents(self, symbol: str, **kwargs: Any):
        return self._error(dataset="index.constituents", trade_date=today_str(), error=f"ths index constituents unsupported for {symbol}")

    def fetch_sector_snapshot(self, sector_code: str, **kwargs: Any):
        return self._error(dataset="sector.snapshot", trade_date=today_str(), error=f"ths sector snapshot unsupported for {sector_code}")


__all__ = ["THSProvider"]
