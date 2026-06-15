from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_ROOT = REPO_ROOT / "packages"
SCRIPTS_ROOT = REPO_ROOT / "apps" / "scripts"
for import_path in (str(PACKAGES_ROOT), str(SCRIPTS_ROOT)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from prism_data.env import load_project_env, project_env_path

load_project_env(root=REPO_ROOT)

import stock_parameter_config as parameter_config

from control_panel.dashboard_data import (
    APP_STATE_REPOSITORY,
    CONTROL_PANEL_LOGS_DIR,
    CONTROL_PANEL_LOG_DIRS,
    CONTROL_PANEL_RUNS_DIR,
    CONTROL_PANEL_RUN_DIRS,
    CONTROL_PANEL_STATE_DIR,
    INVEST_FLOW_ROOT,
    TASK_DEFINITIONS,
    WORKSPACE_ROOT,
    STOCK_ANALYZER_ROOT,
    AccountBookError,
    build_ask_followup_view,
    build_ask_page_view,
    build_ask_suggestions,
    build_overview_summary,
    build_opportunities_context_view,
    build_opportunities_source_cards_view,
    build_opportunities_view,
    build_portfolio_account_view,
    build_review_evidence_view,
    build_review_research_view,
    build_review_source_cards_view,
    build_shadow_replay_review_summary,
    build_review_view,
    build_shell_status_view,
    build_stock_profile_detail_view,
    build_stock_profile_evidence_view,
    build_stock_profile_formal_data_section_view,
    build_stock_profile_learning_scorecard,
    build_stock_profile_secondary_view,
    build_stock_profile_today_action_view,
    build_stock_profile_summary_view,
    build_today_action_contracts_view,
    build_today_actions_view,
    build_today_command_brief_detail_view,
    build_today_readiness_view,
    build_today_source_cards_view,
    build_today_summary_view,
    build_today_view,
    build_watchlist_manager_api_view,
    build_watchlist_source_cards_view,
    build_watchlist_summary_view,
    clear_today_base_inputs_cache,
    clear_run_list_cache,
    clear_stock_profile_cache,
    ensure_runtime_dirs,
    list_runs,
    parse_timestamp,
    public_today_summary_readiness,
    record_cash_adjustment,
    record_fill,
    record_no_fill_intent,
    record_reconciliation,
    set_account_mode,
    TASK_RUN_REPOSITORY,
    amend_holding_identity,
    update_today_action_decision,
)
from watchlist_registry import archive_watchlist_stock, fetch_stock_name, lookup_stock_name_local, restore_watchlist_stock, upsert_watchlist_stock
from stock_name_backfill import (
    needs_backfill as _stock_name_needs_backfill,
    request_name_backfill as _request_stock_name_backfill,
    start_worker as _start_stock_name_backfill_worker,
    stop_worker as _stop_stock_name_backfill_worker,
)
from source_budget import build_source_budget_payload
from dataset_manifests import (  # type: ignore  # local module
    FORMAL_FRESHNESS_DATASETS,
    build_dataset_freshness_rows,
    build_formal_freshness_rows,
)
from data_assets import build_data_assets_status
from refresh_policy import (
    CRON_POLICIES,
    PAGE_POLICIES,
    TASK_POLICIES,
    active_auto_windows,
    build_policy_payload,
    current_market_mode,
    eligible_lightweight_task,
    evaluate_auto_refresh,
    manifest_trigger_reasons,
    normalize_task_name,
    page_cooldown_state,
    page_policy,
    pick_recommended_task as policy_pick_recommended_task,
    summarize_auto_decision,
    task_family,
    task_conflict_is_running,
    task_is_running,
    task_policy,
    validate_cron_policies,
)
from readiness import expected_trade_date as readiness_expected_trade_date
from scheduled_run_state import (
    STATE_PATH as SCHEDULER_STATE_PATH,
    load_scheduler_state,
    run_state_for_task,
    scheduler_alive,
)
from trading_calendar import calendar_status
from prism_data.data_capability_matrix import data_capability_matrix_as_dict
from prism_data.providers.tushare import TushareProvider

import decision_ledger

TASK_RUNNER = INVEST_FLOW_ROOT / "scripts" / "control_panel_task_runner.py"
PREVIEW_MAX_BYTES = 220_000
WATCHLIST_REFRESH_COMMAND = ["bash", "apps/scripts/run_watchlist_refresh.sh"]
LIGHTWEIGHT_REFRESH_COMMAND = [sys.executable, "apps/scripts/refresh_lightweight_data.py"]
MORNING_WARMUP_COMMAND = [sys.executable, "apps/scripts/run_morning_warmup.py"]
FORMAL_DATA_REFRESH_COMMAND = [sys.executable, "apps/scripts/refresh_formal_data.py"]
PARAMETERS_PATH = STOCK_ANALYZER_ROOT / "config" / "stocks.json"
WEB_HOST = os.environ.get("PRISM_WEB_HOST", "127.0.0.1").strip() or "127.0.0.1"
WEB_PORT = os.environ.get("PRISM_WEB_PORT", "8000").strip() or "8000"
WEB_ORIGIN = os.environ.get("PRISM_WEB_ORIGIN", f"http://{WEB_HOST}:{WEB_PORT}").rstrip("/")
SCHEDULER_REQUIRED_TASKS = ("morning_warmup", "formal_data_refresh", "watchlist_refresh", "aggressive")
SCHEDULER_SAFETY_GRACE_MINUTES = 2
TASK_NAME_ALIASES = {
    "watchlist": "watchlist_refresh",
}
FEISHU_STATUS_CACHE_TTL_SECONDS = 300
_FEISHU_STATUS_CACHE: tuple[float, dict[str, Any]] | None = None
FORMAL_DATA_STATUS_CACHE_TTL_SECONDS = max(
    0,
    int(os.environ.get("PRISM_FORMAL_DATA_STATUS_CACHE_TTL_SECONDS", "10") or "10"),
)
_FORMAL_DATA_STATUS_CACHE: tuple[float, tuple[str, tuple[str, ...], int | None], dict[str, Any]] | None = None
OPPORTUNITIES_API_CACHE_TTL_SECONDS = max(
    0,
    int(os.environ.get("PRISM_OPPORTUNITIES_API_CACHE_TTL_SECONDS", "30") or "30"),
)
_OPPORTUNITIES_COMPACT_API_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_OPPORTUNITIES_CONTEXT_API_CACHE: tuple[float, dict[str, Any]] | None = None
_OPPORTUNITIES_SOURCE_CARDS_API_CACHE: tuple[float, dict[str, Any]] | None = None
TODAY_SUMMARY_API_CACHE_TTL_SECONDS = max(
    0,
    int(os.environ.get("PRISM_TODAY_SUMMARY_API_CACHE_TTL_SECONDS", "20") or "20"),
)
_TODAY_SUMMARY_API_CACHE: tuple[float, dict[str, Any]] | None = None
TODAY_ACTIONS_API_CACHE_TTL_SECONDS = max(
    0,
    int(os.environ.get("PRISM_TODAY_ACTIONS_API_CACHE_TTL_SECONDS", "20") or "20"),
)
_TODAY_ACTIONS_API_CACHE: tuple[float, dict[str, Any]] | None = None
_TODAY_ACTION_CONTRACTS_API_CACHE: tuple[float, dict[str, Any]] | None = None
_TODAY_COMMAND_BRIEF_DETAIL_API_CACHE: tuple[float, dict[str, Any]] | None = None
WATCHLIST_API_CACHE_TTL_SECONDS = max(
    0,
    int(os.environ.get("PRISM_WATCHLIST_API_CACHE_TTL_SECONDS", "20") or "20"),
)
_WATCHLIST_API_CACHE: tuple[float, dict[str, Any]] | None = None
PORTFOLIO_ACCOUNT_API_CACHE_TTL_SECONDS = max(
    0,
    int(os.environ.get("PRISM_PORTFOLIO_ACCOUNT_API_CACHE_TTL_SECONDS", "20") or "20"),
)
_PORTFOLIO_ACCOUNT_API_CACHE: dict[tuple[bool, bool], tuple[float, dict[str, Any]]] | None = None
OVERVIEW_API_CACHE_TTL_SECONDS = max(
    0,
    int(os.environ.get("PRISM_OVERVIEW_API_CACHE_TTL_SECONDS", "20") or "20"),
)
_OVERVIEW_API_CACHE: dict[bool, tuple[float, dict[str, Any]]] | None = None

app = FastAPI(title="Prism Control", version="0.1.0")


from contextlib import asynccontextmanager


FORMAL_SOURCE_PLAN: dict[str, dict[str, Any]] = {
    "trade_calendar": {
        "provider": "tushare",
        "source_apis": ["trade_cal"],
        "required_permission": "Tushare Pro token；交易日历接口。",
        "docs": ["https://tushare.pro/document/2?doc_id=26"],
    },
    "bars.daily": {
        "provider": "tushare",
        "source_apis": ["daily"],
        "required_permission": "Tushare Pro token；A 股历史日线接口和对应流控额度。",
        "docs": ["https://tushare.pro/document/2?doc_id=27"],
    },
    "adjustment.factor": {
        "provider": "tushare",
        "source_apis": ["adj_factor"],
        "required_permission": "Tushare Pro token；复权因子接口通常需要积分权限。",
        "docs": ["https://tushare.pro/document/2?doc_id=28"],
    },
    "benchmark.index_daily": {
        "provider": "tushare",
        "source_apis": ["index_daily"],
        "required_permission": "Tushare Pro token；指数日线接口通常需要积分权限。",
        "docs": ["https://tushare.pro/document/2?doc_id=95"],
    },
    "price_limit.daily": {
        "provider": "tushare",
        "source_apis": ["stk_limit"],
        "required_permission": "Tushare Pro token；每日涨跌停价格接口通常需要积分权限。",
        "docs": ["https://tushare.pro/document/2?doc_id=183"],
    },
    "execution.flags": {
        "provider": "tushare",
        "source_apis": ["stk_limit", "suspend_d", "stock_st"],
        "required_permission": "Tushare Pro token；涨跌停、每日停复牌、ST 股票列表接口权限。",
        "docs": [
            "https://tushare.pro/document/2?doc_id=183",
            "https://tushare.pro/document/2?doc_id=214",
            "https://tushare.pro/document/2?doc_id=397",
        ],
    },
}


def _prewarm_control_panel_caches() -> None:
    if str(os.environ.get("PRISM_CONTROL_PANEL_PREWARM", "1")).strip().lower() in {"0", "false", "no", "off"}:
        return
    try:
        build_refresh_status_payload("today", auto=False, skip_auto=True, compact=True)
    except Exception:
        pass


@asynccontextmanager
async def _prism_lifespan(_app: FastAPI):
    # Best-effort background worker that backfills friendly stock names
    # asynchronously so account-write paths stay non-blocking.
    try:
        _start_stock_name_backfill_worker()
    except Exception:
        pass
    _prewarm_control_panel_caches()
    try:
        yield
    finally:
        try:
            _stop_stock_name_backfill_worker()
        except Exception:
            pass


app.router.lifespan_context = _prism_lifespan


def allowed_cors_origins() -> list[str]:
    configured = [
        origin.strip().rstrip("/")
        for origin in os.environ.get("PRISM_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    defaults = [
        WEB_ORIGIN,
        f"http://127.0.0.1:{WEB_PORT}",
        f"http://localhost:{WEB_PORT}",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]
    deduped: list[str] = []
    seen: set[str] = set()
    for origin in [*configured, *defaults]:
        if origin and origin not in seen:
            deduped.append(origin)
            seen.add(origin)
    return deduped


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def canonical_task_name(task_name: str) -> str:
    normalized = str(task_name or "").strip()
    return TASK_NAME_ALIASES.get(normalized, normalized)


def _remember_feishu_channel_status(payload: dict[str, Any]) -> dict[str, Any]:
    global _FEISHU_STATUS_CACHE

    _FEISHU_STATUS_CACHE = (time.monotonic(), payload)
    return payload


def feishu_channel_status(*, allow_probe: bool = True, force_probe: bool = False) -> dict[str, Any]:
    global _FEISHU_STATUS_CACHE

    now = time.monotonic()
    if _FEISHU_STATUS_CACHE and not force_probe:
        cached_at, cached_payload = _FEISHU_STATUS_CACHE
        if now - cached_at <= FEISHU_STATUS_CACHE_TTL_SECONDS:
            return {**cached_payload, "cached": True}

    openclaw_bin = shutil.which("openclaw")
    if not openclaw_bin:
        return _remember_feishu_channel_status({
            "available": False,
            "installed": False,
            "configured": False,
            "reason": "openclaw_missing",
            "detail": "未安装 openclaw，无法发送飞书。",
        })

    if not allow_probe:
        cached_payload = _FEISHU_STATUS_CACHE[1] if _FEISHU_STATUS_CACHE else None
        if cached_payload:
            return {**cached_payload, "cached": True}
        return {
            "available": False,
            "installed": True,
            "configured": False,
            "reason": "probe_skipped",
            "detail": "健康检查跳过飞书通道深探测；运行任务时会再确认。",
        }

    try:
        proc = subprocess.run(
            [openclaw_bin, "channels", "list", "--json"],
            cwd=str(WORKSPACE_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception as exc:
        return _remember_feishu_channel_status({
            "available": False,
            "installed": True,
            "configured": False,
            "reason": "probe_failed",
            "detail": f"飞书通道探测失败：{exc}",
        })

    output = (proc.stdout or "").strip()
    if proc.returncode != 0 or not output:
        detail = (proc.stderr or proc.stdout or "飞书通道未就绪").strip()
        return _remember_feishu_channel_status({
            "available": False,
            "installed": True,
            "configured": False,
            "reason": "probe_failed",
            "detail": detail,
        })

    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return _remember_feishu_channel_status({
            "available": False,
            "installed": True,
            "configured": False,
            "reason": "probe_invalid_json",
            "detail": output,
        })

    chat = payload.get("chat") if isinstance(payload, dict) else None
    feishu = chat.get("feishu") if isinstance(chat, dict) else None
    accounts = feishu.get("accounts") if isinstance(feishu, dict) else None
    installed = bool(feishu and feishu.get("installed"))
    configured = isinstance(accounts, list) and len(accounts) > 0
    available = installed and configured
    detail = "飞书通道可用。" if available else "飞书插件已安装，但还没有可用账号。"
    payload = {
        "available": available,
        "installed": installed,
        "configured": configured,
        "accounts": accounts if isinstance(accounts, list) else [],
        "reason": "" if available else "not_configured",
        "detail": detail,
    }
    return _remember_feishu_channel_status(payload)


def web_redirect(path: str, *, query: str = "") -> RedirectResponse:
    separator = "&" if "?" in path else "?"
    target = f"{WEB_ORIGIN}{path}"
    if query:
        target = f"{target}{separator}{query}"
    return RedirectResponse(target, status_code=307)


def build_run_paths(run_id: str) -> tuple[Path, Path]:
    ensure_runtime_dirs()
    meta_path = CONTROL_PANEL_RUNS_DIR / f"{run_id}.json"
    log_path = CONTROL_PANEL_LOGS_DIR / f"{run_id}.log"
    return meta_path, log_path


def resolve_run_log_path(run_id: str) -> Path | None:
    for directory in CONTROL_PANEL_LOG_DIRS:
        path = directory / f"{run_id}.log"
        if path.exists():
            return path
    return None


def launch_background_task(
    *,
    task_name: str,
    title: str,
    command: list[str],
    cwd: str,
    send_to_feishu: bool = False,
) -> dict[str, Any]:
    if not TASK_RUNNER.exists():
        raise HTTPException(status_code=500, detail="task runner missing")

    run_id = f"{task_name}_{now_stamp()}"
    meta_path, log_path = build_run_paths(run_id)
    launch_cmd = [
        sys.executable,
        str(TASK_RUNNER),
        "--task-id",
        run_id,
        "--task-name",
        task_name,
        "--title",
        title,
        "--cwd",
        cwd,
        "--meta",
        str(meta_path),
        "--log",
        str(log_path),
        "--send-to-feishu",
        "1" if send_to_feishu else "0",
        "--",
        *command,
    ]

    subprocess.Popen(
        launch_cmd,
        cwd=str(WORKSPACE_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    clear_run_list_cache()
    _clear_formal_data_status_cache()
    _clear_overview_api_cache()

    return {
        "started": True,
        "run_id": run_id,
        "task_name": task_name,
        "title": title,
        "send_to_feishu": send_to_feishu,
        "meta_path": str(meta_path),
        "log_path": str(log_path),
    }


def safe_path(path_str: str) -> Path:
    path = Path(path_str).expanduser().resolve()
    workspace_root = Path(WORKSPACE_ROOT).resolve()
    if workspace_root not in path.parents and path != workspace_root:
        raise HTTPException(status_code=400, detail="path outside workspace")
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return path


def preview_kind(target: Path) -> str:
    suffix = target.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".json":
        return "json"
    if suffix in {".docx", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return "binary"
    return "text"


def load_preview_text(target: Path, kind: str) -> tuple[str, bool]:
    with target.open("rb") as fh:
        raw = fh.read(PREVIEW_MAX_BYTES + 1)

    truncated = len(raw) > PREVIEW_MAX_BYTES
    if truncated:
        raw = raw[:PREVIEW_MAX_BYTES]

    text = raw.decode("utf-8", errors="replace")
    if kind == "json":
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except Exception:
            pass
    return text, truncated


def load_parameters_value() -> dict[str, Any]:
    if not PARAMETERS_PATH.exists():
        raise HTTPException(status_code=404, detail="parameters file not found")
    try:
        payload = json.loads(PARAMETERS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"parameters json invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="parameters root must be an object")
    return payload


def normalize_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


def parameter_validation_errors(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    stocks = payload.get("stocks")
    if not isinstance(stocks, list):
        errors.append("stocks 必须是数组")
    else:
        for index, stock in enumerate(stocks, start=1):
            if not isinstance(stock, dict):
                errors.append(f"stocks[{index}] 必须是对象")
                continue
            code = str(stock.get("code") or "").strip()
            name = str(stock.get("name") or "").strip()
            if len(code) != 6 or not code.isdigit():
                errors.append(f"stocks[{index}].code 必须是 6 位股票代码")
            if not name:
                errors.append(f"stocks[{index}].name 不能为空")

    ma_periods = payload.get("ma_periods")
    if not isinstance(ma_periods, list) or not ma_periods:
        errors.append("ma_periods 必须是非空数组")
    elif any(normalize_positive_int(item) is None for item in ma_periods):
        errors.append("ma_periods 只能包含正整数")

    if normalize_positive_int(payload.get("news_count")) is None:
        errors.append("news_count 必须是正整数")
    if normalize_positive_int(payload.get("kline_days")) is None:
        errors.append("kline_days 必须是正整数")

    return errors


def parameter_evaluation(
    candidate: dict[str, Any],
    *,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a parameter payload for safety and sane ranges.

    This runs *after* :func:`parameter_validation_errors` (which is purely
    structural) and adds a layer of business-logic safety checks:

    * Hard errors (block apply unless ``unsafe_apply=true``):
      - zero active stocks (downstream pipelines need at least one)
      - duplicate stock codes

    * Warnings (informational, don't block):
      - active count drops > 50% from the currently-saved state
      - ``kline_days`` outside [30, 365]
      - ``news_count`` outside [3, 50]
      - ``ma_periods`` longer than 8 entries or any value > 250
    """

    errors: list[str] = []
    warnings: list[str] = []

    stocks = candidate.get("stocks") if isinstance(candidate.get("stocks"), list) else []
    stock_rows = [item for item in stocks if isinstance(item, dict)]
    active_rows = [item for item in stock_rows if item.get("active", True) is not False]
    active_count = len(active_rows)

    # Hard error: zero active stocks.
    if active_count == 0 and stock_rows:
        errors.append("没有活跃股票（active!=false 数量为 0），下游流水线将无可处理对象")
    elif not stock_rows:
        errors.append("stocks 列表为空")

    # Hard error: duplicate codes.
    seen_codes: set[str] = set()
    duplicate_codes: list[str] = []
    for item in stock_rows:
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        if code in seen_codes and code not in duplicate_codes:
            duplicate_codes.append(code)
        seen_codes.add(code)
    if duplicate_codes:
        errors.append("发现重复的股票代码：" + ", ".join(duplicate_codes))

    # Soft warning: large drop in active count vs current.
    if isinstance(current, dict):
        current_stocks = current.get("stocks") if isinstance(current.get("stocks"), list) else []
        current_active = sum(
            1
            for item in current_stocks
            if isinstance(item, dict) and item.get("active", True) is not False
        )
        if current_active > 0 and active_count < current_active / 2:
            warnings.append(
                f"活跃股票数量大幅减少（{current_active} → {active_count}，下降超过 50%）"
            )

    # Soft warnings: range sanity.
    kline_days = normalize_positive_int(candidate.get("kline_days"))
    if kline_days is not None:
        if kline_days < 30:
            warnings.append(f"kline_days={kline_days} 偏小（<30），技术指标可能不稳定")
        elif kline_days > 365:
            warnings.append(f"kline_days={kline_days} 偏大（>365），抓取耗时显著上升")

    news_count = normalize_positive_int(candidate.get("news_count"))
    if news_count is not None:
        if news_count < 3:
            warnings.append(f"news_count={news_count} 偏小（<3），新闻覆盖度不足")
        elif news_count > 50:
            warnings.append(f"news_count={news_count} 偏大（>50），抓取与渲染成本上升")

    ma_periods = candidate.get("ma_periods")
    if isinstance(ma_periods, list):
        if len(ma_periods) > 8:
            warnings.append(f"ma_periods 含 {len(ma_periods)} 项（>8），UI 渲染会拥挤")
        oversized = [p for p in ma_periods if isinstance(p, int) and p > 250]
        if oversized:
            warnings.append(f"ma_periods 中 {oversized} 大于 250，可能超出常见 K 线窗口")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def parameter_group_status(payload: dict[str, Any]) -> list[dict[str, Any]]:
    stocks = payload.get("stocks") if isinstance(payload.get("stocks"), list) else []
    stock_rows = [item for item in stocks if isinstance(item, dict)]
    active_count = sum(1 for item in stock_rows if item.get("active", True) is not False)
    archived_count = max(len(stock_rows) - active_count, 0)
    ma_periods = payload.get("ma_periods")
    news_count = payload.get("news_count")
    kline_days = payload.get("kline_days")

    return [
        {
            "key": "stocks",
            "label": "自选股名单",
            "required": True,
            "ok": isinstance(stocks, list),
            "detail": f"活跃 {active_count} / 归档 {archived_count}",
        },
        {
            "key": "ma_periods",
            "label": "均线周期",
            "required": True,
            "ok": isinstance(ma_periods, list)
            and bool(ma_periods)
            and all(normalize_positive_int(item) is not None for item in ma_periods),
            "detail": ", ".join(str(item) for item in ma_periods) if isinstance(ma_periods, list) else "未配置",
        },
        {
            "key": "news_count",
            "label": "新闻/公告条数",
            "required": True,
            "ok": normalize_positive_int(news_count) is not None,
            "detail": str(news_count or "未配置"),
        },
        {
            "key": "kline_days",
            "label": "K 线回看天数",
            "required": True,
            "ok": normalize_positive_int(kline_days) is not None,
            "detail": str(kline_days or "未配置"),
        },
    ]


def build_parameters_payload(value: dict[str, Any], *, saved: bool = False) -> dict[str, Any]:
    stat = PARAMETERS_PATH.stat() if PARAMETERS_PATH.exists() else None
    stocks = value.get("stocks") if isinstance(value.get("stocks"), list) else []
    stock_rows = [item for item in stocks if isinstance(item, dict)]
    active_count = sum(1 for item in stock_rows if item.get("active", True) is not False)
    archived_count = max(len(stock_rows) - active_count, 0)
    errors = parameter_validation_errors(value)

    return {
        "ok": not errors,
        "saved": saved,
        "path": str(PARAMETERS_PATH),
        "updated_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S") if stat else "",
        "summary_cards": [
            {"label": "活跃持仓", "value": active_count, "detail": "stocks 中 active!=false", "tone": "positive"},
            {"label": "归档名单", "value": archived_count, "detail": "stocks 中 active=false", "tone": "watch"},
            {"label": "均线周期", "value": len(value.get("ma_periods") or []), "detail": "ma_periods", "tone": "info"},
            {"label": "K线天数", "value": value.get("kline_days", "-"), "detail": "kline_days", "tone": "info"},
        ],
        "required_groups": parameter_group_status(value),
        "validation": {
            "ok": not errors,
            "errors": errors,
        },
        "value": value,
        "raw": json.dumps(value, ensure_ascii=False, indent=2),
    }


def watchlist_message(action: str, status: str, stock: dict[str, Any], refresh_started: bool) -> str:
    code = str(stock.get("code") or "").strip()
    name = str(stock.get("name") or code).strip() or code
    label = f"{name} {code}".strip()

    if action == "add":
        if status == "added":
            return f"已加入 {label}，后台开始刷新自选股全流程。"
        if status == "restored":
            return f"已恢复 {label}，后台开始刷新自选股全流程。"
        if status == "updated":
            return f"已更新 {label} 的自选股配置。"
        return f"{label} 已在当前自选股里。"

    if action == "archive":
        if status == "archived":
            if refresh_started:
                return f"已归档 {label}，后台会同步隐藏它在当前报告链路中的展示。"
            return f"已归档 {label}。"
        return f"{label} 当前已经在归档区。"

    if action == "restore":
        if status == "restored":
            return f"已恢复 {label}，后台开始刷新自选股全流程。"
        return f"{label} 当前已经在活跃自选股里。"

    return f"{label} 已更新。"


def parse_bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"0", "false", "no", "off"}:
        return False
    if text in {"1", "true", "yes", "on"}:
        return True
    return default


def resolve_stock_display_name(code: Any, name: Any = None) -> str:
    raw_code = str(code or "").strip().lower()
    provided_name = str(name or "").strip()
    code_like_names = {raw_code}
    if len(raw_code) == 8 and raw_code[:2].isalpha():
        code_like_names.add(raw_code[2:])

    if provided_name and provided_name.lower() not in code_like_names:
        return provided_name

    bare_code = raw_code[2:] if len(raw_code) == 8 and raw_code[:2].isalpha() else raw_code
    if len(bare_code) == 6 and bare_code.isdigit():
        # Local-only lookup. The account-write request path must NOT block
        # on a synchronous external quote roundtrip just to attach a
        # friendlier display name; if local sources can't resolve it, fall
        # through to the bare code and let an async backfill upgrade later.
        try:
            local_book = load_account_book()
        except Exception:
            local_book = None
        local = lookup_stock_name_local(bare_code, account_book=local_book)
        if local:
            return local
        # Fell through — enqueue an async backfill so the friendly name
        # eventually lands in account_book/watchlist without blocking the
        # current request.
        try:
            _request_stock_name_backfill(bare_code)
        except Exception:
            pass

    return provided_name or bare_code or raw_code


REFRESH_STATE_PATH = CONTROL_PANEL_STATE_DIR / "refresh_state.json"
REFRESH_PAGE_CONFIG: dict[str, dict[str, Any]] = {
    page: policy.as_dict() for page, policy in PAGE_POLICIES.items()
}


def normalize_refresh_page(value: Any) -> str:
    page = str(value or "").strip().lower()
    if page_policy(page) is None:
        raise HTTPException(status_code=400, detail="unsupported page")
    return page


def _cron_daily_minute(expr: str) -> int | None:
    try:
        minute_s, hour_s, day_s, month_s, _weekday_s = str(expr or "").split()
        if day_s != "*" or month_s != "*":
            return None
        if any(mark in minute_s or mark in hour_s for mark in ("*", ",", "-", "/")):
            return None
        return int(hour_s) * 60 + int(minute_s)
    except Exception:
        return None


def age_label(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 60:
        return "刚刚"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} 分钟前"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} 小时前"
    days = hours // 24
    return f"{days} 天前"


def load_refresh_state() -> dict[str, Any]:
    ensure_runtime_dirs()
    payload = APP_STATE_REPOSITORY.get(
        "refresh_state",
        legacy_path=REFRESH_STATE_PATH,
        default={"pages": {}, "tasks": {}, "audit_events": []},
    )
    if not isinstance(payload, dict):
        return {"pages": {}, "tasks": {}, "audit_events": []}
    pages = payload.get("pages")
    if not isinstance(pages, dict):
        payload["pages"] = {}
    tasks = payload.get("tasks")
    if not isinstance(tasks, dict):
        payload["tasks"] = {}
    audit_events = payload.get("audit_events")
    if not isinstance(audit_events, list):
        payload["audit_events"] = []
    return payload


def save_refresh_state(payload: dict[str, Any]) -> None:
    ensure_runtime_dirs()
    APP_STATE_REPOSITORY.set("refresh_state", payload, legacy_path=REFRESH_STATE_PATH)


def resolve_refresh_task(task_name: str) -> dict[str, Any]:
    normalized = normalize_task_name(str(task_name or "").strip())
    policy = task_policy(normalized)
    if normalized in {"quotes_light", "capital_flow_light"}:
        kind = "quotes" if normalized == "quotes_light" else "capital_flow"
        return {
            "task_name": normalized,
            "title": policy.title if policy else ("轻量行情补刷" if kind == "quotes" else "轻量资金流补刷"),
            "command": [*LIGHTWEIGHT_REFRESH_COMMAND, "--kind", kind],
            "cwd": str(WORKSPACE_ROOT),
            "send_to_feishu": False,
        }

    if normalized == "formal_data_refresh":
        return {
            "task_name": normalized,
            "title": policy.title if policy else "正式口径数据刷新",
            "command": FORMAL_DATA_REFRESH_COMMAND,
            "cwd": str(WORKSPACE_ROOT),
            "send_to_feishu": False,
        }

    if normalized == "formal_data_refresh_postclose":
        return {
            "task_name": normalized,
            "title": policy.title if policy else "正式日线复权盘后补齐",
            "command": [*FORMAL_DATA_REFRESH_COMMAND, "--datasets", "bars.daily,adjustment.factor"],
            "cwd": str(WORKSPACE_ROOT),
            "send_to_feishu": False,
        }

    if normalized.startswith("formal_data_refresh_index_"):
        return {
            "task_name": normalized,
            "title": policy.title if policy else "正式基准指数补刷",
            "command": [*FORMAL_DATA_REFRESH_COMMAND, "--datasets", "benchmark.index_daily"],
            "cwd": str(WORKSPACE_ROOT),
            "send_to_feishu": False,
        }

    if normalized == "morning_warmup":
        return {
            "task_name": normalized,
            "title": policy.title if policy else "晨间数据预热",
            "command": MORNING_WARMUP_COMMAND,
            "cwd": str(WORKSPACE_ROOT),
            "send_to_feishu": False,
        }

    if normalized in {"preclose_risk_refresh", "postclose_command_brief"}:
        return {
            "task_name": normalized,
            "title": policy.title if policy else "投资总控简报",
            "command": ["bash", "apps/scripts/run_command_brief.sh"],
            "cwd": str(WORKSPACE_ROOT),
            "send_to_feishu": False,
        }

    if normalized == "watchlist_refresh":
        return {
            "task_name": normalized,
            "title": "自选股全流程刷新",
            "command": WATCHLIST_REFRESH_COMMAND,
            "cwd": str(WORKSPACE_ROOT),
            "send_to_feishu": False,
        }

    task = TASK_DEFINITIONS.get(normalized)
    if not task:
        raise HTTPException(status_code=400, detail="unknown refresh task")
    return {
        "task_name": normalized,
        "title": task["title"],
        "command": task["command"],
        "cwd": task["cwd"],
        "send_to_feishu": False,
    }


def read_page_source_cards(page: str) -> list[dict[str, Any]]:
    if page == "today":
        return list((build_today_source_cards_view().get("source_cards") or []))
    if page == "watchlist":
        return list((build_watchlist_source_cards_view().get("source_cards") or []))
    if page == "opportunities":
        return list((build_opportunities_source_cards_view().get("source_cards") or []))
    if page == "review":
        return list((build_review_source_cards_view().get("source_cards") or []))
    return []


def build_page_freshness(page: str, market_mode: str) -> list[dict[str, Any]]:
    stale_after = int(REFRESH_PAGE_CONFIG[page]["stale_after_seconds"][market_mode])
    now = datetime.now()
    items: list[dict[str, Any]] = []

    for idx, source in enumerate(read_page_source_cards(page), start=1):
        label = str(source.get("label") or f"source_{idx}").strip() or f"source_{idx}"
        value = str(source.get("value") or "-").strip() or "-"
        detail = str(source.get("detail") or "").strip()
        parsed_dt = parse_timestamp(value)
        age_seconds = max(int((now - parsed_dt).total_seconds()), 0) if parsed_dt else None
        stale = bool(parsed_dt and age_seconds is not None and age_seconds > stale_after)
        key = str(label).lower().replace(" ", "_")
        items.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "detail": detail,
                "available": bool(parsed_dt),
                "age_seconds": age_seconds,
                "age_label": age_label(age_seconds),
                "stale": stale,
                "stale_after_seconds": stale_after,
            }
        )
    return items


def build_running_refresh_tasks(page: str) -> list[dict[str, Any]]:
    cfg = page_policy(page)
    related = {normalize_task_name(item) for item in (cfg.related_tasks if cfg else ())}
    related_families = {task_family(item) for item in related}
    rows: list[dict[str, Any]] = []
    seen_families: set[str] = set()
    for item in list_runs(limit=80):
        if str(item.get("status") or "") != "running":
            continue
        task_name = normalize_task_name(str(item.get("task_name") or "").strip())
        family = task_family(task_name)
        if task_name not in related and family not in related_families:
            continue
        seen_families.add(family)
        policy = task_policy(task_name)
        rows.append(
            {
                "task_name": task_name,
                "title": str(item.get("title") or task_name),
                "task_kind": policy.kind if policy else "unknown",
                "task_family": family,
                "status": "running",
                "started_at": str(item.get("started_at") or ""),
                "summary": str(item.get("summary") or "后台执行中"),
            }
        )
    for task_name in sorted(related):
        family = task_family(task_name)
        if family in seen_families:
            continue
        scheduled_state = run_state_for_task(task_name)
        if not scheduled_state.get("running"):
            continue
        policy = task_policy(task_name)
        rows.append(
            {
                "task_name": task_name,
                "title": str(scheduled_state.get("title") or (policy.title if policy else task_name)),
                "task_kind": policy.kind if policy else "unknown",
                "task_family": family,
                "status": "running",
                "started_at": str(scheduled_state.get("started_at") or ""),
                "summary": "Prism 调度器正在执行",
                "run_id": str(scheduled_state.get("run_id") or ""),
                "source": "scheduler",
            }
        )
        seen_families.add(family)
    return rows


def _latest_run_for_task_family(task_name: str) -> dict[str, Any] | None:
    expected_family = task_family(normalize_task_name(task_name))
    for item in list_runs(limit=80):
        candidate = normalize_task_name(str(item.get("task_name") or ""))
        if candidate and task_family(candidate) == expected_family:
            return item
    return None


def _formal_row_state(row: dict[str, Any], *, token_configured: bool) -> str:
    flags = {str(item or "").strip() for item in row.get("quality_flags") or []}
    reasons = {str(item or "").strip() for item in row.get("stale_reasons") or []}
    target = str(row.get("target_authority_provider") or row.get("authority_provider") or "")
    available = bool(row.get("available"))
    has_manifest = bool(row.get("manifest_path"))
    if row.get("formal_decision_allowed") and not row.get("stale"):
        return "ready"
    if "provider_token_invalid" in flags:
        return "token_invalid"
    if "provider_rate_limited" in flags:
        return "rate_limited"
    if "provider_permission_or_points_blocked" in flags:
        return "permission_or_points_blocked"
    if "execution_flags_price_limit_missing" in flags or "execution_flags_code_coverage_mismatch" in flags:
        return "coverage_incomplete"
    if target == "tushare" and not token_configured and not available and not has_manifest:
        return "token_missing"
    if "manifest_missing" in reasons:
        return "manifest_missing"
    if row.get("error"):
        return "provider_error"
    if row.get("stale"):
        return "stale_or_misaligned"
    return "formal_not_allowed"


def _formal_action_for_state(state: str) -> str:
    return {
        "ready": "无需处理",
        "token_missing": "运行 apps/scripts/configure_tushare_token.py 写入本机 .env，然后重启后端并刷新正式口径。",
        "token_invalid": "更换或重新确认 Tushare token，不要写入仓库或日志。",
        "rate_limited": "Tushare 触发接口流控；当前刷新脚本会复用已接入数据，等待流控窗口后只补缺口。",
        "permission_or_points_blocked": "在 Tushare 账号里开通或补足对应接口权限/积分，或改用同等级授权源。",
        "provider_adapter_missing": "接入 RiceQuant 或 JoinQuant 执行约束 adapter，并配置对应授权。",
        "coverage_incomplete": "正式源已返回，但覆盖不完整；检查自选股代码、交易日和对应 Tushare 接口返回。",
        "manifest_missing": "运行正式口径数据刷新。",
        "provider_error": "查看最近 formal_data_refresh 日志，按接口错误处理。",
        "stale_or_misaligned": "重新运行正式口径数据刷新并确认交易日对齐。",
        "formal_not_allowed": "检查 provider、target authority 和 manifest flags。",
    }.get(state, "查看 manifest 和最近任务日志。")


def _formal_data_status_cache_key(env_file: Path) -> tuple[str, tuple[str, ...], int | None]:
    try:
        env_mtime = env_file.stat().st_mtime_ns
    except FileNotFoundError:
        env_mtime = None
    return (
        str(env_file),
        tuple(TushareProvider.configured_token_env_names()),
        env_mtime,
    )


def _clear_formal_data_status_cache() -> None:
    global _FORMAL_DATA_STATUS_CACHE
    _FORMAL_DATA_STATUS_CACHE = None


def _build_formal_data_status_payload_uncached() -> dict[str, Any]:
    current = datetime.now()
    expected_date = readiness_expected_trade_date(current)
    configured_token_names = TushareProvider.configured_token_env_names()
    token_configured = bool(configured_token_names)
    env_file = project_env_path(REPO_ROOT)
    rows = build_formal_freshness_rows(
        expected_date=expected_date,
        now=current,
        datasets=FORMAL_FRESHNESS_DATASETS,
    )
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        plan = FORMAL_SOURCE_PLAN.get(str(item.get("dataset") or item.get("key") or ""), {})
        state = _formal_row_state(item, token_configured=token_configured)
        item["setup_state"] = state
        item["next_action"] = _formal_action_for_state(state)
        item["source_apis"] = list(plan.get("source_apis") or [])
        item["required_permission"] = plan.get("required_permission")
        item["docs"] = list(plan.get("docs") or [])
        enriched_rows.append(item)

    ready_rows = [item for item in enriched_rows if item.get("setup_state") == "ready"]
    blockers = [
        {
            "dataset": item.get("dataset"),
            "label": item.get("label"),
            "state": item.get("setup_state"),
            "next_action": item.get("next_action"),
            "error": item.get("error"),
            "quality_flags": item.get("quality_flags") or [],
            "source_apis": item.get("source_apis") or [],
            "required_permission": item.get("required_permission"),
            "docs": item.get("docs") or [],
            "required_request_keys": item.get("required_request_keys") or [],
            "missing_request_keys": item.get("missing_request_keys") or [],
            "blocked_request_keys": item.get("blocked_request_keys") or [],
        }
        for item in enriched_rows
        if item.get("setup_state") != "ready"
    ]
    last_run = _latest_run_for_task_family("formal_data_refresh")
    running = bool(last_run and last_run.get("status") == "running")
    return {
        "generated_at": current.strftime("%Y-%m-%d %H:%M:%S"),
        "expected_trade_date": expected_date,
        "provider": {
            "name": "tushare",
            "token_configured": token_configured,
            "token_env_names": list(TushareProvider.token_env_names()),
            "configured_token_env_names": configured_token_names,
            "api_url": os.environ.get("PRISM_TUSHARE_API_URL", "http://api.tushare.pro"),
            "token_value_visible": False,
            "local_env_path": str(env_file),
            "local_env_file_exists": env_file.exists(),
        },
        "source_plan": [
            {"dataset": dataset, **dict(plan)}
            for dataset, plan in FORMAL_SOURCE_PLAN.items()
        ],
        "setup_steps": [
            "申请或确认 Tushare Pro 账号 token。",
            "确认 token 具备 trade_cal、daily、adj_factor、index_daily、stk_limit、suspend_d、stock_st 接口权限。",
            "运行 apps/scripts/configure_tushare_token.py，把 token 写入本机 .env；不要把 token 写进代码、文档或聊天。",
            "在设置页触发 formal_data_refresh，或运行 apps/scripts/refresh_formal_data.py。",
        ],
        "ready": len(ready_rows) == len(enriched_rows) and bool(enriched_rows),
        "ready_count": len(ready_rows),
        "total_count": len(enriched_rows),
        "blocked_count": len(blockers),
        "datasets": enriched_rows,
        "blockers": blockers,
        "last_run": last_run,
        "running": running,
        "recommended_task": {
            "task_name": "formal_data_refresh",
            "title": "正式口径数据刷新",
        },
    }


def build_formal_data_status_payload(*, fresh: bool = False) -> dict[str, Any]:
    global _FORMAL_DATA_STATUS_CACHE

    load_project_env(root=REPO_ROOT)
    env_file = project_env_path(REPO_ROOT)
    cache_key = _formal_data_status_cache_key(env_file)
    if FORMAL_DATA_STATUS_CACHE_TTL_SECONDS > 0 and _FORMAL_DATA_STATUS_CACHE and not fresh:
        cached_at, cached_key, cached_payload = _FORMAL_DATA_STATUS_CACHE
        if cached_key == cache_key and time.monotonic() - cached_at <= FORMAL_DATA_STATUS_CACHE_TTL_SECONDS:
            return deepcopy(cached_payload)

    payload = _build_formal_data_status_payload_uncached()
    if FORMAL_DATA_STATUS_CACHE_TTL_SECONDS > 0:
        _FORMAL_DATA_STATUS_CACHE = (time.monotonic(), cache_key, deepcopy(payload))
    return payload


_FORMAL_DATA_STATUS_COMPACT_ROW_KEYS = (
    "key",
    "dataset",
    "label",
    "provider",
    "authority_provider",
    "target_authority_provider",
    "trade_date",
    "available",
    "stale",
    "freshness_status",
    "age_label",
    "setup_state",
    "next_action",
    "error",
)


def _compact_formal_data_status_list(value: Any, *, limit: int = 3) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item not in (None, "")][:limit]


def _compact_formal_data_status_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    payload = {
        key: deepcopy(row[key])
        for key in _FORMAL_DATA_STATUS_COMPACT_ROW_KEYS
        if row.get(key) not in (None, "", [], {})
    }
    for key in ("quality_flags", "source_apis", "blocked_request_keys", "missing_request_keys"):
        values = _compact_formal_data_status_list(row.get(key))
        if values:
            payload[key] = values
    if row.get("required_permission") and row.get("setup_state") != "ready":
        payload["required_permission"] = row.get("required_permission")
    if row.get("manifest_path"):
        payload["has_manifest"] = True
    return payload


def _compact_formal_data_status_blocker(blocker: Any) -> dict[str, Any]:
    if not isinstance(blocker, dict):
        return {}
    payload = {
        key: deepcopy(blocker[key])
        for key in ("dataset", "label", "state", "next_action", "error", "required_permission")
        if blocker.get(key) not in (None, "", [], {})
    }
    for key in ("quality_flags", "source_apis", "blocked_request_keys", "missing_request_keys"):
        values = _compact_formal_data_status_list(blocker.get(key))
        if values:
            payload[key] = values
    return payload


def _compact_formal_data_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    provider = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
    recommended_task = payload.get("recommended_task") if isinstance(payload.get("recommended_task"), dict) else {}
    last_run = payload.get("last_run") if isinstance(payload.get("last_run"), dict) else None
    compact: dict[str, Any] = {
        "generated_at": payload.get("generated_at"),
        "expected_trade_date": payload.get("expected_trade_date"),
        "ready": payload.get("ready", False),
        "ready_count": payload.get("ready_count", 0),
        "total_count": payload.get("total_count", 0),
        "blocked_count": payload.get("blocked_count", 0),
        "provider": {
            key: provider.get(key)
            for key in (
                "name",
                "token_configured",
                "token_env_names",
                "configured_token_env_names",
                "local_env_file_exists",
            )
            if provider.get(key) not in (None, "", [], {})
        },
        "datasets": [
            item
            for item in (_compact_formal_data_status_row(row) for row in (payload.get("datasets") or []))
            if item
        ],
        "blockers": [
            item
            for item in (_compact_formal_data_status_blocker(row) for row in (payload.get("blockers") or [])[:4])
            if item
        ],
        "running": payload.get("running", False),
        "compact": True,
    }
    if last_run:
        compact["last_run"] = {
            key: last_run.get(key)
            for key in (
                "run_id",
                "task_id",
                "task_name",
                "title",
                "status",
                "started_at",
                "finished_at",
                "checked_started_at",
                "summary",
            )
            if last_run.get(key) not in (None, "", [], {})
        }
    if recommended_task:
        compact["recommended_task"] = {
            key: recommended_task.get(key)
            for key in ("task_name", "title")
            if recommended_task.get(key) not in (None, "", [], {})
        }
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _clear_today_api_cache() -> None:
    global _TODAY_SUMMARY_API_CACHE, _TODAY_ACTIONS_API_CACHE, _TODAY_ACTION_CONTRACTS_API_CACHE
    global _TODAY_COMMAND_BRIEF_DETAIL_API_CACHE
    _TODAY_SUMMARY_API_CACHE = None
    _TODAY_ACTIONS_API_CACHE = None
    _TODAY_ACTION_CONTRACTS_API_CACHE = None
    _TODAY_COMMAND_BRIEF_DETAIL_API_CACHE = None
    clear_today_base_inputs_cache()


def _clear_opportunities_api_cache() -> None:
    global _OPPORTUNITIES_CONTEXT_API_CACHE, _OPPORTUNITIES_SOURCE_CARDS_API_CACHE
    _OPPORTUNITIES_CONTEXT_API_CACHE = None
    _OPPORTUNITIES_SOURCE_CARDS_API_CACHE = None
    _OPPORTUNITIES_COMPACT_API_CACHE.clear()


def _clear_watchlist_api_cache() -> None:
    global _WATCHLIST_API_CACHE
    _WATCHLIST_API_CACHE = None


def _clear_portfolio_account_api_cache() -> None:
    global _PORTFOLIO_ACCOUNT_API_CACHE
    _PORTFOLIO_ACCOUNT_API_CACHE = None


def _clear_overview_api_cache() -> None:
    global _OVERVIEW_API_CACHE
    _OVERVIEW_API_CACHE = None


def _clear_portfolio_related_api_caches() -> None:
    _clear_portfolio_account_api_cache()
    _clear_today_api_cache()


def _clear_watchlist_related_api_caches() -> None:
    _clear_watchlist_api_cache()
    _clear_portfolio_account_api_cache()
    _clear_today_api_cache()
    _clear_opportunities_api_cache()


_STOCK_PROFILE_ACCOUNT_SENSITIVE_SECTIONS = (
    "summary",
    "detail-compact",
    "evidence",
    "secondary",
    "source-details",
    "source-details:learning",
    "today-action",
)


def _clear_stock_profile_account_sensitive_cache(code: str | None = None) -> None:
    clear_stock_profile_cache(code, sections=_STOCK_PROFILE_ACCOUNT_SENSITIVE_SECTIONS)


def _clear_stock_profile_cache_when_fresh(code: str, fresh: bool) -> None:
    if fresh:
        clear_stock_profile_cache(code)


def _stock_code_from_action_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    direct = decision_ledger.normalize_stock_code(text)
    if direct:
        return direct
    matches = re.findall(r"(?:sh|sz)?\d{6}", text)
    for item in reversed(matches):
        normalized = decision_ledger.normalize_stock_code(item)
        if normalized:
            return normalized
    return ""


def _build_portfolio_account_api_payload(
    *,
    refresh_quotes: bool = False,
    include_holding_reviews: bool = False,
    include_account_history: bool = True,
    fresh_formal_status: bool = False,
) -> dict[str, Any]:
    global _PORTFOLIO_ACCOUNT_API_CACHE

    payload = build_portfolio_account_view(
        refresh_quotes=refresh_quotes,
        formal_data_status=build_formal_data_status_payload(fresh=fresh_formal_status),
        include_holding_reviews=include_holding_reviews,
        include_account_history=include_account_history,
    )
    if PORTFOLIO_ACCOUNT_API_CACHE_TTL_SECONDS > 0:
        if not isinstance(_PORTFOLIO_ACCOUNT_API_CACHE, dict):
            _PORTFOLIO_ACCOUNT_API_CACHE = {}
        cache_key = (include_holding_reviews, include_account_history)
        _PORTFOLIO_ACCOUNT_API_CACHE[cache_key] = (time.monotonic(), deepcopy(payload))
    return payload


def _watchlist_api_payload(*, fresh: bool = False) -> dict[str, Any]:
    global _WATCHLIST_API_CACHE

    if WATCHLIST_API_CACHE_TTL_SECONDS > 0 and _WATCHLIST_API_CACHE and not fresh:
        cached_at, cached_payload = _WATCHLIST_API_CACHE
        if time.monotonic() - cached_at <= WATCHLIST_API_CACHE_TTL_SECONDS:
            return deepcopy(cached_payload)

    payload = build_watchlist_summary_view()
    if WATCHLIST_API_CACHE_TTL_SECONDS > 0:
        _WATCHLIST_API_CACHE = (time.monotonic(), deepcopy(payload))
    return payload


def _readiness_freshness_rows(
    readiness: dict[str, Any],
    *,
    fallback_threshold: int,
) -> list[dict[str, Any]]:
    """Convert ``readiness.source_freshness`` into the legacy freshness shape.

    Keeps the keys the existing UI consumes (key/label/value/age_seconds/age_label/
    stale/stale_after_seconds/available/detail) and threads through the extra
    readiness metadata (trade_date, stale_reasons) so callers can drill in.
    """

    rows: list[dict[str, Any]] = []
    for item in readiness.get("source_freshness") or []:
        rows.append(
            {
                "key": item.get("key"),
                "label": item.get("label"),
                "value": item.get("value") or "-",
                "detail": item.get("detail") or "",
                "available": bool(item.get("available")),
                "age_seconds": item.get("age_seconds"),
                "age_label": item.get("age_label", "-"),
                "stale": bool(item.get("stale")),
                "stale_after_seconds": int(
                    item.get("stale_after_seconds") or fallback_threshold
                ),
                "trade_date": item.get("trade_date"),
                "stale_reasons": list(item.get("stale_reasons") or []),
                "degraded": bool(item.get("degraded")),
                "degradation_reasons": list(item.get("degradation_reasons") or []),
                "deferred": bool(item.get("deferred")),
                "deferred_reason": item.get("deferred_reason"),
            }
        )
    return rows


def _dataset_manifest_freshness_rows(*, expected_date: str, now: datetime) -> list[dict[str, Any]]:
    """Bottom-level dataset freshness for the /api/refresh-status payload.

    Delegates to :func:`dataset_manifests.build_dataset_freshness_rows` so
    we have a single implementation: same parsing, same reasons, same
    schema as the rows surfaced through the readiness gate and the
    Settings page detail view. The dataset list is restricted to the
    lightweight market-data manifests this page cares about; for the
    full registry-driven sweep used by the capability gate, callers go
    through ``build_dataset_freshness_rows`` directly.
    """
    return build_dataset_freshness_rows(
        expected_date=expected_date,
        now=now,
        datasets=(
            "quotes.snapshot",
            "quotes.batch",
            "capital_flow.daily",
            "capital_flow.batch",
        ),
    )


def _stale_subset(freshness: list[dict[str, Any]], dependencies: list[str]) -> list[dict[str, Any]]:
    if not dependencies:
        return freshness
    dependency_set = set(dependencies)
    subset = [
        item
        for item in freshness
        if _freshness_row_matches_dependency(item, dependency_set)
    ]
    return subset or freshness


def _freshness_row_matches_dependency(item: dict[str, Any], dependencies: set[str]) -> bool:
    key = str(item.get("key") or "")
    label = str(item.get("label") or "")
    if key in dependencies or label in dependencies:
        return True
    aliases = {
        "watchlist": "watchlist.snapshot",
        "screening": "screening.batch",
        "confirmation": "screening.confirmation",
        "decision_brief": "decision_brief.snapshot",
    }
    return aliases.get(key, "") in dependencies


def _latest_audit_event(*, state: dict[str, Any], trigger_type: str | None = None) -> dict[str, Any] | None:
    events = state.get("audit_events") if isinstance(state, dict) else []
    if not isinstance(events, list):
        return None
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        if trigger_type and event.get("trigger_type") != trigger_type:
            continue
        return event
    return None


def _compact_audit_event_payload(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    return {
        "ts": str(event.get("ts") or ""),
        "trigger_type": str(event.get("trigger_type") or ""),
        "page": str(event.get("page") or ""),
        "task_name": str(event.get("task_name") or ""),
        "task_family": str(event.get("task_family") or ""),
        "run_id": str(event.get("run_id") or ""),
        "force": bool(event.get("force")),
        "reason": str(event.get("reason") or ""),
    }


def _compact_cooldown_payload(cooldown: dict[str, Any]) -> dict[str, Any]:
    return {
        "seconds": int(cooldown.get("seconds") or 0),
        "remaining_seconds": int(cooldown.get("remaining_seconds") or 0),
        "ready": bool(cooldown.get("ready")),
        "next_allowed_at": str(cooldown.get("next_allowed_at") or ""),
        "last_trigger_at": str(cooldown.get("last_trigger_at") or ""),
        "last_task_name": str(cooldown.get("last_task_name") or ""),
        "last_run_id": str(cooldown.get("last_run_id") or cooldown.get("page_last_run_id") or ""),
        "last_reason": str(cooldown.get("last_reason") or ""),
        "page_last_trigger_at": str(cooldown.get("page_last_trigger_at") or ""),
        "page_last_run_id": str(cooldown.get("page_last_run_id") or ""),
    }


def _compact_auto_decision_payload(decision: dict[str, Any]) -> dict[str, Any]:
    trigger = decision.get("trigger") if isinstance(decision.get("trigger"), dict) else None
    return {
        "enabled": bool(decision.get("enabled")),
        "allowed": bool(decision.get("allowed")),
        "should_trigger": bool(decision.get("should_trigger")),
        "force": bool(decision.get("force")),
        "page": str(decision.get("page") or ""),
        "task_name": str(decision.get("task_name") or ""),
        "task_kind": str(decision.get("task_kind") or ""),
        "reason_codes": list(decision.get("reason_codes") or []),
        "blocked_reasons": list(decision.get("blocked_reasons") or []),
        "manifest_reasons": list(decision.get("manifest_reasons") or []),
        "stale_count": int(decision.get("stale_count") or 0),
        "cooldown_remaining_seconds": int(decision.get("cooldown_remaining_seconds") or 0),
        "next_allowed_at": str(decision.get("next_allowed_at") or ""),
        "summary": str(decision.get("summary") or ""),
        "triggered": bool(decision.get("triggered")),
        "trigger": (
            {
                "started": bool(trigger.get("started")),
                "run_id": str(trigger.get("run_id") or ""),
                "task_name": str(trigger.get("task_name") or ""),
                "title": str(trigger.get("title") or ""),
                "log_path": str(trigger.get("log_path") or ""),
                "meta_path": str(trigger.get("meta_path") or ""),
            }
            if trigger
            else None
        ),
    }


_RECOVERY_TASK_METADATA: dict[str, dict[str, Any]] = {
    "watchlist_refresh": {
        "purpose": "刷新自选股快照，后续观察池与持仓复核都依赖它。",
        "writes_to_ledger": False,
        "estimated_seconds": 60,
    },
    "aggressive": {
        "purpose": "重跑进攻型选股，决定今天有没有新的候选股。",
        "writes_to_ledger": False,
        "estimated_seconds": 120,
    },
    "screening": {
        "purpose": "重跑进攻型选股，决定今天有没有新的候选股。",
        "writes_to_ledger": False,
        "estimated_seconds": 120,
    },
    "midday_confirmation": {
        "purpose": "重跑午盘承接确认，决定哪些观察项继续保留。",
        "writes_to_ledger": False,
        "estimated_seconds": 90,
    },
    "command_brief": {
        "purpose": "重新生成投资总控简报，把当日判断串成一条链。",
        "writes_to_ledger": False,
        "estimated_seconds": 30,
    },
    "portfolio_cash": {
        "purpose": "修复账户现金口径，避免真钱执行误判。",
        "writes_to_ledger": True,
        "estimated_seconds": 30,
    },
    "account_reconcile": {
        "purpose": "完成账户对账，让真钱执行重新有依据。",
        "writes_to_ledger": True,
        "estimated_seconds": 60,
    },
}


def _recovery_metadata(task_name: str) -> dict[str, Any]:
    base = _RECOVERY_TASK_METADATA.get(task_name) or {}
    return {
        "purpose": base.get("purpose") or "运行此任务以恢复对应数据源。",
        "writes_to_ledger": bool(base.get("writes_to_ledger", False)),
        "estimated_seconds": int(base.get("estimated_seconds") or 60),
    }


def _build_readiness_recovery_steps(
    *,
    page: str,
    readiness_payload: dict[str, Any] | None,
    recommended_task_name: str,
    recommended_task: dict[str, Any],
    running: list[dict[str, Any]],
    cooldown: dict[str, Any],
) -> list[dict[str, Any]]:
    if page != "today":
        return []

    allowed_tasks = {normalize_task_name(item) for item in REFRESH_PAGE_CONFIG[page]["allowed_tasks"]}
    task_order = ["watchlist_refresh", "aggressive", "midday_confirmation", "command_brief"]
    issue_map: dict[str, list[dict[str, Any]]] = {}
    for issue in [
        *((readiness_payload or {}).get("blockers") or []),
        *((readiness_payload or {}).get("warnings") or []),
    ]:
        task_name = normalize_task_name(str(issue.get("recommended_task") or "").strip())
        if task_name:
            issue_map.setdefault(task_name, []).append(issue)

    ordered_tasks: list[str] = []
    for task_name in task_order:
        if task_name in allowed_tasks and task_name in issue_map:
            ordered_tasks.append(task_name)
    if recommended_task_name and recommended_task_name in allowed_tasks and recommended_task_name not in ordered_tasks:
        ordered_tasks.insert(0, recommended_task_name)

    if not ordered_tasks and recommended_task_name:
        ordered_tasks = [recommended_task_name]

    state = load_refresh_state()

    steps: list[dict[str, Any]] = []
    for index, task_name in enumerate(ordered_tasks, start=1):
        try:
            task = resolve_refresh_task(task_name)
        except HTTPException:
            continue
        issues = issue_map.get(task_name) or []
        if task_name == recommended_task_name and not issues:
            issues = [{
                "label": "建议动作",
                "message": f"运行 {recommended_task.get('title') or task['title']} 后重新检查 readiness。",
            }]
        step_cooldown = page_cooldown_state(page=page, task_name=task_name, state=state)
        cooldown_remaining = int(step_cooldown.get("remaining_seconds") or 0)
        status = "ready"
        if task_conflict_is_running(task_name, running):
            status = "running"
        elif cooldown_remaining > 0:
            status = "cooldown"
        metadata = _recovery_metadata(task_name)
        steps.append(
            {
                "step": index,
                "task_name": task_name,
                "title": task["title"],
                "status": status,
                "can_trigger": status == "ready",
                "cooldown_remaining_seconds": cooldown_remaining if status == "cooldown" else 0,
                "next_allowed_at": step_cooldown.get("next_allowed_at") or "",
                "issue_count": len(issues),
                "issues": [
                    {
                        "code": item.get("code"),
                        "label": item.get("label") or "阻断项",
                        "message": item.get("message") or "",
                    }
                    for item in issues[:3]
                ],
                "purpose": metadata["purpose"],
                "writes_to_ledger": metadata["writes_to_ledger"],
                "estimated_seconds": metadata["estimated_seconds"],
            }
        )
    return steps


def _public_run_state(task_name: str, *, now: datetime) -> dict[str, Any]:
    state = run_state_for_task(task_name, now=now)
    return {
        "task_name": state.get("task_name") or task_name,
        "status": state.get("status") or "missing",
        "same_day": bool(state.get("same_day")),
        "today_success": bool(state.get("today_success")),
        "running": bool(state.get("running")),
        "orphaned": bool(state.get("orphaned")),
        "pid_alive": bool(state.get("pid_alive")),
        "running_age_seconds": state.get("running_age_seconds"),
        "failed_today": bool(state.get("failed_today")),
        "missing": bool(state.get("missing")),
        "stale_latest": bool(state.get("stale_latest")),
        "trade_date": state.get("trade_date") or "",
        "expected_trade_date": state.get("expected_trade_date") or "",
        "run_id": state.get("run_id") or "",
        "title": state.get("title") or task_name,
        "started_at": state.get("started_at") or "",
        "finished_at": state.get("finished_at") or "",
        "exit_code": state.get("exit_code"),
        "skip_reason": state.get("skip_reason") or "",
        "log_path": state.get("log_path") or "",
        "meta_path": state.get("meta_path") or "",
    }


def _job_health(run_state: dict[str, Any]) -> str:
    if run_state.get("running"):
        return "running"
    if run_state.get("today_success"):
        return "success"
    if run_state.get("failed_today"):
        return "failed"
    if run_state.get("stale_latest"):
        return "stale"
    return "missing"


def build_scheduler_status_payload(*, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now()
    state = load_scheduler_state()
    alive = scheduler_alive(state, now=current)
    catchup_fired = state.get("catchup_fired") if isinstance(state.get("catchup_fired"), dict) else {}
    retry_counts = state.get("retry_counts") if isinstance(state.get("retry_counts"), dict) else {}
    day = current.strftime("%Y-%m-%d")
    jobs: list[dict[str, Any]] = []
    counts = {"total": 0, "success": 0, "running": 0, "failed": 0, "stale": 0, "missing": 0}
    for policy in CRON_POLICIES:
        run_state = _public_run_state(policy.task_name, now=current)
        health = _job_health(run_state)
        counts["total"] += 1
        counts[health] = counts.get(health, 0) + 1
        key = f"{day}:{policy.task_name}"
        jobs.append(
            {
                "task_name": policy.task_name,
                "name": policy.name,
                "cron_expr": policy.cron_expr,
                "catchup_enabled": bool(policy.catchup_enabled),
                "catchup_until": policy.catchup_until,
                "catchup_fired": catchup_fired.get(key) or None,
                "retry_attempts": int(policy.retry_attempts or 0),
                "retry_delay_seconds": int(policy.retry_delay_seconds or 0),
                "retry_count_today": int(retry_counts.get(key) or 0),
                "depends_on": list(policy.depends_on),
                "health": health,
                "run": run_state,
            }
        )
    return {
        "server_time": current.strftime("%Y-%m-%d %H:%M:%S"),
        "calendar": calendar_status(current),
        "scheduler": {
            "alive": alive,
            "pid": state.get("pid"),
            "started_at": state.get("started_at") or "",
            "last_tick_at": state.get("last_tick_at") or "",
            "state_path": str(SCHEDULER_STATE_PATH),
            "send_to_feishu": bool(state.get("send_to_feishu")),
            "fire_on_start": bool(state.get("fire_on_start")),
            "freshness_guardian": state.get("freshness_guardian") if isinstance(state.get("freshness_guardian"), dict) else {},
        },
        "summary": counts,
        "jobs": jobs,
    }


def _scheduler_safety_status_payload(*, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now()
    state = load_scheduler_state()
    required = set(SCHEDULER_REQUIRED_TASKS)
    jobs: list[dict[str, Any]] = []
    for policy in CRON_POLICIES:
        if policy.task_name not in required:
            continue
        run_state = _public_run_state(policy.task_name, now=current)
        jobs.append(
            {
                "task_name": policy.task_name,
                "cron_expr": policy.cron_expr,
                "run": {
                    "running": bool(run_state.get("running")),
                    "today_success": bool(run_state.get("today_success")),
                },
            }
        )
    return {
        "calendar": calendar_status(current),
        "scheduler": {"alive": scheduler_alive(state, now=current)},
        "jobs": jobs,
    }


def _scheduler_safety_lightweight_task(
    *,
    page: str,
    freshness: list[dict[str, Any]],
    readiness_payload: dict[str, Any] | None,
    running: list[dict[str, Any]],
    state: dict[str, Any],
    now: datetime,
) -> str:
    if page != "today":
        return ""
    if readiness_payload and not readiness_payload.get("ready"):
        return ""
    allowed_tasks = list((page_policy(page).allowed_tasks) if page_policy(page) else ())
    task_name = eligible_lightweight_task(page=page, freshness=freshness, allowed_tasks=allowed_tasks)
    if not task_name:
        return ""
    if task_conflict_is_running(task_name, running):
        return ""
    cooldown = page_cooldown_state(page=page, task_name=task_name, state=state, now=now)
    if int(cooldown.get("remaining_seconds") or 0) > 0:
        return ""
    return task_name


def build_refresh_status_payload(
    page: str,
    *,
    auto: bool = False,
    now: datetime | None = None,
    skip_auto: bool = False,
    compact: bool = False,
) -> dict[str, Any]:
    current = now or datetime.now()
    market_mode, market_label = current_market_mode(current)
    running = build_running_refresh_tasks(page)
    cfg = page_policy(page)
    state = load_refresh_state()

    # Single source of truth for the today page: readiness drives freshness,
    # stale_count, recommended_task and the readiness_mode signature.  The
    # legacy ``build_page_freshness`` heuristic is bypassed entirely so the
    # refresh widget cannot disagree with the Today summary/readiness surfaces.
    readiness_payload: dict[str, Any] | None = None
    if page == "today":
        try:
            today_view = build_today_readiness_view()
            readiness_payload = today_view.get("readiness")
        except Exception:
            readiness_payload = None

    if readiness_payload:
        fallback_threshold = int(REFRESH_PAGE_CONFIG[page]["stale_after_seconds"][market_mode])
        freshness = _readiness_freshness_rows(
            readiness_payload, fallback_threshold=fallback_threshold
        )
        try:
            expected_date = str(readiness_payload.get("expected_trade_date") or readiness_expected_trade_date(current))
        except Exception:
            expected_date = current.strftime("%Y-%m-%d")
        freshness.extend(_dataset_manifest_freshness_rows(expected_date=expected_date, now=current))
        page_stale_count = int(readiness_payload.get("stale_count") or 0)
        readiness_recommendations = [
            normalize_task_name(str(name).strip())
            for name in (readiness_payload.get("recommended_tasks") or [])
            if str(name).strip()
        ]
    else:
        freshness = build_page_freshness(page, market_mode)
        page_stale_count = sum(1 for item in freshness if item.get("stale"))
        readiness_recommendations = []

    if readiness_payload and readiness_payload.get("ready"):
        freshness = [item for item in freshness if not item.get("dataset_manifest")]
    elif page != "today":
        try:
            freshness.extend(
                _dataset_manifest_freshness_rows(
                    expected_date=readiness_expected_trade_date(current),
                    now=current,
                )
            )
        except Exception:
            pass

    allowed_tasks = list(cfg.allowed_tasks if cfg else ())
    lightweight_task = None if (page == "today" and readiness_payload and not readiness_payload.get("ready")) else eligible_lightweight_task(
        page=page,
        freshness=freshness,
        allowed_tasks=allowed_tasks,
    )
    recommended_task_name = lightweight_task or policy_pick_recommended_task(
        page=page,
        freshness=freshness,
        market_mode=market_mode,
        readiness_payload=readiness_payload,
        now=current,
    )
    recommended_task_name = normalize_task_name(recommended_task_name)
    recommended_task = resolve_refresh_task(recommended_task_name)
    policy = task_policy(recommended_task_name)
    policy_freshness = _stale_subset(
        freshness,
        list(policy.manifest_dependencies if policy else ()),
    )
    manifest_stale_count = sum(1 for item in freshness if item.get("stale"))
    task_stale_count = sum(1 for item in policy_freshness if item.get("stale"))
    cooldown = page_cooldown_state(
        page=page,
        task_name=recommended_task_name,
        state=state,
        now=current,
    )
    auto_decision = evaluate_auto_refresh(
        page=page,
        recommended_task=recommended_task_name,
        freshness=policy_freshness,
        readiness_payload=readiness_payload,
        running=running,
        cooldown=cooldown,
        force=False,
        now=current,
    )
    trigger_result: dict[str, Any] | None = None
    scheduler_status: dict[str, Any] = {}
    if auto and not skip_auto:
        scheduler_status = (
            _scheduler_safety_status_payload(now=current)
            if compact
            else build_scheduler_status_payload(now=current)
        )
    elif not compact:
        scheduler_status = build_scheduler_status_payload(now=current)
    scheduler_safety_refresh: dict[str, Any] | None = None
    if auto and not skip_auto:
        scheduler_safety_refresh = maybe_trigger_scheduler_safety_refresh(
            page=page,
            scheduler_status=scheduler_status,
            running=running,
            current=current,
            state=state,
        )
        if scheduler_safety_refresh:
            state = load_refresh_state()
            running = build_running_refresh_tasks(page)
            scheduler_status = (
                _scheduler_safety_status_payload(now=current)
                if compact
                else build_scheduler_status_payload(now=current)
            )
            suggested_poll_seconds = min(int(REFRESH_PAGE_CONFIG[page]["poll_seconds"][market_mode]), 25)

    if auto and not skip_auto and not scheduler_safety_refresh and auto_decision.get("should_trigger"):
        trigger_result = trigger_refresh_task(
            page=page,
            task_name=recommended_task_name,
            force=False,
            trigger_type="auto",
            reason=str(auto_decision.get("summary") or "auto_refresh"),
            decision=auto_decision,
            freshness=policy_freshness,
        )
        auto_decision = {
            **auto_decision,
            "triggered": True,
            "trigger": trigger_result,
        }
        state = load_refresh_state()
        running = build_running_refresh_tasks(page)
        cooldown = page_cooldown_state(
            page=page,
            task_name=recommended_task_name,
            state=state,
            now=current,
        )
        auto_decision["cooldown_remaining_seconds"] = int(cooldown.get("remaining_seconds") or 0)
        auto_decision["next_allowed_at"] = str(cooldown.get("next_allowed_at") or "")
    else:
        auto_decision = {**auto_decision, "triggered": False, "trigger": None}

    if auto and not skip_auto and not auto_decision.get("triggered") and not scheduler_safety_refresh:
        lightweight_task = _scheduler_safety_lightweight_task(
            page=page,
            freshness=freshness,
            readiness_payload=readiness_payload,
            running=running,
            state=state,
            now=current,
        )
        if lightweight_task:
            lightweight_policy = task_policy(lightweight_task)
            lightweight_freshness = _stale_subset(
                freshness,
                list(lightweight_policy.manifest_dependencies if lightweight_policy else ()),
            )
            decision = {
                "enabled": True,
                "allowed": True,
                "should_trigger": True,
                "force": False,
                "page": page,
                "task_name": lightweight_task,
                "task_kind": (lightweight_policy.kind if lightweight_policy else "lightweight"),
                "reason_codes": ["lightweight_dataset_stale", "first_open_recovery"],
                "blocked_reasons": [],
                "active_windows": active_auto_windows(current),
                "required_windows": list(lightweight_policy.auto_windows if lightweight_policy else ()),
                "manifest_reasons": manifest_trigger_reasons(lightweight_freshness),
                "stale_count": sum(1 for item in lightweight_freshness if item.get("stale")),
                "cooldown_remaining_seconds": 0,
                "next_allowed_at": "",
                "calendar_status": calendar_status(current),
                "summary": "",
            }
            decision["summary"] = summarize_auto_decision(decision)
            trigger_result = trigger_refresh_task(
                page=page,
                task_name=lightweight_task,
                force=False,
                trigger_type="auto",
                reason="homepage_lightweight_first_open_recovery",
                decision=decision,
                freshness=lightweight_freshness,
            )
            auto_decision = {
                **decision,
                "triggered": True,
                "trigger": trigger_result,
            }
            state = load_refresh_state()
            running = build_running_refresh_tasks(page)
            cooldown = page_cooldown_state(
                page=page,
                task_name=lightweight_task,
                state=state,
                now=current,
            )
            auto_decision["cooldown_remaining_seconds"] = int(cooldown.get("remaining_seconds") or 0)
            auto_decision["next_allowed_at"] = str(cooldown.get("next_allowed_at") or "")

    suggested_poll_seconds = int(REFRESH_PAGE_CONFIG[page]["poll_seconds"][market_mode])
    if running:
        suggested_poll_seconds = min(suggested_poll_seconds, 25)

    recovery_steps = [] if compact else _build_readiness_recovery_steps(
        page=page,
        readiness_payload=readiness_payload,
        recommended_task_name=recommended_task_name,
        recommended_task=recommended_task,
        running=running,
        cooldown=cooldown,
    )

    signature_payload = {
        "page": page,
        "recommended_task": recommended_task_name,
        "recovery_steps": [(item.get("task_name"), item.get("status")) for item in recovery_steps],
        "stale_count": page_stale_count,
        "freshness": [
            (item.get("label"), item.get("value"), bool(item.get("stale")))
            for item in freshness
        ],
        "running": [(item.get("task_name"), item.get("started_at")) for item in running],
        "cooldown_remaining": cooldown.get("remaining_seconds"),
        "readiness_mode": (readiness_payload or {}).get("readiness_mode"),
        "auto_refresh": auto_decision,
    }
    signature_seed = json.dumps(signature_payload, ensure_ascii=False, sort_keys=True)
    snapshot_signature = hashlib.sha1(signature_seed.encode("utf-8")).hexdigest()[:16]

    last_auto_refresh = _latest_audit_event(state=state, trigger_type="auto")
    last_refresh_event = _latest_audit_event(state=state)
    payload = {
        "page": page,
        "server_time": current.strftime("%Y-%m-%d %H:%M:%S"),
        "market_mode": market_mode,
        "market_label": market_label,
        "suggested_poll_seconds": suggested_poll_seconds,
        "freshness": freshness,
        "stale_count": page_stale_count,
        "manifest_stale_count": manifest_stale_count,
        "task_stale_count": task_stale_count,
        "running": running,
        "recommended_task": {
            "task_name": recommended_task_name,
            "title": recommended_task["title"],
            "kind": policy.kind if policy else "unknown",
            "cooldown_seconds": policy.cooldown_seconds if policy else cooldown.get("seconds"),
            "manifest_dependencies": list(policy.manifest_dependencies if policy else ()),
        },
        "cooldown": cooldown,
        "auto_refresh": auto_decision,
        "snapshot_signature": snapshot_signature,
    }
    if compact:
        if page == "today":
            payload.pop("freshness", None)
            payload["freshness_deferred"] = True
            payload["links_lazy"] = {"freshness": f"/api/refresh/status?page={page}&compact=0"}
        payload["cooldown"] = _compact_cooldown_payload(cooldown)
        payload["auto_refresh"] = _compact_auto_decision_payload(auto_decision)
        payload["last_auto_refresh"] = _compact_audit_event_payload(last_auto_refresh)
        if scheduler_safety_refresh:
            payload["scheduler_safety_refresh"] = scheduler_safety_refresh
    else:
        payload["recovery_steps"] = recovery_steps
        payload["last_auto_refresh"] = last_auto_refresh
        payload["last_refresh_event"] = last_refresh_event
        payload["policy"] = {
            "page": cfg.as_dict() if cfg else {},
            "task": policy.as_dict() if policy else {},
        }
        payload["policy_catalog"] = build_policy_payload()
        payload["scheduler_status"] = scheduler_status
        payload["scheduler_safety_refresh"] = scheduler_safety_refresh
        payload["active_auto_windows"] = active_auto_windows(current)
    if readiness_payload:
        payload["readiness_mode"] = readiness_payload.get("readiness_mode")
        payload["recommended_tasks"] = readiness_recommendations
        if not compact:
            payload["readiness"] = readiness_payload
    return payload


def save_refresh_trigger(
    *,
    page: str,
    task_name: str,
    run_id: str,
    force: bool,
    trigger_type: str,
    reason: str,
    decision: dict[str, Any] | None = None,
    freshness: list[dict[str, Any]] | None = None,
) -> None:
    state = load_refresh_state()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normalized_task = normalize_task_name(task_name)
    pages = state.setdefault("pages", {})
    if not isinstance(pages, dict):
        pages = {}
        state["pages"] = pages
    pages[page] = {
        "task_name": normalized_task,
        "run_id": run_id,
        "forced": bool(force),
        "last_trigger_at": timestamp,
        "trigger_type": trigger_type,
        "reason": reason,
        "decision": decision or {},
    }
    tasks = state.setdefault("tasks", {})
    if not isinstance(tasks, dict):
        tasks = {}
        state["tasks"] = tasks
    task_event = {
        "task_name": normalized_task,
        "task_family": task_family(normalized_task),
        "page": page,
        "run_id": run_id,
        "forced": bool(force),
        "last_trigger_at": timestamp,
        "trigger_type": trigger_type,
        "reason": reason,
        "decision": decision or {},
    }
    tasks[normalized_task] = task_event
    audit_events = state.setdefault("audit_events", [])
    if not isinstance(audit_events, list):
        audit_events = []
        state["audit_events"] = audit_events
    audit_events.append(
        {
            "ts": timestamp,
            "trigger_type": trigger_type,
            "page": page,
            "task_name": normalized_task,
            "task_family": task_family(normalized_task),
            "run_id": run_id,
            "force": bool(force),
            "reason": reason,
            "manifest_state": [
                {
                    "key": item.get("key"),
                    "label": item.get("label"),
                    "stale": bool(item.get("stale")),
                    "freshness_status": item.get("freshness_status"),
                    "trade_date": item.get("trade_date"),
                    "stale_reasons": list(item.get("stale_reasons") or []),
                }
                for item in (freshness or [])[:12]
            ],
            "cooldown": {
                "remaining_seconds": int((decision or {}).get("cooldown_remaining_seconds") or 0),
                "next_allowed_at": str((decision or {}).get("next_allowed_at") or ""),
            },
            "decision": decision or {},
        }
    )
    state["audit_events"] = audit_events[-100:]
    state["updated_at"] = timestamp
    save_refresh_state(state)


def trigger_refresh_task(
    *,
    page: str,
    task_name: str,
    force: bool,
    trigger_type: str,
    reason: str,
    decision: dict[str, Any] | None = None,
    freshness: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_task_name(task_name)
    task = resolve_refresh_task(normalized)
    result = launch_background_task(
        task_name=task["task_name"],
        title=task["title"],
        command=task["command"],
        cwd=task["cwd"],
        send_to_feishu=bool(task.get("send_to_feishu", False)),
    )
    save_refresh_trigger(
        page=page,
        task_name=normalized,
        run_id=str(result.get("run_id") or ""),
        force=force,
        trigger_type=trigger_type,
        reason=reason,
        decision=decision,
        freshness=freshness,
    )
    return result


def _scheduler_safety_task(status: dict[str, Any], *, now: datetime) -> str:
    scheduler = status.get("scheduler") if isinstance(status.get("scheduler"), dict) else {}
    calendar = status.get("calendar") if isinstance(status.get("calendar"), dict) else {}
    if calendar.get("status") != "trading":
        return ""
    jobs = status.get("jobs") if isinstance(status.get("jobs"), list) else []
    by_task = {
        str(job.get("task_name") or ""): job
        for job in jobs
        if isinstance(job, dict)
    }
    for task_name in SCHEDULER_REQUIRED_TASKS:
        job = by_task.get(task_name)
        if job is None:
            continue
        due_minute = _cron_daily_minute(str(job.get("cron_expr") or ""))
        if due_minute is not None and now.hour * 60 + now.minute < due_minute + SCHEDULER_SAFETY_GRACE_MINUTES:
            continue
        run = job.get("run") if isinstance(job.get("run"), dict) else {}
        if run.get("running"):
            return ""
        if not run.get("today_success") and not _control_panel_task_success_today(task_name, now=now):
            return task_name
    return ""


def _control_panel_task_success_today(task_name: str, *, now: datetime) -> bool:
    family = task_family(task_name)
    today = now.strftime("%Y-%m-%d")
    for item in list_runs(limit=120):
        item_task = normalize_task_name(str(item.get("task_name") or ""))
        if task_family(item_task) != family:
            continue
        if str(item.get("status") or "") != "success":
            continue
        for timestamp in (item.get("finished_at"), item.get("started_at")):
            text = str(timestamp or "")
            if text.startswith(today):
                return True
    return False


def _scheduler_recovery_running(running: list[dict[str, Any]]) -> bool:
    for item in running:
        task_name = normalize_task_name(str(item.get("task_name") or ""))
        if task_name in SCHEDULER_REQUIRED_TASKS:
            return True
    return False


def maybe_trigger_scheduler_safety_refresh(
    *,
    page: str,
    scheduler_status: dict[str, Any],
    running: list[dict[str, Any]],
    current: datetime,
    state: dict[str, Any],
) -> dict[str, Any] | None:
    if page != "today":
        return None
    if _scheduler_recovery_running(running):
        return None
    task_name = _scheduler_safety_task(scheduler_status, now=current)
    if not task_name:
        return None

    cooldown = page_cooldown_state(page=page, task_name=task_name, state=state, now=current)
    if int(cooldown.get("remaining_seconds") or 0) > 0:
        return None

    scheduler = scheduler_status.get("scheduler") if isinstance(scheduler_status.get("scheduler"), dict) else {}
    scheduler_alive_flag = bool(scheduler.get("alive"))
    reason_codes = [
        "morning_required_task_missing",
        "scheduler_due_task_missing" if scheduler_alive_flag else "scheduler_offline",
    ]
    reason = "scheduler_due_required_task_missing" if scheduler_alive_flag else "scheduler_offline_required_task_missing"
    summary_reason = "今日早盘关键任务到点后仍未成功" if scheduler_alive_flag else "Scheduler 不在线且今日关键任务缺跑"
    decision = {
        "enabled": True,
        "allowed": True,
        "should_trigger": True,
        "force": False,
        "page": page,
        "task_name": task_name,
        "task_kind": (task_policy(task_name).kind if task_policy(task_name) else "lightweight"),
        "reason_codes": reason_codes,
        "blocked_reasons": [],
        "active_windows": active_auto_windows(current),
        "required_windows": ["premarket", "morning"],
        "manifest_reasons": ["trade_date_mismatch"],
        "stale_count": 1,
        "cooldown_remaining_seconds": 0,
        "next_allowed_at": "",
        "calendar_status": scheduler_status.get("calendar") or calendar_status(current),
        "summary": f"{summary_reason}，自动触发 {task_policy(task_name).title if task_policy(task_name) else task_name}。",
    }
    result = trigger_refresh_task(
        page=page,
        task_name=task_name,
        force=False,
        trigger_type="scheduler_safety",
        reason=reason,
        decision=decision,
        freshness=[],
    )
    return {
        "triggered": True,
        "task_name": task_name,
        "reason": reason,
        "trigger": result,
    }


@app.get("/", include_in_schema=False)
async def index(request: Request) -> RedirectResponse:
    return web_redirect("/", query=request.url.query)


@app.get("/api/overview")
def api_overview(fresh: bool = False, compact: bool = True) -> JSONResponse:
    global _OVERVIEW_API_CACHE

    cache = _OVERVIEW_API_CACHE or {}
    if OVERVIEW_API_CACHE_TTL_SECONDS > 0 and compact in cache and not fresh:
        cached_at, cached_payload = cache[compact]
        if time.monotonic() - cached_at <= OVERVIEW_API_CACHE_TTL_SECONDS:
            return JSONResponse(deepcopy(cached_payload))

    if fresh:
        clear_run_list_cache()
    payload = build_overview_summary(compact=compact)
    if OVERVIEW_API_CACHE_TTL_SECONDS > 0:
        cache[compact] = (time.monotonic(), deepcopy(payload))
        _OVERVIEW_API_CACHE = cache
    return JSONResponse(payload)


@app.get("/api/shell/status")
def api_shell_status() -> JSONResponse:
    return JSONResponse(build_shell_status_view())


@app.get("/today", include_in_schema=False)
async def today(request: Request) -> RedirectResponse:
    return web_redirect("/", query=request.url.query)


_TODAY_SUMMARY_READINESS_DEFERRED_KEYS = {
    "blockers",
    "warnings",
    "formal_blockers",
    "source_freshness",
}


def _today_summary_readiness_payload(
    readiness: dict[str, Any],
    formal_data_status: dict[str, Any],
) -> dict[str, Any]:
    payload = public_today_summary_readiness(readiness, formal_data_status)
    return {
        key: value
        for key, value in payload.items()
        if key not in _TODAY_SUMMARY_READINESS_DEFERRED_KEYS
    }


@app.get("/api/today/summary")
def api_today_summary(fresh: bool = False) -> JSONResponse:
    global _TODAY_SUMMARY_API_CACHE

    if TODAY_SUMMARY_API_CACHE_TTL_SECONDS > 0 and _TODAY_SUMMARY_API_CACHE and not fresh:
        cached_at, cached_payload = _TODAY_SUMMARY_API_CACHE
        if time.monotonic() - cached_at <= TODAY_SUMMARY_API_CACHE_TTL_SECONDS:
            return JSONResponse(deepcopy(cached_payload))

    if fresh:
        clear_today_base_inputs_cache()

    today_view = build_today_summary_view()
    readiness = today_view.get("readiness")
    if isinstance(readiness, dict):
        today_view["readiness"] = _today_summary_readiness_payload(
            readiness,
            build_formal_data_status_payload(fresh=fresh),
        )
        today_view["readiness_details_deferred"] = True
    if TODAY_SUMMARY_API_CACHE_TTL_SECONDS > 0:
        _TODAY_SUMMARY_API_CACHE = (time.monotonic(), deepcopy(today_view))
    return JSONResponse(today_view)


@app.get("/api/today/actions")
def api_today_actions(fresh: bool = False) -> JSONResponse:
    global _TODAY_ACTIONS_API_CACHE, _TODAY_ACTION_CONTRACTS_API_CACHE

    if fresh:
        _TODAY_ACTION_CONTRACTS_API_CACHE = None
        clear_today_base_inputs_cache()

    if TODAY_ACTIONS_API_CACHE_TTL_SECONDS > 0 and _TODAY_ACTIONS_API_CACHE and not fresh:
        cached_at, cached_payload = _TODAY_ACTIONS_API_CACHE
        if time.monotonic() - cached_at <= TODAY_ACTIONS_API_CACHE_TTL_SECONDS:
            return JSONResponse(deepcopy(cached_payload))

    payload = build_today_actions_view()
    if TODAY_ACTIONS_API_CACHE_TTL_SECONDS > 0:
        _TODAY_ACTIONS_API_CACHE = (time.monotonic(), deepcopy(payload))
    return JSONResponse(payload)


@app.get("/api/today/action-contracts")
def api_today_action_contracts(fresh: bool = False) -> JSONResponse:
    global _TODAY_ACTION_CONTRACTS_API_CACHE

    if TODAY_ACTIONS_API_CACHE_TTL_SECONDS > 0 and _TODAY_ACTION_CONTRACTS_API_CACHE and not fresh:
        cached_at, cached_payload = _TODAY_ACTION_CONTRACTS_API_CACHE
        if time.monotonic() - cached_at <= TODAY_ACTIONS_API_CACHE_TTL_SECONDS:
            return JSONResponse(deepcopy(cached_payload))

    if fresh:
        clear_today_base_inputs_cache()

    payload = build_today_action_contracts_view()
    if TODAY_ACTIONS_API_CACHE_TTL_SECONDS > 0:
        _TODAY_ACTION_CONTRACTS_API_CACHE = (time.monotonic(), deepcopy(payload))
    return JSONResponse(payload)


@app.get("/api/today/command-brief-detail")
def api_today_command_brief_detail(fresh: bool = False) -> JSONResponse:
    global _TODAY_COMMAND_BRIEF_DETAIL_API_CACHE

    if TODAY_ACTIONS_API_CACHE_TTL_SECONDS > 0 and _TODAY_COMMAND_BRIEF_DETAIL_API_CACHE and not fresh:
        cached_at, cached_payload = _TODAY_COMMAND_BRIEF_DETAIL_API_CACHE
        if time.monotonic() - cached_at <= TODAY_ACTIONS_API_CACHE_TTL_SECONDS:
            return JSONResponse(deepcopy(cached_payload))

    if fresh:
        clear_today_base_inputs_cache()

    payload = build_today_command_brief_detail_view()
    if TODAY_ACTIONS_API_CACHE_TTL_SECONDS > 0:
        _TODAY_COMMAND_BRIEF_DETAIL_API_CACHE = (time.monotonic(), deepcopy(payload))
    return JSONResponse(payload)


@app.get("/ask", include_in_schema=False)
async def ask(request: Request, q: str | None = None) -> RedirectResponse:
    query = str(q or "").strip()
    if len(query) == 6 and query.isdigit():
        return web_redirect(f"/stock/{query}")
    return web_redirect("/", query=request.url.query)


@app.get("/api/ask")
async def api_ask(q: str | None = None) -> JSONResponse:
    if not str(q or "").strip():
        return JSONResponse(build_ask_page_view())
    try:
        return JSONResponse(build_ask_page_view(query=q))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ask/suggest")
async def api_ask_suggest(q: str | None = None) -> JSONResponse:
    query = str(q or "").strip()
    digit_query = "".join(ch for ch in query if ch.isdigit())
    if not query or (len(query) < 2 and len(digit_query) != 6):
        return JSONResponse(
            {
                "query": query,
                "items": [],
                "message": "输入至少 2 个字符或 6 位代码后开始联想。",
                "recent_queries": [],
            }
        )

    items = build_ask_suggestions(query, None, None, None)
    if items:
        message = f"找到 {len(items)} 个系统内/历史库/全市场候选。"
    else:
        message = "当前系统、历史库和全市场联想都没匹配，建议直接输入 6 位代码。"
    return JSONResponse(
        {
            "query": query,
            "items": items,
            "message": message,
            "recent_queries": [],
        }
    )


@app.post("/api/ask/followup")
async def api_ask_followup(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    query = str(payload.get("q") or payload.get("query") or "").strip()
    question = str(payload.get("question") or "").strip()
    history = payload.get("history")
    try:
        return JSONResponse(build_ask_followup_view(question, query, history))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/today/actions/decision")
async def api_today_action_decision(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    trade_date = str(payload.get("trade_date") or "").strip()
    key = str(payload.get("key") or "").strip()
    decision = str(payload.get("decision") or "pending").strip().lower()

    try:
        update_today_action_decision(trade_date, key, decision)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    parsed_code = _stock_code_from_action_key(key)
    if trade_date and trade_date < readiness_expected_trade_date():
        _clear_stock_profile_account_sensitive_cache()
    else:
        _clear_stock_profile_account_sensitive_cache(parsed_code or None)
    _clear_portfolio_related_api_caches()

    actions_view = build_today_actions_view()
    action_queue = actions_view.get("action_queue") or {}
    matched_item = next(
        (
            item
            for item in [
                *(action_queue.get("items") or []),
                *(action_queue.get("stale_items") or []),
            ]
            if item.get("key") == key
        ),
        None,
    )

    # ``watch`` / ``skip`` are real operator decisions that belong in the
    # ledger.  ``done`` is intentionally NOT translated into a filled
    # event -- a fill needs price + quantity, which Portfolio writeback
    # supplies.  ``pending`` is an undo of the local action queue
    # checklist state, not a decision.
    if decision in {"watch", "skip"}:
        parsed_code = key.split(":", 1)[1].strip() if ":" in key else ""
        ledger_result = decision_ledger.append_execution_event_for_writeback(
            trade_date=trade_date,
            code=parsed_code,
            status=decision,
            today_action_key=key,
            source="today_decision_writeback",
        )
    else:
        ledger_result = {"attached": False, "reason": "ineligible"}

    return JSONResponse(
        {
            "ok": True,
            "trade_date": trade_date,
            "key": key,
            "decision": (matched_item or {}).get("decision")
            or {
                "value": decision,
                "label": decision,
                "tone": "watch",
                "updated_at": "",
            },
            "counts": action_queue.get("counts") or {},
            "ledger": ledger_result,
        }
    )


@app.get("/watchlist", include_in_schema=False)
async def watchlist(request: Request) -> RedirectResponse:
    return web_redirect("/portfolio", query=request.url.query)


@app.get("/api/watchlist")
def api_watchlist(fresh: bool = False) -> JSONResponse:
    return JSONResponse(_watchlist_api_payload(fresh=fresh))


@app.get("/api/watchlist/manage")
def api_watchlist_manage(fresh: bool = False) -> JSONResponse:
    if fresh:
        _clear_watchlist_api_cache()
    return JSONResponse({"manager": build_watchlist_manager_api_view()})


@app.post("/api/watchlist/manage/add")
async def api_watchlist_manage_add(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    code = str(payload.get("code") or "").strip()
    name = str(payload.get("name") or "").strip() or None
    if not code:
        raise HTTPException(status_code=400, detail="缺少股票代码")

    try:
        operation = upsert_watchlist_stock(code, name=name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _clear_stock_profile_account_sensitive_cache(code)
    _clear_watchlist_related_api_caches()

    trigger_refresh = parse_bool_value(payload.get("trigger_refresh"), True)
    refresh = {"started": False}
    should_refresh = operation.get("status") in {"added", "restored", "updated"}
    if trigger_refresh and should_refresh:
        refresh = launch_background_task(
            task_name="watchlist_refresh",
            title="自选股名单刷新",
            command=WATCHLIST_REFRESH_COMMAND,
            cwd=str(WORKSPACE_ROOT),
            send_to_feishu=False,
        )

    manager = build_watchlist_manager_api_view()
    message = watchlist_message("add", str(operation.get("status") or ""), operation.get("stock") or {}, refresh["started"])
    return JSONResponse(
        {
            "ok": True,
            "action": "add",
            "message": message,
            "operation": operation,
            "refresh": refresh,
            "manager": manager,
        }
    )


@app.post("/api/watchlist/manage/archive")
async def api_watchlist_manage_archive(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    code = str(payload.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="缺少股票代码")

    try:
        operation = archive_watchlist_stock(code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _clear_stock_profile_account_sensitive_cache(code)
    _clear_watchlist_related_api_caches()

    trigger_refresh = parse_bool_value(payload.get("trigger_refresh"), True)
    refresh = {"started": False}
    if trigger_refresh and operation.get("status") == "archived":
        refresh = launch_background_task(
            task_name="watchlist_refresh",
            title="自选股名单刷新",
            command=WATCHLIST_REFRESH_COMMAND,
            cwd=str(WORKSPACE_ROOT),
            send_to_feishu=False,
        )

    manager = build_watchlist_manager_api_view()
    message = watchlist_message("archive", str(operation.get("status") or ""), operation.get("stock") or {}, refresh["started"])
    return JSONResponse(
        {
            "ok": True,
            "action": "archive",
            "message": message,
            "operation": operation,
            "refresh": refresh,
            "manager": manager,
        }
    )


@app.post("/api/watchlist/manage/restore")
async def api_watchlist_manage_restore(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    code = str(payload.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="缺少股票代码")

    try:
        operation = restore_watchlist_stock(code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _clear_stock_profile_account_sensitive_cache(code)
    _clear_watchlist_related_api_caches()

    trigger_refresh = parse_bool_value(payload.get("trigger_refresh"), True)
    refresh = {"started": False}
    if trigger_refresh and operation.get("status") == "restored":
        refresh = launch_background_task(
            task_name="watchlist_refresh",
            title="自选股名单刷新",
            command=WATCHLIST_REFRESH_COMMAND,
            cwd=str(WORKSPACE_ROOT),
            send_to_feishu=False,
        )

    manager = build_watchlist_manager_api_view()
    message = watchlist_message("restore", str(operation.get("status") or ""), operation.get("stock") or {}, refresh["started"])
    return JSONResponse(
        {
            "ok": True,
            "action": "restore",
            "message": message,
            "operation": operation,
            "refresh": refresh,
            "manager": manager,
        }
    )


@app.get("/opportunities", include_in_schema=False)
async def opportunities(request: Request) -> RedirectResponse:
    return web_redirect("/discovery", query=request.url.query)


def _opportunities_group_key(group: Any) -> str:
    if not isinstance(group, dict):
        return ""
    return str(group.get("key") or group.get("title") or "").strip()


def _select_opportunities_group_key(payload: dict[str, Any], requested_group: str | None) -> str:
    groups = [group for group in payload.get("groups") or [] if isinstance(group, dict)]
    available = {_opportunities_group_key(group) for group in groups}
    requested = str(requested_group or "").strip()
    if requested and requested in available:
        return requested
    for group in groups:
        if int(group.get("count") or len(group.get("cards") or []) or 0) > 0:
            return _opportunities_group_key(group)
    return _opportunities_group_key(groups[0]) if groups else ""


def _compact_opportunity_sidebar_payload(response: dict[str, Any]) -> None:
    """Trim Discovery sidebar lists to what the page renders above the fold."""

    if isinstance(response.get("learning_memories"), list):
        response["learning_memories"] = response["learning_memories"][:3]
    if isinstance(response.get("theme_cards"), list):
        compact_theme_cards: list[Any] = []
        for card in response["theme_cards"][:5]:
            if isinstance(card, dict):
                compact_card = dict(card)
                if isinstance(compact_card.get("leaders"), list):
                    compact_card["leaders"] = compact_card["leaders"][:6]
                compact_theme_cards.append(compact_card)
            else:
                compact_theme_cards.append(card)
        response["theme_cards"] = compact_theme_cards
    if isinstance(response.get("lifecycle_cards"), list):
        response["lifecycle_cards"] = response["lifecycle_cards"][:3]
    if isinstance(response.get("lifecycle_groups"), list):
        compact_groups: list[Any] = []
        for item in response["lifecycle_groups"][:4]:
            if isinstance(item, dict):
                compact_item = dict(item)
                if isinstance(compact_item.get("cards"), list):
                    compact_item["cards"] = compact_item["cards"][:3]
                compact_groups.append(compact_item)
            else:
                compact_groups.append(item)
        response["lifecycle_groups"] = compact_groups


_OPPORTUNITIES_CONTEXT_KEYS = (
    "source_cards",
    "learning_memories",
    "lifecycle_groups",
    "lifecycle_cards",
    "lifecycle_note",
    "theme_cards",
)
OPPORTUNITIES_DEFAULT_GROUP_CARD_LIMIT = 3


def _opportunities_response_payload(
    payload: dict[str, Any],
    *,
    group: str | None,
) -> dict[str, Any]:
    """Return a Discovery payload shaped for the current interaction.

    The API keeps only one observation stage hydrated and leaves the rest as
    count-only shells so the Discovery page can lazy-load them on demand.
    """

    response = {
        key: value
        for key, value in payload.items()
        if key != "groups" and key not in _OPPORTUNITIES_CONTEXT_KEYS
    }
    groups = [item for item in payload.get("groups") or [] if isinstance(item, dict)]
    selected_key = _select_opportunities_group_key(payload, group)
    preview_selected_group = not str(group or "").strip()
    compact_groups: list[dict[str, Any]] = []
    for item in groups:
        item_key = _opportunities_group_key(item)
        cards = list(item.get("cards") or []) if isinstance(item.get("cards"), list) else []
        count = int(item.get("count") or len(cards) or 0)
        loaded = bool(item_key == selected_key or count == 0)
        compact_item = dict(item)
        if not loaded:
            compact_item["cards"] = []
            compact_item["deferred_cards"] = True
        elif preview_selected_group and item_key == selected_key and len(cards) > OPPORTUNITIES_DEFAULT_GROUP_CARD_LIMIT:
            compact_item["cards"] = cards[:OPPORTUNITIES_DEFAULT_GROUP_CARD_LIMIT]
            compact_item["cards_preview_limit"] = OPPORTUNITIES_DEFAULT_GROUP_CARD_LIMIT
            compact_item["deferred_cards"] = True
            loaded = False
        else:
            compact_item["deferred_cards"] = False
        compact_item["cards_loaded"] = loaded
        compact_groups.append(compact_item)

    response["groups"] = compact_groups
    response.pop("learning_memories", None)
    response.pop("lifecycle_groups", None)
    response.pop("lifecycle_cards", None)
    response.pop("lifecycle_note", None)
    response.pop("theme_cards", None)
    response["context_deferred"] = True
    response["evidence_deferred"] = True
    response["active_group_key"] = selected_key
    response["compact"] = True
    return response


def _opportunities_context_payload(payload: dict[str, Any]) -> dict[str, Any]:
    response = {
        key: payload[key]
        for key in (
            "generated_at",
            "display_date",
            "trade_date",
            "source_cards",
            "learning_memories",
            "lifecycle_groups",
            "lifecycle_cards",
            "lifecycle_note",
            "theme_cards",
        )
        if key in payload
    }
    _compact_opportunity_sidebar_payload(response)
    return response


def _opportunities_source_cards_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: payload[key]
        for key in (
            "generated_at",
            "display_date",
            "trade_date",
            "expected_trade_date",
            "data_trade_date",
            "readiness_mode",
            "source_cards",
        )
        if key in payload
    }


@app.get("/api/opportunities")
def api_opportunities(fresh: bool = False, group: str | None = None) -> JSONResponse:
    cache_key = str(group or "").strip()
    if OPPORTUNITIES_API_CACHE_TTL_SECONDS > 0 and not fresh:
        cached = _OPPORTUNITIES_COMPACT_API_CACHE.get(cache_key)
        if cached:
            cached_at, cached_payload = cached
            if time.monotonic() - cached_at <= OPPORTUNITIES_API_CACHE_TTL_SECONDS:
                return JSONResponse(_opportunities_response_payload(cached_payload, group=group))

    payload = build_opportunities_view(
        hydrate_all_groups=False,
        active_group_key=group,
        include_context=False,
        include_lifecycle=False,
    )
    if OPPORTUNITIES_API_CACHE_TTL_SECONDS > 0:
        _OPPORTUNITIES_COMPACT_API_CACHE[cache_key] = (time.monotonic(), deepcopy(payload))
    return JSONResponse(_opportunities_response_payload(payload, group=group))


@app.get("/api/opportunities/context")
def api_opportunities_context(fresh: bool = False) -> JSONResponse:
    global _OPPORTUNITIES_CONTEXT_API_CACHE

    if OPPORTUNITIES_API_CACHE_TTL_SECONDS > 0 and _OPPORTUNITIES_CONTEXT_API_CACHE and not fresh:
        cached_at, cached_payload = _OPPORTUNITIES_CONTEXT_API_CACHE
        if time.monotonic() - cached_at <= OPPORTUNITIES_API_CACHE_TTL_SECONDS:
            return JSONResponse(_opportunities_context_payload(deepcopy(cached_payload)))

    payload = build_opportunities_context_view()
    if OPPORTUNITIES_API_CACHE_TTL_SECONDS > 0:
        _OPPORTUNITIES_CONTEXT_API_CACHE = (time.monotonic(), deepcopy(payload))
    return JSONResponse(_opportunities_context_payload(payload))


@app.get("/api/opportunities/source-cards")
def api_opportunities_source_cards(fresh: bool = False) -> JSONResponse:
    global _OPPORTUNITIES_SOURCE_CARDS_API_CACHE

    if OPPORTUNITIES_API_CACHE_TTL_SECONDS > 0 and _OPPORTUNITIES_CONTEXT_API_CACHE and not fresh:
        cached_at, cached_payload = _OPPORTUNITIES_CONTEXT_API_CACHE
        if time.monotonic() - cached_at <= OPPORTUNITIES_API_CACHE_TTL_SECONDS:
            return JSONResponse(_opportunities_source_cards_payload(cached_payload))

    if OPPORTUNITIES_API_CACHE_TTL_SECONDS > 0 and _OPPORTUNITIES_SOURCE_CARDS_API_CACHE and not fresh:
        cached_at, cached_payload = _OPPORTUNITIES_SOURCE_CARDS_API_CACHE
        if time.monotonic() - cached_at <= OPPORTUNITIES_API_CACHE_TTL_SECONDS:
            return JSONResponse(_opportunities_source_cards_payload(deepcopy(cached_payload)))

    payload = build_opportunities_source_cards_view()
    if OPPORTUNITIES_API_CACHE_TTL_SECONDS > 0:
        _OPPORTUNITIES_SOURCE_CARDS_API_CACHE = (time.monotonic(), deepcopy(payload))
    return JSONResponse(_opportunities_source_cards_payload(payload))


@app.get("/api/refresh/status")
async def api_refresh_status(page: str, auto: bool = False, compact: bool = False) -> JSONResponse:
    normalized_page = normalize_refresh_page(page)
    return JSONResponse(build_refresh_status_payload(normalized_page, auto=auto, compact=compact))


@app.get("/api/refresh/policy")
async def api_refresh_policy() -> JSONResponse:
    return JSONResponse(build_policy_payload())


@app.get("/api/scheduler/status")
async def api_scheduler_status() -> JSONResponse:
    return JSONResponse(build_scheduler_status_payload())


@app.get("/api/cron/validate")
async def api_cron_validate() -> JSONResponse:
    return JSONResponse(validate_cron_policies())


@app.get("/api/source-budget")
async def api_source_budget() -> JSONResponse:
    """Static business profile registry for all Prism data sources.

    Read-only. Does not trigger any task or fetch. Useful for capability
    diagnostics and future UI panels.
    """
    return JSONResponse(build_source_budget_payload())


@app.get("/api/data-capability-matrix")
async def api_data_capability_matrix() -> JSONResponse:
    """Static data capability matrix derived from prism_data DATASET_REGISTRY.

    Read-only. Reports each dataset's configured source authority semantics
    (primary / fallback / authority / target_authority / audit providers,
    source_lane, decision_scope, required_for_live_small, the static
    source_authority_ready and formal_decision_allowed values reachable
    given the configuration, and risk_flags such as display_only,
    target_authority_not_in_use, fallback_default_not_live, pipeline_dataset).
    Does not perform any fetch or trigger any task.
    """
    return JSONResponse(data_capability_matrix_as_dict())


@app.get("/api/formal-data/status")
def api_formal_data_status(fresh: bool = False, compact: bool = True) -> JSONResponse:
    payload = build_formal_data_status_payload(fresh=fresh)
    return JSONResponse(_compact_formal_data_status_payload(payload) if compact else payload)


@app.get("/api/data-assets/status")
def api_data_assets_status(fresh: bool = False, compact: bool = True) -> JSONResponse:
    return JSONResponse(build_data_assets_status(readiness_expected_trade_date(), fresh=fresh, compact=compact))


@app.get("/api/capabilities")
def api_capabilities() -> JSONResponse:
    """Read-only capability matrix for the current readiness payload.

    Returns 6 investment capabilities (observe/review/approve/trade/notify/
    ledger_capture) translated from the engineering-language readiness into
    operator-facing status, why_not and degraded_path. Strictly read-only.
    """
    readiness_view = build_today_readiness_view()
    readiness = readiness_view.get("readiness") or {}
    return JSONResponse(
        {
            "checked_at": readiness.get("checked_at"),
            "session": readiness.get("session"),
            "readiness_mode": readiness.get("readiness_mode"),
            "trust_level": readiness.get("trust_level"),
            "capabilities": readiness.get("capabilities", {}),
        }
    )


@app.get("/api/readiness/live")
def api_readiness_live() -> JSONResponse:
    """Operator-facing readiness summary.

    Returns the same readiness object used by the Today summary, so the
    operator can hit one endpoint to know whether the system is fresh,
    aligned, and safe to act on.
    """

    readiness_view = build_today_readiness_view()
    readiness = readiness_view.get("readiness") or {}
    matrix_payload = data_capability_matrix_as_dict()
    formal_status = build_formal_data_status_payload()
    return JSONResponse(
        {
            "generated_at": readiness_view.get("generated_at"),
            "expected_trade_date": readiness.get("expected_trade_date"),
            "data_trade_date": readiness.get("data_trade_date"),
            "display_date": readiness_view.get("display_date"),
            "trade_date": readiness_view.get("trade_date"),
            "readiness_mode": readiness.get("readiness_mode"),
            "ready": readiness.get("ready", False),
            "session": readiness.get("session"),
            "stale_count": readiness.get("stale_count", 0),
            "blockers": readiness.get("blockers", []),
            "warnings": readiness.get("warnings", []),
            "formal_ready": readiness.get("formal_ready", False),
            "formal_base_ready": readiness.get("formal_base_ready", False),
            "pipeline_formal_ready": readiness.get("pipeline_formal_ready", False),
            "formal_blockers": readiness.get("formal_blockers", []),
            "formal_base_blockers": readiness.get("formal_base_blockers", []),
            "pipeline_formal_blockers": readiness.get("pipeline_formal_blockers", []),
            "source_freshness": readiness.get("source_freshness", []),
            "quality_freshness": readiness.get("quality_freshness", []),
            "dataset_freshness": readiness.get("dataset_freshness", []),
            "formal_freshness": readiness.get("formal_freshness", []),
            "recommended_tasks": readiness.get("recommended_tasks", []),
            "source_states": readiness.get("source_states", {}),
            "capabilities": readiness.get("capabilities", {}),
            "trust_level": readiness.get("trust_level"),
            "formal_data_status": formal_status,
            "data_capability_summary": {
                **matrix_payload["summary"],
                "registry_issues": matrix_payload["registry_issues"],
            },
        }
    )


@app.post("/api/refresh/trigger")
async def api_refresh_trigger(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    page = normalize_refresh_page(payload.get("page"))
    force = parse_bool_value(payload.get("force"), False)
    requested_reason = str(payload.get("reason") or "").strip()
    status = build_refresh_status_payload(page)
    running = status.get("running") or []
    suggested = str((status.get("recommended_task") or {}).get("task_name") or "").strip()
    task_name = normalize_task_name(str(payload.get("task_name") or suggested).strip())
    if not task_name:
        raise HTTPException(status_code=400, detail="missing task_name")

    allowed_tasks = {normalize_task_name(item) for item in REFRESH_PAGE_CONFIG[page]["allowed_tasks"]}
    if task_name not in allowed_tasks:
        raise HTTPException(status_code=400, detail="当前页面不支持该刷新任务")

    task = resolve_refresh_task(task_name)
    state = load_refresh_state()
    cooldown = page_cooldown_state(page=page, task_name=task_name, state=state)
    remaining = int(cooldown.get("remaining_seconds") or 0)
    if task_conflict_is_running(task_name, running):
        raise HTTPException(status_code=409, detail="同类刷新任务仍在运行，请稍后再试。")
    if remaining > 0 and not force:
        raise HTTPException(status_code=429, detail=f"刷新冷却中，请 {remaining} 秒后再试。")

    policy = task_policy(task_name)
    freshness = _stale_subset(
        list(status.get("freshness") or []),
        list(policy.manifest_dependencies if policy else ()),
    )
    decision = evaluate_auto_refresh(
        page=page,
        recommended_task=task_name,
        freshness=freshness,
        readiness_payload=status.get("readiness") if isinstance(status.get("readiness"), dict) else None,
        running=running,
        cooldown=cooldown,
        force=force,
    )
    reason = requested_reason or ("manual_force" if force else "manual")
    result = trigger_refresh_task(
        page=page,
        task_name=task_name,
        force=force,
        trigger_type="manual",
        reason=reason,
        decision=decision,
        freshness=freshness,
    )
    return JSONResponse(
        {
            "ok": True,
            "page": page,
            "force": force,
            "task": {
                "task_name": task_name,
                "title": task["title"],
            },
            "trigger": result,
            "status": build_refresh_status_payload(page, skip_auto=True, compact=True),
        }
    )


@app.get("/parameters", include_in_schema=False)
async def parameters_page(request: Request) -> RedirectResponse:
    return web_redirect("/settings", query=request.url.query)


@app.get("/review", include_in_schema=False)
async def review(request: Request) -> RedirectResponse:
    return web_redirect("/review", query=request.url.query)


_REVIEW_API_COMPACT_KEYS = (
    "generated_at",
    "freshness_alerts",
    "freshness_summary",
    "comparison_cards",
    "lifecycle_cards",
    "research_panels_deferred",
)


def _compact_review_api_payload(payload: dict[str, Any]) -> dict[str, Any]:
    response = {
        key: deepcopy(payload[key])
        for key in _REVIEW_API_COMPACT_KEYS
        if key in payload
    }
    response["compact"] = True
    return response


def _review_research_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(payload[key])
        for key in (
            "generated_at",
            "active_baseline_id",
            "active_window_id",
            "research_panels",
            "research_panels_deferred",
        )
        if key in payload
    }


def _review_evidence_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(payload[key])
        for key in (
            "generated_at",
            "active_baseline_id",
            "active_window_id",
            "source_cards",
            "artifacts",
        )
        if key in payload
    }


@app.get("/api/review")
def api_review(
    baseline: str | None = None,
    window: str | None = None,
) -> JSONResponse:
    payload = build_review_view(
        baseline_id=baseline,
        window_id=window,
        include_evidence=False,
        include_shadow_replay=False,
    )
    return JSONResponse(_compact_review_api_payload(payload))


@app.get("/api/review/research")
def api_review_research(baseline: str | None = None, window: str | None = None) -> JSONResponse:
    return JSONResponse(
        _review_research_payload(
            build_review_research_view(baseline_id=baseline, window_id=window)
        )
    )


@app.get("/api/review/evidence")
def api_review_evidence(baseline: str | None = None, window: str | None = None) -> JSONResponse:
    return JSONResponse(
        _review_evidence_payload(
            build_review_evidence_view(baseline_id=baseline, window_id=window)
        )
    )


@app.get("/api/review/shadow-replay")
def api_review_shadow_replay() -> JSONResponse:
    return JSONResponse(build_shadow_replay_review_summary())


@app.get("/review/detail", include_in_schema=False)
async def review_detail(
    request: Request,
    section: str,
    label: str,
    baseline: str | None = None,
    window: str | None = None,
) -> RedirectResponse:
    return web_redirect("/review", query=request.url.query)


@app.get("/watchlist/{code}", include_in_schema=False)
async def watchlist_detail(request: Request, code: str) -> RedirectResponse:
    return web_redirect(f"/stock/{code}", query=request.url.query)


@app.get("/today/watchlist/{code}", include_in_schema=False)
async def today_watchlist_detail(request: Request, code: str) -> RedirectResponse:
    return web_redirect(f"/stock/{code}", query=request.url.query)


@app.get("/api/stock/{code}/summary")
def api_stock_profile_summary(code: str, trade_date: str | None = None, fresh: bool = False) -> JSONResponse:
    _clear_stock_profile_cache_when_fresh(code, fresh)
    return JSONResponse(build_stock_profile_summary_view(code, trade_date=trade_date))


@app.get("/api/stock/{code}/detail")
def api_stock_profile_detail(code: str, trade_date: str | None = None, fresh: bool = False) -> JSONResponse:
    _clear_stock_profile_cache_when_fresh(code, fresh)
    return JSONResponse(build_stock_profile_detail_view(code, trade_date=trade_date))


@app.get("/api/stock/{code}/evidence")
def api_stock_profile_evidence(code: str, trade_date: str | None = None, fresh: bool = False) -> JSONResponse:
    _clear_stock_profile_cache_when_fresh(code, fresh)
    return JSONResponse(build_stock_profile_evidence_view(code, trade_date=trade_date))


@app.get("/api/stock/{code}/secondary")
def api_stock_profile_secondary(code: str, trade_date: str | None = None, fresh: bool = False) -> JSONResponse:
    _clear_stock_profile_cache_when_fresh(code, fresh)
    return JSONResponse(build_stock_profile_secondary_view(code, trade_date=trade_date))


@app.get("/api/stock/{code}/formal-data/{section}")
def api_stock_profile_formal_data_section(
    code: str,
    section: str,
    trade_date: str | None = None,
    fresh: bool = False,
) -> JSONResponse:
    _clear_stock_profile_cache_when_fresh(code, fresh)
    try:
        return JSONResponse(build_stock_profile_formal_data_section_view(code, section, trade_date=trade_date))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/stock/{code}/today-action")
def api_stock_profile_today_action(code: str, trade_date: str | None = None, fresh: bool = False) -> JSONResponse:
    _clear_stock_profile_cache_when_fresh(code, fresh)
    return JSONResponse(build_stock_profile_today_action_view(code, trade_date=trade_date))


@app.get("/api/stock/{code}/learning-scorecard")
def api_stock_profile_learning_scorecard(code: str, trade_date: str | None = None, fresh: bool = False) -> JSONResponse:
    _clear_stock_profile_cache_when_fresh(code, fresh)
    return JSONResponse(build_stock_profile_learning_scorecard(code, trade_date=trade_date))


@app.get("/opportunities/batch/{kind}", include_in_schema=False)
async def opportunities_batch_detail(request: Request, kind: str) -> RedirectResponse:
    return web_redirect("/discovery", query=request.url.query)


@app.get("/opportunities/{code}", include_in_schema=False)
async def opportunities_candidate_detail(request: Request, code: str) -> RedirectResponse:
    return web_redirect(f"/stock/{code}", query=request.url.query)


@app.get("/today/candidates/{code}", include_in_schema=False)
async def today_candidate_detail(request: Request, code: str) -> RedirectResponse:
    return web_redirect(f"/stock/{code}", query=request.url.query)


@app.get("/today/batch/{kind}", include_in_schema=False)
async def today_batch_detail(request: Request, kind: str) -> RedirectResponse:
    return web_redirect("/discovery", query=request.url.query)


_RUN_LIST_COMPACT_KEYS = (
    "run_id",
    "task_id",
    "task_name",
    "title",
    "status",
    "started_at",
    "finished_at",
    "checked_started_at",
    "checked_finished_at",
    "batch_label",
    "summary",
    "exit_code",
    "log_path",
    "meta_path",
)


def _compact_run_list_item(run: Any) -> dict[str, Any]:
    if not isinstance(run, dict):
        return {}
    return {
        key: deepcopy(run[key])
        for key in _RUN_LIST_COMPACT_KEYS
        if key in run
    }


@app.get("/api/runs")
async def api_runs(fresh: bool = False) -> JSONResponse:
    runs = list_runs(fresh=fresh)
    runs = [item for item in (_compact_run_list_item(run) for run in runs) if item]
    return JSONResponse({"runs": runs, "compact": True})


@app.get("/api/parameters")
async def api_parameters() -> JSONResponse:
    return JSONResponse(build_parameters_payload(load_parameters_value()))


@app.post("/api/parameters")
async def api_save_parameters(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="request body must be json") from exc

    candidate: Any = body
    if isinstance(body, dict) and isinstance(body.get("raw"), str):
        try:
            candidate = json.loads(str(body["raw"]))
        except json.JSONDecodeError as exc:
            return JSONResponse(
                {
                    "ok": False,
                    "saved": False,
                    "detail": f"JSON 解析失败：{exc}",
                    "validation": {"ok": False, "errors": [str(exc)]},
                },
                status_code=400,
            )
    elif isinstance(body, dict) and isinstance(body.get("value"), dict):
        candidate = body["value"]

    if not isinstance(candidate, dict):
        raise HTTPException(status_code=400, detail="parameters root must be an object")

    errors = parameter_validation_errors(candidate)
    if errors:
        return JSONResponse(
            {
                **build_parameters_payload(candidate),
                "ok": False,
                "saved": False,
                "detail": "参数校验失败",
            },
            status_code=400,
        )

    body_dict = body if isinstance(body, dict) else {}
    raw_unsafe = body_dict.get("unsafe_apply")
    # Only honor an explicit JSON ``true``.  Strings like "false", "0" and
    # "off" must NOT bypass the hard-error gate — see parse_bool_value().
    if isinstance(raw_unsafe, bool):
        unsafe_apply = raw_unsafe
    else:
        unsafe_apply = parse_bool_value(raw_unsafe, default=False)
    current_value = load_parameters_value() if PARAMETERS_PATH.exists() else None
    evaluation = parameter_evaluation(candidate, current=current_value)

    if evaluation["errors"] and not unsafe_apply:
        return JSONResponse(
            {
                **build_parameters_payload(candidate),
                "ok": False,
                "saved": False,
                "detail": "参数评估未通过：" + "；".join(evaluation["errors"]),
                "evaluation": evaluation,
            },
            status_code=400,
        )

    PARAMETERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = PARAMETERS_PATH.with_name(f"{PARAMETERS_PATH.name}.{now_stamp()}.tmp")
    tmp_path.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(PARAMETERS_PATH)
    response_payload = build_parameters_payload(candidate, saved=True)
    response_payload["evaluation"] = evaluation
    return JSONResponse(response_payload)


@app.post("/api/tasks/{task_name}/run")
async def run_task(task_name: str, request: Request) -> JSONResponse:
    normalized_task_name = canonical_task_name(task_name)
    if normalized_task_name == "watchlist_refresh":
        task = {
            "title": "自选股全流程刷新",
            "command": WATCHLIST_REFRESH_COMMAND,
            "cwd": str(WORKSPACE_ROOT),
        }
    else:
        task = TASK_DEFINITIONS.get(normalized_task_name)
    if not task:
        raise HTTPException(status_code=404, detail="unknown task")

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    send_to_feishu = bool(payload.get("send_to_feishu", False))
    feishu_status = feishu_channel_status() if send_to_feishu else None
    feishu_warning = ""
    if send_to_feishu and feishu_status and not feishu_status.get("available"):
        send_to_feishu = False
        feishu_warning = str(feishu_status.get("detail") or "飞书通道当前不可用，本次仅执行任务本体。")

    result = launch_background_task(
        task_name=normalized_task_name,
        title=task["title"],
        command=task["command"],
        cwd=task["cwd"],
        send_to_feishu=send_to_feishu,
    )
    return JSONResponse(
        {
            "ok": True,
            **result,
            "requested_task_name": task_name,
            "canonical_task_name": normalized_task_name,
            "feishu_warning": feishu_warning,
            "feishu_status": feishu_status,
        }
    )


@app.get("/api/runs/{run_id}")
async def api_run_detail(run_id: str) -> JSONResponse:
    payload = TASK_RUN_REPOSITORY.get(run_id, legacy_dirs=CONTROL_PANEL_RUN_DIRS)
    if not payload:
        raise HTTPException(status_code=404, detail="run not found")
    return JSONResponse(payload)


@app.get("/api/preview")
async def api_preview(path: str) -> JSONResponse:
    target = safe_path(path)
    kind = preview_kind(target)
    stat = target.stat()
    payload: dict[str, Any] = {
        "path": str(target),
        "name": target.name,
        "kind": kind,
        "size_bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "truncated": False,
        "text": "",
    }
    if kind == "binary":
        return JSONResponse(payload)

    text, truncated = load_preview_text(target, kind)
    payload["text"] = text
    payload["truncated"] = truncated
    payload["preview_bytes"] = len(text.encode("utf-8"))
    return JSONResponse(payload)


@app.get("/api/runs/{run_id}/log")
async def api_run_log(run_id: str) -> FileResponse:
    log_path = resolve_run_log_path(run_id)
    if not log_path:
        raise HTTPException(status_code=404, detail="log not found")
    return FileResponse(log_path, media_type="text/plain", filename=log_path.name)


@app.get("/artifacts")
async def artifact(path: str) -> FileResponse:
    target = safe_path(path)
    media_type = "text/plain"
    suffix = target.suffix.lower()
    if suffix == ".md":
        media_type = "text/markdown"
    elif suffix == ".json":
        media_type = "application/json"
    elif suffix == ".docx":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(target, media_type=media_type, filename=target.name)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "workspace": str(WORKSPACE_ROOT),
            "channels": {
                "feishu": feishu_channel_status(allow_probe=False),
            },
        }
    )


# ---------------------------------------------------------------------------
# Portfolio account endpoints (small-amount real-money operation)
# ---------------------------------------------------------------------------


@app.get("/portfolio", include_in_schema=False)
async def portfolio_redirect() -> RedirectResponse:
    return web_redirect("/portfolio")


@app.get("/api/portfolio/account")
def api_portfolio_account(request: Request, fresh: bool = False) -> JSONResponse:
    """Canonical account view: mode, cash, positions, fills, readiness."""

    compact = parse_bool_value(request.query_params.get("compact"), True)
    include_holding_reviews = not compact
    include_account_history = (not compact) or parse_bool_value(request.query_params.get("history"), False)
    cache_key = (include_holding_reviews, include_account_history)
    if (
        PORTFOLIO_ACCOUNT_API_CACHE_TTL_SECONDS > 0
        and isinstance(_PORTFOLIO_ACCOUNT_API_CACHE, dict)
        and cache_key in _PORTFOLIO_ACCOUNT_API_CACHE
        and not fresh
    ):
        cached_at, cached_payload = _PORTFOLIO_ACCOUNT_API_CACHE[cache_key]
        if time.monotonic() - cached_at <= PORTFOLIO_ACCOUNT_API_CACHE_TTL_SECONDS:
            return JSONResponse(deepcopy(cached_payload))

    return JSONResponse(
        _build_portfolio_account_api_payload(
            include_holding_reviews=include_holding_reviews,
            include_account_history=include_account_history,
            fresh_formal_status=fresh,
        )
    )


@app.get("/api/portfolio/holding-reviews")
def api_portfolio_holding_reviews(fresh: bool = False) -> JSONResponse:
    """Holding action desk payload, loaded separately from the account shell."""

    cache_key = (True, False)
    if (
        PORTFOLIO_ACCOUNT_API_CACHE_TTL_SECONDS > 0
        and isinstance(_PORTFOLIO_ACCOUNT_API_CACHE, dict)
        and cache_key in _PORTFOLIO_ACCOUNT_API_CACHE
        and not fresh
    ):
        cached_at, cached_payload = _PORTFOLIO_ACCOUNT_API_CACHE[cache_key]
        if time.monotonic() - cached_at <= PORTFOLIO_ACCOUNT_API_CACHE_TTL_SECONDS:
            payload = deepcopy(cached_payload)
        else:
            payload = _build_portfolio_account_api_payload(
                include_holding_reviews=True,
                include_account_history=False,
                fresh_formal_status=fresh,
            )
    else:
        payload = _build_portfolio_account_api_payload(
            include_holding_reviews=True,
            include_account_history=False,
            fresh_formal_status=fresh,
        )

    return JSONResponse(
        {
            "generated_at": payload.get("generated_at"),
            "trade_date": payload.get("trade_date"),
            "expected_trade_date": payload.get("expected_trade_date"),
            "data_trade_date": payload.get("data_trade_date"),
            "readiness_mode": (payload.get("readiness") or {}).get("readiness_mode"),
            "market_quotes": payload.get("market_quotes") or {},
            "holding_reviews": payload.get("holding_reviews") or [],
            "holding_action_summary": payload.get("holding_action_summary") or {},
            "position_count": len(((payload.get("account") or {}).get("open_positions") or [])),
        }
    )


@app.post("/api/portfolio/quotes/refresh")
def api_portfolio_quotes_refresh() -> JSONResponse:
    """Refresh market quotes for current open positions and recompute P/L."""

    _clear_portfolio_account_api_cache()
    return JSONResponse(
        _build_portfolio_account_api_payload(
            refresh_quotes=True,
            include_holding_reviews=True,
            fresh_formal_status=True,
        )
    )


@app.post("/api/portfolio/mode")
async def api_portfolio_mode(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    mode = str(payload.get("mode") or "").strip().lower()
    note = str(payload.get("note") or "").strip()
    starting_cash = payload.get("starting_cash")
    allow_unsafe = parse_bool_value(payload.get("allow_unsafe"), False)
    if allow_unsafe and not note:
        raise HTTPException(status_code=400, detail="allow_unsafe requires note/reason")
    try:
        set_account_mode(
            mode,
            starting_cash=starting_cash if starting_cash not in (None, "") else None,
            note=note,
            allow_unsafe=allow_unsafe,
        )
    except AccountBookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _clear_stock_profile_account_sensitive_cache()
    _clear_portfolio_related_api_caches()

    return JSONResponse(_build_portfolio_account_api_payload())


@app.post("/api/portfolio/cash")
async def api_portfolio_cash(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    delta = payload.get("delta")
    reason = str(payload.get("reason") or "").strip()
    try:
        record_cash_adjustment(delta=delta, reason=reason)
    except AccountBookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _clear_stock_profile_account_sensitive_cache()
    _clear_portfolio_related_api_caches()

    return JSONResponse(_build_portfolio_account_api_payload())


@app.post("/api/portfolio/fills")
async def api_portfolio_fill(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    resolved_name = resolve_stock_display_name(payload.get("code"), payload.get("name"))
    try:
        record_fill(
            trade_date=payload.get("trade_date"),
            code=payload.get("code"),
            side=payload.get("side"),
            qty=payload.get("qty"),
            price=payload.get("price"),
            fees=payload.get("fees"),
            name=resolved_name,
            broker_ref=payload.get("broker_ref"),
            intent_key=payload.get("intent_key"),
            note=payload.get("note"),
        )
    except AccountBookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _clear_stock_profile_account_sensitive_cache()
    _clear_portfolio_related_api_caches()

    qty_val = payload.get("qty")
    price_val = payload.get("price")
    amount_val: float | None = None
    try:
        if qty_val is not None and price_val is not None:
            amount_val = round(float(qty_val) * float(price_val), 2)
    except (TypeError, ValueError):
        amount_val = None

    ledger_result = decision_ledger.append_execution_event_for_writeback(
        trade_date=payload.get("trade_date"),
        code=payload.get("code"),
        status="filled",
        side=str(payload.get("side") or "").lower() or None,
        price=payload.get("price"),
        quantity=payload.get("qty"),
        amount=amount_val,
        note=str(payload.get("note") or ""),
        intent_key=payload.get("intent_key"),
        source="portfolio_writeback",
    )
    view = _build_portfolio_account_api_payload()
    view["ledger"] = ledger_result
    return JSONResponse(view)


@app.post("/api/portfolio/holding/identity")
async def api_portfolio_holding_identity(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    from_code = str(payload.get("from_code") or "").strip()
    to_code = str(payload.get("to_code") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    if not from_code or not to_code:
        raise HTTPException(status_code=400, detail="缺少原代码或新代码")

    resolved_name = resolve_stock_display_name(to_code, payload.get("name"))
    try:
        amend_holding_identity(
            from_code=from_code,
            to_code=to_code,
            name=resolved_name,
            reason=reason,
        )
    except AccountBookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _clear_stock_profile_account_sensitive_cache(from_code)
    _clear_stock_profile_account_sensitive_cache(to_code)
    _clear_portfolio_related_api_caches()

    return JSONResponse(_build_portfolio_account_api_payload())


@app.post("/api/portfolio/intent/no_fill")
async def api_portfolio_intent_no_fill(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    try:
        record_no_fill_intent(
            trade_date=payload.get("trade_date"),
            intent_key=payload.get("intent_key"),
            reason=payload.get("reason"),
        )
    except AccountBookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _clear_stock_profile_account_sensitive_cache()
    _clear_portfolio_related_api_caches()

    # The intent payload does not carry an explicit ``code``; we rely on
    # ``intent_key`` matching the captured decision's ``source.action_key``.
    ledger_result = decision_ledger.append_execution_event_for_writeback(
        trade_date=payload.get("trade_date"),
        code=None,
        status="no_fill",
        note=str(payload.get("reason") or ""),
        intent_key=payload.get("intent_key"),
        source="portfolio_writeback",
    )
    view = _build_portfolio_account_api_payload()
    view["ledger"] = ledger_result
    return JSONResponse(view)


@app.post("/api/portfolio/reconcile")
async def api_portfolio_reconcile(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    try:
        record_reconciliation(
            trade_date=payload.get("trade_date"),
            broker_cash=payload.get("broker_cash"),
            broker_equity=payload.get("broker_equity"),
            note=payload.get("note") or "",
        )
    except AccountBookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _clear_stock_profile_account_sensitive_cache()
    _clear_portfolio_related_api_caches()

    return JSONResponse(_build_portfolio_account_api_payload())


# ---------------------------------------------------------------- decision ledger


@app.post("/api/decision-ledger/capture")
async def api_decision_ledger_capture(request: Request) -> JSONResponse:
    """Capture today's action queue into the ledger.

    Callers may post a ``today_view`` body to capture an exact snapshot
    (used by tests and by tasks that already assembled the view).  When
    the body omits ``today_view``, we rebuild via ``build_today_view``
    so an operator can hit the endpoint directly without coordinating
    with the dashboard route.
    """

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    today_view = payload.get("today_view")
    if today_view is None:
        today_view = build_today_view()

    try:
        summary = decision_ledger.capture_today_action_queue(today_view)
    except decision_ledger.DecisionLedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(summary)


# ----------------------------------------------- decision ledger read-only API
#
# These endpoints are pure queries -- they never mutate the ledger, never
# trigger capture, never hit the network.  Corrupt files surface either
# in an ``errors`` field (for the scan-style endpoints) or as a 5xx
# response (for the targeted detail endpoint) so an operator notices.


import re as _re  # local alias to avoid clashing with anything below

_DECISION_ID_PREFIX_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}:")


def _parse_window_days(value: Any) -> int:
    """Parse ``?window=7d`` / ``?window=7`` / int into a positive int.

    Defaults to 7 on missing / unparseable input rather than raising:
    the API stays usable without forcing the caller to hand-craft the
    parameter.
    """

    if value is None:
        return 7
    text = str(value).strip().lower()
    if text.endswith("d"):
        text = text[:-1]
    try:
        n = int(text)
    except (TypeError, ValueError):
        return 7
    return max(1, n)


def _parse_limit(value: Any, *, default: int = 20) -> int:
    if value is None:
        return default
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(1, n)


_DECISION_LEDGER_CALIBRATION_COMPACT_KEYS = (
    "as_of",
    "window_days",
    "from_date",
    "to_date",
    "overall",
    "review_workbench",
    "review_queue",
    "pending_reviews",
    "needs_review_count",
    "reviewed_case_count",
    "review_case_summary",
    "errors",
)

_DECISION_LEDGER_REVIEW_PATTERN_COMPACT_KEYS = (
    "pattern_id",
    "lane",
    "action",
    "action_label",
    "review_reason_key",
    "review_reason_label",
    "primary_cause",
    "primary_cause_label",
    "sample_count",
    "stock_count",
    "dominant_primary_cause",
    "dominant_primary_cause_label",
    "dominant_secondary_causes",
    "dominant_secondary_cause_labels",
    "evidence_strength",
    "evidence_strength_label",
    "evidence_strength_detail",
    "rule_action_allowed",
    "stock_theme",
    "market_regime",
    "evidence_source",
    "rule_hypothesis",
    "follow_up_status",
    "follow_up_status_label",
    "dominant_conclusion_action",
    "dominant_conclusion_action_label",
    "learning_hint",
    "learning_memory_scope",
    "rule_candidate_allowed",
)

_DECISION_LEDGER_REVIEW_ROW_COMPACT_KEYS = (
    "decision_id",
    "trade_date",
    "code",
    "name",
    "action",
    "action_label",
    "lane",
    "surface",
    "status",
    "main_conclusion",
    "latest_outcome",
    "review_status",
    "review_reason",
    "review_reason_key",
    "maturity_label",
    "is_overdue",
    "next_action_label",
    "next_action_reason",
    "priority_score",
    "priority_label",
    "calibration_action",
    "calibration_action_label",
    "calibration_action_reason",
    "outcome_status",
    "outcome_tone",
    "execution_status",
)

_DECISION_LEDGER_READY_REVIEW_STATUSES = {"ready_review", "blocked_data"}


def _compact_decision_review_row(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    return {
        key: deepcopy(item[key])
        for key in _DECISION_LEDGER_REVIEW_ROW_COMPACT_KEYS
        if key in item
    }


def _compact_review_case_pattern(pattern: Any) -> dict[str, Any]:
    if not isinstance(pattern, dict):
        return {}
    return {
        key: deepcopy(pattern[key])
        for key in _DECISION_LEDGER_REVIEW_PATTERN_COMPACT_KEYS
        if key in pattern
    }


def _compact_decision_ledger_calibration_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the Review page projection without low-frequency learning data."""

    response = {
        key: deepcopy(payload[key])
        for key in _DECISION_LEDGER_CALIBRATION_COMPACT_KEYS
        if key in payload
    }
    review_queue = [
        item for item in (payload.get("review_queue") or [])
        if str((item or {}).get("review_status") or "") in _DECISION_LEDGER_READY_REVIEW_STATUSES
    ]
    response["review_queue"] = [
        item for item in (_compact_decision_review_row(row) for row in review_queue) if item
    ]
    response["pending_reviews"] = [
        item for item in (_compact_decision_review_row(row) for row in (payload.get("pending_reviews") or [])[:5]) if item
    ]
    response["learning_patterns_deferred"] = True
    response["links_lazy"] = {
        "learning_patterns": "/api/decision-ledger/calibration-detail",
    }
    return response


def _compact_decision_ledger_calibration_detail_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return Review learning-pattern data that is only needed after expand."""

    response = {
        key: deepcopy(payload[key])
        for key in (
            "as_of",
            "window_days",
            "from_date",
            "to_date",
            "overall",
            "by_lane",
            "by_action",
            "review_case_summary",
            "suggestion_cards",
            "errors",
        )
        if key in payload
    }
    patterns = [
        _compact_review_case_pattern(item)
        for item in (payload.get("review_case_patterns") or [])[:8]
    ]
    response["review_case_patterns"] = [item for item in patterns if item]
    return response


_FACTOR_LEARNING_WINDOW_KEYS = (
    "sample_count",
    "win_rate",
    "avg_return_pct",
    "avg_excess_return_pct",
    "sample_too_small",
)


def _compact_factor_learning_stats_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    response = {
        key: deepcopy(row[key])
        for key in ("key", "label", "sample_count", "mature_count", "sample_too_small")
        if key in row
    }
    window_stats = row.get("window_stats") or {}
    if isinstance(window_stats, dict):
        compact_windows: dict[str, Any] = {}
        for window, stats in window_stats.items():
            if not isinstance(stats, dict):
                continue
            compact_windows[str(window)] = {
                key: deepcopy(stats[key])
                for key in _FACTOR_LEARNING_WINDOW_KEYS
                if key in stats
            }
        response["window_stats"] = compact_windows
    return response


def _compact_factor_learning_summary(summary: Any) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    response = {
        key: deepcopy(summary[key])
        for key in (
            "version",
            "generated_at",
            "sample_window",
            "sample_count",
            "factor_record_count",
            "min_sample_size",
            "guardrail",
        )
        if key in summary
    }
    for key in ("best_positive_factors", "worst_risk_flags", "noisy_factors"):
        response[key] = deepcopy((summary.get(key) or [])[:3])
    response["score_bucket_performance"] = [
        row
        for row in (_compact_factor_learning_stats_row(item) for item in (summary.get("score_bucket_performance") or [])[:4])
        if row
    ]
    response["recommendations_for_weights"] = deepcopy((summary.get("recommendations_for_weights") or [])[:3])
    return response


def _compact_factor_learning_loop_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    response = {
        key: deepcopy(payload[key])
        for key in ("version", "generated_at", "as_of", "outcome_windows", "samples_total", "dimensions")
        if key in payload
    }
    summary = _compact_factor_learning_summary(payload.get("learning_summary"))
    if summary is not None:
        response["learning_summary"] = summary
    return response


def _compact_decision_ledger_learning_loop_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the learning-loop summary the Review page actually renders."""

    keys = (
        "version",
        "generated_at",
        "as_of",
        "ruleset_versions",
        "samples_total",
        "mature_samples",
        "pending_review_count",
        "suggestions",
        "errors",
    )
    response = {key: deepcopy(payload[key]) for key in keys if key in payload}
    factor_loop = _compact_factor_learning_loop_payload(payload.get("factor_learning_loop"))
    if factor_loop is not None:
        response["factor_learning_loop"] = factor_loop
    return response


@app.get("/api/decision-ledger/summary")
async def api_decision_ledger_summary(request: Request) -> JSONResponse:
    """Aggregate ledger counts over a trailing ``window`` (default 7d).

    Query params:

    * ``window`` -- ``7d`` / ``14d`` / integer days (default ``7``).
    * ``as_of`` -- end date in ``YYYY-MM-DD`` (default today).

    The response shape is stable; an empty ledger yields zeroed
    counters.  Corrupt files surface under ``errors`` so the dashboard
    can show a banner without losing the rest of the data.
    """

    window_days = _parse_window_days(request.query_params.get("window"))
    as_of = request.query_params.get("as_of") or None

    summary = decision_ledger.summarize_window(
        window_days=window_days,
        as_of=as_of,
    )
    return JSONResponse(summary)


@app.get("/api/decision-ledger/recent")
async def api_decision_ledger_recent(request: Request) -> JSONResponse:
    """Most-recent decisions plus their latest execution / outcome events.

    Query params:

    * ``limit`` -- 1..500 (default 20).  Invalid input is clamped, not
      rejected -- a dashboard should not break because a URL got
      hand-edited.
    """

    limit = _parse_limit(request.query_params.get("limit"), default=20)
    codes_param = str(request.query_params.get("codes") or "").strip()
    codes = [
        item.strip()
        for item in re.split(r"[,，\s]+", codes_param)
        if item.strip()
    ]
    latest_per_code = parse_bool_value(
        request.query_params.get("latest_per_code"),
        False,
    )
    payload = decision_ledger.list_recent_decisions(
        limit=limit,
        codes=codes,
        latest_per_code=latest_per_code,
    )
    return JSONResponse(payload)


@app.get("/api/decision-ledger/calibration")
async def api_decision_ledger_calibration(request: Request) -> JSONResponse:
    """Review-oriented ledger projection for calibration work.

    This endpoint does not mutate the ledger.  It groups decisions by
    lane/action, highlights failed or questionable outcomes, and returns
    small suggestion cards so Review can guide the operator toward the
    next useful inspection instead of dumping another raw list.  Low-frequency
    learning and shadow samples are loaded through dedicated detail endpoints.
    """

    window_days = _parse_window_days(request.query_params.get("window") or "20d")
    as_of = request.query_params.get("as_of") or None
    limit = _parse_limit(request.query_params.get("limit"), default=12)
    payload = decision_ledger.build_calibration_review(
        window_days=window_days,
        as_of=as_of,
        limit=limit,
        include_shadow_calibration=False,
        include_review_case_patterns=False,
    )
    return JSONResponse(_compact_decision_ledger_calibration_payload(payload))


@app.get("/api/decision-ledger/calibration-detail")
async def api_decision_ledger_calibration_detail(request: Request) -> JSONResponse:
    """Low-frequency Review learning details, loaded after the fold opens."""

    window_days = _parse_window_days(request.query_params.get("window") or "20d")
    as_of = request.query_params.get("as_of") or None
    limit = _parse_limit(request.query_params.get("limit"), default=12)
    payload = decision_ledger.build_calibration_review(
        window_days=window_days,
        as_of=as_of,
        limit=limit,
        include_shadow_calibration=False,
        include_review_case_patterns=True,
    )
    return JSONResponse(_compact_decision_ledger_calibration_detail_payload(payload))


@app.get("/api/decision-ledger/shadow-calibration")
async def api_decision_ledger_shadow_calibration() -> JSONResponse:
    """Research-only shadow calibration hints, loaded on demand."""

    return JSONResponse(decision_ledger.build_shadow_calibration_summary())


@app.get("/api/decision-ledger/learning-loop")
async def api_decision_ledger_learning_loop(request: Request) -> JSONResponse:
    """Rule-versioned learning loop for Decision Ledger outcomes.

    The default response keeps only summary data needed by the Review page.
    """

    as_of = request.query_params.get("as_of") or None
    records, errors = decision_ledger.scan_all_decisions()
    payload = decision_ledger.build_rule_learning_loop(records, errors=errors, as_of=as_of)
    factor_learning_loop = decision_ledger.build_factor_learning_loop(records, as_of=as_of)
    payload["factor_learning_loop"] = factor_learning_loop
    payload["learning_summary"] = factor_learning_loop.get("learning_summary")
    return JSONResponse(_compact_decision_ledger_learning_loop_payload(payload))


@app.get("/api/decision-ledger/review-cases")
async def api_decision_ledger_review_cases() -> JSONResponse:
    """Saved Review Cases plus same-pattern learning clusters."""

    try:
        payload = decision_ledger.list_review_cases()
    except decision_ledger.DecisionLedgerError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse(payload)


@app.get("/api/decision-ledger/review-case/{decision_id}")
async def api_decision_ledger_review_case(decision_id: str) -> JSONResponse:
    """Single-decision Review Case workbench.

    The payload combines the immutable DecisionRecord, the current
    learning-card projection, any saved Review Case, and same-pattern
    cases so the frontend can render a complete attribution workspace.
    """

    try:
        payload = decision_ledger.build_review_case_workbench(decision_id)
    except decision_ledger.DecisionLedgerError as exc:
        message = str(exc)
        status = 404 if "decision not found" in message else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return JSONResponse(payload)


@app.post("/api/decision-ledger/review-case/{decision_id}/attribution-draft")
async def api_decision_ledger_attribution_draft(decision_id: str) -> JSONResponse:
    """Generate an AI attribution draft without saving final attribution."""

    try:
        draft = decision_ledger.build_attribution_draft(decision_id)
    except decision_ledger.DecisionLedgerError as exc:
        message = str(exc)
        status = 404 if "decision not found" in message else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return JSONResponse({"ok": True, "draft": draft})


@app.post("/api/decision-ledger/review-case/{decision_id}/auto-review")
async def api_decision_ledger_auto_review_case(decision_id: str) -> JSONResponse:
    """Generate an AI attribution draft and save it as a Review Case."""

    try:
        payload = decision_ledger.auto_review_case(decision_id)
    except decision_ledger.DecisionLedgerError as exc:
        message = str(exc)
        status = 404 if "decision not found" in message else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return JSONResponse(payload)


@app.post("/api/decision-ledger/review-case/{decision_id}")
async def api_decision_ledger_save_review_case(decision_id: str, request: Request) -> JSONResponse:
    """Save structured attribution for one Decision Ledger record."""

    payload = await request.json()
    try:
        review_case = decision_ledger.save_review_case(decision_id, payload)
        workbench = decision_ledger.build_review_case_workbench(decision_id)
    except decision_ledger.DecisionLedgerError as exc:
        message = str(exc)
        status = 404 if "decision not found" in message else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return JSONResponse({"ok": True, "review_case": review_case, "workbench": workbench})


@app.get("/api/decision-ledger/stock/{code}")
async def api_decision_ledger_stock(code: str) -> JSONResponse:
    """Decision history for one stock code.

    Accepts ``600690`` / ``sh600690`` / ``sz000001`` forms; returns the
    canonical prefixed form in the response so downstream caches can
    key off it.  Garbage codes get a 400 (not silently empty) so a
    client typo is loud.
    """

    canonical = decision_ledger.normalize_stock_code(code)
    if not canonical:
        raise HTTPException(status_code=400, detail=f"invalid stock code: {code!r}")

    records, errors = decision_ledger.scan_all_decisions()
    matched = [
        r for r in records
        if (r.get("stock") or {}).get("code") == canonical
    ]
    matched.sort(
        key=lambda r: (
            str(r.get("trade_date") or ""),
            str(r.get("decision_id") or ""),
        ),
        reverse=True,
    )
    items = [decision_ledger._decision_summary_card(r) for r in matched]
    return JSONResponse(
        {
            "code": canonical,
            "items": items,
            "count": len(items),
            "errors": errors,
        }
    )


@app.get("/api/decision-ledger/decision/{decision_id}")
async def api_decision_ledger_detail(decision_id: str) -> JSONResponse:
    """Raw DecisionRecord for one decision_id.

    * 400 -- id doesn't start with ``YYYY-MM-DD:`` (malformed).
    * 404 -- id is well-formed but no record matches.
    * 500 -- the file that should host the record is corrupt; the
      detail message points at the ledger error so the operator can
      fix the file.
    """

    if not _DECISION_ID_PREFIX_RE.match(decision_id):
        raise HTTPException(
            status_code=400,
            detail=f"malformed decision_id: {decision_id!r}",
        )

    try:
        record = decision_ledger.load_decision(decision_id)
    except decision_ledger.DecisionLedgerError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"ledger error reading {decision_id!r}: {exc}",
        ) from exc

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"decision not found: {decision_id!r}",
        )

    return JSONResponse(record)


@app.get("/api/decision-ledger/health")
async def api_decision_ledger_health() -> JSONResponse:
    """Surface Decision Ledger capture + evaluation health for Settings.

    Combines the last capture status, the last outcome-evaluation
    status, any corrupt decisions/status files, and a coarse pending
    outcome counter into a single payload.  Always returns 200 -- the
    shape is stable, missing sections degrade to ``null`` so the UI can
    show "never run yet" without distinguishing it from "endpoint
    failed".
    """

    payload = decision_ledger.build_ledger_health()
    if isinstance(payload.get("learning_loop"), dict):
        payload["learning_loop"] = _compact_decision_ledger_learning_loop_payload(payload["learning_loop"])
    return JSONResponse(payload)
