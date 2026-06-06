"""Unit tests for the Tushare Pro provider adapter.

These tests mock HTTP responses; they do not require or read a real token.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from prism_data.contracts import DatasetStatus  # noqa: E402
from prism_data.providers.tushare import TushareProvider  # noqa: E402
from prism_data.repositories import DatasetRepository  # noqa: E402
from prism_data.utils import hash_payload  # noqa: E402


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class TushareProviderTests(unittest.TestCase):
    def _local_manifest(self, dataset: str, trade_date: str, data) -> dict[str, object]:
        return {
            "schema_version": 1,
            "dataset": dataset,
            "provider": "tushare",
            "provider_role": "primary",
            "trade_date": trade_date,
            "fetched_at": f"{trade_date} 15:30:00",
            "asof": f"{trade_date} 15:30:00",
            "ttl_seconds": 86400,
            "status": "ok",
            "freshness_status": "fresh",
            "fallback_used": False,
            "row_count": len(data) if isinstance(data, (list, dict)) else 1,
            "payload_hash": hash_payload(data),
            "live_small_allowed": True,
            "quality_flags": [],
            "source_endpoint": "tinyshare://pro_api/raw_research_harvest",
            "params_hash": "unit-local-params",
            "license_scope": "authorized_tinyshare_proxy",
            "source_authority_ready": True,
        }

    def test_missing_token_returns_unavailable_without_http_call(self) -> None:
        provider = TushareProvider(token="")
        with mock.patch.object(provider.session, "post") as post:
            result = provider.fetch_adjustment_factor("600690", trade_date="2026-05-07")

        post.assert_not_called()
        self.assertEqual(result.status, DatasetStatus.UNAVAILABLE)
        self.assertFalse(result.live_small_allowed)
        self.assertIn("provider_token_missing", result.quality_flags)
        self.assertIn("Tushare token missing", result.error or "")

    def test_fetch_adjustment_factor_normalizes_success_rows(self) -> None:
        provider = TushareProvider(token="unit-test-token")
        response = FakeResponse({
            "code": 0,
            "msg": "",
            "data": {
                "fields": ["ts_code", "trade_date", "adj_factor"],
                "items": [["600690.SH", "20260507", 12.3456]],
            },
        })
        with mock.patch.object(provider.session, "post", return_value=response) as post:
            result = provider.fetch_adjustment_factor("sh600690", trade_date="2026-05-07")

        self.assertEqual(result.status, DatasetStatus.OK)
        self.assertEqual(result.dataset, "adjustment.factor")
        self.assertEqual(result.trade_date, "2026-05-07")
        self.assertEqual(result.provider, "tushare")
        self.assertEqual(result.license_scope, "authorized_tushare_token")
        self.assertEqual(result.data[0]["code"], "sh600690")
        self.assertEqual(result.data[0]["adj_factor"], 12.3456)
        request_body = post.call_args.kwargs["json"]
        self.assertEqual(request_body["api_name"], "adj_factor")
        self.assertEqual(request_body["token"], "unit-test-token")
        self.assertEqual(request_body["params"]["ts_code"], "600690.SH")

    def test_token_can_load_from_project_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".env").write_text("PRISM_TUSHARE_TOKEN=unit-env-token\n", encoding="utf-8")
            provider = TushareProvider()
            response = FakeResponse({
                "code": 0,
                "msg": "",
                "data": {
                    "fields": ["exchange", "cal_date", "is_open", "pretrade_date"],
                    "items": [["SSE", "20260507", 1, "20260506"]],
                },
            })
            with mock.patch.dict(
                "os.environ",
                {"PRISM_REPO_ROOT": tmpdir},
                clear=True,
            ), mock.patch.object(provider.session, "post", return_value=response) as post:
                result = provider.fetch_trade_calendar(trade_date="2026-05-07")

        self.assertEqual(result.status, DatasetStatus.OK)
        self.assertEqual(post.call_args.kwargs["json"]["token"], "unit-env-token")

    def test_permission_error_is_actionable(self) -> None:
        provider = TushareProvider(token="unit-test-token")
        response = FakeResponse({"code": -2001, "msg": "抱歉，您没有访问该接口的权限"})
        with mock.patch.object(provider.session, "post", return_value=response):
            result = provider.fetch_price_limit(trade_date="2026-05-07")

        self.assertEqual(result.status, DatasetStatus.UNAVAILABLE)
        self.assertFalse(result.live_small_allowed)
        self.assertIn("provider_permission_or_points_blocked", result.quality_flags)
        self.assertIn("权限", result.error or "")

    def test_rate_limit_error_is_actionable(self) -> None:
        provider = TushareProvider(token="unit-test-token", retries=0)
        response = FakeResponse({"code": -2002, "msg": "抱歉，您访问接口(index_daily)频率超限(1次/分钟)"})
        with mock.patch.object(provider.session, "post", return_value=response):
            result = provider.fetch_index_daily("000905", trade_date="2026-05-07")

        self.assertEqual(result.status, DatasetStatus.UNAVAILABLE)
        self.assertFalse(result.live_small_allowed)
        self.assertIn("provider_rate_limited", result.quality_flags)
        self.assertIn("频率超限", result.error or "")

    def test_fetch_index_daily_batch_scopes_each_index_request(self) -> None:
        provider = TushareProvider(token="unit-test-token")
        responses = [
            FakeResponse({
                "code": 0,
                "msg": "",
                "data": {
                    "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"],
                    "items": [
                        ["000300.SH", "20260507", 1, 2, 1, 2, 1.5, 0.5, 1.2, 100, 200],
                        ["000905.SH", "20260507", 3, 4, 3, 4, 3.5, 0.5, 1.4, 300, 400],
                    ],
                },
            }),
            FakeResponse({
                "code": 0,
                "msg": "",
                "data": {
                    "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"],
                    "items": [
                        ["000300.SH", "20260507", 1, 2, 1, 2, 1.5, 0.5, 1.2, 100, 200],
                        ["000905.SH", "20260507", 3, 4, 3, 4, 3.5, 0.5, 1.4, 300, 400],
                    ],
                },
            }),
        ]
        with mock.patch.object(provider.session, "post", side_effect=responses) as post:
            result = provider.fetch_index_daily_batch(["000300", "000905"], trade_date="2026-05-07")

        self.assertEqual(result.status, DatasetStatus.OK)
        self.assertTrue(result.live_small_allowed)
        self.assertEqual({row["ts_code"] for row in result.data}, {"000300.SH", "000905.SH"})
        calls = post.call_args_list
        self.assertEqual(len(calls), 2)
        bodies = [call.kwargs["json"] for call in calls]
        self.assertEqual([body["api_name"] for body in bodies], ["index_daily", "index_daily"])
        self.assertEqual([body["params"]["ts_code"] for body in bodies], ["000300.SH", "000905.SH"])

    def test_fetch_index_daily_batch_missing_symbol_does_not_mark_found_rows(self) -> None:
        provider = TushareProvider(token="unit-test-token")
        responses = [
            FakeResponse({
                "code": 0,
                "msg": "",
                "data": {
                    "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"],
                    "items": [
                        ["000300.SH", "20260507", 1, 2, 1, 2, 1.5, 0.5, 1.2, 100, 200],
                    ],
                },
            }),
            FakeResponse({
                "code": 0,
                "msg": "",
                "data": {
                    "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"],
                    "items": [],
                },
            }),
        ]
        with mock.patch.object(provider.session, "post", side_effect=responses):
            result = provider.fetch_index_daily_batch(["000300", "000905"], trade_date="2026-05-07")

        self.assertEqual(result.status, DatasetStatus.OK)
        self.assertFalse(result.live_small_allowed)
        self.assertIn("index_daily_batch_missing_symbols", result.quality_flags)
        self.assertEqual({row["ts_code"] for row in result.data}, {"000300.SH"})

    def test_fetch_index_daily_batch_all_failed_keeps_actionable_error(self) -> None:
        provider = TushareProvider(token="unit-test-token", retries=0)
        response = FakeResponse({
            "code": -2002,
            "msg": "抱歉，您访问接口(index_daily)频率超限(1次/分钟)",
        })
        with mock.patch.object(provider.session, "post", return_value=response):
            result = provider.fetch_index_daily_batch(["000300", "000905"], trade_date="2026-05-07")

        self.assertEqual(result.status, DatasetStatus.UNAVAILABLE)
        self.assertFalse(result.live_small_allowed)
        self.assertIn("provider_rate_limited", result.quality_flags)
        self.assertIn("频率超限", result.error or "")

    def test_legacy_unscoped_index_daily_response_is_not_required_for_batch(self) -> None:
        provider = TushareProvider(token="unit-test-token")
        response = FakeResponse({
            "code": 0,
            "msg": "",
            "data": {
                "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"],
                "items": [
                    ["000300.SH", "20260507", 1, 2, 1, 2, 1.5, 0.5, 1.2, 100, 200],
                    ["000905.SH", "20260507", 3, 4, 3, 4, 3.5, 0.5, 1.4, 300, 400],
                    ["399001.SZ", "20260507", 5, 6, 5, 6, 5.5, 0.5, 1.6, 500, 600],
                ],
            },
        })
        with mock.patch.object(provider.session, "post", return_value=response) as post:
            result = provider.fetch_index_daily_batch(["000300"], trade_date="2026-05-07")

        self.assertEqual(result.status, DatasetStatus.OK)
        self.assertTrue(result.live_small_allowed)
        self.assertEqual({row["ts_code"] for row in result.data}, {"000300.SH"})
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["api_name"], "index_daily")
        self.assertEqual(body["params"]["ts_code"], "000300.SH")

    def test_fetch_execution_flags_combines_limit_suspend_and_st(self) -> None:
        provider = TushareProvider(token="unit-test-token")
        responses = [
            FakeResponse({
                "code": 0,
                "msg": "",
                "data": {
                    "fields": ["ts_code", "trade_date", "up_limit", "down_limit"],
                    "items": [["600690.SH", "20260507", 30.0, 24.0]],
                },
            }),
            FakeResponse({
                "code": 0,
                "msg": "",
                "data": {
                    "fields": ["ts_code", "trade_date", "suspend_timing", "suspend_type"],
                    "items": [["000625.SZ", "20260507", "全天", "S"]],
                },
            }),
            FakeResponse({
                "code": 0,
                "msg": "",
                "data": {
                    "fields": ["ts_code", "name", "trade_date", "type", "type_name"],
                    "items": [["000625.SZ", "*ST测试", "20260507", "ST", "风险警示板"]],
                },
            }),
        ]
        with mock.patch.object(provider.session, "post", side_effect=responses) as post:
            result = provider.fetch_execution_flags(
                trade_date="2026-05-07",
                codes=["sh600690", "sz000625"],
            )

        self.assertEqual(result.status, DatasetStatus.OK)
        self.assertEqual(result.dataset, "execution.flags")
        self.assertEqual(result.trade_date, "2026-05-07")
        self.assertTrue(result.live_small_allowed)
        self.assertEqual(post.call_args_list[0].kwargs["json"]["api_name"], "stk_limit")
        self.assertEqual(post.call_args_list[1].kwargs["json"]["api_name"], "suspend_d")
        self.assertEqual(post.call_args_list[2].kwargs["json"]["api_name"], "stock_st")
        by_code = {row["code"]: row for row in result.data}
        self.assertEqual(by_code["sh600690"]["up_limit"], 30.0)
        self.assertFalse(by_code["sh600690"]["is_suspended"])
        self.assertTrue(by_code["sz000625"]["is_suspended"])
        self.assertFalse(by_code["sz000625"]["is_tradable"])
        self.assertTrue(by_code["sz000625"]["is_st"])
        self.assertNotIn("execution_flags_price_limit_missing", result.quality_flags)

    def test_duplicate_stk_limit_call_reuses_process_cache(self) -> None:
        provider = TushareProvider(token="unit-test-token", request_cache_seconds=60)
        responses = [
            FakeResponse({
                "code": 0,
                "msg": "",
                "data": {
                    "fields": ["ts_code", "trade_date", "up_limit", "down_limit"],
                    "items": [["600690.SH", "20260507", 30.0, 24.0]],
                },
            }),
            FakeResponse({
                "code": 0,
                "msg": "",
                "data": {
                    "fields": ["ts_code", "trade_date", "suspend_timing", "suspend_type"],
                    "items": [],
                },
            }),
            FakeResponse({
                "code": 0,
                "msg": "",
                "data": {
                    "fields": ["ts_code", "name", "trade_date", "type", "type_name"],
                    "items": [],
                },
            }),
        ]
        with mock.patch.object(provider.session, "post", side_effect=responses) as post:
            price_limit = provider.fetch_price_limit(trade_date="2026-05-07")
            execution_flags = provider.fetch_execution_flags(
                trade_date="2026-05-07",
                codes=["sh600690"],
            )

        self.assertEqual(price_limit.status, DatasetStatus.OK)
        self.assertEqual(execution_flags.status, DatasetStatus.OK)
        self.assertEqual(
            [call.kwargs["json"]["api_name"] for call in post.call_args_list],
            ["stk_limit", "suspend_d", "stock_st"],
        )
        self.assertEqual(execution_flags.data[0]["up_limit"], 30.0)

    def test_fetch_execution_flags_can_reuse_price_limit_rows(self) -> None:
        provider = TushareProvider(token="unit-test-token")
        responses = [
            FakeResponse({
                "code": 0,
                "msg": "",
                "data": {
                    "fields": ["ts_code", "trade_date", "suspend_timing", "suspend_type"],
                    "items": [],
                },
            }),
            FakeResponse({
                "code": 0,
                "msg": "",
                "data": {
                    "fields": ["ts_code", "name", "trade_date", "type", "type_name"],
                    "items": [],
                },
            }),
        ]
        with mock.patch.object(provider.session, "post", side_effect=responses) as post:
            result = provider.fetch_execution_flags(
                trade_date="2026-05-07",
                codes=["sh600690"],
                price_limit_rows=[
                    {
                        "code": "sh600690",
                        "ts_code": "600690.SH",
                        "trade_date": "2026-05-07",
                        "up_limit": 30.0,
                        "down_limit": 24.0,
                    }
                ],
            )

        self.assertEqual(result.status, DatasetStatus.OK)
        self.assertEqual(
            [call.kwargs["json"]["api_name"] for call in post.call_args_list],
            ["suspend_d", "stock_st"],
        )
        self.assertEqual(result.data[0]["up_limit"], 30.0)

    def test_fetch_capital_flow_prefers_promoted_local_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = DatasetRepository(tmpdir)
            rows = [
                {"code": "600690", "symbol": "sh600690", "ts_code": "600690.SH", "trade_date": "2026-05-06", "main_net": 1.0},
                {"code": "600690", "symbol": "sh600690", "ts_code": "600690.SH", "trade_date": "2026-05-07", "main_net": 2.0},
            ]
            repository.save_dataset(
                "capital_flow.daily",
                "2026-05-07",
                "600690",
                rows,
                self._local_manifest("capital_flow.daily", "2026-05-07", rows),
            )
            with mock.patch.dict("os.environ", {"PRISM_DATASET_REPOSITORY_ROOT": tmpdir}, clear=False):
                provider = TushareProvider(token="")
                with mock.patch.object(provider.session, "post") as post:
                    result = provider.fetch_capital_flow("sh600690", trade_date="2026-05-07", count=1)

        post.assert_not_called()
        self.assertEqual(result.status, DatasetStatus.OK)
        self.assertEqual(result.provider, "tushare")
        self.assertEqual(result.license_scope, "authorized_tinyshare_proxy")
        self.assertEqual(len(result.data), 1)
        self.assertEqual(result.data[0]["trade_date"], "2026-05-07")
        self.assertEqual(result.data[0]["main_net"], 2.0)

    def test_fetch_fundamentals_batch_filters_promoted_local_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = DatasetRepository(tmpdir)
            rows = {
                "600690": {"code": "600690", "symbol": "sh600690", "trade_date": "2026-05-07", "pe_ttm": 12.3, "pb": 1.8},
                "000001": {"code": "000001", "symbol": "sz000001", "trade_date": "2026-05-07", "pe_ttm": 7.7, "pb": 0.8},
            }
            repository.save_dataset(
                "fundamentals.batch",
                "2026-05-07",
                "tinyshare-hs300-zz500",
                rows,
                self._local_manifest("fundamentals.batch", "2026-05-07", rows),
            )
            with mock.patch.dict("os.environ", {"PRISM_DATASET_REPOSITORY_ROOT": tmpdir}, clear=False):
                provider = TushareProvider(token="")
                with mock.patch.object(provider.session, "post") as post:
                    result = provider.fetch_fundamentals_batch(["600690"], trade_date="2026-05-07")

        post.assert_not_called()
        self.assertEqual(result.status, DatasetStatus.OK)
        self.assertEqual(set(result.data), {"600690"})
        self.assertEqual(result.data["600690"]["pe_ttm"], 12.3)
        self.assertTrue(result.live_small_allowed)


if __name__ == "__main__":
    unittest.main()
