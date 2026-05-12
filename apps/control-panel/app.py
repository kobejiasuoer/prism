from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_ROOT = REPO_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

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
    build_candidate_detail_view,
    build_confirmation_view,
    build_overview,
    build_opportunities_view,
    build_portfolio_account_view,
    build_review_detail_view,
    build_review_view,
    build_screening_batch_view,
    build_stock_profile_view,
    build_today_view,
    build_watchlist_page_view,
    build_watchlist_detail_view,
    ensure_runtime_dirs,
    list_runs,
    parse_timestamp,
    record_cash_adjustment,
    record_fill,
    record_no_fill_intent,
    record_reconciliation,
    set_account_mode,
    TASK_RUN_REPOSITORY,
    update_today_action_decision,
)
from watchlist_registry import archive_watchlist_stock, restore_watchlist_stock, upsert_watchlist_stock
from refresh_policy import (
    PAGE_POLICIES,
    TASK_POLICIES,
    active_auto_windows,
    build_policy_payload,
    current_market_mode,
    eligible_lightweight_task,
    evaluate_auto_refresh,
    normalize_task_name,
    page_cooldown_state,
    page_policy,
    pick_recommended_task as policy_pick_recommended_task,
    task_family,
    task_is_running,
    task_policy,
    validate_cron_policies,
)
from readiness import expected_trade_date as readiness_expected_trade_date
from prism_data.freshness import update_manifest_freshness
from prism_data.repositories import DatasetRepository
from prism_data.utils import default_dataset_repository_root


TASK_RUNNER = INVEST_FLOW_ROOT / "scripts" / "control_panel_task_runner.py"
PREVIEW_MAX_BYTES = 220_000
WATCHLIST_REFRESH_COMMAND = ["bash", "apps/scripts/run_watchlist_refresh.sh"]
LIGHTWEIGHT_REFRESH_COMMAND = [sys.executable, "apps/scripts/refresh_lightweight_data.py"]
PARAMETERS_PATH = STOCK_ANALYZER_ROOT / "config" / "stocks.json"
WEB_ORIGIN = os.environ.get("PRISM_WEB_ORIGIN", "http://127.0.0.1:8000").rstrip("/")
TASK_NAME_ALIASES = {
    "watchlist": "watchlist_refresh",
}

app = FastAPI(title="Prism Control", version="0.1.0")


def allowed_cors_origins() -> list[str]:
    configured = [
        origin.strip().rstrip("/")
        for origin in os.environ.get("PRISM_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    defaults = [
        WEB_ORIGIN,
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


def feishu_channel_status() -> dict[str, Any]:
    openclaw_bin = shutil.which("openclaw")
    if not openclaw_bin:
        return {
            "available": False,
            "installed": False,
            "configured": False,
            "reason": "openclaw_missing",
            "detail": "未安装 openclaw，无法发送飞书。",
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
        return {
            "available": False,
            "installed": True,
            "configured": False,
            "reason": "probe_failed",
            "detail": f"飞书通道探测失败：{exc}",
        }

    output = (proc.stdout or "").strip()
    if proc.returncode != 0 or not output:
        detail = (proc.stderr or proc.stdout or "飞书通道未就绪").strip()
        return {
            "available": False,
            "installed": True,
            "configured": False,
            "reason": "probe_failed",
            "detail": detail,
        }

    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return {
            "available": False,
            "installed": True,
            "configured": False,
            "reason": "probe_invalid_json",
            "detail": output,
        }

    chat = payload.get("chat") if isinstance(payload, dict) else None
    feishu = chat.get("feishu") if isinstance(chat, dict) else None
    accounts = feishu.get("accounts") if isinstance(feishu, dict) else None
    installed = bool(feishu and feishu.get("installed"))
    configured = isinstance(accounts, list) and len(accounts) > 0
    available = installed and configured
    detail = "飞书通道可用。" if available else "飞书插件已安装，但还没有可用账号。"
    return {
        "available": available,
        "installed": installed,
        "configured": configured,
        "accounts": accounts if isinstance(accounts, list) else [],
        "reason": "" if available else "not_configured",
        "detail": detail,
    }


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


REFRESH_STATE_PATH = CONTROL_PANEL_STATE_DIR / "refresh_state.json"
REFRESH_PAGE_CONFIG: dict[str, dict[str, Any]] = {
    page: policy.as_dict() for page, policy in PAGE_POLICIES.items()
}


def normalize_refresh_page(value: Any) -> str:
    page = str(value or "").strip().lower()
    if page_policy(page) is None:
        raise HTTPException(status_code=400, detail="unsupported page")
    return page


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
        return list((build_today_view().get("source_cards") or []))
    if page == "watchlist":
        return list((build_watchlist_page_view().get("source_cards") or []))
    if page == "opportunities":
        return list((build_opportunities_view().get("source_cards") or []))
    if page == "review":
        return list((build_review_view().get("source_cards") or []))
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
    for item in list_runs(limit=80):
        if str(item.get("status") or "") != "running":
            continue
        task_name = normalize_task_name(str(item.get("task_name") or "").strip())
        family = task_family(task_name)
        if task_name not in related and family not in related_families:
            continue
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
    return rows


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
            }
        )
    return rows


def _manifest_dt(value: Any) -> datetime | None:
    return parse_timestamp(str(value or ""))


def _manifest_sort_key(manifest: dict[str, Any]) -> datetime:
    return (
        _manifest_dt(manifest.get("asof"))
        or _manifest_dt(manifest.get("fetched_at"))
        or datetime.min
    )


def _latest_dataset_manifest(
    *,
    repository: DatasetRepository,
    dataset: str,
    expected_date: str,
    now: datetime,
) -> dict[str, Any] | None:
    manifests = repository.list_manifests(dataset, expected_date)
    if not manifests:
        return None
    refreshed = [update_manifest_freshness(dict(item), expected_date, now=now) for item in manifests]
    return max(refreshed, key=_manifest_sort_key)


def _dataset_manifest_freshness_rows(*, expected_date: str, now: datetime) -> list[dict[str, Any]]:
    try:
        repository = DatasetRepository(os.environ.get("PRISM_DATASET_REPOSITORY_ROOT", "").strip() or default_dataset_repository_root())
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    labels = {
        "quotes.snapshot": "轻量行情快照",
        "quotes.batch": "轻量行情批量",
        "capital_flow.daily": "轻量资金流单票",
        "capital_flow.batch": "轻量资金流批量",
    }
    for dataset, label in labels.items():
        manifest = _latest_dataset_manifest(
            repository=repository,
            dataset=dataset,
            expected_date=expected_date,
            now=now,
        )
        reasons: list[str] = []
        if not manifest:
            rows.append(
                {
                    "key": dataset,
                    "label": label,
                    "value": "-",
                    "detail": "dataset_manifest_missing",
                    "available": False,
                    "age_seconds": None,
                    "age_label": "-",
                    "stale": True,
                    "stale_after_seconds": int((task_policy("quotes_light") if dataset.startswith("quotes.") else task_policy("capital_flow_light")).cooldown_seconds),
                    "trade_date": None,
                    "stale_reasons": ["manifest_missing"],
                    "dataset_manifest": True,
                }
            )
            continue

        raw_value = manifest.get("asof") or manifest.get("fetched_at")
        parsed = parse_timestamp(str(raw_value or ""))
        age_seconds = max(int((now - parsed).total_seconds()), 0) if parsed else None
        trade_date = str(manifest.get("trade_date") or "").strip() or None
        freshness_status = str(manifest.get("freshness_status") or "").strip().lower()
        status = str(manifest.get("status") or "").strip().lower()
        if status and status != "ok":
            reasons.append(f"manifest_status_{status}")
        if freshness_status in {"stale", "expired"}:
            reasons.append(f"freshness_{freshness_status}")
        elif not freshness_status:
            reasons.append("freshness_unknown")
        if trade_date != expected_date:
            reasons.append("trade_date_mismatch" if trade_date else "trade_date_unknown")
        if not bool(manifest.get("live_small_allowed")):
            reasons.append("live_small_not_allowed")
        if bool(manifest.get("fallback_used")) and not bool(manifest.get("live_small_allowed")):
            reasons.append("fallback_not_allowed")
        if not parsed:
            reasons.append("missing")
        if manifest.get("error") and status != "ok":
            reasons.append("provider_failure")

        rows.append(
            {
                "key": dataset,
                "label": label,
                "value": str(raw_value or "-"),
                "detail": str(manifest.get("provider") or ""),
                "available": bool(parsed),
                "age_seconds": age_seconds,
                "age_label": age_label(age_seconds),
                "stale": bool(reasons),
                "stale_after_seconds": int(manifest.get("ttl_seconds") or 0),
                "trade_date": trade_date,
                "stale_reasons": reasons,
                "provider": manifest.get("provider"),
                "provider_role": manifest.get("provider_role"),
                "freshness_status": freshness_status,
                "fallback_used": bool(manifest.get("fallback_used")),
                "live_small_allowed": bool(manifest.get("live_small_allowed")),
                "manifest_path": manifest.get("manifest_path"),
                "dataset_manifest": True,
            }
        )
    return rows


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
        if task_is_running(task_name, running):
            status = "running"
        elif cooldown_remaining > 0:
            status = "cooldown"
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
            }
        )
    return steps


def build_refresh_status_payload(
    page: str,
    *,
    auto: bool = False,
    now: datetime | None = None,
    skip_auto: bool = False,
) -> dict[str, Any]:
    current = now or datetime.now()
    market_mode, market_label = current_market_mode(current)
    running = build_running_refresh_tasks(page)
    cfg = page_policy(page)
    state = load_refresh_state()

    # Single source of truth for the today page: readiness drives freshness,
    # stale_count, recommended_task and the readiness_mode signature.  The
    # legacy ``build_page_freshness`` heuristic is bypassed entirely so the
    # refresh widget cannot disagree with /api/today.
    readiness_payload: dict[str, Any] | None = None
    if page == "today":
        try:
            today_view = build_today_view()
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
    if auto and not skip_auto and auto_decision.get("should_trigger"):
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

    suggested_poll_seconds = int(REFRESH_PAGE_CONFIG[page]["poll_seconds"][market_mode])
    if running:
        suggested_poll_seconds = min(suggested_poll_seconds, 25)

    recovery_steps = _build_readiness_recovery_steps(
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
        "recovery_steps": recovery_steps,
        "cooldown": cooldown,
        "auto_refresh": auto_decision,
        "last_auto_refresh": _latest_audit_event(state=state, trigger_type="auto"),
        "last_refresh_event": _latest_audit_event(state=state),
        "policy": {
            "page": cfg.as_dict() if cfg else {},
            "task": policy.as_dict() if policy else {},
        },
        "policy_catalog": build_policy_payload(),
        "active_auto_windows": active_auto_windows(current),
        "snapshot_signature": snapshot_signature,
    }
    if readiness_payload:
        payload["readiness"] = readiness_payload
        payload["readiness_mode"] = readiness_payload.get("readiness_mode")
        payload["recommended_tasks"] = readiness_recommendations
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


@app.get("/", include_in_schema=False)
async def index(request: Request) -> RedirectResponse:
    return web_redirect("/", query=request.url.query)


@app.get("/api/overview")
async def api_overview() -> JSONResponse:
    return JSONResponse(build_overview())


@app.get("/today", include_in_schema=False)
async def today(request: Request) -> RedirectResponse:
    return web_redirect("/", query=request.url.query)


@app.get("/api/today")
async def api_today() -> JSONResponse:
    return JSONResponse(build_today_view())


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
    ask_view = build_ask_page_view()
    items = build_ask_suggestions(q, None, None, None)
    if not str(q or "").strip():
        message = "这里先给最近问过和系统里常见的候选。"
    elif items:
        message = f"找到 {len(items)} 个系统内/历史库/全市场候选。"
    else:
        message = "当前系统、历史库和全市场联想都没匹配，建议直接输入 6 位代码。"
    return JSONResponse(
        {
            "query": str(q or "").strip(),
            "items": items,
            "message": message,
            "recent_queries": ask_view.get("recent_queries") or [],
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

    today_view = build_today_view()
    matched_item = next(
        (
            item
            for item in ((today_view.get("action_queue") or {}).get("items") or [])
            if item.get("key") == key
        ),
        None,
    )
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
            "counts": ((today_view.get("action_queue") or {}).get("counts") or {}),
        }
    )


@app.get("/watchlist", include_in_schema=False)
async def watchlist(request: Request) -> RedirectResponse:
    return web_redirect("/portfolio", query=request.url.query)


@app.get("/api/watchlist")
async def api_watchlist() -> JSONResponse:
    return JSONResponse(build_watchlist_page_view())


@app.get("/api/watchlist/manage")
async def api_watchlist_manage() -> JSONResponse:
    return JSONResponse({"manager": (build_watchlist_page_view().get("manager") or {})})


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

    manager = build_watchlist_page_view().get("manager") or {}
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

    manager = build_watchlist_page_view().get("manager") or {}
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

    manager = build_watchlist_page_view().get("manager") or {}
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


@app.get("/api/opportunities")
async def api_opportunities() -> JSONResponse:
    return JSONResponse(build_opportunities_view())


@app.get("/api/refresh/status")
async def api_refresh_status(page: str, auto: bool = False) -> JSONResponse:
    normalized_page = normalize_refresh_page(page)
    return JSONResponse(build_refresh_status_payload(normalized_page, auto=auto))


@app.get("/api/refresh/policy")
async def api_refresh_policy() -> JSONResponse:
    return JSONResponse(build_policy_payload())


@app.get("/api/cron/validate")
async def api_cron_validate() -> JSONResponse:
    return JSONResponse(validate_cron_policies())


@app.get("/api/readiness/live")
async def api_readiness_live() -> JSONResponse:
    """Operator-facing readiness summary.

    Returns the same readiness object that ``/api/today`` embeds, so the
    operator can hit one endpoint to know whether the system is fresh,
    aligned, and safe to act on.
    """

    today_view = build_today_view()
    readiness = today_view.get("readiness") or {}
    return JSONResponse(
        {
            "generated_at": today_view.get("generated_at"),
            "expected_trade_date": readiness.get("expected_trade_date"),
            "data_trade_date": readiness.get("data_trade_date"),
            "display_date": today_view.get("display_date"),
            "trade_date": today_view.get("trade_date"),
            "readiness_mode": readiness.get("readiness_mode"),
            "ready": readiness.get("ready", False),
            "session": readiness.get("session"),
            "stale_count": readiness.get("stale_count", 0),
            "blockers": readiness.get("blockers", []),
            "warnings": readiness.get("warnings", []),
            "source_freshness": readiness.get("source_freshness", []),
            "quality_freshness": readiness.get("quality_freshness", []),
            "recommended_tasks": readiness.get("recommended_tasks", []),
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
    if task_is_running(task_name, running):
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
            "status": build_refresh_status_payload(page, skip_auto=True),
        }
    )


@app.get("/parameters", include_in_schema=False)
async def parameters_page(request: Request) -> RedirectResponse:
    return web_redirect("/settings", query=request.url.query)


@app.get("/review", include_in_schema=False)
async def review(request: Request) -> RedirectResponse:
    return web_redirect("/review", query=request.url.query)


@app.get("/api/review")
async def api_review(baseline: str | None = None, window: str | None = None) -> JSONResponse:
    return JSONResponse(build_review_view(baseline_id=baseline, window_id=window))


@app.get("/review/detail", include_in_schema=False)
async def review_detail(
    request: Request,
    section: str,
    label: str,
    baseline: str | None = None,
    window: str | None = None,
) -> RedirectResponse:
    return web_redirect("/review", query=request.url.query)


@app.get("/api/review/detail")
async def api_review_detail(
    section: str,
    label: str,
    baseline: str | None = None,
    window: str | None = None,
) -> JSONResponse:
    try:
        return JSONResponse(build_review_detail_view(section, label, baseline_id=baseline, window_id=window))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/watchlist/{code}", include_in_schema=False)
async def watchlist_detail(request: Request, code: str) -> RedirectResponse:
    return web_redirect(f"/stock/{code}", query=request.url.query)


@app.get("/api/watchlist/{code}")
async def api_watchlist_detail(code: str) -> JSONResponse:
    try:
        return JSONResponse(build_watchlist_detail_view(code))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/today/watchlist/{code}", include_in_schema=False)
async def today_watchlist_detail(request: Request, code: str) -> RedirectResponse:
    return web_redirect(f"/stock/{code}", query=request.url.query)


@app.get("/api/today/watchlist/{code}")
async def api_today_watchlist_detail(code: str) -> JSONResponse:
    try:
        return JSONResponse(build_watchlist_detail_view(code))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/stock/{code}")
async def api_stock_profile(code: str) -> JSONResponse:
    return JSONResponse(build_stock_profile_view(code))


@app.get("/opportunities/batch/{kind}", include_in_schema=False)
async def opportunities_batch_detail(request: Request, kind: str) -> RedirectResponse:
    return web_redirect("/discovery", query=request.url.query)


@app.get("/api/opportunities/batch/{kind}")
async def api_opportunities_batch_detail(kind: str) -> JSONResponse:
    if kind == "screener":
        return JSONResponse(build_screening_batch_view())
    if kind == "confirmation":
        return JSONResponse(build_confirmation_view())
    raise HTTPException(status_code=404, detail="unknown batch")


@app.get("/opportunities/{code}", include_in_schema=False)
async def opportunities_candidate_detail(request: Request, code: str) -> RedirectResponse:
    return web_redirect(f"/stock/{code}", query=request.url.query)


@app.get("/api/opportunities/{code}")
async def api_opportunities_candidate_detail(code: str) -> JSONResponse:
    try:
        return JSONResponse(build_candidate_detail_view(code))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/today/candidates/{code}", include_in_schema=False)
async def today_candidate_detail(request: Request, code: str) -> RedirectResponse:
    return web_redirect(f"/stock/{code}", query=request.url.query)


@app.get("/api/today/candidates/{code}")
async def api_today_candidate_detail(code: str) -> JSONResponse:
    try:
        return JSONResponse(build_candidate_detail_view(code))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/today/batch/{kind}", include_in_schema=False)
async def today_batch_detail(request: Request, kind: str) -> RedirectResponse:
    return web_redirect("/discovery", query=request.url.query)


@app.get("/api/today/batch/{kind}")
async def api_today_batch_detail(kind: str) -> JSONResponse:
    if kind == "screener":
        return JSONResponse(build_screening_batch_view())
    if kind == "confirmation":
        return JSONResponse(build_confirmation_view())
    raise HTTPException(status_code=404, detail="unknown batch")


@app.get("/api/runs")
async def api_runs() -> JSONResponse:
    overview = build_overview()
    return JSONResponse({"runs": overview["runs"]})


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
                "feishu": feishu_channel_status(),
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
async def api_portfolio_account() -> JSONResponse:
    """Canonical account view: mode, cash, positions, fills, readiness."""

    return JSONResponse(build_portfolio_account_view())


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

    return JSONResponse(build_portfolio_account_view())


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

    return JSONResponse(build_portfolio_account_view())


@app.post("/api/portfolio/fills")
async def api_portfolio_fill(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    try:
        record_fill(
            trade_date=payload.get("trade_date"),
            code=payload.get("code"),
            side=payload.get("side"),
            qty=payload.get("qty"),
            price=payload.get("price"),
            fees=payload.get("fees"),
            name=payload.get("name"),
            broker_ref=payload.get("broker_ref"),
            intent_key=payload.get("intent_key"),
            note=payload.get("note"),
        )
    except AccountBookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(build_portfolio_account_view())


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

    return JSONResponse(build_portfolio_account_view())


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

    return JSONResponse(build_portfolio_account_view())
