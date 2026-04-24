from __future__ import annotations

import os
import subprocess
import hashlib
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from control_panel.dashboard_data import (
    CONTROL_PANEL_LOGS_DIR,
    CONTROL_PANEL_ROOT,
    CONTROL_PANEL_RUNS_DIR,
    CONTROL_PANEL_STATE_DIR,
    INVEST_FLOW_ROOT,
    TASK_DEFINITIONS,
    WORKSPACE_ROOT,
    build_ask_followup_view,
    build_ask_page_view,
    build_ask_suggestions,
    build_candidate_detail_view,
    build_confirmation_view,
    build_overview,
    build_opportunities_view,
    build_review_detail_view,
    build_review_view,
    build_screening_batch_view,
    build_today_view,
    build_watchlist_page_view,
    build_watchlist_detail_view,
    ensure_runtime_dirs,
    list_runs,
    parse_timestamp,
    update_today_action_decision,
)
from watchlist_registry import archive_watchlist_stock, restore_watchlist_stock, upsert_watchlist_stock


APP_ROOT = CONTROL_PANEL_ROOT
TEMPLATES = Jinja2Templates(directory=str(APP_ROOT / "templates"))
TASK_RUNNER = INVEST_FLOW_ROOT / "scripts" / "control_panel_task_runner.py"
PREVIEW_MAX_BYTES = 220_000
WATCHLIST_REFRESH_COMMAND = ["bash", "skills/invest-flow/scripts/run_watchlist_refresh.sh"]
PREVIEW_THEME_QUERY_KEY = "theme"
PREVIEW_THEME_IBM = "ibm-preview"
PREVIEW_THEME_LABELS = {
    PREVIEW_THEME_IBM: "IBM 预览",
}

app = FastAPI(title="Prism Control", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(APP_ROOT / "static")), name="static")


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def resolve_preview_theme(request: Request) -> str | None:
    value = str(request.query_params.get(PREVIEW_THEME_QUERY_KEY) or "").strip()
    return value if value in PREVIEW_THEME_LABELS else None


def update_relative_url_query(url: str, **updates: str | None) -> str:
    parsed = urlsplit(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in updates.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    query = urlencode(params, doseq=True)
    return urlunsplit(("", "", parsed.path, query, parsed.fragment))


def build_request_relative_url(request: Request, *, preview_theme: str | None) -> str:
    raw_url = urlunsplit(("", "", request.url.path, request.url.query, ""))
    return update_relative_url_query(raw_url, **{PREVIEW_THEME_QUERY_KEY: preview_theme})


def should_apply_preview_theme(url: str) -> bool:
    if not url.startswith("/"):
        return False
    if url.startswith("/Users/") or url.startswith("/static/"):
        return False
    return (
        url == "/"
        or url.startswith("/?")
        or url.startswith("/api/")
        or url.startswith("/today")
        or url.startswith("/ask")
        or url.startswith("/watchlist")
        or url.startswith("/opportunities")
        or url.startswith("/review")
        or url.startswith("/artifacts")
    )


def apply_preview_theme_to_urls(value: Any, preview_theme: str | None) -> Any:
    if not preview_theme:
        return value
    if isinstance(value, dict):
        return {key: apply_preview_theme_to_urls(item, preview_theme) for key, item in value.items()}
    if isinstance(value, list):
        return [apply_preview_theme_to_urls(item, preview_theme) for item in value]
    if isinstance(value, tuple):
        return tuple(apply_preview_theme_to_urls(item, preview_theme) for item in value)
    if isinstance(value, str) and should_apply_preview_theme(value):
        return update_relative_url_query(value, **{PREVIEW_THEME_QUERY_KEY: preview_theme})
    return value


def build_preview_context(request: Request) -> dict[str, str | None]:
    preview_theme = resolve_preview_theme(request)
    return {
        "preview_theme": preview_theme,
        "preview_theme_label": PREVIEW_THEME_LABELS.get(preview_theme),
        "preview_theme_exit_url": build_request_relative_url(request, preview_theme=None),
        "preview_theme_dashboard_url": update_relative_url_query("/", **{PREVIEW_THEME_QUERY_KEY: preview_theme}),
        "preview_theme_ask_url": update_relative_url_query("/ask", **{PREVIEW_THEME_QUERY_KEY: preview_theme}),
    }


def preview_template_response(request: Request, template_name: str, context: dict[str, Any]) -> HTMLResponse:
    preview_context = build_preview_context(request)
    themed_context = {
        key: apply_preview_theme_to_urls(value, preview_context["preview_theme"])
        for key, value in context.items()
    }
    return TEMPLATES.TemplateResponse(
        request,
        template_name,
        {
            **themed_context,
            **preview_context,
        },
    )


def build_run_paths(run_id: str) -> tuple[Path, Path]:
    ensure_runtime_dirs()
    meta_path = CONTROL_PANEL_RUNS_DIR / f"{run_id}.json"
    log_path = CONTROL_PANEL_LOGS_DIR / f"{run_id}.log"
    return meta_path, log_path


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
    "today": {
        "allowed_tasks": {"watchlist_refresh", "command_brief", "midday_refresh", "aggressive"},
        "related_tasks": {
            "watchlist_refresh",
            "watchlist",
            "command_brief",
            "aggressive",
            "midday_refresh",
            "midday_confirmation",
        },
        "poll_seconds": {"trading": 45, "standby": 120, "off": 300},
        "cooldown_seconds": {"trading": 900, "standby": 1200, "off": 1800},
        "stale_after_seconds": {"trading": 2700, "standby": 5400, "off": 14_400},
    },
    "watchlist": {
        "allowed_tasks": {"watchlist_refresh", "watchlist"},
        "related_tasks": {"watchlist_refresh", "watchlist", "command_brief"},
        "poll_seconds": {"trading": 60, "standby": 150, "off": 300},
        "cooldown_seconds": {"trading": 900, "standby": 1200, "off": 1800},
        "stale_after_seconds": {"trading": 3600, "standby": 7200, "off": 14_400},
    },
    "opportunities": {
        "allowed_tasks": {"midday_refresh", "aggressive", "midday_confirmation"},
        "related_tasks": {"aggressive", "midday_refresh", "midday_confirmation"},
        "poll_seconds": {"trading": 40, "standby": 120, "off": 300},
        "cooldown_seconds": {"trading": 600, "standby": 900, "off": 1800},
        "stale_after_seconds": {"trading": 1800, "standby": 3600, "off": 10_800},
    },
}


def normalize_refresh_page(value: Any) -> str:
    page = str(value or "").strip().lower()
    if page not in REFRESH_PAGE_CONFIG:
        raise HTTPException(status_code=400, detail="unsupported page")
    return page


def current_market_mode(now_dt: datetime | None = None) -> tuple[str, str]:
    now = now_dt or datetime.now()
    if now.weekday() >= 5:
        return "off", "周末休市"

    clock = now.hour * 60 + now.minute
    if (570 <= clock < 690) or (780 <= clock < 900):
        return "trading", "交易时段"
    if (540 <= clock < 570) or (690 <= clock < 780) or (900 <= clock < 930):
        return "standby", "盘前/午间/收盘过渡"
    return "off", "非交易时段"


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
    if not REFRESH_STATE_PATH.exists():
        return {"pages": {}}
    try:
        payload = json.loads(REFRESH_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"pages": {}}
    if not isinstance(payload, dict):
        return {"pages": {}}
    pages = payload.get("pages")
    if not isinstance(pages, dict):
        payload["pages"] = {}
    return payload


def save_refresh_state(payload: dict[str, Any]) -> None:
    ensure_runtime_dirs()
    REFRESH_STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_refresh_task(task_name: str) -> dict[str, Any]:
    normalized = str(task_name or "").strip()
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
    related = REFRESH_PAGE_CONFIG[page]["related_tasks"]
    rows: list[dict[str, Any]] = []
    for item in list_runs(limit=80):
        if str(item.get("status") or "") != "running":
            continue
        task_name = str(item.get("task_name") or "").strip()
        if task_name not in related:
            continue
        rows.append(
            {
                "task_name": task_name,
                "title": str(item.get("title") or task_name),
                "status": "running",
                "started_at": str(item.get("started_at") or ""),
                "summary": str(item.get("summary") or "后台执行中"),
            }
        )
    return rows


def build_refresh_cooldown(page: str, market_mode: str) -> dict[str, Any]:
    cooldown_seconds = int(REFRESH_PAGE_CONFIG[page]["cooldown_seconds"][market_mode])
    state = load_refresh_state()
    pages = state.get("pages")
    page_state = pages.get(page) if isinstance(pages, dict) and isinstance(pages.get(page), dict) else {}
    last_trigger_at = str(page_state.get("last_trigger_at") or "").strip()
    last_trigger_dt = parse_timestamp(last_trigger_at)
    if not last_trigger_dt:
        remaining = 0
    else:
        elapsed = max(int((datetime.now() - last_trigger_dt).total_seconds()), 0)
        remaining = max(cooldown_seconds - elapsed, 0)
    return {
        "seconds": cooldown_seconds,
        "remaining_seconds": remaining,
        "ready": remaining == 0,
        "last_trigger_at": last_trigger_at,
        "last_task_name": str(page_state.get("task_name") or ""),
        "last_run_id": str(page_state.get("run_id") or ""),
    }


def pick_recommended_task(page: str, freshness: list[dict[str, Any]], market_mode: str) -> str:
    if page == "watchlist":
        return "watchlist_refresh"
    if page == "opportunities":
        return "midday_refresh" if market_mode != "off" else "aggressive"

    stale_labels = {str(item.get("label") or "") for item in freshness if item.get("stale")}
    if {"自选股", "自选股快照"} & stale_labels:
        return "watchlist_refresh"
    if {"机会扫描", "早盘批次", "午盘确认"} & stale_labels:
        return "midday_refresh" if market_mode != "off" else "aggressive"
    return "command_brief"


def build_refresh_status_payload(page: str) -> dict[str, Any]:
    market_mode, market_label = current_market_mode()
    freshness = build_page_freshness(page, market_mode)
    running = build_running_refresh_tasks(page)
    cooldown = build_refresh_cooldown(page, market_mode)
    recommended_task_name = pick_recommended_task(page, freshness, market_mode)
    recommended_task = resolve_refresh_task(recommended_task_name)
    stale_count = sum(1 for item in freshness if item.get("stale"))

    suggested_poll_seconds = int(REFRESH_PAGE_CONFIG[page]["poll_seconds"][market_mode])
    if running:
        suggested_poll_seconds = min(suggested_poll_seconds, 25)

    signature_payload = {
        "page": page,
        "recommended_task": recommended_task_name,
        "stale_count": stale_count,
        "freshness": [
            (item.get("label"), item.get("value"), bool(item.get("stale")))
            for item in freshness
        ],
        "running": [(item.get("task_name"), item.get("started_at")) for item in running],
        "cooldown_remaining": cooldown.get("remaining_seconds"),
    }
    signature_seed = json.dumps(signature_payload, ensure_ascii=False, sort_keys=True)
    snapshot_signature = hashlib.sha1(signature_seed.encode("utf-8")).hexdigest()[:16]

    return {
        "page": page,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market_mode": market_mode,
        "market_label": market_label,
        "suggested_poll_seconds": suggested_poll_seconds,
        "freshness": freshness,
        "stale_count": stale_count,
        "running": running,
        "recommended_task": {
            "task_name": recommended_task_name,
            "title": recommended_task["title"],
        },
        "cooldown": cooldown,
        "snapshot_signature": snapshot_signature,
    }


def save_refresh_trigger(page: str, task_name: str, run_id: str, force: bool) -> None:
    state = load_refresh_state()
    pages = state.setdefault("pages", {})
    if not isinstance(pages, dict):
        pages = {}
        state["pages"] = pages
    pages[page] = {
        "task_name": task_name,
        "run_id": run_id,
        "forced": bool(force),
        "last_trigger_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_refresh_state(state)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    overview = build_overview()
    has_running = any(item.get("status") == "running" for item in overview["runs"])
    return preview_template_response(
        request,
        "dashboard.html",
        {
            "overview": overview,
            "has_running": has_running,
        },
    )


@app.get("/api/overview")
async def api_overview() -> JSONResponse:
    return JSONResponse(build_overview())


@app.get("/today", response_class=HTMLResponse)
async def today(request: Request) -> HTMLResponse:
    today_view = build_today_view()
    return preview_template_response(request, "today.html", {"today": today_view})


@app.get("/api/today")
async def api_today() -> JSONResponse:
    return JSONResponse(build_today_view())


@app.get("/ask", response_class=HTMLResponse)
async def ask(request: Request, q: str | None = None) -> HTMLResponse:
    error = None
    try:
        ask_view = build_ask_page_view(query=q)
    except ValueError as exc:
        error = str(exc)
        ask_view = build_ask_page_view(query=q, error=error)
    return preview_template_response(request, "ask.html", {"ask": ask_view})


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


@app.get("/watchlist", response_class=HTMLResponse)
async def watchlist(request: Request) -> HTMLResponse:
    return preview_template_response(
        request,
        "watchlist.html",
        {
            "watchlist": build_watchlist_page_view(),
        },
    )


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


@app.get("/opportunities", response_class=HTMLResponse)
async def opportunities(request: Request) -> HTMLResponse:
    return preview_template_response(
        request,
        "opportunities.html",
        {
            "opportunities": build_opportunities_view(),
        },
    )


@app.get("/api/opportunities")
async def api_opportunities() -> JSONResponse:
    return JSONResponse(build_opportunities_view())


@app.get("/api/refresh/status")
async def api_refresh_status(page: str) -> JSONResponse:
    normalized_page = normalize_refresh_page(page)
    return JSONResponse(build_refresh_status_payload(normalized_page))


@app.post("/api/refresh/trigger")
async def api_refresh_trigger(request: Request) -> JSONResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    page = normalize_refresh_page(payload.get("page"))
    force = parse_bool_value(payload.get("force"), False)
    status = build_refresh_status_payload(page)
    running = status.get("running") or []
    cooldown = status.get("cooldown") or {}
    remaining = int(cooldown.get("remaining_seconds") or 0)

    if running and not force:
        raise HTTPException(status_code=409, detail="刷新任务仍在运行，请稍后再试。")
    if remaining > 0 and not force:
        raise HTTPException(status_code=429, detail=f"刷新冷却中，请 {remaining} 秒后再试。")

    suggested = str((status.get("recommended_task") or {}).get("task_name") or "").strip()
    task_name = str(payload.get("task_name") or suggested).strip()
    if not task_name:
        raise HTTPException(status_code=400, detail="missing task_name")

    allowed_tasks = REFRESH_PAGE_CONFIG[page]["allowed_tasks"]
    if task_name not in allowed_tasks:
        raise HTTPException(status_code=400, detail="当前页面不支持该刷新任务")

    task = resolve_refresh_task(task_name)
    result = launch_background_task(
        task_name=task["task_name"],
        title=task["title"],
        command=task["command"],
        cwd=task["cwd"],
        send_to_feishu=bool(task.get("send_to_feishu", False)),
    )
    save_refresh_trigger(page, task_name, str(result.get("run_id") or ""), force)
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
            "status": build_refresh_status_payload(page),
        }
    )


@app.get("/review", response_class=HTMLResponse)
async def review(request: Request, baseline: str | None = None, window: str | None = None) -> HTMLResponse:
    return preview_template_response(
        request,
        "review.html",
        {
            "review": build_review_view(baseline_id=baseline, window_id=window),
        },
    )


@app.get("/api/review")
async def api_review(baseline: str | None = None, window: str | None = None) -> JSONResponse:
    return JSONResponse(build_review_view(baseline_id=baseline, window_id=window))


@app.get("/review/detail", response_class=HTMLResponse)
async def review_detail(
    request: Request,
    section: str,
    label: str,
    baseline: str | None = None,
    window: str | None = None,
) -> HTMLResponse:
    try:
        detail = build_review_detail_view(section, label, baseline_id=baseline, window_id=window)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return preview_template_response(request, "review_detail.html", {"detail": detail})


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


@app.get("/watchlist/{code}", response_class=HTMLResponse)
async def watchlist_detail(request: Request, code: str) -> HTMLResponse:
    try:
        detail = build_watchlist_detail_view(code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return preview_template_response(request, "today_watchlist_detail.html", {"detail": detail})


@app.get("/api/watchlist/{code}")
async def api_watchlist_detail(code: str) -> JSONResponse:
    try:
        return JSONResponse(build_watchlist_detail_view(code))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/today/watchlist/{code}", response_class=HTMLResponse)
async def today_watchlist_detail(request: Request, code: str) -> HTMLResponse:
    try:
        detail = build_watchlist_detail_view(code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return preview_template_response(request, "today_watchlist_detail.html", {"detail": detail})


@app.get("/api/today/watchlist/{code}")
async def api_today_watchlist_detail(code: str) -> JSONResponse:
    try:
        return JSONResponse(build_watchlist_detail_view(code))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/opportunities/batch/{kind}", response_class=HTMLResponse)
async def opportunities_batch_detail(request: Request, kind: str) -> HTMLResponse:
    if kind == "screener":
        detail = build_screening_batch_view()
    elif kind == "confirmation":
        detail = build_confirmation_view()
    else:
        raise HTTPException(status_code=404, detail="unknown batch")

    return preview_template_response(request, "today_batch_detail.html", {"detail": detail})


@app.get("/api/opportunities/batch/{kind}")
async def api_opportunities_batch_detail(kind: str) -> JSONResponse:
    if kind == "screener":
        return JSONResponse(build_screening_batch_view())
    if kind == "confirmation":
        return JSONResponse(build_confirmation_view())
    raise HTTPException(status_code=404, detail="unknown batch")


@app.get("/opportunities/{code}", response_class=HTMLResponse)
async def opportunities_candidate_detail(request: Request, code: str) -> HTMLResponse:
    try:
        detail = build_candidate_detail_view(code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return preview_template_response(request, "today_candidate_detail.html", {"detail": detail})


@app.get("/api/opportunities/{code}")
async def api_opportunities_candidate_detail(code: str) -> JSONResponse:
    try:
        return JSONResponse(build_candidate_detail_view(code))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/today/candidates/{code}", response_class=HTMLResponse)
async def today_candidate_detail(request: Request, code: str) -> HTMLResponse:
    try:
        detail = build_candidate_detail_view(code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return preview_template_response(request, "today_candidate_detail.html", {"detail": detail})


@app.get("/api/today/candidates/{code}")
async def api_today_candidate_detail(code: str) -> JSONResponse:
    try:
        return JSONResponse(build_candidate_detail_view(code))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/today/batch/{kind}", response_class=HTMLResponse)
async def today_batch_detail(request: Request, kind: str) -> HTMLResponse:
    if kind == "screener":
        detail = build_screening_batch_view()
    elif kind == "confirmation":
        detail = build_confirmation_view()
    else:
        raise HTTPException(status_code=404, detail="unknown batch")

    return preview_template_response(request, "today_batch_detail.html", {"detail": detail})


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


@app.post("/api/tasks/{task_name}/run")
async def run_task(task_name: str, request: Request) -> JSONResponse:
    task = TASK_DEFINITIONS.get(task_name)
    if not task:
        raise HTTPException(status_code=404, detail="unknown task")

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    send_to_feishu = bool(payload.get("send_to_feishu", False))
    result = launch_background_task(
        task_name=task_name,
        title=task["title"],
        command=task["command"],
        cwd=task["cwd"],
        send_to_feishu=send_to_feishu,
    )
    return JSONResponse({"ok": True, **result})


@app.get("/api/runs/{run_id}")
async def api_run_detail(run_id: str) -> JSONResponse:
    meta_path = CONTROL_PANEL_RUNS_DIR / f"{run_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="run not found")
    return JSONResponse(json.loads(meta_path.read_text(encoding="utf-8")))


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
    log_path = CONTROL_PANEL_LOGS_DIR / f"{run_id}.log"
    if not log_path.exists():
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
    return JSONResponse({"ok": True, "workspace": str(WORKSPACE_ROOT)})
