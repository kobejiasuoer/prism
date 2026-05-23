from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote


CONTROL_PANEL_ROOT = Path(__file__).resolve().parent
INVEST_FLOW_ROOT = CONTROL_PANEL_ROOT.parent
SKILLS_ROOT = INVEST_FLOW_ROOT.parent
WORKSPACE_ROOT = SKILLS_ROOT
SCRIPTS_ROOT = INVEST_FLOW_ROOT / "scripts"
STOCK_ANALYZER_ROOT = SKILLS_ROOT / "stock-analyzer"
STOCK_SCREENER_ROOT = SKILLS_ROOT / "stock-screener"
PACKAGES_ROOT = SKILLS_ROOT / "packages"
CURRENT_SCREENER_DATA_DIR = PACKAGES_ROOT / "data"
SCREENER_DATA_DIRS = (CURRENT_SCREENER_DATA_DIR, STOCK_SCREENER_ROOT / "data")

if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
if str(STOCK_ANALYZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STOCK_ANALYZER_ROOT))
# Force control-panel ahead of the stock-analyzer copy of ``watchlist_registry``.
# Defense in depth — the legacy duplicate at stock-analyzer/watchlist_registry.py
# is now a thin re-export shim around the canonical control-panel module, but
# pinning control-panel first keeps ``watchlist_registry.__file__`` stable and
# avoids loading two distinct module objects into ``sys.modules``.
_control_panel_root_str = str(CONTROL_PANEL_ROOT)
if _control_panel_root_str in sys.path:
    sys.path.remove(_control_panel_root_str)
sys.path.insert(0, _control_panel_root_str)

from prism_canonical import (  # type: ignore
    diff_watchlist_snapshots,
    find_candidate_detail,
    load_confirmation,
    load_decision_brief,
    load_lifecycle,
    load_quality_status,
    load_research_review,
    load_screening_batch,
    load_watchlist_snapshot,
    resolve_previous_watchlist_snapshot_path,
)
from readiness import (  # type: ignore  # local module under apps/control-panel
    compute_readiness,
    current_session,
    expected_trade_date,
)
from dataset_manifests import build_dataset_freshness_rows  # type: ignore  # local module under apps/control-panel
from account_book import (  # type: ignore  # local module under apps/control-panel
    ACCOUNT_MODES,
    AccountBookError,
    amend_holding_identity,
    compute_account_view,
    load_account_book,
    record_cash_adjustment,
    record_fill,
    record_no_fill_intent,
    record_reconciliation,
    set_account_mode,
)
from watchlist_registry import (
    fetch_stock_name,
    infer_market_from_code,
    infer_sina_code,
    list_active_watchlist_stocks,
    list_archived_watchlist_stocks,
    list_historical_stock_catalog,
    list_watchlist_stocks,
    search_sina_stock_suggestions,
)
from prism_storage import AppStateRepository, ArtifactRepository, TaskRunRepository
from prism_storage.paths import RUNTIME_ROOT, ensure_data_dirs, resolve_workspace_path
from prism_data.providers.common import request_json_http
from prism_data.service import get_data_gateway
from prism_data.utils import normalize_code
from decision_ledger import (  # type: ignore
    AttributionProviderConfig,
    DecisionLedgerError,
    _chat_completions_url,
    _extract_json_object,
    _provider_config,
)
from command_brief import build_today_command_brief  # type: ignore  # local module under apps/control-panel

RESEARCH_REPORTS_DIR = STOCK_SCREENER_ROOT / "data" / "research_backfill" / "reports"
SHADOW_REPLAY_ROOT = WORKSPACE_ROOT / "data" / "quant" / "shadow_replay"
ARTIFACTS_ROOT = SKILLS_ROOT / "data" / "artifacts"

LEGACY_CONTROL_PANEL_RUNS_DIR = INVEST_FLOW_ROOT / "data" / "control_panel_runs"
LEGACY_CONTROL_PANEL_LOGS_DIR = LEGACY_CONTROL_PANEL_RUNS_DIR / "logs"
CONTROL_PANEL_RUNS_DIR = RUNTIME_ROOT / "runs" / "control_panel"
CONTROL_PANEL_LOGS_DIR = CONTROL_PANEL_RUNS_DIR / "logs"
CONTROL_PANEL_RUN_DIRS = (CONTROL_PANEL_RUNS_DIR, LEGACY_CONTROL_PANEL_RUNS_DIR)
CONTROL_PANEL_LOG_DIRS = (CONTROL_PANEL_LOGS_DIR, LEGACY_CONTROL_PANEL_LOGS_DIR)
CONTROL_PANEL_STATE_DIR = INVEST_FLOW_ROOT / "data" / "control_panel_state"
TODAY_ACTION_STATE_PATH = CONTROL_PANEL_STATE_DIR / "today_action_decisions.json"
ASK_RECENT_STATE_PATH = CONTROL_PANEL_STATE_DIR / "ask_recent_queries.json"
QUALITY_DASHBOARD_PATH = RUNTIME_ROOT / "reports" / "command_brief" / "feishu-quality-dashboard.md"
LEGACY_QUALITY_DASHBOARD_PATHS = (
    INVEST_FLOW_ROOT / "reports" / "feishu-quality-dashboard.md",
    WORKSPACE_ROOT / "data" / "history" / "reports" / "command_brief" / "feishu-quality-dashboard.md",
)
WATCHLIST_REFRESH_TASK_NAME = "watchlist_refresh"
TASK_NAME_ALIASES = {
    "watchlist": WATCHLIST_REFRESH_TASK_NAME,
}
APP_STATE_REPOSITORY = AppStateRepository()
ARTIFACT_REPOSITORY = ArtifactRepository()
TASK_RUN_REPOSITORY = TaskRunRepository()

ACTION_DECISION_LABELS = {
    "pending": "待确认",
    "done": "已处理",
    "watch": "继续观察",
    "skip": "今日放弃",
}

ACTION_DECISION_TONES = {
    "pending": "watch",
    "done": "positive",
    "watch": "watch",
    "skip": "risk",
}

ACTION_DISPLAY_LABELS = {
    "pending": "待处理",
    "done": "已完成",
    "watch": "继续观察中",
    "skip": "已放弃",
    "no_fill": "未成交，已记录",
}

ACTION_DISPLAY_TONES = {
    "pending": "watch",
    "done": "positive",
    "watch": "watch",
    "skip": "risk",
    "no_fill": "hold",
}

ACTION_TIER_LABELS = {
    "act_now": "优先处理",
    "wait_trigger": "等触发",
    "observe": "仅观察",
    "avoid": "明确回避",
}

QUALITY_PATTERNS = {
    "watchlist": [STOCK_ANALYZER_ROOT / "data" / "quality_gate_watchlist_*.json"],
    "aggressive": [
        CURRENT_SCREENER_DATA_DIR / "quality_gate_*.json",
        STOCK_SCREENER_ROOT / "data" / "quality_gate_*.json",
    ],
    "midday_confirmation": [
        CURRENT_SCREENER_DATA_DIR / "quality_gate_midday_*.json",
        STOCK_SCREENER_ROOT / "data" / "quality_gate_midday_*.json",
    ],
}

ARTIFACT_GROUPS = {
    "command_brief": {
        "title": "总控简报正文",
        "paths": [ARTIFACTS_ROOT / "command_brief", INVEST_FLOW_ROOT / "reports"],
        "glob": "prism_command_brief_*.txt",
    },
    "command_report": {
        "title": "总控简报报告",
        "paths": [ARTIFACTS_ROOT / "command_brief", INVEST_FLOW_ROOT / "reports"],
        "glob": "prism_command_brief_*.md",
    },
    "watchlist_summary": {
        "title": "自选股摘要",
        "paths": [STOCK_ANALYZER_ROOT / "reports"],
        "glob": "analysis-summary-*.txt",
    },
    "watchlist_report": {
        "title": "自选股完整报告",
        "paths": [STOCK_ANALYZER_ROOT / "reports"],
        "glob": "analysis-report-*.md",
    },
    "aggressive_brief": {
        "title": "进攻型早盘摘要",
        "paths": [STOCK_SCREENER_ROOT / "reports"],
        "glob": "stock_recommendation_*.txt",
        "exclude_contains": ["_midday_"],
    },
    "aggressive_report": {
        "title": "进攻型早盘报告",
        "paths": [STOCK_SCREENER_ROOT / "reports"],
        "glob": "stock_recommendation_*.md",
        "exclude_contains": ["_midday_"],
    },
    "midday_refresh_brief": {
        "title": "午盘刷新摘要",
        "paths": [STOCK_SCREENER_ROOT / "reports"],
        "glob": "stock_recommendation_midday_*.txt",
    },
    "midday_refresh_report": {
        "title": "午盘刷新报告",
        "paths": [STOCK_SCREENER_ROOT / "reports"],
        "glob": "stock_recommendation_midday_*.md",
    },
    "midday_confirmation_brief": {
        "title": "午盘确认摘要",
        "paths": [STOCK_SCREENER_ROOT / "reports"],
        "glob": "stock_midday_confirmation_*.txt",
    },
    "midday_confirmation_report": {
        "title": "午盘确认报告",
        "paths": [STOCK_SCREENER_ROOT / "reports"],
        "glob": "stock_midday_confirmation_*.md",
    },
}

TASK_DEFINITIONS = {
    "command_brief": {
        "title": "投资总控简报",
        "lane": "command_center",
        "command": ["bash", "apps/scripts/run_command_brief.sh"],
        "cwd": str(WORKSPACE_ROOT),
        "description": "汇总自选股、进攻型阀门与午盘状态，生成一份总决策简报。",
    },
    "watchlist": {
        "title": "自选股早盘摘要",
        "lane": "watchlist",
        "command": ["python3", "stock-analyzer/scripts/fetch.py"],
        "cwd": str(WORKSPACE_ROOT),
        "description": "重算自选股摘要与完整报告，默认不发飞书。",
    },
    "aggressive": {
        "title": "进攻型选股",
        "lane": "aggressive",
        "command": [
            "bash",
            "packages/screener/run_full_workflow.sh",
            "--pool",
            "aggressive",
            "--top",
            "10",
            "--handoff-analyzer",
            "--handoff-top",
            "3",
            "--handoff-min-consistency",
            "6",
            "--lifecycle",
        ],
        "cwd": str(WORKSPACE_ROOT),
        "description": "重跑进攻型早盘主流程，默认不发飞书。",
    },
    "midday_refresh": {
        "title": "进攻型午盘刷新",
        "lane": "aggressive",
        "command": [
            "bash",
            "packages/screener/run_midday_refresh.sh",
            "--pool",
            "aggressive",
            "--top",
            "10",
        ],
        "cwd": str(WORKSPACE_ROOT),
        "description": "重跑午盘刷新，不顶替早盘报告。",
    },
    "midday_confirmation": {
        "title": "进攻型午盘确认",
        "lane": "midday_confirmation",
        "command": [
            "bash",
            "packages/screener/run_midday_confirmation.sh",
            "--pool",
            "aggressive",
            "--top",
            "10",
        ],
        "cwd": str(WORKSPACE_ROOT),
        "description": "按晨间基线做午盘承接确认，默认不发飞书。",
    },
    "decision_ledger_outcomes": {
        "title": "Decision Ledger 结果评估",
        "lane": "decision_ledger",
        "command": [sys.executable, "apps/scripts/evaluate_decision_ledger.py"],
        "cwd": str(WORKSPACE_ROOT),
        "description": "补跑已成熟决策样本的 T+1/T+3/T+5 outcome，并把结果写回 Decision Ledger。",
    },
}


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def canonical_task_name(task_name: str | None) -> str:
    normalized = str(task_name or "").strip()
    if not normalized:
        return ""
    return TASK_NAME_ALIASES.get(normalized, normalized)


def fmt_dt(value: str | None) -> str:
    dt = parse_timestamp(value)
    return dt.strftime("%m-%d %H:%M:%S") if dt else (value or "-")


def fmt_mtime(path: Path | None) -> str:
    if not path or not path.exists():
        return "-"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%m-%d %H:%M:%S")


def fmt_mtime_full(path: Path | None) -> str:
    if not path or not path.exists():
        return "-"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_log_tail(path: Path, max_bytes: int = 16_000) -> str:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            return fh.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def ensure_runtime_dirs() -> None:
    ensure_data_dirs()
    CONTROL_PANEL_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    CONTROL_PANEL_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    CONTROL_PANEL_STATE_DIR.mkdir(parents=True, exist_ok=True)


def artifact_from_path(title: str, path_like: str | Path | None, key: str | None = None) -> dict[str, Any] | None:
    if not path_like:
        return None
    path = Path(path_like).expanduser()
    if not path.exists():
        return None
    try:
        path = path.resolve()
    except Exception:
        return None
    workspace_root = Path(WORKSPACE_ROOT).resolve()
    if workspace_root not in path.parents and path != workspace_root:
        return None
    return {
        "key": key or path.stem,
        "title": title,
        "path": str(path),
        "url": f"/artifacts?path={quote(str(path), safe='')}",
        "name": path.name,
        "mtime": fmt_mtime(path),
        "mtime_full": fmt_mtime_full(path),
    }


def workspace_relative(path_like: str | Path | None) -> str | None:
    if not path_like:
        return None
    try:
        path = Path(path_like).expanduser().resolve()
        return str(path.relative_to(Path(WORKSPACE_ROOT).resolve()))
    except Exception:
        return str(path_like)


def _match_quality_files(lane: str) -> list[Path]:
    files: list[Path] = []
    for pattern in QUALITY_PATTERNS[lane]:
        files.extend(pattern.parent.glob(pattern.name))
    if lane == "aggressive":
        files = [path for path in files if "midday_" not in path.name]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def latest_quality_item(lane: str) -> dict[str, Any] | None:
    files = _match_quality_files(lane)
    for path in files:
        data = load_json(path)
        if not data:
            continue
        return {
            "lane": lane,
            "path": str(path),
            "checked_at": data.get("checked_at") or "",
            "expected_timestamp": data.get("expected_timestamp") or "",
            "status": data.get("validation_status") or "unknown",
            "errors": data.get("errors") or [],
            "warnings": data.get("warnings") or [],
            "paths": data.get("paths") or {},
            "stats": data.get("stats") or {},
        }
    return None


def scan_artifact_candidates(group_key: str) -> list[dict[str, Any]]:
    config = ARTIFACT_GROUPS[group_key]
    candidates: list[Path] = []
    for directory in config["paths"]:
        candidates.extend(directory.glob(config["glob"]))
    exclude_contains = config.get("exclude_contains") or []
    filtered = []
    for path in candidates:
        if any(token in path.name for token in exclude_contains):
            continue
        filtered.append(path)
    return [
        {
            "key": group_key,
            "title": config["title"],
            "path": str(path),
            "name": path.name,
            "mtime": fmt_mtime(path),
            "mtime_full": fmt_mtime_full(path),
        }
        for path in sorted(filtered, key=lambda item: item.stat().st_mtime, reverse=True)
    ]


def sync_artifact_group(group_key: str) -> None:
    config = ARTIFACT_GROUPS[group_key]
    for item in scan_artifact_candidates(group_key):
        try:
            ARTIFACT_REPOSITORY.register_file(
                item["path"],
                artifact_type=group_key,
                source="control_panel",
                generated_at=item.get("mtime_full"),
                metadata={
                    "title": config["title"],
                    "group_key": group_key,
                    "name": item["name"],
                },
            )
        except Exception:
            continue


def artifact_item_from_index(group_key: str, item: dict[str, Any]) -> dict[str, Any] | None:
    path_value = item.get("path")
    if not path_value:
        return None
    try:
        path = resolve_workspace_path(path_value)
    except Exception:
        return None
    if not path.exists():
        return None
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    config = ARTIFACT_GROUPS[group_key]
    return {
        "key": group_key,
        "title": metadata.get("title") or config["title"],
        "path": str(path),
        "name": metadata.get("name") or path.name,
        "mtime": fmt_mtime(path),
        "mtime_full": fmt_mtime_full(path),
        "artifact_id": item.get("artifact_id") or "",
    }


def artifact_candidates(group_key: str) -> list[dict[str, Any]]:
    try:
        sync_artifact_group(group_key)
        indexed = [
            candidate
            for item in ARTIFACT_REPOSITORY.list(artifact_type=group_key, limit=80)
            if (candidate := artifact_item_from_index(group_key, item))
        ]
        if indexed:
            return indexed
    except Exception:
        pass
    return scan_artifact_candidates(group_key)


def latest_artifact(group_key: str) -> dict[str, Any] | None:
    items = artifact_candidates(group_key)
    return items[0] if items else None


def pick_artifact_for_reference(
    group_key: str,
    reference_dt: datetime | None,
    max_delta_seconds: int,
) -> dict[str, Any] | None:
    candidates = artifact_candidates(group_key)
    if not candidates:
        return None
    if not reference_dt:
        return candidates[0]

    def sort_key(item: dict[str, Any]) -> tuple[float, float]:
        artifact_dt = parse_timestamp(item.get("mtime_full"))
        if not artifact_dt:
            return (float("inf"), 0.0)
        delta = abs((artifact_dt - reference_dt).total_seconds())
        return (delta, -artifact_dt.timestamp())

    best = min(candidates, key=sort_key)
    best_dt = parse_timestamp(best.get("mtime_full"))
    if not best_dt:
        return candidates[0]

    delta = abs((best_dt - reference_dt).total_seconds())
    if delta <= max_delta_seconds or best_dt.date() == reference_dt.date():
        return best
    return None


def infer_watchlist_report(summary_path: str | Path | None, quality: dict[str, Any] | None) -> dict[str, Any] | None:
    summary = Path(summary_path).expanduser() if summary_path else None
    report_date = None
    if summary and summary.exists():
        match = re.search(r"analysis-summary-(\d{4}-\d{2}-\d{2})\.txt$", summary.name)
        if match:
            report_date = match.group(1)
    if not report_date and quality:
        checked = (quality.get("checked_at") or "").strip()
        if checked:
            report_date = checked.split(" ")[0]
    if not report_date:
        return None
    report_path = STOCK_ANALYZER_ROOT / "reports" / f"analysis-report-{report_date}.md"
    return artifact_from_path("自选股完整报告", report_path, key="watchlist_report")


def quality_report_artifact(quality: dict[str, Any] | None) -> dict[str, Any] | None:
    if not quality:
        return None
    source_value = str(quality.get("path") or "").strip()
    if not source_value:
        return None
    source = Path(source_value)
    if not source.exists():
        return None
    reports_root = STOCK_ANALYZER_ROOT / "reports" if quality.get("lane") == "watchlist" else STOCK_SCREENER_ROOT / "reports"
    report_path = reports_root / f"{source.stem}.md"
    return artifact_from_path("质检报告", report_path, key=f"{quality.get('lane')}_quality_report")


def reference_dt_for_lane(quality: dict[str, Any] | None, task_name: str | None = None) -> datetime | None:
    if quality:
        expected = parse_timestamp(quality.get("expected_timestamp"))
        checked = parse_timestamp(quality.get("checked_at"))
        if expected and checked:
            if abs((checked - expected).total_seconds()) > 1800:
                return checked
            return expected
        if expected:
            return expected
        if checked:
            return checked
    if task_name:
        latest_run = latest_run_for_task(task_name)
        if latest_run:
            return parse_timestamp(latest_run.get("started_at")) or parse_timestamp(latest_run.get("finished_at"))
    return None


def matched_run_for_task(task_name: str, reference_dt: datetime | None, max_delta_seconds: int) -> dict[str, Any] | None:
    expected = canonical_task_name(task_name)
    candidates = [item for item in list_runs(limit=80) if canonical_task_name(item.get("task_name")) == expected]
    if not candidates:
        return None
    if not reference_dt:
        return candidates[0]

    matched: list[tuple[float, dict[str, Any]]] = []
    for item in candidates:
        started = parse_timestamp(item.get("started_at")) or parse_timestamp(item.get("finished_at"))
        if not started:
            continue
        delta = abs((started - reference_dt).total_seconds())
        if delta <= max_delta_seconds:
            matched.append((delta, item))
    if matched:
        matched.sort(key=lambda pair: pair[0])
        return matched[0][1]
    return None


def clean_log_line(line: str) -> str:
    cleaned = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
    cleaned = re.sub(r"^\[[0-9:\- ]+\]\s*", "", cleaned)
    return cleaned.strip()


WATCHLIST_REFRESH_PROGRESS_MAP = {
    "refresh:start": {
        "summary": "已启动自选股全流程，正在准备刷新。",
        "steps": ["current", "pending", "pending"],
    },
    "watchlist:start": {
        "summary": "正在进入自选股链路刷新。",
        "steps": ["current", "pending", "pending"],
    },
    "watchlist:snapshot": {
        "summary": "正在抓取自选股快照。",
        "steps": ["current", "pending", "pending"],
    },
    "watchlist:snapshot_done": {
        "summary": "自选股快照已更新，准备生成报告。",
        "steps": ["completed", "pending", "pending"],
    },
    "watchlist:summary": {
        "summary": "正在生成自选股摘要与完整报告。",
        "steps": ["completed", "current", "pending"],
    },
    "watchlist:summary_done": {
        "summary": "自选股报告已更新，准备刷新总控简报。",
        "steps": ["completed", "completed", "pending"],
    },
    "watchlist:done": {
        "summary": "自选股链路已完成，准备刷新总控简报。",
        "steps": ["completed", "completed", "pending"],
    },
    "command_brief:start": {
        "summary": "正在刷新总控简报。",
        "steps": ["completed", "completed", "current"],
    },
    "command_brief:done": {
        "summary": "总控简报已刷新。",
        "steps": ["completed", "completed", "completed"],
    },
    "refresh:done": {
        "summary": "自选股全流程已完成。",
        "steps": ["completed", "completed", "completed"],
    },
}


def run_log_lines(run: dict[str, Any], max_bytes: int = 16_000) -> list[str]:
    log_path = Path(run.get("log_path") or "")
    if not log_path.exists():
        return []
    text = load_log_tail(log_path, max_bytes=max_bytes)
    if not text:
        return []
    return [clean_log_line(line) for line in text.splitlines() if clean_log_line(line)]


def latest_stage_marker(lines: list[str]) -> str | None:
    for line in reversed(lines):
        if not line.startswith("[stage] "):
            continue
        token = line[len("[stage] ") :].split(" ", 1)[0].strip()
        if token:
            return token
    return None


def watchlist_refresh_progress(run: dict[str, Any] | None) -> dict[str, Any]:
    steps = [
        {"label": "更新快照", "state": "pending", "detail": "抓取最新自选股快照"},
        {"label": "生成报告", "state": "pending", "detail": "生成摘要与完整报告"},
        {"label": "刷新总控", "state": "pending", "detail": "刷新总控简报"},
    ]
    if not run:
        return {
            "summary": "添加、恢复或归档后，会自动重跑自选股全流程和总控简报。",
            "steps": steps,
        }

    status = str(run.get("status") or "").strip()
    if status in {"success", "ok"}:
        for item in steps:
            item["state"] = "completed"
        return {
            "summary": "自选股全流程已完成。",
            "steps": steps,
        }

    lines = run_log_lines(run)
    marker = latest_stage_marker(lines)
    progress = WATCHLIST_REFRESH_PROGRESS_MAP.get(marker or "")
    if progress:
        step_states = progress["steps"]
        for index, item in enumerate(steps):
            item["state"] = step_states[index]
        summary = progress["summary"]
    else:
        summary = run.get("summary") or "后台刷新已触发，请稍后刷新页面查看。"

    if status in {"failed", "unknown"}:
        for item in steps:
            if item["state"] == "current":
                item["state"] = "failed"
                break
        summary = f"{summary.rstrip('。')}，但本次执行未完成。"

    return {
        "summary": summary,
        "steps": steps,
    }


def extract_run_summary(run: dict[str, Any]) -> str:
    status = str(run.get("status") or "").strip()
    if status == "running":
        if str(run.get("task_name") or "").strip() == WATCHLIST_REFRESH_TASK_NAME:
            return watchlist_refresh_progress(run).get("summary") or "后台执行中"
        lines = run_log_lines(run)
        if lines:
            return lines[-1]
        return "后台执行中"

    log_path = Path(run.get("log_path") or "")
    text = load_log_tail(log_path) if log_path.exists() else ""
    if text:
        lines = [clean_log_line(line) for line in text.splitlines()]
        if any("Feishu send failed:" in line and "502" in line for line in lines):
            return "飞书上游接口返回 502，但总控简报已生成"
        if any("tenant_access_token" in line and "undefined" in line for line in lines):
            return "飞书插件已加载，但缺少 tenant_access_token 配置"
        skip_prefixes = (
            "start ",
            "command:",
            "summary ->",
            "quality_json ->",
            "quality_report ->",
            "report ->",
            "Feishu message saved:",
            "Feishu summary saved:",
            "完成：",
            "结果保存:",
            "最新结果:",
            "自动归档:",
        )
        for line in reversed(lines):
            if not line or any(line.startswith(prefix) for prefix in skip_prefixes):
                continue
            if "SEND_TO_FEISHU 已开启，但 FEISHU_TARGET 为空" in line:
                return "允许发飞书，但飞书收件人为空"
            if "tenant_access_token" in line and "undefined" in line:
                return "飞书插件已加载，但缺少 tenant_access_token 配置"
            if line.startswith("ModuleNotFoundError:"):
                missing = re.search(r"No module named '([^']+)'", line)
                if missing:
                    return f"缺少 Python 依赖 {missing.group(1)}"
                return line
            if line.startswith("ImportError:"):
                return line
            if line.startswith("[warn] analyzer handoff 失败"):
                return "Analyzer 接力失败，但主流程已继续"
            if line.startswith("ERROR:"):
                return line
            if "Traceback (most recent call last):" in line:
                return "脚本抛出异常，请打开日志查看堆栈"
            if any(token in line for token in ("未通过", "失败", "超时", "为空", "缺少", "中断", "not found", "Unknown arg")):
                return line
        if status not in {"success", "ok"}:
            for line in reversed(lines):
                if line:
                    return line

    if status in {"success", "ok"}:
        return "最近一次运行成功"
    exit_code = run.get("exit_code")
    return f"退出码 {exit_code if exit_code is not None else '-'}，建议查看日志"


def build_lane_alignment_warning(quality: dict[str, Any] | None, artifacts: list[dict[str, Any]]) -> str | None:
    if not quality or not artifacts:
        return None
    expected_dt = parse_timestamp(quality.get("expected_timestamp"))
    if not expected_dt:
        return None

    deltas: list[float] = []
    for artifact in artifacts:
        artifact_dt = parse_timestamp(artifact.get("mtime_full"))
        if not artifact_dt:
            continue
        deltas.append(abs((artifact_dt - expected_dt).total_seconds()))

    if not deltas:
        return None
    if min(deltas) <= 1800:
        return None
    return "当前最新质检对应的批次时间，与下方展示的最新附件不是同一轮，查看时请优先以时间戳为准。"


def latest_snapshot_info() -> dict[str, Any]:
    snapshot_dir = STOCK_ANALYZER_ROOT / "data" / "daily_snapshots"
    files = sorted(snapshot_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        return {"label": "自选股快照", "value": "-", "detail": "暂无快照"}
    data = load_json(files[0]) or {}
    return {
        "label": "自选股快照",
        "value": data.get("generated_at") or fmt_mtime(files[0]),
        "detail": files[0].name,
    }


def latest_command_brief_info() -> dict[str, Any]:
    item = latest_artifact("command_report")
    if not item:
        return {"label": "总控简报", "value": "-", "detail": "尚未生成"}
    return {
        "label": "总控简报",
        "value": item.get("mtime_full") or "-",
        "detail": item.get("name") or "-",
    }


def latest_ai_history_info() -> dict[str, Any]:
    files: list[Path] = []
    for data_dir in SCREENER_DATA_DIRS:
        files.extend(data_dir.glob("ai_history/ai_screening_*.json"))
    files = sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        return {"label": "最新二筛", "value": "-", "detail": "暂无 ai_history"}
    data = load_json(files[0]) or {}
    return {
        "label": "最新二筛",
        "value": data.get("timestamp") or fmt_mtime(files[0]),
        "detail": files[0].name,
    }


def latest_midday_info() -> dict[str, Any]:
    expected = expected_trade_date()
    path = next(
        (
            candidate
            for data_dir in SCREENER_DATA_DIRS
            if (candidate := data_dir / "midday_verification_result.json").exists()
            and (load_json(candidate) or {}).get("timestamp", "")[:10] == expected
        ),
        None,
    )
    if path is None:
        return {"label": "午盘确认", "value": "-", "detail": "暂无午盘结果"}
    data = load_json(path) or {}
    return {
        "label": "午盘确认",
        "value": data.get("verified_against_scan_timestamp") or data.get("timestamp") or fmt_mtime(path),
        "detail": data.get("validation_status") or "-",
    }


def latest_midday_refresh_info() -> dict[str, Any]:
    expected = expected_trade_date()
    path = next(
        (
            candidate
            for data_dir in SCREENER_DATA_DIRS
            if (candidate := data_dir / "midday_refresh_result.json").exists()
            and (
                (load_json(candidate) or {}).get("scan_timestamp", "")[:10] == expected
                or (load_json(candidate) or {}).get("source_scan_timestamp", "")[:10] == expected
                or (load_json(candidate) or {}).get("timestamp", "")[:10] == expected
            )
        ),
        None,
    )
    if path is None:
        return {"label": "午盘刷新", "value": "-", "detail": "暂无刷新结果"}
    data = load_json(path) or {}
    return {
        "label": "午盘刷新",
        "value": data.get("scan_timestamp") or data.get("source_scan_timestamp") or data.get("timestamp") or fmt_mtime_full(path),
        "detail": data.get("validation_status") or "-",
    }


def latest_dashboard_info() -> dict[str, Any]:
    path = next((candidate for candidate in (QUALITY_DASHBOARD_PATH, *LEGACY_QUALITY_DASHBOARD_PATHS) if candidate.exists()), None)
    if path is None:
        return {"label": "质检总览", "value": "-", "detail": "尚未生成"}
    return {
        "label": "质检总览",
        "value": fmt_mtime_full(path),
        "detail": path.name,
    }


def latest_midday_refresh_status() -> dict[str, Any] | None:
    expected = expected_trade_date()
    path = next(
        (
            candidate
            for data_dir in SCREENER_DATA_DIRS
            if (candidate := data_dir / "midday_refresh_result.json").exists()
            and (
                (load_json(candidate) or {}).get("scan_timestamp", "")[:10] == expected
                or (load_json(candidate) or {}).get("source_scan_timestamp", "")[:10] == expected
                or (load_json(candidate) or {}).get("timestamp", "")[:10] == expected
            )
        ),
        None,
    )
    if path is None:
        return None
    data = load_json(path) or {}
    validation_status = (data.get("validation_status") or "").strip()
    status = {
        "ok": "ok",
        "workflow_failed": "blocked",
        "invalid": "blocked",
        "terminated": "blocked",
        "missing_output": "blocked",
    }.get(validation_status, "unknown")
    return {
        "lane": "midday_refresh",
        "path": str(path),
        "checked_at": data.get("timestamp") or "",
        "expected_timestamp": data.get("scan_timestamp") or data.get("source_scan_timestamp") or data.get("ai_timestamp") or "",
        "status": status,
        "status_label": "就绪" if status == "ok" else ("待查" if status == "unknown" else "拦截"),
        "errors": data.get("validation_errors") or [],
        "warnings": [],
        "paths": {
            "brief": data.get("selected_brief_path") or "",
            "report": data.get("selected_report_path") or "",
            "json": str(path),
        },
        "stats": {
            "scan_timestamp": data.get("scan_timestamp") or "",
            "ai_timestamp": data.get("ai_timestamp") or "",
        },
    }


def is_pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def list_runs(limit: int = 12) -> list[dict[str, Any]]:
    ensure_runtime_dirs()
    items: list[dict[str, Any]] = []
    for data in TASK_RUN_REPOSITORY.list(legacy_dirs=CONTROL_PANEL_RUN_DIRS, limit=limit):
        if data.get("status") == "running" and not is_pid_alive(data.get("pid")):
            data["status"] = "unknown"
        data["checked_started_at"] = fmt_dt(data.get("started_at"))
        data["checked_finished_at"] = fmt_dt(data.get("finished_at"))
        data["batch_label"] = data["checked_started_at"]
        data["summary"] = extract_run_summary(data)
        items.append(data)
    return items[:limit]


def latest_run_for_task(task_name: str) -> dict[str, Any] | None:
    expected = canonical_task_name(task_name)
    for item in list_runs(limit=50):
        if canonical_task_name(item.get("task_name")) == expected:
            return item
    return None


def task_cards() -> list[dict[str, Any]]:
    cards = []
    for task_name, config in TASK_DEFINITIONS.items():
        latest_run = latest_run_for_task(task_name)
        cards.append(
            {
                "task_name": canonical_task_name(task_name),
                "title": config["title"],
                "description": config["description"],
                "lane": config["lane"],
                "last_run": latest_run,
            }
        )
    return cards


def build_lane_batch(
    lane_key: str,
    task_name: str,
    quality: dict[str, Any] | None,
    artifact_group_keys: list[str],
    tolerance_seconds: int,
) -> dict[str, Any]:
    reference_dt = reference_dt_for_lane(quality, task_name)
    reference_label = reference_dt.strftime("%m-%d %H:%M:%S") if reference_dt else "-"
    artifacts: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    def push(item: dict[str, Any] | None) -> None:
        if not item:
            return
        path = item.get("path")
        if not path or path in seen_paths:
            return
        seen_paths.add(path)
        artifacts.append(item)

    if lane_key == "watchlist" and quality:
        summary = pick_artifact_for_reference("watchlist_summary", reference_dt, tolerance_seconds)
        push(summary)
        push(infer_watchlist_report(summary.get("path") if summary else "", quality))
    elif lane_key == "midday_refresh" and quality:
        push(artifact_from_path("午盘刷新摘要", (quality.get("paths") or {}).get("brief"), key="midday_refresh_brief"))
        push(artifact_from_path("午盘刷新报告", (quality.get("paths") or {}).get("report"), key="midday_refresh_report"))
        push(artifact_from_path("刷新结果 JSON", (quality.get("paths") or {}).get("json"), key="midday_refresh_result"))
    else:
        for group_key in artifact_group_keys:
            push(pick_artifact_for_reference(group_key, reference_dt, tolerance_seconds))

    push(quality_report_artifact(quality))

    matched_run = matched_run_for_task(task_name, reference_dt, tolerance_seconds)
    push(artifact_from_path("关联日志", matched_run.get("log_path") if matched_run else "", key=f"{lane_key}_run_log"))

    detail_parts = []
    if quality and quality.get("expected_timestamp"):
        detail_parts.append(f"锚点 {quality['expected_timestamp']}")
    elif reference_dt:
        detail_parts.append(f"锚点 {reference_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    if matched_run:
        detail_parts.append(f"手动运行 {matched_run.get('checked_started_at') or '-'}")

    return {
        "label": reference_label,
        "detail": " | ".join(detail_parts) if detail_parts else "按当前最新产物自动归组",
        "artifacts": artifacts,
        "matched_run": matched_run,
    }


def build_lane_detail_cards(batch: dict[str, Any] | None) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    if not batch:
        return cards

    cards.append(
        {
            "kind": "batch",
            "title": "当前批次",
            "label": batch.get("label") or "-",
            "detail": batch.get("detail") or "按当前最新产物自动归组",
        }
    )

    matched_run = batch.get("matched_run")
    if matched_run:
        status = str(matched_run.get("status") or "unknown")
        cards.append(
            {
                "kind": "run_note",
                "title": "关联手动运行",
                "label": f"{matched_run.get('checked_started_at') or '-'} | {status}",
                "detail": matched_run.get("summary") or "暂无运行摘要",
                "status": status,
            }
        )

    for artifact in batch.get("artifacts") or []:
        cards.append(
            {
                "kind": "artifact",
                "title": artifact.get("title") or "产物",
                "label": artifact.get("name") or "-",
                "detail": artifact.get("mtime") or "-",
                "path": artifact.get("path") or "",
            }
        )

    if len(cards) == 1:
        cards.append(
            {
                "kind": "empty",
                "detail": "当前批次还没有可直接预览的摘要、报告或日志。",
            }
        )
    return cards


def lane_cards() -> list[dict[str, Any]]:
    mappings = [
        {
            "key": "command_center",
            "task_name": "command_brief",
            "title": "投资总控",
            "subtitle": "把自选股与进攻池收束成一份日决策",
            "quality": None,
            "artifact_groups": ["command_brief", "command_report"],
            "tolerance_seconds": 86_400,
        },
        {
            "key": "watchlist",
            "task_name": WATCHLIST_REFRESH_TASK_NAME,
            "title": "自选股",
            "subtitle": "日常持仓/观察池摘要",
            "quality": latest_quality_item("watchlist"),
            "artifact_groups": ["watchlist_summary", "watchlist_report"],
            "tolerance_seconds": 86_400,
        },
        {
            "key": "aggressive",
            "task_name": "aggressive",
            "title": "进攻型早盘",
            "subtitle": "早盘主流程与 Analyzer 接力",
            "quality": latest_quality_item("aggressive"),
            "artifact_groups": ["aggressive_brief", "aggressive_report"],
            "tolerance_seconds": 14_400,
        },
        {
            "key": "midday_refresh",
            "task_name": "midday_refresh",
            "title": "午盘刷新",
            "subtitle": "午盘重扫，不替代晨间基线",
            "quality": latest_midday_refresh_status(),
            "artifact_groups": ["midday_refresh_brief", "midday_refresh_report"],
            "tolerance_seconds": 14_400,
        },
        {
            "key": "midday_confirmation",
            "task_name": "midday_confirmation",
            "title": "午盘确认",
            "subtitle": "晨间基线后的承接验证",
            "quality": latest_quality_item("midday_confirmation"),
            "artifact_groups": ["midday_confirmation_brief", "midday_confirmation_report"],
            "tolerance_seconds": 14_400,
        },
    ]

    for item in mappings:
        item["batch"] = build_lane_batch(
            lane_key=item["key"],
            task_name=item["task_name"],
            quality=item.get("quality"),
            artifact_group_keys=item["artifact_groups"],
            tolerance_seconds=item["tolerance_seconds"],
        )
        item["artifacts"] = item["batch"]["artifacts"]
        item["detail_cards"] = build_lane_detail_cards(item["batch"])
        item["alignment_warning"] = build_lane_alignment_warning(item.get("quality"), item["artifacts"])
    return mappings


def kpi_cards() -> list[dict[str, str]]:
    qualities = [
        latest_quality_item("watchlist"),
        latest_quality_item("aggressive"),
        latest_midday_refresh_status(),
        latest_quality_item("midday_confirmation"),
    ]
    blocked = sum(1 for item in qualities if item and item.get("status") == "blocked")
    ok_count = sum(1 for item in qualities if item and item.get("status") == "ok")
    running = sum(1 for item in list_runs(limit=20) if item.get("status") == "running")

    freshness = [
        latest_command_brief_info(),
        latest_snapshot_info(),
        latest_ai_history_info(),
        latest_midday_refresh_info(),
        latest_midday_info(),
        latest_dashboard_info(),
    ]
    newest = max((parse_timestamp(item["value"]) for item in freshness if parse_timestamp(item["value"])), default=None)

    return [
        {"label": "链路正常", "value": str(ok_count), "detail": "最近四条主链路"},
        {"label": "质检拦截", "value": str(blocked), "detail": "需要人工复核"},
        {"label": "运行中任务", "value": str(running), "detail": "后台异步任务"},
        {"label": "最近刷新", "value": newest.strftime("%m-%d %H:%M") if newest else "-", "detail": "来自状态/质检产物"},
    ]


def latest_quality_reports() -> list[dict[str, Any]]:
    reports = []
    for lane in ("watchlist", "aggressive", "midday_confirmation"):
        item = latest_quality_item(lane)
        if not item:
            continue
        path = Path(item["path"])
        reports.append(
            {
                "title": lane,
                "name": path.name.replace(".json", ".md"),
                "json_path": item["path"],
                "md_path": str(path.with_suffix(".md").resolve().parent / path.with_suffix(".md").name),
            }
        )
    return reports


def build_overview() -> dict[str, Any]:
    ensure_runtime_dirs()
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "workspace_root": str(WORKSPACE_ROOT),
        "quality_dashboard_path": str(QUALITY_DASHBOARD_PATH),
        "kpis": kpi_cards(),
        "lanes": lane_cards(),
        "tasks": task_cards(),
        "runs": list_runs(),
        "freshness": [
            latest_command_brief_info(),
            latest_snapshot_info(),
            latest_ai_history_info(),
            latest_midday_refresh_info(),
            latest_midday_info(),
            latest_dashboard_info(),
        ],
    }


def safe_canonical_load(loader, **kwargs) -> dict[str, Any] | None:
    try:
        return loader(**kwargs)
    except (FileNotFoundError, KeyError):
        return None
    except Exception:
        return None


_HOLDING_AI_REVIEW_KEY = "portfolio_holding_ai_reviews"
_HOLDING_AI_REVIEW_VERSION = "v3"


def _holding_ai_review_store() -> dict[str, Any]:
    raw = APP_STATE_REPOSITORY.get(_HOLDING_AI_REVIEW_KEY, default={}) or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _holding_ai_review_save(store: dict[str, Any]) -> None:
    APP_STATE_REPOSITORY.set(_HOLDING_AI_REVIEW_KEY, store)


def artifact_url(path: str | None) -> str | None:
    if not path:
        return None
    return f"/artifacts?path={quote(path, safe='')}"


def watchlist_page_url() -> str:
    return "/portfolio"


def ask_page_url(query: str | None = None) -> str:
    if not query:
        return "/"
    value = str(query).strip()
    if len(value) == 6 and value.isdigit():
        return f"/stock/{quote(value, safe='')}"
    return "/"


def opportunities_page_url() -> str:
    return "/discovery"


def review_page_url() -> str:
    return "/review"


def api_watchlist_page_url() -> str:
    return "/api/watchlist"


def api_ask_page_url(query: str | None = None) -> str:
    base = "/api/ask"
    if not query:
        return base
    return f"{base}?q={quote(str(query), safe='')}"


def api_ask_suggest_url(query: str | None = None) -> str:
    base = "/api/ask/suggest"
    if not query:
        return base
    return f"{base}?q={quote(str(query), safe='')}"


def api_ask_followup_url() -> str:
    return "/api/ask/followup"


def api_opportunities_page_url() -> str:
    return "/api/opportunities"


def api_review_page_url() -> str:
    return "/api/review"


def review_page_with_params(baseline_id: str | None = None, window_id: str | None = None, *, api: bool = False) -> str:
    base = api_review_page_url() if api else review_page_url()
    params: list[str] = []
    if baseline_id:
        params.append(f"baseline={quote(str(baseline_id), safe='')}")
    if window_id:
        params.append(f"window={quote(str(window_id), safe='')}")
    return f"{base}?{'&'.join(params)}" if params else base


def watchlist_detail_url(code: str | None) -> str | None:
    if not code:
        return None
    return f"/stock/{quote(str(code), safe='')}"


def candidate_detail_url(code: str | None) -> str | None:
    if not code:
        return None
    return f"/stock/{quote(str(code), safe='')}"


def batch_detail_url(kind: str) -> str:
    return "/discovery"


def api_watchlist_detail_url(code: str | None) -> str | None:
    if not code:
        return None
    return f"/api/watchlist/{quote(str(code), safe='')}"


def api_candidate_detail_url(code: str | None) -> str | None:
    if not code:
        return None
    return f"/api/opportunities/{quote(str(code), safe='')}"


def api_batch_detail_url(kind: str) -> str:
    return f"/api/opportunities/batch/{quote(kind, safe='')}"


def today_watchlist_detail_url(code: str | None) -> str | None:
    return watchlist_detail_url(code)


def today_candidate_detail_url(code: str | None) -> str | None:
    return candidate_detail_url(code)


def today_batch_detail_url(kind: str) -> str:
    return batch_detail_url(kind)


def api_today_watchlist_detail_url(code: str | None) -> str | None:
    return api_watchlist_detail_url(code)


def api_today_candidate_detail_url(code: str | None) -> str | None:
    return api_candidate_detail_url(code)


def api_today_batch_detail_url(kind: str) -> str:
    return api_batch_detail_url(kind)


def today_nav_links() -> dict[str, str]:
    return {
        "parameters": "/settings",
        "today": "/",
        "ask": ask_page_url(),
        "watchlist": watchlist_page_url(),
        "opportunities": opportunities_page_url(),
        "review": review_page_url(),
        "api_today": "/api/today",
        "api_ask": api_ask_page_url(),
        "api_watchlist": api_watchlist_page_url(),
        "api_opportunities": api_opportunities_page_url(),
        "api_review": api_review_page_url(),
        "api_parameters": "/api/parameters",
        "screener_batch": today_batch_detail_url("screener"),
        "confirmation_batch": today_batch_detail_url("confirmation"),
        "api_screener_batch": api_today_batch_detail_url("screener"),
        "api_confirmation_batch": api_today_batch_detail_url("confirmation"),
    }


def action_tone(action: str | None) -> str:
    text = action or ""
    if any(keyword in text for keyword in ("回避", "清仓", "逢高减仓", "减仓")):
        return "risk"
    if any(keyword in text for keyword in ("轻仓跟踪", "买入", "偏多")):
        return "positive"
    return "watch"


def candidate_status_label(status: str | None) -> str:
    mapping = {
        "approved": "进入候选",
        "caution": "继续观察",
        "excluded": "排除",
        "confirmed": "仍可跟踪",
        "downgraded": "降级",
        "fresh_candidate": "新增观察",
        "unknown": "待查",
    }
    return mapping.get(str(status or "").strip(), str(status or "待查"))


def candidate_tone(item: dict[str, Any]) -> str:
    quality_score = safe_float((item.get("execution_quality") or {}).get("score"), default=0)
    status = item.get("screening_status") or item.get("status")
    if status == "approved" and quality_score >= 6:
        return "positive"
    if status in {"confirmed", "fresh_candidate"}:
        return "positive"
    if status in {"downgraded", "excluded"}:
        return "risk"
    if quality_score <= 0:
        return "risk"
    return "watch"


def action_tier_label(value: str | None) -> str:
    return ACTION_TIER_LABELS.get(str(value or "").strip(), ACTION_TIER_LABELS["observe"])


def build_action_tier_legend() -> list[dict[str, str]]:
    return [
        {
            "key": "act_now",
            "label": ACTION_TIER_LABELS["act_now"],
            "detail": "已经具备明确处理条件，今天先做，不继续拖。",
        },
        {
            "key": "wait_trigger",
            "label": ACTION_TIER_LABELS["wait_trigger"],
            "detail": "方向成立，但必须等价格、量能或承接条件确认。",
        },
        {
            "key": "observe",
            "label": ACTION_TIER_LABELS["observe"],
            "detail": "暂不动作，只跟踪变化，避免被噪音带着走。",
        },
        {
            "key": "avoid",
            "label": ACTION_TIER_LABELS["avoid"],
            "detail": "今天明确不做，先避开高风险或低把握动作。",
        },
    ]


def infer_action_tier(*, action: Any = None, tone: Any = None, status: Any = None, title: Any = None) -> str:
    combined = " ".join(
        str(part or "").strip()
        for part in (action, status, title)
        if str(part or "").strip()
    )
    normalized_tone = str(tone or "").strip().lower()

    if any(token in combined for token in ("回避", "别做", "不做", "清仓", "减仓")):
        return "avoid"
    if any(token in combined for token in ("买入", "开仓", "试错", "介入")):
        return "wait_trigger"
    if any(token in combined for token in ("立即", "处理", "保留")):
        return "act_now"
    if any(token in combined for token in ("触发", "等待", "确认", "评估")):
        return "wait_trigger"
    if any(token in combined for token in ("观察", "观望", "谨慎", "先看")):
        return "observe"

    if normalized_tone in {"risk"}:
        return "avoid"
    if normalized_tone in {"positive", "good"}:
        return "act_now"
    if normalized_tone in {"watch", "warn"}:
        return "observe"
    return "observe"


def pick_watchlist_cards(watchlist: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not watchlist:
        return []
    stocks = watchlist.get("stocks") or []
    priority_codes = set(watchlist.get("priority_codes") or [])
    selected = [item for item in stocks if item.get("code") in priority_codes]
    if not selected:
        selected = stocks[:4]
    else:
        selected = selected[:4]

    cards: list[dict[str, Any]] = []
    for item in selected:
        trade_levels = item.get("trade_levels") or {}
        reason = (
            (item.get("hard_flags") or [None])[0]
            or (item.get("watch_points") or [None])[0]
            or (item.get("positives") or [None])[0]
            or (item.get("rule_snapshot") or {}).get("signal")
            or "等待更多确认"
        )
        cards.append(
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "action": item.get("action"),
                "position": item.get("position"),
                "tone": action_tone(item.get("action")),
                "reason": reason,
                "support": trade_levels.get("support"),
                "resistance": trade_levels.get("resistance"),
                "stop_loss": trade_levels.get("stop_loss"),
                "signal": (item.get("rule_snapshot") or {}).get("signal"),
                "detail_url": today_watchlist_detail_url(item.get("code")),
            }
        )
    return cards


def pick_opportunity_cards(screening_batch: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not screening_batch:
        return []
    candidates = screening_batch.get("candidates") or []
    approved = [item for item in candidates if item.get("screening_status") == "approved"]
    selected = approved[:4] if approved else candidates[:4]
    cards: list[dict[str, Any]] = []
    for item in selected:
        execution_quality = item.get("execution_quality") or {}
        cards.append(
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "setup_label": item.get("setup_label") or item.get("setup_type") or "待确认",
                "screening_status": candidate_status_label(item.get("screening_status") or "unknown"),
                "tone": candidate_tone(item),
                "priority_score": item.get("priority_score"),
                "change_pct": item.get("change_pct"),
                "amount_yi": item.get("amount_yi"),
                "theme": ", ".join(item.get("themes") or []) or "其他",
                "risk": item.get("main_risk") or ((item.get("risk_flags") or [None])[0]) or "等待更多确认",
                "watch_condition": item.get("watch_condition") or "等待下一次确认",
                "execution_label": execution_quality.get("label") or "未评级",
                "execution_score": execution_quality.get("score"),
                "detail_url": today_candidate_detail_url(item.get("code")),
            }
        )
    return cards


def pick_midday_cards(confirmation: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not confirmation:
        return []
    selected = []
    for key in ("confirmed", "fresh_candidates", "downgraded"):
        selected.extend((confirmation.get(key) or [])[:2])
    cards: list[dict[str, Any]] = []
    for item in selected[:6]:
        cards.append(
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "status": candidate_status_label(item.get("status")),
                "tone": candidate_tone(item),
                "theme": item.get("theme") or "其他",
                "setup_label": item.get("setup_label") or "待确认",
                "change_pct": item.get("change_pct"),
                "amount_yi": item.get("amount_yi"),
                "risk": item.get("main_risk") or "等待更多确认",
                "detail_url": today_candidate_detail_url(item.get("code")),
            }
        )
    return cards


def quality_lane_cards(quality_status: dict[str, Any] | None) -> list[dict[str, Any]]:
    lanes = (quality_status or {}).get("lanes") or {}
    cards = []
    for key, title in (
        ("watchlist", "自选股"),
        ("aggressive", "进攻型早盘"),
        ("midday_confirmation", "午盘确认"),
    ):
        lane = lanes.get(key) or {}
        status = lane.get("validation_status") or "unknown"
        tone = "positive" if status == "ok" else ("risk" if status in {"blocked", "failed"} else "watch")
        cards.append(
            {
                "title": title,
                "status": status,
                "tone": tone,
                "checked_at": lane.get("checked_at") or "-",
                "expected_timestamp": lane.get("expected_timestamp") or "-",
                "issue": (lane.get("errors") or [None])[0] or (lane.get("warnings") or [None])[0] or "当前没有质检异常",
                "path": lane.get("path"),
                "url": artifact_url(lane.get("path")),
            }
        )
    return cards


def current_trade_date(
    watchlist: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    decision_brief: dict[str, Any] | None,
) -> str:
    if watchlist and watchlist.get("trade_date"):
        return str(watchlist["trade_date"])
    screening_dt = parse_timestamp((screening_batch or {}).get("generated_at"))
    if screening_dt:
        return screening_dt.strftime("%Y-%m-%d")
    if decision_brief and decision_brief.get("trade_date"):
        return str(decision_brief["trade_date"])
    return datetime.now().strftime("%Y-%m-%d")


def current_display_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def action_decision_label(decision: str | None) -> str:
    return ACTION_DECISION_LABELS.get(str(decision or "pending").strip(), "待确认")


def action_decision_tone(decision: str | None) -> str:
    return ACTION_DECISION_TONES.get(str(decision or "pending").strip(), "watch")


def action_display_label(state: str | None) -> str:
    return ACTION_DISPLAY_LABELS.get(str(state or "pending").strip(), "待处理")


def action_display_tone(state: str | None) -> str:
    return ACTION_DISPLAY_TONES.get(str(state or "pending").strip(), "watch")


def load_today_action_decision_store() -> dict[str, Any]:
    ensure_runtime_dirs()
    data = APP_STATE_REPOSITORY.get("today_action_decisions", legacy_path=TODAY_ACTION_STATE_PATH, default={}) or {}
    trade_dates = data.get("trade_dates")
    if not isinstance(trade_dates, dict):
        trade_dates = {}
    return {
        "version": 1,
        "updated_at": data.get("updated_at") or "",
        "trade_dates": trade_dates,
    }


def write_today_action_decision_store(data: dict[str, Any]) -> dict[str, Any]:
    ensure_runtime_dirs()
    trade_dates = data.get("trade_dates")
    if not isinstance(trade_dates, dict):
        trade_dates = {}

    kept_dates = sorted((str(key), value) for key, value in trade_dates.items() if isinstance(value, dict))
    if len(kept_dates) > 20:
        kept_dates = kept_dates[-20:]

    payload = {
        "version": 1,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trade_dates": {key: value for key, value in kept_dates},
    }
    return APP_STATE_REPOSITORY.set("today_action_decisions", payload, legacy_path=TODAY_ACTION_STATE_PATH)


def load_ask_recent_store() -> dict[str, Any]:
    ensure_runtime_dirs()
    data = APP_STATE_REPOSITORY.get("ask_recent_queries", legacy_path=ASK_RECENT_STATE_PATH, default={}) or {}
    items = data.get("items")
    if not isinstance(items, list):
        items = []
    return {
        "version": 1,
        "updated_at": data.get("updated_at") or "",
        "items": [item for item in items if isinstance(item, dict)],
    }


def write_ask_recent_store(data: dict[str, Any]) -> dict[str, Any]:
    ensure_runtime_dirs()
    normalized_items: list[dict[str, Any]] = []
    for raw in data.get("items") or []:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("code") or "").strip()
        if not re.fullmatch(r"\d{6}", code):
            continue
        name = str(raw.get("name") or code).strip() or code
        query = str(raw.get("query") or code).strip() or code
        normalized_items.append(
            {
                "code": code,
                "name": name,
                "query": query,
                "query_mode": str(raw.get("query_mode") or "code").strip() or "code",
                "updated_at": str(raw.get("updated_at") or "").strip(),
            }
        )

    payload = {
        "version": 1,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "items": normalized_items[-12:],
    }
    return APP_STATE_REPOSITORY.set("ask_recent_queries", payload, legacy_path=ASK_RECENT_STATE_PATH)


def remember_ask_query(
    *,
    code: str,
    name: str | None,
    query: str | None,
    query_mode: str | None,
) -> dict[str, Any]:
    normalized_code = str(code or "").strip()
    if not re.fullmatch(r"\d{6}", normalized_code):
        return load_ask_recent_store()

    store = load_ask_recent_store()
    items = [item for item in store.get("items") or [] if str(item.get("code") or "").strip() != normalized_code]
    items.append(
        {
            "code": normalized_code,
            "name": str(name or normalized_code).strip() or normalized_code,
            "query": str(query or normalized_code).strip() or normalized_code,
            "query_mode": str(query_mode or "code").strip() or "code",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    store["items"] = items
    return write_ask_recent_store(store)


def get_today_action_decision_map(trade_date: str | None) -> dict[str, dict[str, Any]]:
    if not trade_date:
        return {}
    store = load_today_action_decision_store()
    decisions = (store.get("trade_dates") or {}).get(str(trade_date))
    if not isinstance(decisions, dict):
        return {}
    return decisions


def update_today_action_decision(trade_date: str, key: str, decision: str) -> dict[str, Any]:
    normalized_trade_date = str(trade_date or "").strip()
    normalized_key = str(key or "").strip()
    normalized_decision = str(decision or "pending").strip().lower()
    if not normalized_trade_date:
        raise ValueError("trade_date is required")
    if not normalized_key:
        raise ValueError("key is required")
    if normalized_decision not in ACTION_DECISION_LABELS:
        raise ValueError("invalid decision")

    store = load_today_action_decision_store()
    trade_dates = store.setdefault("trade_dates", {})
    trade_state = trade_dates.setdefault(normalized_trade_date, {})

    if normalized_decision == "pending":
        trade_state.pop(normalized_key, None)
    else:
        trade_state[normalized_key] = {
            "decision": normalized_decision,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    if not trade_state:
        trade_dates.pop(normalized_trade_date, None)

    return write_today_action_decision_store(store)


def detail_value(value: Any, fallback: str = "-") -> Any:
    if value in (None, "", [], {}):
        return fallback
    return value


def round_money(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def optional_round_money(value: Any) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def text_items(values: list[Any] | None) -> list[str]:
    output: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text:
            output.append(text)
    return output


def normalize_review_note_text(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    replacements = {
        "避免在线接口回看历史时漂移或超时": "避免远端历史接口回看时漂移或超时",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized


def normalize_stock_ui_copy(text: Any) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    replacements = {
        "高质量候选": "优先观察名单",
        "高质量触发": "优先触发条件",
        "条件化放量": "条件化处理",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized


STOCK_RESULT_COPY_REPLACEMENTS = (
    ("买还是卖", "按纪律怎么处理"),
    ("要不要买", "是否满足触发条件"),
    ("能不能买", "是否满足触发条件"),
    ("强烈买入", "等待触发后再处理"),
    ("建议买入", "等待触发后再处理"),
    ("可以买入", "满足条件后再处理"),
    ("可以买", "满足条件后再处理"),
    ("该买", "满足条件后再处理"),
    ("买点", "触发条件"),
    ("卖点", "风险边界"),
    ("买入", "等待触发"),
    ("开新仓", "新增动作"),
    ("开仓", "新增动作"),
    ("介入", "纳入观察"),
    ("轻仓试错", "小仓位验证"),
    ("轻仓跟踪", "小仓位跟踪"),
    ("加仓", "提高仓位前先等确认"),
    ("满仓", "不放大仓位"),
    ("清仓", "停止原计划"),
    ("卖出", "风险优先处理"),
    ("目标价", "上方观察位"),
    ("收益预测", "表现推演"),
    ("收益承诺", "确定性承诺"),
    ("DCF", "估值模型"),
)

ASK_FOLLOWUP_COPY_REPLACEMENTS = (
    ("建议仓位", "仓位参考"),
    ("怎么操作", "怎么按纪律处理"),
    ("今天怎么操作", "今天怎么按纪律处理"),
    ("现在该怎么做", "现在按纪律怎么处理"),
    ("该怎么做", "按纪律怎么处理"),
    ("必须买", "必须等触发条件"),
    ("马上买", "先等触发条件"),
    ("直接买", "满足条件后再处理"),
)


def normalize_stock_result_copy(value: Any, fallback: str = "-") -> str:
    text = str(detail_value(value, fallback)).strip()
    if not text:
        return fallback
    text = normalize_stock_ui_copy(text)
    for source, target in STOCK_RESULT_COPY_REPLACEMENTS:
        text = text.replace(source, target)
    text = text.replace("新新增动作", "新增动作")
    return text


def normalize_position_guidance(value: Any, fallback: str = "待定") -> str:
    text = normalize_stock_result_copy(value, fallback)
    if text in {"-", "待定"}:
        return text
    if "小仓位" in text and "不放大" not in text:
        return f"{text}，不放大"
    return text


def normalize_ask_followup_copy(value: Any, fallback: str = "") -> str:
    text = normalize_stock_result_copy(value, fallback)
    for source, target in ASK_FOLLOWUP_COPY_REPLACEMENTS:
        text = text.replace(source, target)
    return text


def find_watchlist_stock(watchlist: dict[str, Any] | None, code: str) -> dict[str, Any] | None:
    target = code.strip()
    for item in (watchlist or {}).get("stocks") or []:
        if item.get("code") == target:
            return item
    return None


def find_confirmation_match(confirmation: dict[str, Any] | None, code: str) -> dict[str, Any] | None:
    target = code.strip()
    for key, label in (
        ("confirmed", "仍可跟踪"),
        ("downgraded", "降级"),
        ("fresh_candidates", "新增观察"),
    ):
        for item in (confirmation or {}).get(key) or []:
            if item.get("code") != target:
                continue
            return {
                "group_key": key,
                "group_label": label,
                "item": item,
            }
    return None


def find_screening_candidate(screening_batch: dict[str, Any] | None, code: str) -> dict[str, Any] | None:
    target = code.strip()
    for item in (screening_batch or {}).get("candidates") or []:
        if item.get("code") == target:
            return item
    return None


_STOCK_FETCH_MODULE: Any | None = None
_ASK_CASE_CACHE: dict[str, dict[str, Any]] = {}
ASK_CASE_CACHE_TTL_SECONDS = 300
ASK_FOLLOWUP_HISTORY_LIMIT = 6


def load_stock_fetch_module() -> Any:
    global _STOCK_FETCH_MODULE
    if _STOCK_FETCH_MODULE is not None:
        return _STOCK_FETCH_MODULE

    module_path = STOCK_ANALYZER_ROOT / "scripts" / "fetch.py"
    spec = importlib.util.spec_from_file_location("prism_stock_fetch", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("stock analyzer fetch module missing")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _STOCK_FETCH_MODULE = module
    return module


def first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, (list, tuple)):
            text = first_text(*value)
            if text:
                return text
            continue
        text = str(value or "").strip()
        if text and text != "-":
            return text
    return None


def normalize_next_step_sentence(value: Any, fallback: str = "先处理当前最靠前的一步。") -> str:
    text = normalize_stock_result_copy(value, fallback)
    if not text:
        return fallback
    if text.startswith(("先", "今天", "当前", "午盘", "新增", "等待", "触发", "按", "继续", "暂停", "只", "不")):
        return text
    return f"先{text}"


def normalize_trigger_sentence(value: Any, fallback: str = "先等触发条件明确，再决定下一步动作。") -> str:
    text = normalize_stock_result_copy(value, fallback)
    if not text:
        return fallback
    if text.startswith(("先", "等待", "当前没有", "暂无", "没有")):
        return text
    if "再" in text:
        return text
    if text.endswith(("。", "！", "？", ".", "!", "?")):
        text = text[:-1].rstrip()
    if text.endswith(("后", "之后", "时")):
        return f"{text}，再决定下一步动作。"
    return f"{text}后，再决定下一步动作。"


def normalize_avoid_sentence(value: Any, fallback: str = "先不要做超出纪律边界的动作。") -> str:
    text = normalize_stock_result_copy(value, fallback)
    if not text:
        return fallback
    if text.startswith(("当前没有", "暂无", "没有")):
        return text
    if text.startswith(("先不要", "不要", "先停")):
        return text
    if text.startswith("先不"):
        return f"先不要{text[2:]}"
    if text.startswith("不"):
        return f"不要{text[1:]}"
    return f"先不要{text}"


def normalize_main_conclusion(value: Any) -> str:
    text = str(detail_value(value, "观察")).strip()
    if any(token in text for token in ("卖", "清仓", "退出", "减仓")):
        return "风险优先"
    if any(token in text for token in ("买", "试错", "开仓", "介入")):
        return "等待触发"
    if any(token in text for token in ("持有", "保留")):
        return "持仓纪律"
    return "继续观察"


def source_scope_label(value: Any) -> str:
    normalized = str(detail_value(value, "live_fallback")).strip()
    return {
        "holdings": "自选股链路",
        "opportunity": "观察池链路",
        "live_fallback": "临时分析",
    }.get(normalized, normalized or "临时分析")


def normalize_canonical_action_tier(
    value: Any = None,
    *,
    action: Any = None,
    tone: Any = None,
    status: Any = None,
    title: Any = None,
) -> str:
    text = str(value or "").strip()
    if text in ACTION_TIER_LABELS:
        return ACTION_TIER_LABELS[text]
    if text in ACTION_TIER_LABELS.values():
        return text
    return action_tier_label(infer_action_tier(action=action, tone=tone, status=status, title=title))


def build_canonical_decision(
    *,
    stock_id: Any,
    stock_name: Any,
    trade_date: Any,
    source_scope: Any,
    main_conclusion: Any,
    action_tier: Any,
    position_guidance: Any,
    risk_boundary: Any,
    why_now: Any,
    continue_condition: Any,
    stop_condition: Any,
    next_step: Any,
    trigger_condition: Any,
    avoid_action: Any,
    evidence_entry: Any,
    confidence_note: Any,
    updated_at: Any,
) -> dict[str, Any]:
    normalized_main_conclusion = normalize_main_conclusion(main_conclusion)
    return {
        "stock_id": str(detail_value(stock_id)).strip(),
        "stock_name": str(detail_value(stock_name)).strip(),
        "trade_date": detail_value(trade_date),
        "source_scope": str(detail_value(source_scope, "live_fallback")).strip(),
        "main_conclusion": normalized_main_conclusion,
        "action_tier": normalize_canonical_action_tier(
            action_tier,
            action=main_conclusion,
            tone=action_tone(main_conclusion),
            status=normalized_main_conclusion,
            title=stock_name,
        ),
        "position_guidance": normalize_position_guidance(position_guidance, "待定"),
        "risk_boundary": normalize_stock_result_copy(risk_boundary, "先守纪律边界"),
        "why_now": normalize_stock_result_copy(why_now, "先按当前主结论理解这只股票。"),
        "continue_condition": normalize_stock_result_copy(continue_condition, "满足当前纪律前，先不升级动作。"),
        "stop_condition": normalize_stock_result_copy(stop_condition, "一旦触发失效条件，先停下来。"),
        "next_step": normalize_next_step_sentence(next_step),
        "trigger_condition": normalize_trigger_sentence(trigger_condition),
        "avoid_action": normalize_avoid_sentence(avoid_action),
        "evidence_entry": normalize_stock_result_copy(evidence_entry, "看原始证据入口"),
        "confidence_note": normalize_stock_result_copy(confidence_note, "当前证据不完整，先别放大动作。"),
        "updated_at": detail_value(updated_at),
    }


def ask_context_tags(
    watchlist_stock: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    confirmation_match: dict[str, Any] | None,
    *,
    stock: dict[str, Any] | None = None,
    query_mode: str,
) -> list[str]:
    tags: list[str] = []
    if query_mode == "name":
        tags.append("名称命中")
    if watchlist_stock:
        tags.append("已命中自选股")
    if candidate:
        tags.append("已命中观察池")
    if confirmation_match:
        tags.append(f"午盘{confirmation_match.get('group_label')}")
    if stock and "historical_catalog" in (stock.get("sources") or []):
        tags.append("历史库命中")
    if stock and ("full_market_search" in (stock.get("sources") or []) or stock.get("source") == "sina_search"):
        tags.append("实时搜索命中")
    if not tags:
        tags.append("仅临时分析")
    return tags


def ask_search_fill_value(name: str | None, code: str | None) -> str:
    normalized_code = str(code or "").strip()
    normalized_name = str(name or "").strip()
    if normalized_name and normalized_name != normalized_code:
        return f"{normalized_name} {normalized_code}".strip()
    return normalized_code


def ask_catalog_source_tag(item: dict[str, Any]) -> str:
    sources = list(item.get("sources") or [])
    if "watchlist_snapshot" in sources or "watchlist_config" in sources:
        return "自选股" if item.get("watchlist_active", True) else "归档自选"
    if "screening_batch" in sources:
        return "观察池"
    if any(str(source).startswith("confirmation:") for source in sources):
        return "午盘确认"
    if "historical_catalog" in sources:
        return str(item.get("history_label") or "历史库").strip() or "历史库"
    if "full_market_search" in sources or item.get("source") == "sina_search":
        return "全市场搜索"
    return "系统已知"


def ask_catalog_priority(item: dict[str, Any]) -> int:
    tag = ask_catalog_source_tag(item)
    return {
        "自选股": 0,
        "观察池": 1,
        "午盘确认": 2,
        "归档自选": 3,
        "全市场搜索": 4,
        "系统已知": 5,
    }.get(tag, 5)


def build_stock_catalog(
    watchlist: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}

    def add_entry(entry: dict[str, Any] | None, source: str) -> None:
        if not isinstance(entry, dict):
            return
        code = str(entry.get("code") or "").strip()
        if not re.fullmatch(r"\d{6}", code):
            return

        item = catalog.setdefault(
            code,
            {
                "code": code,
                "name": code,
                "market": infer_market_from_code(code),
                "sina": infer_sina_code(code),
                "sources": [],
            },
        )

        name = str(entry.get("name") or "").strip()
        if name and item.get("name") in {"", code}:
            item["name"] = name

        for field in ("industry", "sector_code", "market", "sina", "history_label"):
            value = entry.get(field)
            if value and not item.get(field):
                item[field] = value

        if source == "watchlist_config" and "active" in entry:
            item["watchlist_active"] = bool(entry.get("active", True))

        if source not in item["sources"]:
            item["sources"].append(source)

    for item in list_watchlist_stocks():
        add_entry(item, "watchlist_config")
    for item in (watchlist or {}).get("stocks") or []:
        add_entry(item, "watchlist_snapshot")
    for item in (screening_batch or {}).get("candidates") or []:
        add_entry(item, "screening_batch")
    for key in ("confirmed", "downgraded", "fresh_candidates"):
        for item in (confirmation or {}).get(key) or []:
            add_entry(item, f"confirmation:{key}")
    for item in list_historical_stock_catalog():
        add_entry(item, "historical_catalog")

    return catalog


def resolve_ask_stock(
    query: str,
    watchlist: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_query = str(query or "").strip()
    if not normalized_query:
        raise ValueError("请输入股票代码或名称")

    catalog = build_stock_catalog(watchlist, screening_batch, confirmation)
    code_match = re.search(r"(\d{6})", normalized_query)
    if code_match:
        code = code_match.group(1)
        stock = dict(catalog.get(code) or {})
        stock.setdefault("code", code)
        stock.setdefault("market", infer_market_from_code(code))
        stock.setdefault("sina", infer_sina_code(code, stock.get("market")))
        name = stock.get("name")
        if not name or name == code:
            stock["name"] = fetch_stock_name(code, stock.get("market")) or code
        return {
            "query": normalized_query,
            "mode": "code",
            "stock": stock,
            "matches": [],
        }

    lowered = normalized_query.lower()
    exact: list[dict[str, Any]] = []
    fuzzy: list[dict[str, Any]] = []
    for item in catalog.values():
        name = str(item.get("name") or "").strip()
        if not name or name == item.get("code"):
            continue
        current = dict(item)
        if name.lower() == lowered:
            exact.append(current)
        elif lowered in name.lower():
            fuzzy.append(current)

    remote_matches: list[dict[str, Any]] = []
    if not exact and not fuzzy:
        for item in search_sina_stock_suggestions(normalized_query, limit=8):
            remote_matches.append(
                {
                    **item,
                    "sources": ["full_market_search"],
                }
            )

    matches = exact or fuzzy or remote_matches
    if not matches:
        raise ValueError("名称搜索会先查系统内、历史库和全市场联想；如果还没命中，建议直接输入 6 位代码。")

    stock = matches[0]
    stock.setdefault("market", infer_market_from_code(stock.get("code")))
    stock.setdefault("sina", infer_sina_code(stock.get("code"), stock.get("market")))
    if not stock.get("name") or stock.get("name") == stock.get("code"):
        stock["name"] = fetch_stock_name(stock.get("code"), stock.get("market")) or stock.get("code")
    return {
        "query": normalized_query,
        "mode": "name",
        "stock": stock,
        "matches": matches[:6],
    }


def build_live_stock_context(stock: dict[str, Any]) -> dict[str, Any]:
    fetch = load_stock_fetch_module()
    code = str(stock.get("code") or "").strip()
    market = str(stock.get("market") or infer_market_from_code(code)).strip().lower()
    sina = str(stock.get("sina") or infer_sina_code(code, market)).strip()
    name = str(stock.get("name") or code).strip() or code

    realtime = None
    news: list[dict[str, Any]] = []
    announcements: list[dict[str, Any]] = []
    tech = None
    flow = None
    fundamentals = None
    sector = None
    warnings: list[str] = []
    component_status = {
        "realtime": False,
        "events": False,
        "technical": False,
        "flow": False,
        "fundamentals": False,
        "sector": False,
    }

    try:
        realtime = fetch.fetch_realtime(sina)
        component_status["realtime"] = True
    except Exception:
        warnings.append("实时行情未取到")

    try:
        news = fetch.fetch_news(name, code, 5) or []
        announcements = fetch.fetch_announcements(code, 5) or []
        component_status["events"] = True
    except Exception:
        warnings.append("公告/新闻未取到")

    try:
        tech = fetch.fetch_technical_indicators(sina, 60)
        component_status["technical"] = True
    except Exception:
        warnings.append("技术指标未取到")

    try:
        flow = fetch.fetch_capital_flow(code, market)
        component_status["flow"] = bool(flow)
        if not flow:
            warnings.append("资金流向未取到")
    except Exception:
        warnings.append("资金流向未取到")

    try:
        fundamentals = fetch.fetch_fundamentals(code, market)
        component_status["fundamentals"] = bool(fundamentals)
        if not fundamentals:
            warnings.append("基本面数据未取到")
    except Exception:
        warnings.append("基本面数据未取到")

    sector_code = str(stock.get("sector_code") or "").strip()
    if sector_code:
        try:
            sector = fetch.fetch_sector(sector_code)
            component_status["sector"] = bool(sector)
        except Exception:
            sector = None

    snapshot = None
    trade_levels = None
    intraday_triggers: list[dict[str, Any]] = []
    snapshot_record = None
    if realtime:
        try:
            snapshot = fetch.build_rule_snapshot(stock, realtime, news, announcements, tech, flow, fundamentals, sector)
            trade_levels = fetch.select_support_resistance(tech, realtime, snapshot)
            intraday_triggers = fetch.build_intraday_triggers(snapshot, trade_levels, realtime, tech, flow, sector)
            snapshot_record = fetch.build_snapshot_record(
                stock,
                snapshot,
                tech,
                trade_levels,
                intraday_triggers,
                datetime.now().strftime("%Y-%m-%d"),
                realtime=realtime,
                capital_flow=flow,
            )
        except Exception:
            warnings.append("规则化快照生成失败")

    return {
        "realtime": realtime,
        "news": news,
        "announcements": announcements,
        "tech": tech,
        "flow": flow,
        "fundamentals": fundamentals,
        "sector": sector,
        "snapshot": snapshot,
        "trade_levels": trade_levels,
        "intraday_triggers": intraday_triggers,
        "snapshot_record": snapshot_record,
        "warnings": warnings,
        "component_status": component_status,
    }


def watchlist_snapshot_to_case(stock: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not stock:
        return None, None
    snapshot = {
        "tech_base": stock.get("rule_snapshot", {}).get("tech_base"),
        "flow_base": stock.get("rule_snapshot", {}).get("flow_base"),
        "event_base": stock.get("rule_snapshot", {}).get("event_base"),
        "action": stock.get("action"),
        "position": stock.get("position"),
        "signal": stock.get("rule_snapshot", {}).get("signal"),
        "score": stock.get("rule_snapshot", {}).get("score"),
        "score_kind": stock.get("rule_snapshot", {}).get("score_kind"),
        "hard_flags": stock.get("hard_flags") or [],
        "positives": stock.get("positives") or [],
        "watch_points": stock.get("watch_points") or [],
    }
    levels = stock.get("trade_levels") or {}
    trade_levels = {
        "support": {"label": "快照支撑位", "value": levels.get("support")},
        "resistance": {"label": "快照压力位", "value": levels.get("resistance")},
        "stop_loss": {"label": "快照止损位", "value": levels.get("stop_loss"), "status": "-"},
    }
    return snapshot, trade_levels


def ask_confidence(live_context: dict[str, Any], *, has_existing_context: bool) -> dict[str, Any]:
    status = live_context.get("component_status") or {}
    live_hits = sum(1 for ok in status.values() if ok)
    warnings = text_items(live_context.get("warnings"))
    if live_hits >= 5 or (live_hits >= 4 and has_existing_context):
        label = "高"
        tone = "positive"
    elif live_hits >= 3:
        label = "中"
        tone = "watch"
    else:
        label = "低"
        tone = "risk"

    missing_map = {
        "realtime": "实时行情",
        "events": "公告新闻",
        "technical": "技术指标",
        "flow": "资金流向",
        "fundamentals": "基本面",
    }
    missing = [title for key, title in missing_map.items() if not status.get(key)]
    note = []
    if missing:
        note.append(f"缺少 {' / '.join(missing)}")
    if warnings:
        note.append("；".join(warnings[:2]))

    return {
        "label": label,
        "tone": tone,
        "detail": "；".join(note) if note else "实时链路和系统上下文都比较完整。",
        "live_hits": live_hits,
    }


def ask_decision_from_candidate(candidate: dict[str, Any], confirmation_match: dict[str, Any] | None) -> tuple[str, str]:
    group_key = (confirmation_match or {}).get("group_key")
    if group_key == "confirmed":
        return "轻仓跟踪", detail_value(((confirmation_match or {}).get("item") or {}).get("entry_reason"), "午盘确认后仍可跟踪。")
    if group_key == "fresh_candidates":
        return "只观察不执行", detail_value(((confirmation_match or {}).get("item") or {}).get("entry_reason"), "午盘新增观察，先别急着开仓。")
    if group_key == "downgraded":
        return "回避", detail_value(((confirmation_match or {}).get("item") or {}).get("main_risk"), "午盘已降级，先退出执行名单。")

    status = str(candidate.get("screening_status") or "").strip()
    entry_action = first_text(((candidate.get("entry_plan") or {}).get("action")), candidate.get("screening_note")) or ""
    if "不开新仓" in entry_action or "观察" in entry_action:
        return "只观察不执行", entry_action
    if status == "approved":
        return "轻仓跟踪", first_text(candidate.get("entry_reason"), entry_action) or "当前进入早盘候选名单。"
    if status == "excluded":
        return "回避", first_text(candidate.get("main_risk"), candidate.get("screening_note")) or "当前不在继续跟踪名单。"
    return "只观察不执行", first_text(candidate.get("screening_note"), candidate.get("entry_reason")) or "当前只保留观察。"


def ask_state_tone(value: str | None) -> str:
    text = str(value or "").strip()
    if any(keyword in text for keyword in ("看多", "偏多", "进入候选", "仍可跟踪", "轻仓", "买入")):
        return "positive"
    if any(keyword in text for keyword in ("看空", "偏空", "回避", "降级", "减仓")):
        return "risk"
    return "watch"


def ask_analysis_groups(
    active_snapshot: dict[str, Any] | None,
    live_context: dict[str, Any],
    stock: dict[str, Any],
    candidate: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    tech = live_context.get("tech") or {}
    flow = live_context.get("flow") or {}
    fundamentals = live_context.get("fundamentals") or {}
    sector = live_context.get("sector") or {}
    realtime = live_context.get("realtime") or {}
    snapshot = active_snapshot or {}
    price_position = tech.get("price_position") or {}
    ma = tech.get("ma") or {}
    execution_quality = (candidate or {}).get("execution_quality") or {}

    sector_items = []
    if sector:
        sector_items.append(f"所属行业 {detail_value(stock.get('industry'), sector.get('name') or '未知')}")
        sector_items.append(f"行业涨幅 {signed_pct(sector.get('change_pct'))}")
        if realtime.get("change_pct") is not None and sector.get("change_pct") is not None:
            diff = float(realtime.get("change_pct")) - float(sector.get("change_pct"))
            relation = "强于行业" if diff > 0.5 else ("弱于行业" if diff < -0.5 else "与行业持平")
            sector_items.append(f"相对强弱 {relation}")
    elif (candidate or {}).get("themes"):
        sector_items.append(f"主题 {', '.join((candidate or {}).get('themes') or [])}")
    else:
        sector_items.append("当前没有行业对比数据")

    risk_items = text_items(snapshot.get("hard_flags"))
    risk_items.extend(text_items((candidate or {}).get("risk_flags")))
    risk_items.extend(text_items(live_context.get("warnings")))

    groups = [
        {
            "title": "技术面",
            "tone": ask_state_tone(snapshot.get("tech_base")),
            "metric": detail_value(snapshot.get("signal"), detail_value(snapshot.get("tech_base"))),
            "items": text_items(
                [
                    first_text(snapshot.get("signal"), snapshot.get("tech_base")),
                    f"规则分 {detail_value(snapshot.get('score'))}",
                    f"MA20 {detail_value(ma.get('MA20'))}",
                    f"MA60 {detail_value(ma.get('MA60'))}",
                    f"距20日高 {signed_pct(price_position.get('pct_from_high'))}" if price_position.get("pct_from_high") is not None else None,
                ]
            ),
            "empty": "技术数据暂不完整。",
        },
        {
            "title": "资金面",
            "tone": ask_state_tone(snapshot.get("flow_base")),
            "metric": detail_value(flow.get("signal"), detail_value(snapshot.get("flow_base"))),
            "items": text_items(
                [
                    first_text(flow.get("signal"), snapshot.get("flow_base")),
                    f"主力净流入 {detail_value(flow.get('main_net'))} 万元" if flow.get("main_net") is not None else None,
                    f"5日累计 {detail_value(sum(item.get('net', 0) for item in (flow.get('main_5d') or [])[:5]))} 万元" if flow.get("main_5d") else None,
                    "资金流仅作历史参考" if flow.get("intraday_unconfirmed") else None,
                ]
            ),
            "empty": "资金数据暂不完整。",
        },
        {
            "title": "事件面",
            "tone": ask_state_tone(snapshot.get("event_base")),
            "metric": detail_value(snapshot.get("event_base")),
            "items": text_items(
                [
                    first_text(snapshot.get("positives")),
                    first_text(snapshot.get("hard_flags")),
                    f"公告 {len(live_context.get('announcements') or [])} 条",
                    f"新闻 {len(live_context.get('news') or [])} 条",
                ]
            ),
            "empty": "当前没有足够的事件线索。",
        },
        {
            "title": "基本面",
            "tone": "risk" if any(flag in text_items(snapshot.get("hard_flags")) for flag in ("PE极高", "ROE为负", "PB与ROE不匹配")) else "watch",
            "metric": f"PE {detail_value(fundamentals.get('pe'))}",
            "items": text_items(
                [
                    f"PE {detail_value(fundamentals.get('pe'))}",
                    f"PB {detail_value(fundamentals.get('pb'))}",
                    f"ROE {detail_value(fundamentals.get('roe'))}%",
                    f"总市值 {detail_value(fundamentals.get('total_mv_yi'))} 亿",
                ]
            ),
            "empty": "基本面数据暂不完整。",
        },
        {
            "title": "情绪板块",
            "tone": "positive" if any("强于行业" in item for item in sector_items) else ("risk" if any("弱于行业" in item for item in sector_items) else "watch"),
            "metric": sector_items[0] if sector_items else "-",
            "items": sector_items,
            "empty": "当前没有板块对比数据。",
        },
        {
            "title": "风险",
            "tone": "risk",
            "metric": detail_value((risk_items or ["暂无额外硬风险"])[0]),
            "items": risk_items[:5],
            "empty": "当前没有额外的风险提示。",
        },
    ]

    if execution_quality:
        groups.append(
            {
                "title": "执行质量",
                "tone": candidate_tone(candidate or {}),
                "metric": detail_value(execution_quality.get("label")),
                "items": text_items(
                    list(execution_quality.get("positives") or [])[:2]
                    + list(execution_quality.get("warnings") or [])[:2]
                ),
                "empty": "当前没有执行质量补充。",
            }
        )

    return groups


def ask_event_groups(live_context: dict[str, Any]) -> list[dict[str, Any]]:
    groups = []
    for key, title, fallback in (
        ("announcements", "最新公告", "当前没有抓到公告。"),
        ("news", "最新新闻", "当前没有抓到新闻。"),
    ):
        items = []
        for item in (live_context.get(key) or [])[:5]:
            headline = first_text(item.get("title"), item.get("content"))
            if not headline:
                continue
            meta = " | ".join(
                text_items([item.get("date"), item.get("source")])
            )
            items.append({"title": headline, "meta": meta})
        groups.append(
            {
                "title": title,
                "items": items,
                "empty": fallback,
            }
        )
    return groups


def find_today_action_match(code: str) -> dict[str, Any] | None:
    try:
        today = build_today_view()
    except Exception:
        return None
    action_queue = today.get("action_queue") or {}
    for collection in (action_queue.get("items") or [], action_queue.get("stale_items") or []):
        for item in collection:
            if str(item.get("code") or "").strip() == code:
                return item
    return None


def build_today_action_context(
    code: str,
    today: dict[str, Any] | None = None,
    account_book: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    normalized_code = str(code or "").strip()
    if not normalized_code:
        return None

    if today is None:
        try:
            today = build_today_view()
        except Exception:
            return None

    trade_date = str(today.get("trade_date") or today.get("expected_trade_date") or "").strip()
    decision_map = get_today_action_decision_map(trade_date) if trade_date else {}
    no_fill_index = build_no_fill_intent_index(account_book if account_book is not None else load_account_book())

    matched_item = None
    action_queue = today.get("action_queue") or {}
    for collection in (action_queue.get("items") or [], action_queue.get("stale_items") or []):
        for item in collection:
            key = str(item.get("key") or "").strip()
            if key.endswith(normalized_code):
                matched_item = item
                break
        if matched_item:
            break

    if not matched_item:
        for group in today.get("action_groups") or []:
            for item in group.get("items") or []:
                key = str(item.get("key") or "").strip()
                if key.endswith(normalized_code):
                    matched_item = item
                    break
            if matched_item:
                break

    if not matched_item:
        return None

    enriched_item = dict(matched_item)
    if not enriched_item.get("decision"):
        enriched_item["decision"] = build_today_action_decision_state(enriched_item, decision_map)
    if not enriched_item.get("display_state") and trade_date:
        enriched_item["display_state"] = build_today_action_display_state(
            item=enriched_item,
            trade_date=trade_date,
            no_fill_index=no_fill_index,
        )

    return {
        "key": str(enriched_item.get("key") or "").strip(),
        "trade_date": trade_date,
        "source": str(enriched_item.get("source") or "").strip(),
        "status": str(enriched_item.get("status") or "").strip(),
        "detail": str(enriched_item.get("detail") or "").strip(),
        "group_title": str(enriched_item.get("group_title") or "").strip(),
        "actionable": bool(enriched_item.get("actionable", True)),
        "trust": enriched_item.get("trust") or None,
        "confidence": enriched_item.get("confidence") or None,
        "decision": enriched_item.get("decision") or None,
        "display_state": enriched_item.get("display_state") or None,
    }


def build_ask_case_view(
    query: str,
    watchlist: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
) -> dict[str, Any]:
    resolved = resolve_ask_stock(query, watchlist, screening_batch, confirmation)
    stock = dict(resolved.get("stock") or {})
    code = str(stock.get("code") or "").strip()
    watchlist_stock = find_watchlist_stock(watchlist, code)
    candidate = find_screening_candidate(screening_batch, code)
    confirmation_match = find_confirmation_match(confirmation, code)
    today_match = find_today_action_match(code)

    watchlist_config_stock = next((item for item in list_watchlist_stocks() if str(item.get("code") or "").strip() == code), None)
    if watchlist_config_stock:
        for field in ("industry", "sector_code", "market", "sina"):
            value = watchlist_config_stock.get(field)
            if value and not stock.get(field):
                stock[field] = value

    stock.setdefault("market", infer_market_from_code(code))
    stock.setdefault("sina", infer_sina_code(code, stock.get("market")))
    stock.setdefault("name", fetch_stock_name(code, stock.get("market")) or code)

    live_context = build_live_stock_context(stock)
    fallback_snapshot, fallback_trade_levels = watchlist_snapshot_to_case(watchlist_stock)
    active_snapshot = live_context.get("snapshot") or fallback_snapshot or {}
    active_levels = live_context.get("trade_levels") or fallback_trade_levels or {}
    active_triggers = live_context.get("intraday_triggers") or list((watchlist_stock or {}).get("intraday_triggers") or [])

    if watchlist_stock:
        decision_label = detail_value(watchlist_stock.get("action"), "观望")
        decision_summary = first_text(
            watchlist_stock.get("hard_flags"),
            watchlist_stock.get("watch_points"),
            watchlist_stock.get("positives"),
            active_snapshot.get("signal"),
        ) or "当前以自选股链路判断为主。"
        position_value = detail_value(watchlist_stock.get("position"), "0-0.5成")
    elif candidate:
        decision_label, decision_summary = ask_decision_from_candidate(candidate, confirmation_match)
        position_value = detail_value(((candidate.get("entry_plan") or {}).get("sizing")), "先不开新仓")
    else:
        decision_label = detail_value(active_snapshot.get("action"), "观望")
        decision_summary = first_text(
            active_snapshot.get("hard_flags"),
            active_snapshot.get("watch_points"),
            active_snapshot.get("positives"),
            active_snapshot.get("signal"),
        ) or "当前主要依据实时抓取结果判断。"
        position_value = detail_value(active_snapshot.get("position"), "0-0.5成")

    confidence = ask_confidence(live_context, has_existing_context=bool(watchlist_stock or candidate or confirmation_match))
    cross_cards = [
        {
            "label": "自选股",
            "value": detail_value((watchlist_stock or {}).get("action"), "未进入"),
            "tone": action_tone((watchlist_stock or {}).get("action")),
            "detail": detail_value((watchlist_stock or {}).get("position"), "当前不在自选股快照"),
        },
        {
            "label": "观察池",
            "value": detail_value(candidate_status_label((candidate or {}).get("screening_status")) if candidate else None, "未进入"),
            "tone": candidate_tone(candidate or {}) if candidate else "watch",
            "detail": detail_value((candidate or {}).get("setup_label"), "当前不在早盘候选池"),
        },
        {
            "label": "午盘确认",
            "value": detail_value((confirmation_match or {}).get("group_label"), "暂无"),
            "tone": candidate_tone(((confirmation_match or {}).get("item") or {})) if confirmation_match else "watch",
            "detail": detail_value((((confirmation_match or {}).get("item") or {}).get("main_risk")), "尚未进入午盘确认链路"),
        },
        {
            "label": "今日动作队列",
            "value": detail_value((today_match or {}).get("group_title"), "未进入"),
            "tone": str((today_match or {}).get("tone") or "watch"),
            "detail": detail_value((today_match or {}).get("detail"), "当前不在今日动作队列"),
        },
    ]

    realtime = live_context.get("realtime") or {}
    flow = live_context.get("flow") or {}
    level_source = active_levels or {}
    metric_cards = [
        {
            "label": "最新价",
            "value": detail_value(realtime.get("price")),
            "detail": detail_value(realtime.get("time"), "暂无实时价格"),
        },
        {
            "label": "涨幅",
            "value": signed_pct(realtime.get("change_pct")),
            "detail": f"成交 {detail_value(round((float(realtime.get('amount', 0) or 0) / 1e8), 2) if realtime.get('amount') is not None else None, '-')}" + " 亿" if realtime else "暂无成交额",
        },
        {
            "label": "规则分",
            "value": detail_value(active_snapshot.get("score")),
            "detail": detail_value(active_snapshot.get("signal"), detail_value(active_snapshot.get("tech_base"))),
        },
        {
            "label": "资金信号",
            "value": detail_value(flow.get("signal"), detail_value(active_snapshot.get("flow_base"))),
            "detail": f"主力 {detail_value(flow.get('main_net'))} 万元" if flow else "当前没有资金信号",
        },
    ]
    level_cards = [
        {
            "label": "支撑位",
            "value": detail_value(((level_source.get("support") or {}).get("value"))),
            "detail": detail_value(((level_source.get("support") or {}).get("label")), "防守参考"),
        },
        {
            "label": "压力位",
            "value": detail_value(((level_source.get("resistance") or {}).get("value"))),
            "detail": detail_value(((level_source.get("resistance") or {}).get("label")), "突破观察"),
        },
        {
            "label": "止损位",
            "value": detail_value(((level_source.get("stop_loss") or {}).get("value"))),
            "detail": detail_value(((level_source.get("stop_loss") or {}).get("label")), "纪律边界"),
        },
        {
            "label": "建议仓位",
            "value": position_value,
            "detail": "来自当前统一判断",
        },
    ]

    entry_plan = (candidate or {}).get("entry_plan") or {}
    plan_rows = [
        {"label": "动作", "value": decision_label},
        {
            "label": "触发",
            "value": detail_value(
                first_text(entry_plan.get("trigger"), ((active_triggers or [None, None])[1] or {}).get("condition")),
                "当前没有单独触发说明",
            ),
        },
        {
            "label": "回避",
            "value": detail_value(
                first_text(entry_plan.get("avoid"), (candidate or {}).get("main_risk"), active_snapshot.get("hard_flags")),
                "当前没有单独回避提示",
            ),
        },
        {
            "label": "失效",
            "value": detail_value(
                first_text(entry_plan.get("invalidate"), ((active_triggers or [None])[0] or {}).get("condition")),
                "当前没有单独失效位",
            ),
        },
        {"label": "仓位", "value": position_value},
    ]
    plan_levels = [
        {
            "label": "触发位",
            "value": detail_value(first_text(((entry_plan.get("levels") or {}).get("trigger")), ((level_source.get("resistance") or {}).get("value")))),
        },
        {
            "label": "回踩位",
            "value": detail_value(first_text(((entry_plan.get("levels") or {}).get("pullback")), ((level_source.get("support") or {}).get("value")))),
        },
        {
            "label": "失效位",
            "value": detail_value(first_text(((entry_plan.get("levels") or {}).get("invalidate")), ((level_source.get("stop_loss") or {}).get("value")))),
        },
    ]

    artifacts = [
        artifact_from_path("自选股快照 JSON", (watchlist or {}).get("snapshot_path"), key="watchlist_snapshot") if watchlist_stock else None,
        artifact_from_path("早盘批次 JSON", (screening_batch or {}).get("path"), key="screening_batch") if candidate else None,
        artifact_from_path("午盘确认 JSON", (confirmation or {}).get("path"), key="confirmation") if confirmation_match else None,
    ]
    action_row = next((item for item in plan_rows if item.get("label") == "动作"), None)
    risk_row = next((item for item in plan_rows if item.get("label") == "回避"), None)
    invalid_row = next((item for item in plan_rows if item.get("label") == "失效"), None)
    config_is_active = bool((watchlist_config_stock or {}).get("active", True)) if watchlist_config_stock else False
    if watchlist_config_stock and config_is_active:
        watchlist_action = {
            "kind": "active",
            "label": "已在自选股",
            "button_label": "去自选股管理",
            "detail": "当前已经纳入自选股链路。"
            if watchlist_stock
            else "名单里已经有这只股票，等待刷新后会补齐快照和摘要。",
            "feedback_hint": "可以直接去自选股页继续看持仓链路。",
            "tone": "positive" if watchlist_stock else "watch",
            "code": code,
            "name": stock.get("name"),
        }
    elif watchlist_config_stock:
        watchlist_action = {
            "kind": "restore",
            "label": "恢复到自选股",
            "button_label": "恢复到自选股",
            "detail": "这只股票当前在归档区，恢复后会自动刷新自选股快照、摘要和总控简报。",
            "feedback_hint": "恢复后页面会自动刷新。",
            "tone": "watch",
            "code": code,
            "name": stock.get("name"),
        }
    else:
        watchlist_action = {
            "kind": "add",
            "label": "加入自选股",
            "button_label": "加入自选股",
            "detail": "把这只股票正式拉进自选股链路，后面日报、新闻和持仓快照都会跟上。",
            "feedback_hint": "加入后会自动触发后台刷新。",
            "tone": "positive",
            "code": code,
            "name": stock.get("name"),
        }

    canonical_decision = build_canonical_decision(
        stock_id=code,
        stock_name=stock.get("name"),
        trade_date=current_trade_date(watchlist, screening_batch, None),
        source_scope=("holdings" if watchlist_stock else "opportunity" if candidate else "live_fallback"),
        main_conclusion=decision_label,
        action_tier=infer_action_tier(
            action=(action_row or {}).get("value") or decision_label,
            tone=action_tone(decision_label),
            status=decision_label,
            title=stock.get("name"),
        ),
        position_guidance=position_value,
        risk_boundary=(invalid_row or {}).get("value") or confidence.get("detail"),
        why_now=decision_summary,
        continue_condition=next((item for item in plan_rows if item.get("label") == "触发"), {}).get("value"),
        stop_condition=(invalid_row or {}).get("value") or confidence.get("detail"),
        next_step=(action_row or {}).get("value"),
        trigger_condition=next((item for item in plan_rows if item.get("label") == "触发"), {}).get("value"),
        avoid_action=(risk_row or {}).get("value"),
        evidence_entry="看关键位与跨层背景",
        confidence_note=confidence.get("detail"),
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    case = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": current_trade_date(watchlist, screening_batch, None),
        "query": resolved.get("query"),
        "query_mode": resolved.get("mode"),
        "code": code,
        "name": stock.get("name"),
        "market": stock.get("market"),
        "industry": stock.get("industry"),
        "tone": action_tone(decision_label),
        "hero": {
            "title": f"{stock.get('name')} {code}",
            "summary": normalize_stock_result_copy(decision_summary, "先按已有证据理解这只股票。"),
            "decision_label": normalize_main_conclusion(decision_label),
            "position": normalize_position_guidance(position_value),
            "confidence_label": confidence.get("label"),
            "confidence_note": normalize_stock_result_copy(confidence.get("detail"), "当前证据不完整，先别放大动作。"),
        },
        "context_tags": ask_context_tags(
            watchlist_stock,
            candidate,
            confirmation_match,
            stock=stock,
            query_mode=str(resolved.get("mode") or "code"),
        ),
        "cross_cards": cross_cards,
        "canonical_decision": canonical_decision,
        "action_tier_legend": build_action_tier_legend(),
        "topline": build_detail_topline(
            badge="单票结论",
            title=decision_label,
            summary=decision_summary,
            meta_pills=build_topline_meta_pills(
                freshness=current_trade_date(watchlist, screening_batch, None),
                position=position_value,
                risk_boundary=(invalid_row or {}).get("value") or confidence.get("detail"),
            ),
            cta_links=[
                {"label": "去看持仓视角", "href": watchlist_detail_url(code)} if watchlist_stock else None,
                {"label": "去看观察池视角", "href": candidate_detail_url(code)} if candidate else None,
                {"label": "去看持仓列表", "href": watchlist_page_url()},
            ],
        ),
        "decision_cards": build_detail_decision_cards(
            conclusion=decision_label,
            conclusion_detail=decision_summary,
            position=position_value,
            position_detail="按当前统一判断控制仓位，不额外放大动作。",
            risk_boundary=(invalid_row or {}).get("value") or confidence.get("detail"),
            risk_detail="先守住失效位和纪律边界，再决定是否继续执行。",
            next_step=(action_row or {}).get("value"),
            next_step_detail="先处理当前最靠前的一步，再决定要不要展开更多证据。",
        ),
        "decision_explanation": build_decision_explanation_block(
            why=decision_summary,
            risk=(risk_row or {}).get("value"),
            invalid=(invalid_row or {}).get("value") or confidence.get("detail"),
        ),
        "execution_loop": build_execution_loop(
            action_now=(action_row or {}).get("value"),
            action_detail="先按当前结论执行，再决定是否升级动作。",
            why_now=decision_summary,
            why_detail="先用当前主判断托底，不让页面先把人带进细节里。",
            trigger=next((item for item in plan_rows if item.get("label") == "触发"), {}).get("value"),
            trigger_detail="触发条件成立后，再看要不要扩大动作。",
            avoid=(risk_row or {}).get("value"),
            avoid_detail="这是当前最容易出错的动作边界。",
            evidence="看关键位与跨层背景",
            evidence_detail="先看关键位和跨系统状态，需要更深时再展开六维与事件证据。",
        ),
        "metric_cards": metric_cards,
        "level_cards": level_cards,
        "analysis_groups": ask_analysis_groups(active_snapshot, live_context, stock, candidate),
        "plan_rows": plan_rows,
        "plan_levels": plan_levels,
        "triggers": active_triggers,
        "event_groups": ask_event_groups(live_context),
        "artifacts": [item for item in artifacts if item],
        "watchlist_action": watchlist_action,
        "links": {
            **today_nav_links(),
            "self": ask_page_url(query),
            "api_self": api_ask_page_url(query),
            "watchlist_detail": watchlist_detail_url(code) if watchlist_stock else None,
            "candidate_detail": candidate_detail_url(code) if candidate else None,
        },
    }
    case["surface_version"] = "ask_v2"
    case["conclusion_card"] = build_ask_conclusion_card(case)
    case["boundary_trio"] = build_ask_boundary_trio(case)
    case["execution_layer"] = build_ask_execution_layer(case)
    case["relation_layer"] = build_ask_relation_layer(case)
    case["evidence_layer"] = build_ask_evidence_layer(case, build_ask_followup_shell(case))
    return case


def ask_case_cache_key(value: Any) -> str:
    return str(value or "").strip().lower()


def remember_ask_case_cache(case: dict[str, Any] | None) -> None:
    if not isinstance(case, dict):
        return

    stored_at = datetime.now().timestamp()
    code = str(case.get("code") or "").strip()
    name = str(case.get("name") or "").strip()
    query = str(case.get("query") or "").strip()
    keys = {
        ask_case_cache_key(code),
        ask_case_cache_key(name),
        ask_case_cache_key(query),
        ask_case_cache_key(f"{name} {code}".strip()),
    }
    for key in keys:
        if not key:
            continue
        _ASK_CASE_CACHE[key] = {
            "stored_at": stored_at,
            "case": deepcopy(case),
        }


def load_ask_case_cache(query: str | None) -> dict[str, Any] | None:
    key = ask_case_cache_key(query)
    if not key:
        return None
    item = _ASK_CASE_CACHE.get(key)
    if not item:
        return None
    if datetime.now().timestamp() - float(item.get("stored_at") or 0) > ASK_CASE_CACHE_TTL_SECONDS:
        _ASK_CASE_CACHE.pop(key, None)
        return None
    cached_case = item.get("case")
    if not isinstance(cached_case, dict):
        return None
    return deepcopy(cached_case)


def ask_followup_topic_key(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def ask_followup_intent_from_title(title: str) -> str | None:
    text = str(title or "").strip()
    if "关键位" in text:
        return "levels"
    if "怎么操作" in text or "怎么做" in text:
        return "plan"
    if "主要风险" in text or "风险" in text:
        return "risk"
    if "公告" in text or "新闻" in text:
        return "events"
    if "资金面" in text:
        return "flow"
    if "技术面" in text:
        return "tech"
    if "基本面" in text:
        return "fundamentals"
    if "可靠" in text or "可信" in text:
        return "confidence"
    if "系统里" in text or "位置" in text:
        return "cross"
    if "为什么当前是" in text:
        return "decision"
    return None


def sanitize_ask_followup_history(history: Any, *, limit: int = ASK_FOLLOWUP_HISTORY_LIMIT) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        bullets = text_items(item.get("bullets"))[:4] if isinstance(item.get("bullets"), list) else []
        references = text_items(item.get("references"))[:3] if isinstance(item.get("references"), list) else []
        engine_label = str(item.get("engine_label") or "").strip()
        if not summary and bullets:
            summary = bullets[0]
        if not title and role == "user":
            title = "继续追问"
        if not summary and not title:
            continue
        entries.append(
            {
                "role": role,
                "title": title,
                "summary": summary,
                "bullets": bullets,
                "references": references,
                "engine_label": engine_label,
            }
        )
    if limit <= 0:
        return []
    return entries[-limit:]


def ask_followup_model_config() -> dict[str, Any] | None:
    disabled = str(os.environ.get("PRISM_ASK_FOLLOWUP_DISABLE") or "").strip().lower()
    if disabled in {"1", "true", "yes", "on"}:
        return None

    api_key = first_text(os.environ.get("PRISM_ASK_FOLLOWUP_API_KEY"), os.environ.get("OPENAI_API_KEY"))
    model = first_text(os.environ.get("PRISM_ASK_FOLLOWUP_MODEL"), os.environ.get("OPENAI_MODEL"))
    if not api_key or not model:
        return None

    base_url = first_text(
        os.environ.get("PRISM_ASK_FOLLOWUP_BASE_URL"),
        os.environ.get("OPENAI_BASE_URL"),
        os.environ.get("OPENAI_API_BASE"),
        "https://api.openai.com/v1",
    ) or "https://api.openai.com/v1"
    endpoint = base_url.rstrip("/")
    if endpoint.endswith("/chat/completions"):
        pass
    elif endpoint.endswith("/v1"):
        endpoint = f"{endpoint}/chat/completions"
    elif endpoint.endswith("/chat"):
        endpoint = f"{endpoint}/completions"
    else:
        endpoint = f"{endpoint}/v1/chat/completions"

    timeout_raw = str(os.environ.get("PRISM_ASK_FOLLOWUP_TIMEOUT_SECONDS") or "8").strip()
    try:
        timeout = max(2.0, min(float(timeout_raw), 30.0))
    except ValueError:
        timeout = 8.0

    return {
        "api_key": api_key,
        "model": model,
        "endpoint": endpoint,
        "timeout": timeout,
    }


def ask_followup_engine_badge() -> dict[str, str]:
    if ask_followup_model_config():
        return {
            "label": "模型增强可用",
            "detail": "规则先托底，回答可结合最近几轮追问上下文继续补强。",
            "tone": "positive",
        }
    return {
        "label": "规则托底",
        "detail": "当前先基于页面分析和最近追问上下文回答，后续接入模型时会自动增强。",
        "tone": "watch",
    }


def build_ask_followup_prompt_payload(
    case: dict[str, Any],
    question: str,
    base_answer: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    hero = case.get("hero") or {}
    return {
        "stock": {
            "name": case.get("name"),
            "code": case.get("code"),
            "trade_date": case.get("trade_date"),
            "decision": normalize_ask_followup_copy(hero.get("decision_label")),
            "position": normalize_position_guidance(hero.get("position")),
            "confidence": hero.get("confidence_label"),
            "confidence_note": normalize_ask_followup_copy(hero.get("confidence_note")),
            "summary": normalize_ask_followup_copy(hero.get("summary")),
            "context_tags": list(case.get("context_tags") or [])[:6],
        },
        "metrics": [
            {"label": item.get("label"), "value": normalize_ask_followup_copy(item.get("value")), "detail": normalize_ask_followup_copy(item.get("detail"))}
            for item in (case.get("metric_cards") or [])[:4]
        ],
        "levels": [
            {"label": item.get("label"), "value": normalize_ask_followup_copy(item.get("value")), "detail": normalize_ask_followup_copy(item.get("detail"))}
            for item in (case.get("level_cards") or [])[:4]
        ],
        "plan": [
            {"label": item.get("label"), "value": normalize_ask_followup_copy(item.get("value"))}
            for item in (case.get("plan_rows") or [])[:5]
        ],
        "analysis": [
            {
                "title": item.get("title"),
                "metric": normalize_ask_followup_copy(item.get("metric")),
                "items": [normalize_ask_followup_copy(entry) for entry in list(item.get("items") or [])[:4]],
            }
            for item in (case.get("analysis_groups") or [])[:6]
        ],
        "events": [
            {
                "title": item.get("title"),
                "items": [
                    normalize_ask_followup_copy(f"{entry.get('title')} | {entry.get('meta')}")
                    for entry in (item.get("items") or [])[:3]
                ],
            }
            for item in (case.get("event_groups") or [])[:2]
        ],
        "cross_cards": [
            {"label": item.get("label"), "value": normalize_ask_followup_copy(item.get("value")), "detail": normalize_ask_followup_copy(item.get("detail"))}
            for item in (case.get("cross_cards") or [])[:4]
        ],
        "history": history,
        "question": question,
        "rule_answer": {
            "intent": base_answer.get("intent"),
            "title": normalize_ask_followup_copy(base_answer.get("title")),
            "summary": normalize_ask_followup_copy(base_answer.get("summary")),
            "bullets": [normalize_ask_followup_copy(item) for item in list(base_answer.get("bullets") or [])[:6]],
            "references": [normalize_ask_followup_copy(item) for item in list(base_answer.get("references") or [])[:6]],
            "followups": list(base_answer.get("followups") or [])[:3],
        },
    }


def extract_first_json_object(text: str) -> dict[str, Any] | None:
    stripped = str(text or "").strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        return payload

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def normalize_ask_followup_llm_answer(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    title = normalize_ask_followup_copy(payload.get("title"))
    summary = normalize_ask_followup_copy(payload.get("summary"))
    bullets = [normalize_ask_followup_copy(item) for item in text_items(payload.get("bullets"))[:6]] if isinstance(payload.get("bullets"), list) else []
    references = [normalize_ask_followup_copy(item) for item in text_items(payload.get("references"))[:3]] if isinstance(payload.get("references"), list) else []
    followups = text_items(payload.get("followups"))[:3] if isinstance(payload.get("followups"), list) else []
    if not summary and not bullets:
        return None
    return {
        "title": title,
        "summary": summary,
        "bullets": bullets,
        "references": references,
        "followups": followups,
    }


def ask_followup_llm_text_content(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        chunks: list[str] = []
        for item in message:
            if isinstance(item, dict):
                item_type = str(item.get("type") or "").strip()
                if item_type in {"text", "output_text"}:
                    text = str(item.get("text") or "").strip()
                    if text:
                        chunks.append(text)
        return "\n".join(chunks).strip()
    return ""


def ask_followup_enhancement_from_model(
    case: dict[str, Any],
    question: str,
    base_answer: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any] | None:
    config = ask_followup_model_config()
    if not config:
        return None

    prompt_payload = build_ask_followup_prompt_payload(case, question, base_answer, history)
    request_body = {
        "model": config["model"],
        "temperature": 0.2,
        "max_tokens": 420,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是棱镜 Prism 的问股追问增强器。"
                    "只能基于提供的 JSON 上下文回答，不能引入外部事实、不能编造公告和价格。"
                    "你的任务是补强规则答案，而不是推翻已有结论。"
                    "必须保留原有纪律口径、仓位参考和风险边界。"
                    "不能输出强投资建议、目标价、收益预测、买入建议、开仓建议或收益承诺。"
                    "涉及动作时只能表述为等待触发、按纪律处理、小仓位验证或风险优先。"
                    "输出纯 JSON 对象，不要 Markdown，不要额外解释。"
                    '字段格式：{"title":"可选","summary":"必填","bullets":["..."],"references":["..."],"followups":["..."]}。'
                    "summary 控制在 2 句话内；bullets 3-5 条；followups 2-3 条。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt_payload, ensure_ascii=False, separators=(",", ":")),
            },
        ],
    }
    try:
        payload, _, _, _ = request_json_http(
            "POST",
            config["endpoint"],
            json_body=request_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config['api_key']}",
            },
            timeout=float(config["timeout"]),
            retries=0,
        )
    except (RuntimeError, json.JSONDecodeError, OSError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices") or []
    if not isinstance(choices, list) or not choices:
        return None
    message = (choices[0] or {}).get("message") or {}
    content = ask_followup_llm_text_content(message.get("content"))
    if not content:
        return None
    return normalize_ask_followup_llm_answer(extract_first_json_object(content))


def merge_ask_followup_answer(
    base_answer: dict[str, Any],
    enhancement: dict[str, Any] | None,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    answer = deepcopy(base_answer)
    if enhancement:
        title = str(enhancement.get("title") or "").strip()
        if title:
            answer["title"] = title
        if enhancement.get("summary"):
            answer["summary"] = enhancement["summary"]
        if enhancement.get("bullets"):
            answer["bullets"] = list(enhancement.get("bullets") or [])[:6]
        merged_refs = ask_followup_references(
            {},
            list(base_answer.get("references") or []) + list(enhancement.get("references") or []),
        )
        if merged_refs:
            answer["references"] = merged_refs
        if enhancement.get("followups"):
            answer["followups"] = list(enhancement.get("followups") or [])[:3]
        answer["engine"] = "hybrid"
        answer["engine_label"] = "规则托底 + 模型增强"
        answer["engine_note"] = "先按当前页分析托底，再结合最近几轮追问做补强表述。"
    else:
        answer["engine"] = "rule"
        answer["engine_label"] = "规则托底"
        answer["engine_note"] = "当前基于页面分析和最近几轮追问直接回答。"
    answer["history_used"] = len(history)
    return normalize_ask_followup_answer(answer)


def normalize_ask_followup_answer(answer: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(answer)
    for key in ("title", "summary", "engine_note"):
        if key in normalized:
            normalized[key] = normalize_ask_followup_copy(normalized.get(key))
    if isinstance(normalized.get("bullets"), list):
        normalized["bullets"] = [
            text
            for text in (normalize_ask_followup_copy(item) for item in normalized["bullets"])
            if text
        ][:6]
    if isinstance(normalized.get("references"), list):
        normalized["references"] = ask_followup_references(
            {},
            [normalize_ask_followup_copy(item) for item in normalized["references"]],
        )
    if isinstance(normalized.get("followups"), list):
        normalized["followups"] = [
            text
            for text in (normalize_ask_followup_copy(item) for item in normalized["followups"])
            if text
        ][:3]
    return normalized


def ask_find_analysis_group(case: dict[str, Any], title: str) -> dict[str, Any] | None:
    for group in case.get("analysis_groups") or []:
        if str(group.get("title") or "").strip() == title:
            return group
    return None


def ask_find_cross_card(case: dict[str, Any], label: str) -> dict[str, Any] | None:
    for item in case.get("cross_cards") or []:
        if str(item.get("label") or "").strip() == label:
            return item
    return None


def ask_followup_presets(case: dict[str, Any]) -> list[dict[str, str]]:
    presets = [
        {"label": "为什么这样判断", "question": "为什么当前是这个结论？"},
        {"label": "今天怎么做", "question": "今天怎么按纪律处理更合适？"},
        {"label": "关键位", "question": "支撑位、压力位和止损位怎么看？"},
        {"label": "主要风险", "question": "这只股票现在最主要的风险是什么？"},
        {"label": "公告新闻", "question": "最近公告和新闻里有什么值得注意？"},
    ]
    if str(((case.get("watchlist_action") or {}).get("kind") or "")).strip() in {"add", "restore"}:
        presets.append({"label": "要不要进自选", "question": "现在适合加入自选股吗？"})
    return presets


def detect_ask_followup_intent(question: str, history: list[dict[str, Any]] | None = None) -> str:
    text = str(question or "").strip().lower()
    if any(token in text for token in ("支撑", "压力", "止损", "关键位", "价位", "位置")):
        return "levels"
    if any(token in text for token in ("怎么操作", "怎么做", "怎么办", "执行", "仓位", "买还是卖", "该怎么", "高开", "低开", "冲高", "回落", "跌破", "破位")):
        return "plan"
    if any(token in text for token in ("风险", "回避", "失效", "注意", "担心", "雷")):
        return "risk"
    if any(token in text for token in ("公告", "新闻", "事件", "催化", "消息")):
        return "events"
    if any(token in text for token in ("资金", "主力", "流入", "流出")):
        return "flow"
    if any(token in text for token in ("技术", "趋势", "均线", "突破", "形态", "评分")):
        return "tech"
    if any(token in text for token in ("基本面", "估值", "pe", "pb", "roe", "市值")):
        return "fundamentals"
    if any(token in text for token in ("可信", "置信", "靠谱吗", "数据完整", "完整")):
        return "confidence"
    if any(token in text for token in ("自选股", "观察池", "机会池", "午盘", "执行队列", "链路", "系统里")):
        return "cross"
    for item in reversed(history or []):
        if str(item.get("role") or "").strip() != "assistant":
            continue
        mapped = ask_followup_intent_from_title(str(item.get("title") or ""))
        if mapped:
            return mapped
    return "decision"


def ask_followup_references(case: dict[str, Any], items: list[str]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        refs.append(text)
    return refs[:6]


def build_ask_followup_answer(
    case: dict[str, Any],
    question: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hero = case.get("hero") or {}
    watchlist_action = case.get("watchlist_action") or {}
    plan_rows = case.get("plan_rows") or []
    plan_levels = case.get("plan_levels") or []
    level_cards = case.get("level_cards") or []
    event_groups = case.get("event_groups") or []
    cross_cards = case.get("cross_cards") or []
    context_tags = case.get("context_tags") or []

    def level_value(label: str) -> str:
        for item in level_cards:
            if str(item.get("label") or "").strip() == label:
                return str(item.get("value") or "-").strip() or "-"
        return "-"

    def row_value(label: str) -> str:
        for item in plan_rows:
            if str(item.get("label") or "").strip() == label:
                return str(item.get("value") or "-").strip() or "-"
        return "-"

    sanitized_history = sanitize_ask_followup_history(history)
    intent = detect_ask_followup_intent(question, sanitized_history)
    tone = str(case.get("tone") or "watch")
    title = "继续拆这只股票"
    summary = str(hero.get("summary") or "继续围绕当前结论拆问题。").strip()
    bullets: list[str] = []
    references: list[str] = []

    if intent == "levels":
        support = level_value("支撑位")
        resistance = level_value("压力位")
        stop_loss = level_value("止损位")
        title = "关键位怎么看"
        summary = f"当前先盯支撑 {support}、压力 {resistance}、止损 {stop_loss}，这三档基本决定今天还能不能继续拿。"
        bullets = [
            f"{item.get('label')}：{item.get('value')}；{item.get('detail')}"
            for item in level_cards
            if item.get("value")
        ]
        bullets.extend(
            [
                f"{item.get('label')}：{item.get('value')}"
                for item in plan_levels
                if str(item.get("value") or "").strip() not in {"", "-"}
            ]
        )
        references = ask_followup_references(case, [f"仓位参考 {hero.get('position')}", f"当前结论 {hero.get('decision_label')}"])
    elif intent == "plan":
        title = "今天怎么按纪律处理"
        summary = f"当前更像是按“{normalize_ask_followup_copy(row_value('动作'))}”去处理，先看触发，再看回避和失效，不要把盘中噪音当成新结论。"
        bullets = [
            f"{item.get('label')}：{normalize_ask_followup_copy(item.get('value'))}"
            for item in plan_rows
            if str(item.get("value") or "").strip()
        ]
        references = ask_followup_references(case, [f"仓位参考 {hero.get('position')}"] + [f"{item.get('label')} {normalize_ask_followup_copy(item.get('value'))}" for item in plan_levels])
    elif intent == "risk":
        risk_group = ask_find_analysis_group(case, "风险") or {}
        title = "主要风险在哪"
        summary = first_text(*(risk_group.get("items") or []), hero.get("summary")) or "当前没有额外风险提示。"
        bullets = list(risk_group.get("items") or [])[:5] or ["当前没有额外风险提示。"]
        references = ask_followup_references(case, [f"止损位 {level_value('止损位')}", f"当前结论 {hero.get('decision_label')}"])
    elif intent == "events":
        title = "公告和新闻怎么看"
        ann_group = event_groups[0] if len(event_groups) > 0 else {"items": []}
        news_group = event_groups[1] if len(event_groups) > 1 else {"items": []}
        summary = f"当前抓到公告 {len(ann_group.get('items') or [])} 条、新闻 {len(news_group.get('items') or [])} 条，先看会不会直接改动作。"
        bullets = [
            f"{item.get('title')} | {item.get('meta')}"
            for group in (ann_group, news_group)
            for item in (group.get("items") or [])[:3]
        ] or ["当前没有抓到新的公告或新闻。"]
        references = ask_followup_references(case, [f"事件标签 {' / '.join(context_tags)}"])
    elif intent == "flow":
        group = ask_find_analysis_group(case, "资金面") or {}
        title = "资金面怎么看"
        summary = first_text(*(group.get("items") or []), hero.get("summary")) or "当前没有足够的资金线索。"
        bullets = list(group.get("items") or [])[:5] or ["当前没有足够的资金线索。"]
        references = ask_followup_references(case, [f"资金信号 {(case.get('metric_cards') or [{}, {}, {}, {}])[3].get('value') if len(case.get('metric_cards') or []) >= 4 else '-'}"])
    elif intent == "tech":
        group = ask_find_analysis_group(case, "技术面") or {}
        title = "技术面怎么看"
        summary = first_text(*(group.get("items") or []), hero.get("summary")) or "当前技术证据还不够完整。"
        bullets = list(group.get("items") or [])[:5] or ["当前技术证据还不够完整。"]
        references = ask_followup_references(case, [f"规则分 {(case.get('metric_cards') or [{}, {}, {}, {}])[2].get('value') if len(case.get('metric_cards') or []) >= 3 else '-'}"])
    elif intent == "fundamentals":
        group = ask_find_analysis_group(case, "基本面") or {}
        title = "基本面怎么看"
        summary = first_text(*(group.get("items") or []), "先看估值和盈利质量，再决定这票值不值得更长拿。")
        bullets = list(group.get("items") or [])[:5] or ["当前基本面数据还不完整。"]
        references = ask_followup_references(case, [f"当前结论 {hero.get('decision_label')}"])
    elif intent == "confidence":
        title = "这个结论有多可靠"
        summary = f"当前是 {hero.get('confidence_label')} 可信度，原因是 {hero.get('confidence_note')}。"
        bullets = [
            f"可信度：{hero.get('confidence_label')}",
            f"说明：{hero.get('confidence_note')}",
            f"上下文标签：{' / '.join(context_tags) if context_tags else '仅临时分析'}",
        ]
        references = ask_followup_references(case, [f"当前结论 {hero.get('decision_label')}", f"仓位参考 {hero.get('position')}"])
    elif intent == "cross":
        title = "这只票在系统里的位置"
        summary = "先看它是不是已进入自选股、观察池、午盘确认或今日动作队列，再决定优先级。"
        bullets = [
            f"{item.get('label')}：{item.get('value')}；{item.get('detail')}"
            for item in cross_cards
        ]
        references = ask_followup_references(case, [f"自选股动作 {watchlist_action.get('label')}"])
    else:
        tech_group = ask_find_analysis_group(case, "技术面") or {}
        flow_group = ask_find_analysis_group(case, "资金面") or {}
        risk_group = ask_find_analysis_group(case, "风险") or {}
        title = f"为什么当前是 {hero.get('decision_label')}"
        summary = f"当前统一结论是 {hero.get('decision_label')}，核心原因还是 {str(hero.get('summary') or '当前结论来自多维度合并判断。').strip()}。"
        bullets = [
            f"纪律与仓位：{hero.get('decision_label')}；仓位参考 {hero.get('position')}",
            f"技术面：{first_text(*(tech_group.get('items') or []), tech_group.get('metric')) or '暂无明确技术线索'}",
            f"资金面：{first_text(*(flow_group.get('items') or []), flow_group.get('metric')) or '暂无明确资金线索'}",
            f"风险面：{first_text(*(risk_group.get('items') or []), '当前没有额外风险提示。')}",
        ]
        references = ask_followup_references(case, [f"可信度 {hero.get('confidence_label')}", f"上下文 {' / '.join(context_tags)}"])

    asked_questions = {
        ask_followup_topic_key(question),
        *(
            ask_followup_topic_key(item.get("summary"))
            for item in sanitized_history
            if str(item.get("role") or "").strip() == "user"
        ),
    }
    followups = [
        item["question"]
        for item in ask_followup_presets(case)
        if item.get("question") and ask_followup_topic_key(item.get("question")) not in asked_questions
    ][:3]

    return {
        "intent": intent,
        "title": title,
        "summary": summary,
        "bullets": bullets[:6],
        "references": references,
        "tone": tone,
        "followups": followups,
    }


def build_ask_followup_view(question: str, query: str, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    question_text = str(question or "").strip()
    query_text = str(query or "").strip()
    if not query_text:
        raise ValueError("缺少当前股票代码或查询词")
    if not question_text:
        raise ValueError("请输入你想继续追问的问题")
    sanitized_history = sanitize_ask_followup_history(history)

    cached_case = load_ask_case_cache(query_text)
    if cached_case:
        case = cached_case
    else:
        trade_date_hint = expected_trade_date()
        watchlist = safe_canonical_load(load_watchlist_snapshot, trade_date=trade_date_hint)
        screening_batch = safe_canonical_load(load_screening_batch, trade_date=trade_date_hint)
        confirmation = safe_canonical_load(load_confirmation, trade_date=trade_date_hint)
        case = build_ask_case_view(query_text, watchlist, screening_batch, confirmation)
        remember_ask_case_cache(case)

    base_answer = build_ask_followup_answer(case, question_text, sanitized_history)
    enhancement = ask_followup_enhancement_from_model(case, question_text, base_answer, sanitized_history)
    answer = merge_ask_followup_answer(base_answer, enhancement, sanitized_history)
    return {
        "query": query_text,
        "question": question_text,
        "code": case.get("code"),
        "name": case.get("name"),
        "hero_title": (case.get("hero") or {}).get("title"),
        "history_used": len(sanitized_history),
        "answer": answer,
    }


def build_ask_followup_shell(case: dict[str, Any] | None) -> dict[str, Any] | None:
    if not case:
        return None
    engine_badge = ask_followup_engine_badge()
    return {
        "api": api_ask_followup_url(),
        "query": str(case.get("code") or case.get("query") or "").strip(),
        "presets": ask_followup_presets(case),
        "starter": {
            "title": "继续追问这只股票",
            "summary": "可以继续问为什么这样判断、今天怎么执行、关键位怎么看；系统会先用当前页结论托底，再带上最近几轮追问继续回答。",
        },
        "engine_badge": engine_badge,
        "hint": engine_badge.get("detail") or "先问最想确认的一件事，页面会连续追加回答。",
    }


def build_ask_explanation_block(case: dict[str, Any] | None) -> dict[str, str]:
    if not case:
        return {"why": "", "risk": "", "invalid": ""}

    hero = case.get("hero") or {}
    plan_rows = list(case.get("plan_rows") or [])
    risk_row = next((item for item in plan_rows if item.get("label") == "回避"), None)
    invalid_row = next((item for item in plan_rows if item.get("label") == "失效"), None)

    return build_decision_explanation_block(
        why=hero.get("summary"),
        risk=(risk_row or {}).get("value"),
        invalid=(invalid_row or {}).get("value") or hero.get("confidence_note"),
    )


def build_decision_explanation_block(*, why: Any, risk: Any, invalid: Any) -> dict[str, str]:
    return {
        "why": str(detail_value(why, "先看当前结论背后的核心理由。"))
        .strip(),
        "risk": str(detail_value(risk, "满足这些条件前，先不要放大动作。"))
        .strip(),
        "invalid": str(detail_value(invalid, "一旦触发这类条件，先停下来，不继续原计划。"))
        .strip(),
    }


def build_detail_explanation_block(*, why: Any, risk: Any, invalid: Any) -> dict[str, str]:
    return build_decision_explanation_block(why=why, risk=risk, invalid=invalid)


def build_execution_loop(
    *,
    action_now: Any,
    action_detail: Any,
    why_now: Any,
    why_detail: Any,
    trigger: Any,
    trigger_detail: Any,
    avoid: Any,
    avoid_detail: Any,
    evidence: Any,
    evidence_detail: Any,
) -> list[dict[str, str]]:
    items = [
        {
            "label": "现在做什么",
            "value": normalize_next_step_sentence(action_now, "先按当前动作执行。"),
            "detail": detail_value(action_detail, "先按当前动作执行，不额外放大。"),
        },
        {
            "label": "为什么先做这一步",
            "value": detail_value(why_now),
            "detail": detail_value(why_detail, "先用最直接的理由判断动作优先级。"),
        },
        {
            "label": "触发条件",
            "value": normalize_trigger_sentence(trigger, "先等触发条件明确，再决定下一步动作。"),
            "detail": detail_value(trigger_detail, "满足触发条件后，再升级下一步动作。"),
        },
        {
            "label": "先不要做什么",
            "value": normalize_avoid_sentence(avoid, "先不要做超出纪律边界的动作。"),
            "detail": detail_value(avoid_detail, "先避开最容易出错的动作。"),
        },
        {
            "label": "去哪看证据",
            "value": detail_value(evidence),
            "detail": detail_value(evidence_detail, "需要复核时直接回到对应证据入口。"),
        },
    ]
    for item in items:
        tier_key = infer_action_tier(action=item.get("value"), status=item.get("label"), tone=None)
        item["tier_key"] = tier_key
        item["tier"] = action_tier_label(tier_key)
    return items


def build_detail_decision_cards(
    *,
    conclusion: Any,
    conclusion_detail: Any,
    position: Any,
    position_detail: Any,
    risk_boundary: Any,
    risk_detail: Any,
    next_step: Any,
    next_step_detail: Any,
) -> list[dict[str, str]]:
    return [
        {
            "label": "当前结论",
            "value": normalize_main_conclusion(conclusion),
            "detail": normalize_stock_result_copy(conclusion_detail, "等待更多确认后再行动。"),
        },
        {
            "label": "仓位建议",
            "value": normalize_position_guidance(position),
            "detail": normalize_stock_result_copy(position_detail, "结合当前结论控制仓位。"),
        },
        {
            "label": "风险边界",
            "value": normalize_stock_result_copy(risk_boundary),
            "detail": normalize_stock_result_copy(risk_detail, "风险边界暂未明确，保持谨慎。"),
        },
        {
            "label": "下一步动作",
            "value": normalize_next_step_sentence(next_step, "先处理当前最靠前的一步。"),
            "detail": normalize_stock_result_copy(next_step_detail, "先处理当前最靠前的一步。"),
        },
    ]


def build_reading_compass_cards(
    *,
    conclusion: Any,
    conclusion_detail: Any,
    conclusion_label: str = "当前结论",
    conclusion_default_detail: str = "先读当前主结论，再决定是否展开。",
    action_focus: Any,
    action_detail: Any,
    risk_boundary: Any,
    risk_detail: Any,
    evidence_entry: Any,
    evidence_detail: Any,
) -> list[dict[str, str]]:
    return [
        {
            "label": conclusion_label,
            "value": detail_value(conclusion),
            "detail": detail_value(conclusion_detail, conclusion_default_detail),
        },
        {
            "label": "动作重点",
            "value": detail_value(action_focus),
            "detail": detail_value(action_detail, "把注意力先放在最先要处理的动作上。"),
        },
        {
            "label": "风险边界",
            "value": detail_value(risk_boundary),
            "detail": detail_value(risk_detail, "出现这类信号时，先收手再判断。"),
        },
        {
            "label": "证据入口",
            "value": detail_value(evidence_entry),
            "detail": detail_value(evidence_detail, "需要核对时直接回到对应证据层。"),
        },
    ]


def build_ask_conclusion_card(case: dict[str, Any]) -> dict[str, Any]:
    canonical = case.get("canonical_decision") or {}
    hero = case.get("hero") or {}
    return {
        "eyebrow": "现在该怎么做",
        "verdict": canonical.get("main_conclusion") or "观察",
        "action_sentence": canonical.get("next_step") or hero.get("summary") or "先观察，不着急动。",
        "confidence_label": hero.get("confidence_label") or "待核",
        "confidence_note": hero.get("confidence_note") or "当前先按已有证据理解。",
        "meta_pills": [
            {"label": "仓位建议", "value": canonical.get("position_guidance") or "仓位待定"},
            {"label": "风险边界", "value": canonical.get("risk_boundary") or "边界待核"},
            {"label": "系统位置", "value": source_scope_label(canonical.get("source_scope"))},
        ],
    }



def build_ask_boundary_trio(case: dict[str, Any]) -> list[dict[str, str]]:
    canonical = case.get("canonical_decision") or {}
    return [
        {
            "key": "why_now",
            "label": "为什么这么判断",
            "title": "当前成立的核心理由",
            "body": str(canonical.get("why_now") or "先按当前主结论理解这只票。").strip(),
        },
        {
            "key": "continue_condition",
            "label": "继续成立的条件",
            "title": "满足这些条件再继续",
            "body": str(canonical.get("continue_condition") or "条件未满足前，先不升级动作。").strip(),
        },
        {
            "key": "stop_condition",
            "label": "一票否决条件",
            "title": "一旦出现就先停",
            "body": str(canonical.get("stop_condition") or "触发后先停止原计划。").strip(),
        },
    ]



def build_ask_execution_layer(case: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = {"现在做什么", "先不要做什么", "去哪看证据"}
    return [item for item in (case.get("execution_loop") or []) if item.get("label") in allowed]



def build_ask_relation_layer(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "这只票和系统里的关系",
        "cards": list(case.get("cross_cards") or [])[:4],
        "watchlist_action": case.get("watchlist_action") or {},
    }



def build_ask_evidence_layer(case: dict[str, Any], followup: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "title": "证据与继续追问",
        "metric_cards": list(case.get("metric_cards") or [])[:4],
        "level_cards": list(case.get("level_cards") or [])[:4],
        "analysis_groups": list(case.get("analysis_groups") or [])[:6],
        "event_groups": list(case.get("event_groups") or [])[:2],
        "artifacts": list(case.get("artifacts") or [])[:4],
        "followup": followup,
    }


def build_ask_examples(
    watchlist: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_item(code: str | None, name: str | None, tag: str) -> None:
        normalized = str(code or "").strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        examples.append(
            {
                "code": normalized,
                "name": str(name or normalized).strip() or normalized,
                "tag": tag,
                "url": ask_page_url(normalized),
            }
        )

    for item in (watchlist or {}).get("stocks") or []:
        add_item(item.get("code"), item.get("name"), "自选股")
        if len(examples) >= 4:
            break
    for item in (screening_batch or {}).get("candidates") or []:
        add_item(item.get("code"), item.get("name"), "观察池")
        if len(examples) >= 8:
            break
    for item in (confirmation or {}).get("fresh_candidates") or []:
        add_item(item.get("code"), item.get("name"), "午盘新增")
        if len(examples) >= 10:
            break
    return examples[:10]


def build_ask_recent_queries(
    watchlist: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    if watchlist is None and screening_batch is None and confirmation is None:
        trade_date_hint = expected_trade_date()
        watchlist = safe_canonical_load(load_watchlist_snapshot, trade_date=trade_date_hint)
        screening_batch = safe_canonical_load(load_screening_batch, trade_date=trade_date_hint)
        confirmation = safe_canonical_load(load_confirmation, trade_date=trade_date_hint)

    catalog = build_stock_catalog(watchlist, screening_batch, confirmation)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for entry in reversed(load_ask_recent_store().get("items") or []):
        code = str(entry.get("code") or "").strip()
        if code in seen or not re.fullmatch(r"\d{6}", code):
            continue
        seen.add(code)

        catalog_item = dict(catalog.get(code) or {})
        name = first_text(catalog_item.get("name"), entry.get("name"), code) or code
        source_tag = ask_catalog_source_tag(catalog_item) if catalog_item else "最近问过"
        detail_parts = [code]
        if source_tag and source_tag != "系统已知":
            detail_parts.append(source_tag)
        updated_at = fmt_dt(entry.get("updated_at"))
        if updated_at != "-":
            detail_parts.append(updated_at)

        items.append(
            {
                "code": code,
                "name": name,
                "tag": "最近问过",
                "detail": " · ".join(detail_parts),
                "url": ask_page_url(code),
                "fill_value": ask_search_fill_value(name, code),
            }
        )
        if len(items) >= limit:
            break

    return items[:limit]


def build_ask_suggestions(
    query: str | None,
    watchlist: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    if watchlist is None and screening_batch is None and confirmation is None:
        trade_date_hint = expected_trade_date()
        watchlist = safe_canonical_load(load_watchlist_snapshot, trade_date=trade_date_hint)
        screening_batch = safe_canonical_load(load_screening_batch, trade_date=trade_date_hint)
        confirmation = safe_canonical_load(load_confirmation, trade_date=trade_date_hint)

    query_text = str(query or "").strip()
    recent_queries = build_ask_recent_queries(watchlist, screening_batch, confirmation, limit=limit)
    if not query_text:
        items = list(recent_queries)
        seen = {item["code"] for item in items}
        for example in build_ask_examples(watchlist, screening_batch, confirmation):
            code = str(example.get("code") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            items.append(
                {
                    "code": code,
                    "name": str(example.get("name") or code).strip() or code,
                    "tag": str(example.get("tag") or "系统样例").strip() or "系统样例",
                    "detail": f"{code} · 可快速带入",
                    "url": ask_page_url(code),
                    "fill_value": ask_search_fill_value(example.get("name"), code),
                }
            )
            if len(items) >= limit:
                break
        return items[:limit]

    catalog = build_stock_catalog(watchlist, screening_batch, confirmation)
    if query_text and not re.fullmatch(r"\d{6}", query_text):
        for item in search_sina_stock_suggestions(query_text, limit=limit):
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            current = catalog.setdefault(
                code,
                {
                    "code": code,
                    "name": code,
                    "market": infer_market_from_code(code),
                    "sina": infer_sina_code(code),
                    "sources": [],
                },
            )
            if item.get("name") and current.get("name") in {"", code}:
                current["name"] = item["name"]
            for field in ("market", "sina", "source"):
                value = item.get(field)
                if value and not current.get(field):
                    current[field] = value
            if "full_market_search" not in current["sources"]:
                current["sources"].append("full_market_search")

    lowered = query_text.lower()
    recent_rank = {
        str(item.get("code") or "").strip(): index
        for index, item in enumerate(reversed(load_ask_recent_store().get("items") or []))
        if str(item.get("code") or "").strip()
    }

    scored: list[tuple[int, int, int, str, str, dict[str, Any]]] = []
    for code, item in catalog.items():
        name = str(item.get("name") or code).strip() or code
        name_lower = name.lower()
        if code == query_text:
            score = 0
        elif code.startswith(query_text):
            score = 1
        elif name_lower == lowered:
            score = 2
        elif name_lower.startswith(lowered):
            score = 3
        elif lowered in name_lower:
            score = 4
        elif query_text in code:
            score = 5
        else:
            continue

        scored.append(
            (
                score,
                ask_catalog_priority(item),
                recent_rank.get(code, 999),
                name,
                code,
                item,
            )
        )

    scored.sort(key=lambda entry: (entry[0], entry[1], entry[2], entry[3], entry[4]))

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, _, _, name, code, item in scored:
        if code in seen:
            continue
        seen.add(code)
        source_tag = ask_catalog_source_tag(item)
        detail_parts = [code]
        if source_tag:
            detail_parts.append(source_tag)
        if code in recent_rank:
            detail_parts.append("最近问过")

        items.append(
            {
                "code": code,
                "name": name,
                "tag": source_tag,
                "detail": " · ".join(detail_parts),
                "url": ask_page_url(code),
                "fill_value": ask_search_fill_value(name, code),
            }
        )
        if len(items) >= limit:
            break

    if items:
        return items[:limit]

    for item in recent_queries:
        haystack = " ".join(
            [
                str(item.get("code") or "").strip(),
                str(item.get("name") or "").strip().lower(),
                str(item.get("fill_value") or "").strip().lower(),
            ]
        )
        if lowered not in haystack:
            continue
        items.append(item)
        if len(items) >= limit:
            break

    return items[:limit]


def build_ask_page_view(query: str | None = None, error: str | None = None) -> dict[str, Any]:
    trade_date_hint = expected_trade_date()
    watchlist = safe_canonical_load(load_watchlist_snapshot, trade_date=trade_date_hint)
    screening_batch = safe_canonical_load(load_screening_batch, trade_date=trade_date_hint)
    confirmation = safe_canonical_load(load_confirmation, trade_date=trade_date_hint)
    query_text = str(query or "").strip()
    ask_case = None
    ask_error = error
    if query_text and not ask_error:
        ask_case = build_ask_case_view(query_text, watchlist, screening_batch, confirmation)
        remember_ask_case_cache(ask_case)
        remember_ask_query(
            code=str(ask_case.get("code") or "").strip(),
            name=str(ask_case.get("name") or "").strip(),
            query=query_text,
            query_mode=str(ask_case.get("query_mode") or "code").strip(),
        )

    links = {
        **today_nav_links(),
        "self": ask_page_url(query_text or None),
        "api_self": api_ask_page_url(query_text or None),
        "suggest_api": api_ask_suggest_url(),
        "followup_api": api_ask_followup_url(),
    }
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "query": query_text,
        "error": ask_error,
        "surface_mode": "result" if ask_case else "empty",
        "search_strip": {
            "title": "先给这只股票一个主结论，再展开原因",
            "promise": "先给结论，再给下一步",
            "is_compact": bool(ask_case),
            "hint": "支持代码/名称联想，候选项会优先回填便于继续查看的查询值。",
        },
        "hero": {
            "title": "先给这只股票一个主结论，再展开原因",
            "summary": "这页先回答这只股票现在该不该动，再把技术、资金、事件和跨系统状态拆开给你看。",
        },
        "examples": build_ask_examples(watchlist, screening_batch, confirmation),
        "recent_queries": build_ask_recent_queries(watchlist, screening_batch, confirmation),
        "case": ask_case,
        "decision_explanation": build_ask_explanation_block(ask_case),
        "followup": build_ask_followup_shell(ask_case),
        "links": links,
        "action_tier_legend": build_action_tier_legend(),
        "manager": {
            "add_api": "/api/watchlist/manage/add",
            "restore_api": "/api/watchlist/manage/restore",
            "watchlist_url": watchlist_page_url(),
        },
    }


def lane_quality_card(title: str, quality: dict[str, Any] | None) -> dict[str, Any]:
    status = (quality or {}).get("validation_status") or "unknown"
    tone = quality_status_tone(status)
    return {
        "title": title,
        "status": status,
        "tone": tone,
        "checked_at": (quality or {}).get("checked_at") or "-",
        "expected_timestamp": (quality or {}).get("expected_timestamp") or "-",
        "issue": ((quality or {}).get("errors") or [None])[0]
        or ((quality or {}).get("warnings") or [None])[0]
        or "当前没有质检异常",
        "path": (quality or {}).get("path") or "",
        "url": artifact_url((quality or {}).get("path")),
    }


def quality_status_tone(status: Any) -> str:
    normalized = str(status or "unknown").strip().lower()
    if normalized == "ok":
        return "positive"
    if normalized in {"blocked", "failed", "invalid"}:
        return "risk"
    return "watch"


def quality_status_label(status: Any) -> str:
    normalized = str(status or "unknown").strip().lower()
    return {
        "ok": "就绪",
        "blocked": "拦截",
        "failed": "失败",
        "invalid": "无效",
        "unknown": "待核",
        "stale": "过期",
        "warning": "警告",
    }.get(normalized, normalized or "待核")


def tone_priority(tone: str) -> int:
    return {"positive": 0, "watch": 1, "risk": 2}.get(tone, 1)


def build_confidence_metric(label: str, value: Any, detail: str | None = None) -> dict[str, Any]:
    return {
        "label": detail_value(label, "-"),
        "value": detail_value(value, "-"),
        "detail": detail_value(detail, "") if detail else "",
    }


def build_confidence_action(title: str, url: str | None, *, external: bool = False) -> dict[str, Any] | None:
    if not url:
        return None
    return {
        "title": title,
        "url": url,
        "external": external,
    }


def build_confidence_switch(
    *,
    status: str,
    label: str,
    tone: str,
    summary: str,
    note: str | None = None,
    metrics: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    return {
        "title": "可信度总开关",
        "status": detail_value(status, "待核"),
        "label": detail_value(label, "先看一眼"),
        "tone": tone or "watch",
        "summary": detail_value(summary, "先看这页现在能不能支撑今天动作。"),
        "note": detail_value(note, ""),
        "metrics": [item for item in (metrics or []) if item],
        "actions": [item for item in (actions or []) if item and item.get("url")],
    }


def first_issue_quality_url(*qualities: dict[str, Any] | None) -> str | None:
    for quality in qualities:
        status = (quality or {}).get("validation_status") or "unknown"
        if quality_status_tone(status) == "positive":
            continue
        url = artifact_url((quality or {}).get("path"))
        if url:
            return url
    return None


def build_today_confidence_switch(
    decision_brief: dict[str, Any] | None,
    quality_status: dict[str, Any] | None,
    *,
    brief_is_live: bool,
    gate: dict[str, Any] | None,
    links: dict[str, Any],
) -> dict[str, Any]:
    brief_trade_date = detail_value((decision_brief or {}).get("trade_date"), "未生成")
    lanes = (quality_status or {}).get("lanes") or {}
    lane_defs = [
        ("watchlist", "自选股"),
        ("aggressive", "早盘"),
        ("midday_confirmation", "午盘"),
    ]
    lane_states = [
        {
            "key": key,
            "title": title,
            "status": (lanes.get(key) or {}).get("validation_status") or "unknown",
        }
        for key, title in lane_defs
    ]
    risk_titles = [item["title"] for item in lane_states if quality_status_tone(item["status"]) == "risk"]
    watch_titles = [item["title"] for item in lane_states if quality_status_tone(item["status"]) == "watch"]

    if risk_titles:
        tone = "risk"
        status = "人工复核"
        label = "先人工核对"
        summary = f"{'、'.join(risk_titles)} 链路没有通过，今天先别把页面结论当成直接动作。"
    elif watch_titles:
        tone = "watch"
        status = "局部待核"
        label = "先局部核对"
        summary = f"{'、'.join(watch_titles)} 还没完全确认，重要动作前先回到原始 JSON 再看一眼。"
    elif brief_is_live:
        tone = "positive"
        status = "总控同步"
        label = "先按当前页整理"
        summary = "总控和三条核心链路都已同步，今天可以先把这页当动作整理入口。"
    else:
        tone = "watch"
        status = "实时回退"
        label = "先看实时"
        summary = "总控没更新到当日，但实时自选股、早盘和午盘链路都可用，可先按实时链路整理判断。"

    issue_url = first_issue_quality_url(
        lanes.get("watchlist"),
        lanes.get("aggressive"),
        lanes.get("midday_confirmation"),
    )
    decision_brief_url = artifact_url(((decision_brief or {}).get("paths") or {}).get("source_json"))
    return build_confidence_switch(
        status=status,
        label=label,
        tone=tone,
        summary=summary,
        note=(
            f"总控交易日 {brief_trade_date}，进攻阀门 {detail_value((gate or {}).get('label'), '实时判断')}。"
            if decision_brief
            else f"当前没有总控简报，进攻阀门按 {detail_value((gate or {}).get('label'), '实时判断')} 执行。"
        ),
        metrics=[
            build_confidence_metric("总控", "已同步" if brief_is_live else f"停留 {brief_trade_date}"),
            build_confidence_metric("自选股", quality_status_label((lanes.get("watchlist") or {}).get("validation_status"))),
            build_confidence_metric("早盘", quality_status_label((lanes.get("aggressive") or {}).get("validation_status"))),
            build_confidence_metric("午盘", quality_status_label((lanes.get("midday_confirmation") or {}).get("validation_status"))),
        ],
        actions=[
            build_confidence_action(
                "打开问题 JSON" if issue_url else "查看总控 JSON",
                issue_url or decision_brief_url,
                external=True,
            ),
            build_confidence_action("查看今日总览", links.get("today")),
        ],
    )


def build_watchlist_confidence_switch(
    decision_brief: dict[str, Any] | None,
    watchlist: dict[str, Any] | None,
    quality: dict[str, Any] | None,
    *,
    brief_is_live: bool,
    links: dict[str, Any],
) -> dict[str, Any]:
    brief_trade_date = detail_value((decision_brief or {}).get("trade_date"), "未生成")
    quality_status = (quality or {}).get("validation_status") or "unknown"
    tone = quality_status_tone(quality_status)

    if tone == "risk":
        status = "人工复核"
        label = "先人工核对"
        summary = "自选股质检没有通过，先别直接照着这页的持仓动作执行。"
    elif tone == "watch":
        status = "局部待核"
        label = "先局部核对"
        summary = "自选股快照已经到位，但质检还没完全通过，关键动作前先回源确认。"
    elif brief_is_live:
        tone = "positive"
        status = "持仓层同步"
        label = "按持仓动作使用"
        summary = "总控持仓层和自选股质检都已同步，这页可作为今天的持仓判断主参考页。"
    else:
        tone = "watch"
        status = "实时快照"
        label = "按快照使用"
        summary = "总控没更新到当日，但自选股快照和质检可用，当前页可先作为实时持仓整理入口。"

    return build_confidence_switch(
        status=status,
        label=label,
        tone=tone,
        summary=summary,
        note=(
            f"快照时间 {detail_value((watchlist or {}).get('generated_at'))}，总控交易日 {brief_trade_date}。"
        ),
        metrics=[
            build_confidence_metric("总控", "已同步" if brief_is_live else f"停留 {brief_trade_date}"),
            build_confidence_metric("快照", detail_value((watchlist or {}).get("generated_at"))),
            build_confidence_metric("质检", quality_status_label(quality_status)),
            build_confidence_metric("优先处理", len((watchlist or {}).get("priority_codes") or [])),
        ],
        actions=[
            build_confidence_action("打开质检 JSON", artifact_url((quality or {}).get("path")), external=True),
            build_confidence_action("看观察池", links.get("opportunities")),
        ],
    )


def build_opportunities_confidence_switch(
    decision_brief: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    aggressive_quality: dict[str, Any] | None,
    midday_quality: dict[str, Any] | None,
    *,
    brief_is_live: bool,
    links: dict[str, Any],
) -> dict[str, Any]:
    brief_trade_date = detail_value((decision_brief or {}).get("trade_date"), "未生成")
    gate = (((screening_batch or {}).get("market_regime") or {}).get("execution_gate") or {})
    allow_new_positions = bool(gate.get("allow_new_positions"))
    early_status = (aggressive_quality or {}).get("validation_status") or "unknown"
    midday_status = (midday_quality or {}).get("validation_status") or "unknown"
    risk_titles = [
        title
        for title, status in (("早盘", early_status), ("午盘", midday_status))
        if quality_status_tone(status) == "risk"
    ]
    watch_titles = [
        title
        for title, status in (("早盘", early_status), ("午盘", midday_status))
        if quality_status_tone(status) == "watch"
    ]

    if risk_titles:
        tone = "risk"
        status = "人工复核"
        label = "先人工核对"
        summary = f"{'、'.join(risk_titles)} 链路没有通过，这页先只能当问题排查入口，不能直接挑新仓。"
    elif watch_titles:
        tone = "watch"
        status = "局部待核"
        label = "先局部核对"
        summary = f"{'、'.join(watch_titles)} 链路还没完全确认，候选名单先看，不急着直接执行。"
    elif not allow_new_positions:
        tone = "watch"
        status = "只保留观察"
        label = "先别开新仓"
        summary = "早盘和午盘链路都可用，但进攻阀门关闭，今天这里主要承担观察池角色。"
    elif brief_is_live:
        tone = "positive"
        status = "观察层同步"
        label = "仅轻仓试错"
        summary = "总控观察层已同步，早盘和午盘链路都已就绪，先看优先观察名单，盘中条件继续确认后再考虑轻仓试错。"
    else:
        tone = "watch"
        status = "实时观察链路"
        label = "按实时链路看"
        summary = "总控没更新到当日，但实时早盘和午盘链路可用，可先按实时观察池判断。"

    issue_url = first_issue_quality_url(aggressive_quality, midday_quality)
    return build_confidence_switch(
        status=status,
        label=label,
        tone=tone,
        summary=summary,
        note=f"进攻阀门 {detail_value(gate.get('label'), '实时判断')}，总控交易日 {brief_trade_date}。",
        metrics=[
            build_confidence_metric("阀门", detail_value(gate.get("label"), "实时判断")),
            build_confidence_metric("总控", "已同步" if brief_is_live else f"停留 {brief_trade_date}"),
            build_confidence_metric("早盘质检", quality_status_label(early_status)),
            build_confidence_metric("午盘质检", quality_status_label(midday_status)),
        ],
        actions=[
            build_confidence_action(
                "打开问题 JSON" if issue_url else "看自选股",
                issue_url or links.get("watchlist"),
                external=bool(issue_url),
            ),
            build_confidence_action("回到今日总览", links.get("today")),
        ],
    )


def build_review_confidence_switch(
    baseline_review: dict[str, Any] | None,
    latest_review: dict[str, Any] | None,
    latest_lifecycle: dict[str, Any] | None,
    active_lifecycle: dict[str, Any] | None,
    *,
    active_baseline_id: str | None,
    active_window_id: str | None,
    lifecycle_note: str,
    links: dict[str, Any],
) -> dict[str, Any]:
    same_window = bool(active_baseline_id and active_window_id and active_baseline_id == active_window_id)
    latest_activity = (latest_lifecycle or {}).get("activity_count") or 0
    active_activity = (active_lifecycle or {}).get("activity_count") or 0
    lifecycle_fallback = bool(
        latest_lifecycle
        and active_lifecycle
        and latest_activity == 0
        and latest_lifecycle.get("path") != active_lifecycle.get("path")
    )

    if not baseline_review or not latest_review:
        tone = "risk"
        status = "窗口不完整"
        label = "先补窗口"
        summary = "基准窗口或对比窗口缺失，这页暂时不适合用来收束比较判断。"
    elif same_window:
        tone = "watch"
        status = "单窗口模式"
        label = "先看结构"
        summary = "当前基准窗口和对比窗口是同一份研究，更适合先看结构，不适合直接看变化结论。"
    elif lifecycle_fallback:
        tone = "watch"
        status = "变化回放回退"
        label = "数据偏旧"
        summary = "研究窗口对比仍可参考，但最近变化回放已回退到最近一次有动作的快照。"
    else:
        tone = "positive"
        status = "窗口可比"
        label = "先做校准"
        summary = "基准窗口、对比窗口和变化回放都已就位，可以先用这页校准判断，再决定要不要钻细节。"

    latest_review_url = artifact_url((latest_review or {}).get("path"))
    baseline_review_url = artifact_url((baseline_review or {}).get("path"))
    return build_confidence_switch(
        status=status,
        label=label,
        tone=tone,
        summary=summary,
        note=lifecycle_note,
        metrics=[
            build_confidence_metric("基准窗口", review_window_text(baseline_review)),
            build_confidence_metric("对比窗口", review_window_text(latest_review)),
            build_confidence_metric("最新变化", f"{latest_activity} 条"),
            build_confidence_metric("当前回放", f"{active_activity} 条", "已回退" if lifecycle_fallback else ""),
        ],
        actions=[
            build_confidence_action(
                "打开对比研究" if latest_review_url else "打开基准研究",
                latest_review_url or baseline_review_url,
                external=True,
            ),
            build_confidence_action("回到今日总览", links.get("today")),
        ],
    )


def normalize_learning_stock_code(value: Any) -> str:
    text = str(value or "").strip().lower()
    match = re.search(r"(\d{6})", text)
    return match.group(1) if match else text


def infer_learning_action(item: dict[str, Any], *, default: str = "observe") -> str:
    entry_plan = item.get("entry_plan") or {}
    text = " ".join(
        str(value or "")
        for value in (
            entry_plan.get("action"),
            item.get("action"),
            item.get("status"),
            item.get("screening_status"),
            item.get("setup_label"),
            item.get("setup_type"),
            item.get("entry_reason"),
            item.get("watch_condition"),
        )
    )
    if any(token in text for token in ("减仓", "卖出", "降低仓位")):
        return "reduce"
    if any(token in text for token in ("试错", "买入", "轻仓")):
        return "trial_buy"
    if any(token in text for token in ("观察", "跟踪", "候选", "待确认", "新增")):
        return "observe"
    return default


def learning_memory_tone(primary_cause: Any, review_reason_key: Any) -> str:
    primary = str(primary_cause or "")
    reason = str(review_reason_key or "")
    if primary in {"too_loose", "execution_gap", "data_unavailable"}:
        return "risk"
    if primary == "too_strict" or reason == "missed_opportunity":
        return "warning"
    return "info"


def learning_memory_summary_from_case(case: dict[str, Any]) -> str:
    return detail_value(
        case.get("learning_hint")
        or case.get("rule_hypothesis")
        or case.get("review_note"),
        "这只股票有历史复盘提醒，今天先把同类错误过一遍。",
    )


def learning_memory_from_case(case: dict[str, Any], *, match_reason: str) -> dict[str, Any]:
    primary_label = case.get("primary_cause_label") or case.get("primary_cause") or "历史偏差"
    reason_label = case.get("review_reason") or case.get("review_reason_key") or "复盘样本"
    stock_name = case.get("stock_name") or case.get("stock_code") or "该股"
    return {
        "key": case.get("review_case_id") or case.get("decision_id") or f"case:{stock_name}",
        "kind": "stock_case",
        "scope": "stock",
        "scope_label": "个股旧案",
        "match_reason": match_reason,
        "title": f"{stock_name}：{primary_label}",
        "summary": learning_memory_summary_from_case(case),
        "tone": learning_memory_tone(case.get("primary_cause"), case.get("review_reason_key")),
        "stock_code": case.get("stock_code"),
        "stock_name": case.get("stock_name"),
        "trade_date": case.get("trade_date"),
        "reviewed_at": case.get("reviewed_at"),
        "lane": case.get("lane"),
        "action": case.get("action"),
        "action_label": case.get("action_label"),
        "review_reason_key": case.get("review_reason_key"),
        "review_reason_label": reason_label,
        "primary_cause": case.get("primary_cause"),
        "primary_cause_label": primary_label,
        "secondary_cause_labels": case.get("secondary_cause_labels") or [],
        "conclusion_action_label": case.get("conclusion_action_label"),
        "sample_count": case.get("sample_count") or 1,
        "evidence_strength": case.get("evidence_strength"),
        "evidence_strength_label": case.get("evidence_strength_label"),
        "learning_hint": learning_memory_summary_from_case(case),
    }


def learning_memory_from_pattern(pattern: dict[str, Any], *, match_reason: str) -> dict[str, Any]:
    primary_label = (
        pattern.get("dominant_primary_cause_label")
        or pattern.get("primary_cause_label")
        or pattern.get("primary_cause")
        or "历史偏差"
    )
    reason_label = pattern.get("review_reason_label") or pattern.get("review_reason_key") or "复盘模式"
    lane = pattern.get("lane") or "unknown"
    action_label = pattern.get("action_label") or pattern.get("action") or "unknown"
    sample_count = int(pattern.get("sample_count") or 0)
    return {
        "key": pattern.get("pattern_id") or f"pattern:{lane}:{action_label}:{reason_label}",
        "kind": "pattern",
        "scope": "pattern",
        "scope_label": "模式记忆",
        "match_reason": match_reason,
        "title": f"{reason_label}：{primary_label}",
        "summary": detail_value(
            pattern.get("learning_hint") or pattern.get("rule_hypothesis"),
            "这类模式有历史复盘提醒，今天先确认是否又在重复同类偏差。",
        ),
        "tone": learning_memory_tone(pattern.get("primary_cause"), pattern.get("review_reason_key")),
        "lane": lane,
        "action": pattern.get("action"),
        "action_label": action_label,
        "review_reason_key": pattern.get("review_reason_key"),
        "review_reason_label": reason_label,
        "primary_cause": pattern.get("primary_cause"),
        "primary_cause_label": primary_label,
        "secondary_cause_labels": pattern.get("dominant_secondary_cause_labels") or [],
        "conclusion_action_label": pattern.get("dominant_conclusion_action_label"),
        "follow_up_status_label": pattern.get("follow_up_status_label"),
        "sample_count": sample_count,
        "stock_count": pattern.get("stock_count"),
        "evidence_strength": pattern.get("evidence_strength"),
        "evidence_strength_label": pattern.get("evidence_strength_label"),
        "learning_hint": pattern.get("learning_hint"),
    }


_REVIEW_LEARNING_INDEX_CACHE: dict[str, Any] = {"mtime_ns": None, "value": None}


def build_review_learning_memory_index() -> dict[str, Any]:
    try:
        import decision_ledger  # type: ignore
    except Exception as exc:
        return {"cases": [], "patterns": [], "by_code": {}, "error": str(exc)}

    try:
        review_cases_path = decision_ledger._review_cases_path()
    except Exception:
        review_cases_path = None

    mtime_ns: int = 0
    if review_cases_path is not None:
        try:
            mtime_ns = review_cases_path.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0

    cached_value = _REVIEW_LEARNING_INDEX_CACHE.get("value")
    if cached_value is not None and _REVIEW_LEARNING_INDEX_CACHE.get("mtime_ns") == mtime_ns:
        return cached_value

    try:
        payload = decision_ledger.list_review_cases()
    except Exception as exc:
        return {"cases": [], "patterns": [], "by_code": {}, "error": str(exc)}
    cases = [item for item in (payload.get("items") or []) if isinstance(item, dict)]
    patterns = [item for item in (payload.get("patterns") or []) if isinstance(item, dict)]

    by_code: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        code_key = normalize_learning_stock_code(case.get("stock_code"))
        if not code_key:
            continue
        by_code.setdefault(code_key, []).append(case)

    result = {
        "cases": cases,
        "patterns": patterns,
        "by_code": by_code,
        "error": None,
    }
    _REVIEW_LEARNING_INDEX_CACHE["mtime_ns"] = mtime_ns
    _REVIEW_LEARNING_INDEX_CACHE["value"] = result
    return result


def learning_theme_values(item: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    raw_themes = item.get("themes")
    if isinstance(raw_themes, list):
        values.extend(raw_themes)
    elif raw_themes:
        values.append(raw_themes)
    values.extend([item.get("theme"), item.get("setup_label"), item.get("setup_type")])
    return [str(value or "").strip() for value in values if str(value or "").strip()]


def candidate_learning_memories(
    item: dict[str, Any],
    *,
    lane: str,
    learning_index: dict[str, Any] | None,
    limit: int = 2,
) -> list[dict[str, Any]]:
    if not learning_index:
        return []

    code = normalize_learning_stock_code(item.get("code"))
    themes = set(learning_theme_values(item))
    action = infer_learning_action(item)
    ranked: list[tuple[int, str, dict[str, Any]]] = []

    by_code = learning_index.get("by_code") if isinstance(learning_index.get("by_code"), dict) else None
    if isinstance(by_code, dict):
        same_code_cases = by_code.get(code) or []
    else:
        same_code_cases = [
            case for case in (learning_index.get("cases") or [])
            if normalize_learning_stock_code(case.get("stock_code")) == code
        ]

    for case in same_code_cases:
        score = 100
        if str(case.get("lane") or "") == lane:
            score += 12
        if str(case.get("action") or "") == action:
            score += 8
        if str(case.get("review_reason_key") or "") == "missed_opportunity":
            score += 4
        ranked.append((score, str(case.get("reviewed_at") or ""), learning_memory_from_case(case, match_reason="same_stock")))

    for pattern in learning_index.get("patterns") or []:
        score = 0
        if str(pattern.get("lane") or "") == lane:
            score += 40
        if str(pattern.get("action") or "") == action:
            score += 16
        pattern_theme = str(pattern.get("stock_theme") or "").strip()
        if pattern_theme and pattern_theme in themes:
            score += 10
        if str(pattern.get("review_reason_key") or "") == "missed_opportunity":
            score += 5
        if str(pattern.get("primary_cause") or "") == "too_strict":
            score += 3
        if "量能判断偏保守" in (pattern.get("dominant_secondary_cause_labels") or []):
            score += 2
        if score < 35:
            continue
        sample_score = min(int(pattern.get("sample_count") or 0), 20)
        ranked.append(
            (
                score + sample_score,
                str((pattern.get("cases") or [{}])[0].get("reviewed_at") or ""),
                learning_memory_from_pattern(pattern, match_reason="same_pattern"),
            )
        )

    ranked.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    seen: set[str] = set()
    seen_stock_signatures: set[tuple[str, str, str, str]] = set()
    memories: list[dict[str, Any]] = []
    for _score, _reviewed_at, memory in ranked:
        key = str(memory.get("key") or "")
        if key in seen:
            continue
        signature = (
            str(memory.get("lane") or ""),
            str(memory.get("action") or ""),
            str(memory.get("review_reason_key") or ""),
            str(memory.get("primary_cause") or ""),
        )
        if memory.get("kind") == "pattern" and signature in seen_stock_signatures:
            continue
        seen.add(key)
        if memory.get("kind") == "stock_case":
            seen_stock_signatures.add(signature)
        memories.append(memory)
        if len(memories) >= limit:
            break
    return memories


def global_learning_memories(learning_index: dict[str, Any] | None, *, limit: int = 3) -> list[dict[str, Any]]:
    if not learning_index:
        return []
    patterns = [item for item in (learning_index.get("patterns") or []) if isinstance(item, dict)]

    def pattern_priority(item: dict[str, Any]) -> tuple[int, int, str]:
        score = 0
        if str(item.get("review_reason_key") or "") == "missed_opportunity":
            score += 40
        if str(item.get("primary_cause") or "") == "too_strict":
            score += 25
        if "量能判断偏保守" in (item.get("dominant_secondary_cause_labels") or []):
            score += 10
        if str(item.get("primary_cause") or "") == "insufficient_sample":
            score -= 15
        return (
            score,
            int(item.get("sample_count") or 0),
            str((item.get("cases") or [{}])[0].get("reviewed_at") or ""),
        )

    patterns.sort(
        key=pattern_priority,
        reverse=True,
    )
    return [
        learning_memory_from_pattern(pattern, match_reason="global_pattern")
        for pattern in patterns[: max(0, limit)]
    ]


def compact_observation_sentence(value: Any, fallback: str = "") -> str:
    text = normalize_stock_result_copy(value, fallback).strip()
    return text.rstrip("。.!！")


def build_observation_instruction(
    *,
    name: Any,
    action: Any,
    upgrade: Any,
    invalid: Any,
) -> str:
    action_text = compact_observation_sentence(action, "只观察，不追")
    if any(token in action_text for token in ("不新增动作", "只保留观察", "先观察", "不急着执行")):
        action_text = "只观察，不追"

    parts = [f"{detail_value(name, '这只票')}：{action_text}"]
    upgrade_text = compact_observation_sentence(upgrade)
    invalid_text = compact_observation_sentence(invalid)
    if upgrade_text:
        parts.append(f"升级：{upgrade_text}")
    if invalid_text:
        parts.append(f"失效：{invalid_text}")
    return f"{'；'.join(parts)}。"


def opportunity_risk_tags(*values: Any, limit: int = 3) -> list[str]:
    tags: list[str] = []
    for value in values:
        items = value if isinstance(value, list) else [value]
        for item in text_items(items):
            text = str(item or "").strip()
            if text and text not in tags:
                tags.append(text)
            if len(tags) >= limit:
                return tags
    return tags


def build_screening_candidate_card(
    item: dict[str, Any],
    *,
    learning_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    execution_quality = item.get("execution_quality") or {}
    entry_plan = item.get("entry_plan") or {}
    upgrade_condition = entry_plan.get("trigger") or item.get("watch_condition")
    invalid_condition = entry_plan.get("invalidate") or ((entry_plan.get("levels") or {}).get("invalidate")) or item.get("main_risk")
    action_text = entry_plan.get("action") or item.get("screening_note") or "只观察，不追"
    card = {
        "code": item.get("code"),
        "name": item.get("name"),
        "status": candidate_status_label(item.get("screening_status") or "unknown"),
        "tone": candidate_tone(item),
        "setup_label": item.get("setup_label") or item.get("setup_type") or "待确认",
        "score": item.get("priority_score"),
        "change_pct": item.get("change_pct"),
        "amount_yi": item.get("amount_yi"),
        "theme": ", ".join(item.get("themes") or []) or "其他",
        "detail": item.get("entry_reason") or item.get("screening_note") or item.get("main_risk") or "等待更多确认",
        "foot": (
            f"{execution_quality.get('label') or '未评级'}"
            f" · {(item.get('main_risk') or ((item.get('risk_flags') or [None])[0]) or '等待更多确认')}"
        ),
        "observation_instruction": build_observation_instruction(
            name=item.get("name"),
            action=action_text,
            upgrade=upgrade_condition,
            invalid=invalid_condition,
        ),
        "upgrade_condition": normalize_trigger_sentence(upgrade_condition, "等待触发条件明确。"),
        "invalid_condition": normalize_stock_result_copy(invalid_condition, "触发失效条件就剔除。"),
        "avoid_condition": normalize_avoid_sentence(entry_plan.get("avoid") or item.get("main_risk")),
        "risk_tags": opportunity_risk_tags(item.get("risk_flags"), execution_quality.get("warnings"), item.get("main_risk")),
        "priority_label": detail_value(item.get("tier"), "观察"),
        "action_key": f"screening:{item.get('code')}",
        "updated_at": item.get("updated_at") or item.get("snapshot_time"),
        "detail_url": today_candidate_detail_url(item.get("code")),
    }
    memories = candidate_learning_memories(item, lane="aggressive", learning_index=learning_index)
    if memories:
        card["learning_memories"] = memories
    return card


def build_confirmation_candidate_card(
    item: dict[str, Any],
    *,
    learning_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    execution_quality = item.get("execution_quality") or {}
    entry_plan = item.get("entry_plan") or {}
    upgrade_condition = entry_plan.get("trigger") or item.get("watch_condition")
    invalid_condition = entry_plan.get("invalidate") or ((entry_plan.get("levels") or {}).get("invalidate")) or item.get("main_risk")
    action_text = entry_plan.get("action") or item.get("watch_condition") or "只观察，不追"
    card = {
        "code": item.get("code"),
        "name": item.get("name"),
        "status": candidate_status_label(item.get("status") or "unknown"),
        "tone": candidate_tone(item),
        "setup_label": item.get("setup_label") or "待确认",
        "score": item.get("score"),
        "change_pct": item.get("change_pct"),
        "amount_yi": item.get("amount_yi"),
        "theme": item.get("theme") or "其他",
        "detail": item.get("entry_reason") or item.get("watch_condition") or item.get("main_risk") or "等待更多确认",
        "foot": item.get("main_risk") or "等待更多确认",
        "observation_instruction": build_observation_instruction(
            name=item.get("name"),
            action=action_text,
            upgrade=upgrade_condition,
            invalid=invalid_condition,
        ),
        "upgrade_condition": normalize_trigger_sentence(upgrade_condition, "等待触发条件明确。"),
        "invalid_condition": normalize_stock_result_copy(invalid_condition, "触发失效条件就剔除。"),
        "avoid_condition": normalize_avoid_sentence(entry_plan.get("avoid") or item.get("main_risk")),
        "risk_tags": opportunity_risk_tags(item.get("risk_flags"), execution_quality.get("warnings"), item.get("main_risk")),
        "priority_label": detail_value(item.get("tier"), "观察"),
        "action_key": f"confirmation:{item.get('code')}",
        "updated_at": item.get("updated_at") or item.get("snapshot_time"),
        "detail_url": today_candidate_detail_url(item.get("code")),
    }
    memories = candidate_learning_memories(item, lane="midday_confirmation", learning_index=learning_index)
    if memories:
        card["learning_memories"] = memories
    return card


def build_watchlist_stock_card(
    item: dict[str, Any],
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
) -> dict[str, Any]:
    trade_levels = item.get("trade_levels") or {}
    rule_snapshot = item.get("rule_snapshot") or {}
    reason = (
        (item.get("hard_flags") or [None])[0]
        or (item.get("watch_points") or [None])[0]
        or (item.get("positives") or [None])[0]
        or rule_snapshot.get("signal")
        or "等待更多确认"
    )
    screening_item = find_screening_candidate(screening_batch, item.get("code") or "")
    confirmation_match = find_confirmation_match(confirmation, item.get("code") or "")
    main_risk = (
        item.get("main_risk")
        or (item.get("risk_flags") or [None])[0]
        or (item.get("hard_flags") or [None])[0]
        or "等待更多确认"
    )
    cross_status: list[str] = []
    if screening_item:
        cross_status.append(f"观察池 {screening_item.get('screening_status') or '候选'}")
    if confirmation_match:
        cross_status.append(f"午盘确认 {(confirmation_match or {}).get('group_label') or '已进入'}")
    if not cross_status:
        cross_status.append("当前未进入观察池链路")

    return {
        "code": item.get("code"),
        "name": item.get("name"),
        "action": item.get("action"),
        "position": item.get("position"),
        "tone": action_tone(item.get("action")),
        "reason": reason,
        "support": trade_levels.get("support"),
        "resistance": trade_levels.get("resistance"),
        "stop_loss": trade_levels.get("stop_loss"),
        "signal": rule_snapshot.get("signal"),
        "risk": main_risk,
        "snapshot_time": item.get("snapshot_time") or item.get("updated_at"),
        "status_line": " · ".join(cross_status),
        "detail_url": watchlist_detail_url(item.get("code")),
    }


def build_theme_cards(screening_batch: dict[str, Any] | None, limit: int = 4) -> list[dict[str, Any]]:
    themes = (((screening_batch or {}).get("market_themes") or {}).get("themes") or [])[:limit]
    return [
        {
            "title": item.get("theme") or "其他",
            "score": detail_value(item.get("score")),
            "detail": detail_value(((item.get("persistence") or {}).get("summary"))),
            "leaders": text_items(item.get("leader_codes")),
        }
        for item in themes
    ]


def build_today_task_item(
    *,
    key: str,
    title: str,
    source: str,
    status: str,
    tone: str,
    detail: str,
    foot: str | None = None,
    metrics: list[str] | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": detail_value(title, "待处理事项"),
        "source": detail_value(source, "系统"),
        "status": detail_value(status, "待看"),
        "tone": tone or "watch",
        "detail": detail_value(detail, "等待更多确认"),
        "foot": detail_value(foot, ""),
        "metrics": [item for item in (metrics or []) if item],
        "url": url,
    }


def build_today_task_context(
    *,
    lane_key: str,
    freshness_at: str | None,
    confidence_status: str | None,
    confidence_note: str | None = None,
) -> dict[str, Any]:
    freshness_label = fmt_dt(freshness_at) if freshness_at else "-"
    normalized_status = str(confidence_status or "unknown").strip().lower()
    if confidence_note:
        note = confidence_note
    elif normalized_status == "ok":
        note = "当前链路已完成质检。"
    else:
        note = "当前链路建议先核对再下结论。"
    return {
        "lane_key": lane_key,
        "freshness": {
            "value": freshness_at or "-",
            "label": freshness_label,
        },
        "confidence": {
            "status": normalized_status or "unknown",
            "label": quality_status_label(normalized_status),
            "tone": quality_status_tone(normalized_status),
            "note": detail_value(note, ""),
        },
    }


def attach_today_task_context(item: dict[str, Any] | None, context: dict[str, Any]) -> dict[str, Any] | None:
    if not item:
        return None
    payload = dict(item)
    payload["lane_key"] = context.get("lane_key") or ""
    payload["freshness"] = dict(context.get("freshness") or {})
    payload["confidence"] = dict(context.get("confidence") or {})
    return payload


def append_today_task(
    target: list[dict[str, Any]],
    seen_keys: set[str],
    item: dict[str, Any] | None,
    *,
    limit: int,
) -> None:
    if not item or len(target) >= limit:
        return
    key = str(item.get("key") or "").strip()
    if not key or key in seen_keys:
        return
    seen_keys.add(key)
    target.append(item)


def build_today_watchlist_task_item(
    item: dict[str, Any],
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
    *,
    source: str,
) -> dict[str, Any]:
    card = build_watchlist_stock_card(item, screening_batch, confirmation)
    metrics = [
        f"仓位 {detail_value(card.get('position'), '待定')}",
        f"信号 {detail_value(card.get('signal'), '待确认')}",
        (
            f"止损 {card.get('stop_loss')}"
            if card.get("stop_loss") not in (None, "", [], {})
            else ""
        ),
    ]
    return build_today_task_item(
        key=f"watchlist:{detail_value(card.get('code'), '-')}",
        title=f"{detail_value(card.get('name'), '持仓标的')} {detail_value(card.get('code'), '')}".strip(),
        source=source,
        status=detail_value(card.get("action"), "处理"),
        tone=str(card.get("tone") or "watch"),
        detail=detail_value(card.get("reason"), "等待更多确认"),
        foot=detail_value(card.get("status_line"), detail_value(card.get("position"), "")),
        metrics=metrics,
        url=card.get("detail_url"),
    )


def build_today_screening_task_item(item: dict[str, Any], *, source: str) -> dict[str, Any]:
    execution_quality = item.get("execution_quality") or {}
    metrics = [
        f"形态 {detail_value(item.get('setup_label') or item.get('setup_type'), '待确认')}",
        (
            f"优先分 {item.get('priority_score')}"
            if item.get("priority_score") not in (None, "", [], {})
            else ""
        ),
        f"执行 {detail_value(execution_quality.get('label'), '未评级')}",
    ]
    return build_today_task_item(
        key=f"screening:{detail_value(item.get('code'), '-')}",
        title=f"{detail_value(item.get('name'), '候选标的')} {detail_value(item.get('code'), '')}".strip(),
        source=source,
        status=candidate_status_label(item.get("screening_status") or "unknown"),
        tone=candidate_tone(item),
        detail=detail_value(
            item.get("watch_condition")
            or item.get("entry_reason")
            or item.get("screening_note")
            or item.get("main_risk"),
            "等待更多确认",
        ),
        foot=detail_value(
            item.get("main_risk")
            or ((item.get("risk_flags") or [None])[0])
            or execution_quality.get("label"),
            "",
        ),
        metrics=metrics,
        url=today_candidate_detail_url(item.get("code")),
    )


def build_today_confirmation_task_item(item: dict[str, Any], *, source: str) -> dict[str, Any]:
    metrics = [
        f"状态 {candidate_status_label(item.get('status') or 'unknown')}",
        (
            f"涨幅 {item.get('change_pct')}%"
            if item.get("change_pct") not in (None, "", [], {})
            else ""
        ),
        f"主题 {detail_value(item.get('theme'), '其他')}",
    ]
    return build_today_task_item(
        key=f"confirmation:{detail_value(item.get('code'), '-')}",
        title=f"{detail_value(item.get('name'), '午盘标的')} {detail_value(item.get('code'), '')}".strip(),
        source=source,
        status=candidate_status_label(item.get("status") or "unknown"),
        tone=candidate_tone(item),
        detail=detail_value(
            item.get("watch_condition")
            or item.get("entry_reason")
            or item.get("main_risk"),
            "等待更多确认",
        ),
        foot=detail_value(item.get("main_risk"), ""),
        metrics=metrics,
        url=today_candidate_detail_url(item.get("code")),
    )


def build_today_system_task_item(
    *,
    key: str,
    title: str,
    source: str,
    status: str,
    tone: str,
    detail: str,
    foot: str | None = None,
    metrics: list[str] | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    return build_today_task_item(
        key=key,
        title=title,
        source=source,
        status=status,
        tone=tone,
        detail=detail,
        foot=foot,
        metrics=metrics,
        url=url,
    )


def build_today_action_groups(
    watchlist: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
    decision_brief: dict[str, Any] | None,
    quality_status: dict[str, Any] | None,
    *,
    brief_is_live: bool,
    gate: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    stocks = (watchlist or {}).get("stocks") or []
    priority_codes = set((watchlist or {}).get("priority_codes") or [])
    observe_codes = set((watchlist or {}).get("observe_codes") or [])
    priority_stocks = [item for item in stocks if item.get("code") in priority_codes]
    observe_stocks = [item for item in stocks if item.get("code") in observe_codes]

    candidates = (screening_batch or {}).get("candidates") or []
    approved = [item for item in candidates if item.get("screening_status") == "approved"]
    caution = [item for item in candidates if item.get("screening_status") == "caution"]
    confirmed = (confirmation or {}).get("confirmed") or []
    fresh_candidates = (confirmation or {}).get("fresh_candidates") or []
    downgraded = (confirmation or {}).get("downgraded") or []
    lanes = (quality_status or {}).get("lanes") or {}
    allow_new_positions = bool((gate or {}).get("allow_new_positions"))
    avoid_points = text_items((((decision_brief or {}).get("focus") or {}).get("avoid_points")) if brief_is_live else [])
    watchlist_lane = lanes.get("watchlist") or {}
    aggressive_lane = lanes.get("aggressive") or {}
    confirmation_lane = lanes.get("midday_confirmation") or {}

    watchlist_context = build_today_task_context(
        lane_key="watchlist",
        freshness_at=(watchlist or {}).get("generated_at"),
        confidence_status=watchlist_lane.get("validation_status"),
        confidence_note=((watchlist_lane.get("errors") or [None])[0]) or ((watchlist_lane.get("warnings") or [None])[0]),
    )
    screening_context = build_today_task_context(
        lane_key="aggressive",
        freshness_at=(screening_batch or {}).get("generated_at"),
        confidence_status=aggressive_lane.get("validation_status"),
        confidence_note=((aggressive_lane.get("errors") or [None])[0])
        or ((aggressive_lane.get("warnings") or [None])[0])
        or detail_value((gate or {}).get("summary"), ""),
    )
    confirmation_context = build_today_task_context(
        lane_key="midday_confirmation",
        freshness_at=(confirmation or {}).get("generated_at"),
        confidence_status=confirmation_lane.get("validation_status") or (confirmation or {}).get("validation_status"),
        confidence_note=((confirmation_lane.get("errors") or [None])[0]) or ((confirmation_lane.get("warnings") or [None])[0]),
    )
    brief_context = build_today_task_context(
        lane_key="decision_brief",
        freshness_at=(decision_brief or {}).get("generated_at"),
        confidence_status="ok" if brief_is_live else ("stale" if decision_brief else "unknown"),
        confidence_note="总控简报已更新到当日。" if brief_is_live else "总控简报不是当日最新，结论需要回到实时链路复核。",
    )

    do_now: list[dict[str, Any]] = []
    observe: list[dict[str, Any]] = []
    avoid: list[dict[str, Any]] = []
    do_now_seen: set[str] = set()
    observe_seen: set[str] = set()
    avoid_seen: set[str] = set()

    for item in priority_stocks:
        append_today_task(
            do_now,
            do_now_seen,
            attach_today_task_context(
                build_today_watchlist_task_item(item, screening_batch, confirmation, source="持仓优先"),
                watchlist_context,
            ),
            limit=3,
        )

    if allow_new_positions:
        for item in confirmed:
            append_today_task(
                do_now,
                do_now_seen,
                attach_today_task_context(
                    build_today_confirmation_task_item(item, source="午盘仍可跟踪"),
                    confirmation_context,
                ),
                limit=3,
            )
        for item in approved:
            append_today_task(
                do_now,
                do_now_seen,
                attach_today_task_context(
                    build_today_screening_task_item(item, source="早盘进入候选"),
                    screening_context,
                ),
                limit=3,
            )

    if not do_now:
        append_today_task(
            do_now,
            do_now_seen,
            attach_today_task_context(
                build_today_system_task_item(
                    key="system:review-holdings-first",
                    title="先复核已有持仓",
                    source="今日总控",
                    status="先看",
                    tone="watch",
                    detail="当前没有额外的强制动作票，先把持仓风险和仓位边界复核一遍，再决定要不要看新仓。",
                    foot="先看持仓，再看新仓。",
                    url=today_nav_links().get("watchlist"),
                ),
                brief_context if brief_is_live else watchlist_context,
            ),
            limit=3,
        )

    for item in observe_stocks:
        append_today_task(
            observe,
            observe_seen,
            attach_today_task_context(
                build_today_watchlist_task_item(item, screening_batch, confirmation, source="持仓观察"),
                watchlist_context,
            ),
            limit=3,
        )
    for item in fresh_candidates:
        append_today_task(
            observe,
            observe_seen,
            attach_today_task_context(
                build_today_confirmation_task_item(item, source="午盘新增"),
                confirmation_context,
            ),
            limit=3,
        )
    for item in caution:
        append_today_task(
            observe,
            observe_seen,
            attach_today_task_context(
                build_today_screening_task_item(item, source="观察池观察"),
                screening_context,
            ),
            limit=3,
        )
    if allow_new_positions:
        for item in approved:
            observe_item = attach_today_task_context(
                build_today_screening_task_item(item, source="早盘进入候选"),
                screening_context,
            )
            if observe_item.get("key") in do_now_seen:
                continue
            append_today_task(
                observe,
                observe_seen,
                observe_item,
                limit=3,
            )

    if not allow_new_positions:
        append_today_task(
            avoid,
            avoid_seen,
            attach_today_task_context(
                build_today_system_task_item(
                    key="system:no-new-positions",
                    title="新仓今天先不做",
                    source="进攻阀门",
                    status="回避",
                    tone="risk",
                    detail=detail_value((gate or {}).get("summary"), "今天不建议开新仓，先保留观察名单。"),
                    foot=f"{detail_value((gate or {}).get('label'), '实时判断')} · 仓位上限 {detail_value((gate or {}).get('position_cap'), '-')}",
                    url=today_nav_links().get("opportunities"),
                ),
                screening_context,
            ),
            limit=3,
        )

    for item in downgraded:
        append_today_task(
            avoid,
            avoid_seen,
            attach_today_task_context(
                build_today_confirmation_task_item(item, source="午盘降级"),
                confirmation_context,
            ),
            limit=3,
        )

    for lane_key, lane_title in (
        ("watchlist", "自选股链路"),
        ("aggressive", "早盘扫描链路"),
        ("midday_confirmation", "午盘确认链路"),
    ):
        lane = lanes.get(lane_key) or {}
        status = lane.get("validation_status") or "unknown"
        if status == "ok":
            continue
        lane_context = build_today_task_context(
            lane_key=lane_key,
            freshness_at=lane.get("checked_at") or lane.get("expected_timestamp"),
            confidence_status=status,
            confidence_note=detail_value(
                ((lane.get("errors") or [None])[0]) or ((lane.get("warnings") or [None])[0]),
                "当前链路状态未完全通过，建议先回到原始数据核对。",
            ),
        )
        append_today_task(
            avoid,
            avoid_seen,
            attach_today_task_context(
                build_today_system_task_item(
                    key=f"quality:{lane_key}",
                    title=f"{lane_title}先别直接下结论",
                    source="链路可信度",
                    status="谨慎",
                    tone="risk" if status in {"blocked", "failed"} else "watch",
                    detail=detail_value(
                        ((lane.get("errors") or [None])[0]) or ((lane.get("warnings") or [None])[0]),
                        "当前链路状态未完全通过，建议先回到原始数据核对。",
                    ),
                    foot=f"最近检查 {detail_value(lane.get('checked_at'), '-')}",
                    metrics=[f"状态 {status}"],
                    url=artifact_url(lane.get("path")),
                ),
                lane_context,
            ),
            limit=3,
        )

    for index, point in enumerate(avoid_points[:2], start=1):
        append_today_task(
            avoid,
            avoid_seen,
            attach_today_task_context(
                build_today_system_task_item(
                    key=f"brief:avoid:{index}",
                    title="动作提醒",
                    source="总控提醒",
                    status="别做",
                    tone="risk",
                    detail=point,
                ),
                brief_context,
            ),
            limit=3,
        )

    return [
        {
            "key": "do-now",
            "eyebrow": "先做",
            "title": "优先处理",
            "count": len(do_now),
            "subtitle": "先处理持仓动作和今天必须先定的事，再决定有没有资格看新仓。",
            "items": do_now,
            "empty": "当前没有必须优先处理的动作。",
        },
        {
            "key": "watch",
            "eyebrow": "盯着看",
            "title": "只观察",
            "count": len(observe),
            "subtitle": "这些名字先放在视野里，不急着给动作，等下一次确认再说。",
            "items": observe,
            "empty": "当前没有需要额外盯着看的观察项。",
        },
        {
            "key": "avoid",
            "eyebrow": "今天别做",
            "title": "今日回避",
            "count": len(avoid),
            "subtitle": "这些动作今天明确别做，避免一边看系统一边又把纪律忘回去。",
            "items": avoid,
            "empty": "当前没有额外的回避提醒。",
        },
    ]


def today_action_queue_priority(item: dict[str, Any]) -> tuple[int, int, int]:
    key = str(item.get("key") or "")
    group_key = str(item.get("group_key") or "")
    if key.startswith("watchlist:"):
        base = 0
    elif key == "system:no-new-positions":
        base = 1
    elif key.startswith("quality:"):
        base = 2
    elif group_key == "do-now":
        base = 3
    elif group_key == "avoid":
        base = 4
    else:
        base = 5
    return (
        base,
        tone_priority(item.get("tone") or "watch"),
        int(item.get("group_index") or 0),
    )


def build_today_action_decision_state(item: dict[str, Any], decision_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    stored = decision_map.get(str(item.get("key") or "")) or {}
    decision = str(stored.get("decision") or "pending").strip().lower()
    updated_at = fmt_dt(stored.get("updated_at")) if stored.get("updated_at") else ""
    return {
        "value": decision,
        "label": action_decision_label(decision),
        "tone": action_decision_tone(decision),
        "updated_at": updated_at,
        "updated_at_raw": stored.get("updated_at") or "",
    }


def build_no_fill_intent_index(account_book: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in (account_book or {}).get("no_fill_intents") or []:
        if not isinstance(item, dict):
            continue
        trade_date = str(item.get("trade_date") or "").strip()
        intent_key = str(item.get("intent_key") or "").strip()
        if trade_date and intent_key:
            index[(trade_date, intent_key)] = item
    return index


def build_today_action_display_state(
    *,
    item: dict[str, Any],
    trade_date: str,
    no_fill_index: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    key = str(item.get("key") or "").strip()
    decision = item.get("decision") or {}
    decision_value = str(decision.get("value") or "pending").strip().lower()
    no_fill = no_fill_index.get((str(trade_date or "").strip(), key))
    state = "no_fill" if no_fill and decision_value == "pending" else decision_value
    updated_at_raw = str(
        ((no_fill or {}).get("ts") if state == "no_fill" else "")
        or decision.get("updated_at_raw")
        or ""
    ).strip()
    return {
        "value": state,
        "label": action_display_label(state),
        "tone": action_display_tone(state),
        "updated_at": fmt_dt(updated_at_raw) if updated_at_raw else str(decision.get("updated_at") or ""),
        "updated_at_raw": updated_at_raw,
        "reason": str((no_fill or {}).get("reason") or "").strip() if state == "no_fill" else "",
    }


def action_item_date(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    return match.group(0) if match else ""


def today_action_item_trade_date(item: dict[str, Any]) -> str:
    freshness = item.get("freshness") or {}
    display_state = item.get("display_state") or {}
    for value in (
        freshness.get("value"),
        freshness.get("label"),
        display_state.get("updated_at_raw"),
        display_state.get("updated_at"),
    ):
        trade_date = action_item_date(value)
        if trade_date:
            return trade_date
    return ""


def today_action_item_trust(
    item: dict[str, Any],
    *,
    expected_trade_date: str,
    readiness_mode: str,
    ready: bool,
) -> dict[str, Any]:
    item_trade_date = today_action_item_trade_date(item)
    stale_reasons: list[str] = []

    if readiness_mode != "live_ready" or not ready:
        stale_reasons.append("readiness_not_live_ready")
    if expected_trade_date and item_trade_date and item_trade_date != expected_trade_date:
        stale_reasons.append("expected_trade_date_mismatch")

    return {
        "trusted": not stale_reasons,
        "trade_date": item_trade_date,
        "expected_trade_date": expected_trade_date,
        "stale_reasons": stale_reasons,
    }


def mark_today_action_stale(item: dict[str, Any], trust: dict[str, Any]) -> dict[str, Any]:
    marked = dict(item)
    confidence = dict(marked.get("confidence") or {})
    item_trade_date = str(trust.get("trade_date") or "").strip()
    expected_trade_date = str(trust.get("expected_trade_date") or "").strip()
    reasons = [str(reason) for reason in trust.get("stale_reasons") or [] if str(reason)]
    reason_text = "；".join(
        {
            "readiness_not_live_ready": "readiness 未就绪，只能复核线索",
            "expected_trade_date_mismatch": f"旧数据 {item_trade_date or '-'}，不是 {expected_trade_date or '预期交易日'}",
        }.get(reason, reason)
        for reason in reasons
    )
    confidence.update(
        {
            "status": "stale",
            "label": "过期",
            "tone": "warning",
            "note": reason_text or "这条线索不可作为今天动作依据。",
        }
    )
    marked["confidence"] = confidence
    marked["trust"] = trust
    marked["stale_reasons"] = reasons
    marked["actionable"] = False
    return marked


def build_today_action_queue(
    action_groups: list[dict[str, Any]],
    trade_date: str,
    *,
    account_book: dict[str, Any] | None = None,
    expected_trade_date: str | None = None,
    readiness_mode: str = "live_ready",
    readiness_ready: bool = True,
) -> dict[str, Any]:
    decision_map = get_today_action_decision_map(trade_date)
    no_fill_index = build_no_fill_intent_index(account_book)
    ranked_items: list[dict[str, Any]] = []
    stale_items: list[dict[str, Any]] = []
    expected = str(expected_trade_date or trade_date or "").strip()

    for group in action_groups:
        for index, item in enumerate(group.get("items") or [], start=1):
            queue_item = dict(item)
            queue_item["group_key"] = group.get("key") or ""
            queue_item["group_title"] = group.get("title") or ""
            queue_item["group_index"] = index
            queue_item["decision"] = build_today_action_decision_state(item, decision_map)
            queue_item["display_state"] = build_today_action_display_state(
                item=queue_item,
                trade_date=trade_date,
                no_fill_index=no_fill_index,
            )
            trust = today_action_item_trust(
                queue_item,
                expected_trade_date=expected,
                readiness_mode=readiness_mode,
                ready=readiness_ready,
            )
            queue_item["trust"] = trust
            queue_item["actionable"] = bool(trust.get("trusted"))
            if trust.get("trusted"):
                ranked_items.append(queue_item)
            else:
                stale_items.append(mark_today_action_stale(queue_item, trust))

    ranked_items.sort(key=today_action_queue_priority)
    stale_items.sort(key=today_action_queue_priority)
    selected_items = ranked_items[:5]
    selected_stale_items = stale_items[:5]

    counts = {
        "total": len(selected_items),
        "pending": sum(1 for item in selected_items if (item.get("display_state") or {}).get("value") == "pending"),
        "done": sum(1 for item in selected_items if (item.get("display_state") or {}).get("value") == "done"),
        "watch": sum(1 for item in selected_items if (item.get("display_state") or {}).get("value") == "watch"),
        "skip": sum(1 for item in selected_items if (item.get("display_state") or {}).get("value") == "skip"),
        "no_fill": sum(1 for item in selected_items if (item.get("display_state") or {}).get("value") == "no_fill"),
    }
    counts["stale"] = len(stale_items)

    last_updated = max(
        (((item.get("display_state") or {}).get("updated_at_raw") or "") for item in selected_items),
        default="",
    )
    counts["last_updated"] = fmt_dt(last_updated) if last_updated else "-"

    return {
        "title": "今日动作队列",
        "subtitle": "先把今天真正要确认的动作收成 3-5 条，避免在全页信息里来回切换。",
        "note": "每条卡片都直接带上来源、更新时间和可信度；确认状态会按交易日记在控制台本地状态里。",
        "items": selected_items,
        "stale_items": selected_stale_items,
        "hidden_count": max(len(ranked_items) - len(selected_items), 0),
        "stale_hidden_count": max(len(stale_items) - len(selected_stale_items), 0),
        "counts": counts,
    }


def build_status_strip(*items: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in items if item.get("label") and item.get("value")]


def today_dispatch_trigger(item: dict[str, Any]) -> str:
    for metric in text_items(item.get("metrics")):
        if "跌破" in metric or "站回" in metric:
            return metric
    first_metric = first_text(item.get("metrics"))
    return first_metric or "查看详情"


def compress_today_actions(action_queue: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (action_queue.get("items") or [])[:3]:
        decision = item.get("decision") or {}
        confidence = item.get("confidence") or {}
        freshness = item.get("freshness") or {}
        rows.append(
            {
                "title": item.get("title") or "待确认动作",
                "action": item.get("status") or decision.get("label") or "查看详情",
                "tier": action_tier_label(
                    infer_action_tier(
                        action=item.get("status") or decision.get("label"),
                        tone=item.get("tone") or decision.get("tone"),
                        title=item.get("title"),
                    )
                ),
                "trigger": today_dispatch_trigger(item),
                "reason": detail_value(item.get("detail"), "先打开详情确认来源"),
                "risk": item.get("foot") or confidence.get("note") or "继续复核",
                "freshness": freshness.get("label") or "-",
                "url": item.get("url"),
                "tone": item.get("tone") or decision.get("tone") or "watch",
            }
        )
    return rows


def build_today_primary_actions(top_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return top_rows[:3]


def build_today_holdings_rows(action_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    do_now_group = next((group for group in action_groups if group.get("key") == "do-now"), None)
    items = [item for item in (do_now_group or {}).get("items") or [] if str(item.get("key") or "").startswith("watchlist:")]
    return compress_today_actions({"items": items})


def build_today_opportunity_rows(action_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    watch_group = next((group for group in action_groups if group.get("key") == "watch"), None)
    items = [
        item
        for item in (watch_group or {}).get("items") or []
        if str(item.get("key") or "").startswith("screening:")
        or str(item.get("key") or "").startswith("confirmation:")
    ]
    return compress_today_actions({"items": items})


def build_today_trusted_group_rows(action_queue: dict[str, Any], group_key: str, key_prefixes: tuple[str, ...]) -> list[dict[str, Any]]:
    items = [
        item
        for item in action_queue.get("items") or []
        if str(item.get("group_key") or "") == group_key
        and str(item.get("key") or "").startswith(key_prefixes)
    ]
    return compress_today_actions({"items": items})


def build_today_risk_rows(change_view: dict[str, Any], action_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for item in (change_view.get("summary_cards") or [])[:2]:
        rows.append(
            {
                "title": item.get("label") or "变化",
                "action": item.get("value") or "查看详情",
                "trigger": item.get("detail") or "查看详情",
                "reason": item.get("detail") or "查看详情",
                "risk": change_view.get("note") or "继续复核",
                "freshness": "变化回放",
                "url": (change_view.get("links") or {}).get("review"),
                "tone": "watch",
            }
        )

    avoid_group = next((group for group in action_groups if group.get("key") == "avoid"), None)
    rows.extend(compress_today_actions({"items": (avoid_group or {}).get("items") or []})[:1])
    return rows[:3]


def build_today_evidence_rows(source_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in source_cards[:3]:
        rows.append(
            {
                "title": item.get("label") or "来源",
                "action": item.get("value") or "-",
                "trigger": item.get("detail") or "查看详情",
                "reason": item.get("detail") or "查看详情",
                "risk": "证据时间",
                "freshness": item.get("value") or "-",
                "tone": "watch",
            }
        )
    return rows


def build_today_command_hero(
    *,
    trade_date: str,
    hero: dict[str, Any],
    top_rows: list[dict[str, Any]],
    brief_is_live: bool,
    readiness_mode: str,
) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    if readiness_mode == "blocked":
        actions = [
            {
                "label": ACTION_TIER_LABELS["act_now"],
                "title": "先恢复数据链路",
                "detail": "当前没有可信的今天动作；先去 Settings 运行安全刷新。",
                "tone": "risk",
                "tier": ACTION_TIER_LABELS["act_now"],
                "url": "/settings",
            },
            {
                "label": ACTION_TIER_LABELS["wait_trigger"],
                "title": "只读复核历史线索",
                "detail": "旧线索可查看来源，但不可作为真钱执行依据。",
                "tone": "watch",
                "tier": ACTION_TIER_LABELS["wait_trigger"],
                "url": "#action-queue",
            },
            {
                "label": ACTION_TIER_LABELS["avoid"],
                "title": "真钱执行：禁止",
                "detail": "等 readiness 回到 live_ready 后，再按仓位纪律处理。",
                "tone": "risk",
                "tier": ACTION_TIER_LABELS["avoid"],
                "url": "/settings",
            },
        ]
    elif readiness_mode == "shadow_only":
        actions = [
            {
                "label": ACTION_TIER_LABELS["act_now"],
                "title": "仅影子盘观察",
                "detail": "当前可复盘和记录观察，不做真钱执行。",
                "tone": "watch",
                "tier": ACTION_TIER_LABELS["act_now"],
                "url": "#action-queue",
            },
            {
                "label": ACTION_TIER_LABELS["wait_trigger"],
                "title": "等数据完全就绪",
                "detail": "若需要真钱执行，先在 Settings 复核 freshness 和推荐刷新任务。",
                "tone": "watch",
                "tier": ACTION_TIER_LABELS["wait_trigger"],
                "url": "/settings",
            },
            {
                "label": ACTION_TIER_LABELS["avoid"],
                "title": "真钱执行：禁止",
                "detail": "shadow_only 下只做观察和记录。",
                "tone": "risk",
                "tier": ACTION_TIER_LABELS["avoid"],
                "url": "/settings",
            },
        ]

    execute_now = next((row for row in top_rows if (row.get("tone") or "") == "positive"), None)
    wait_trigger = next((row for row in top_rows if (row.get("tone") or "") == "watch"), None)
    avoid_row = next((row for row in top_rows if (row.get("tone") or "") == "risk"), None)

    def hero_row(
        label: str,
        fallback_title: str,
        source: dict[str, Any] | None,
        tone: str,
    ) -> dict[str, Any]:
        return {
            "label": label,
            "title": str((source or {}).get("action") or fallback_title),
            "detail": str((source or {}).get("reason") or (source or {}).get("trigger") or "等待链路进一步确认。"),
            "tone": tone,
            "tier": str((source or {}).get("tier") or label),
            "url": str((source or {}).get("url") or ""),
        }

    return {
        "eyebrow": "今日作战指令",
        "title": str(hero.get("title") or "先处理已有仓位，再决定要不要看观察池"),
        "summary": str(hero.get("summary") or "今天先按优先级处理，不做无计划扩张。"),
        "trade_date": trade_date,
        "context_note": str(hero.get("context_note") or ""),
        "source_state": "总控已同步" if brief_is_live else "实时链路判断",
        "actions": actions or [
            hero_row(ACTION_TIER_LABELS["act_now"], "先处理最弱持仓", execute_now, "positive"),
            hero_row(ACTION_TIER_LABELS["wait_trigger"], "只盯最强候选，不抢跑", wait_trigger, "watch"),
            hero_row(ACTION_TIER_LABELS["avoid"], "今天不追高", avoid_row, "risk"),
        ],
    }


def build_today_radar_cards(
    *,
    position_cap: str,
    main_theme: str,
    quality_ok: int,
    confirmation_counts: dict[str, Any],
    brief_is_live: bool,
) -> list[dict[str, str]]:
    risk_value = "低" if quality_ok >= 3 and brief_is_live else ("中" if quality_ok >= 2 else "中偏高")
    risk_note = "链路完整，可按纪律执行" if risk_value == "低" else ("先控仓，再等更清晰确认" if risk_value == "中" else "今天先守纪律，不做激进动作")
    midday_fresh = int(confirmation_counts.get("fresh_candidates") or 0)
    midday_note = "暂无新增观察" if midday_fresh <= 0 else f"新增观察 {midday_fresh} 项"

    return [
        {
            "label": "仓位上限",
            "value": position_cap or "-",
            "note": "今天最多能承受的动作空间",
        },
        {
            "label": "主线方向",
            "value": main_theme or "暂无主线",
            "note": "先只围绕最强方向行动",
        },
        {
            "label": "今日风险",
            "value": risk_value,
            "note": risk_note,
        },
        {
            "label": "午盘观察",
            "value": str(midday_fresh),
            "note": midday_note,
        },
    ]


def build_today_evidence_hint(*, brief_is_live: bool, source_cards: list[dict[str, Any]]) -> dict[str, str]:
    source_labels = "、".join(item.get("label") or "" for item in source_cards[:3] if item.get("label"))
    if not source_labels:
        source_labels = "自选股快照、早盘批次与午盘确认"
    suffix = "总控判断已同步。" if brief_is_live else "当前以实时链路为准。"
    return {
        "title": "今日判断已综合",
        "summary": f"今日判断已综合{source_labels}。{suffix}",
        "cta": "查看证据与原始入口",
        "target": "today-evidence-fold",
    }


def watchlist_trigger_price(card: dict[str, Any]) -> str:
    for label, value in (
        ("止损", card.get("stop_loss")),
        ("支撑", card.get("support")),
        ("压力", card.get("resistance")),
    ):
        if value is not None and str(value).strip():
            return f"{label} {value}"
    return "查看详情"


def compress_watchlist_group(
    group: dict[str, Any],
    limit: int = 3,
    *,
    fallback_freshness: str = "-",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (group.get("cards") or [])[:limit]:
        rows.append(
            {
                "title": f"{detail_value(item.get('name'))} {detail_value(item.get('code'))}",
                "action": detail_value(item.get("action"), "查看详情"),
                "tier": action_tier_label(
                    infer_action_tier(action=item.get("action"), tone=item.get("tone"), title=item.get("name"))
                ),
                "trigger": watchlist_trigger_price(item),
                "reason": detail_value(item.get("reason"), "先看详情确认触发条件"),
                "risk": detail_value(item.get("risk"), item.get("status_line") or "继续复核"),
                "freshness": detail_value(item.get("snapshot_time"), fallback_freshness),
                "url": item.get("detail_url"),
                "tone": item.get("tone") or "watch",
            }
        )
    return rows


def compress_opportunity_group(
    group: dict[str, Any],
    limit: int = 3,
    *,
    fallback_freshness: str = "-",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (group.get("cards") or [])[:limit]:
        freshness_raw = item.get("updated_at") or item.get("snapshot_time") or fallback_freshness
        rows.append(
            {
                "title": f"{detail_value(item.get('name'))} {detail_value(item.get('code'))}",
                "action": detail_value(item.get("status"), "查看详情"),
                "tier": action_tier_label(
                    infer_action_tier(action=item.get("status"), tone=item.get("tone"), title=item.get("name"))
                ),
                "trigger": detail_value(item.get("setup_label"), "查看详情"),
                "reason": detail_value(item.get("detail"), "先看详情确认触发条件"),
                "risk": detail_value(item.get("foot"), "继续复核"),
                "freshness": detail_value(fmt_dt(freshness_raw), "-"),
                "url": item.get("detail_url"),
                "tone": item.get("tone") or "watch",
            }
        )
    return rows


def classify_today_urgent_lane(item: dict[str, Any]) -> str:
    url = str(item.get("url") or "").strip()
    source = str(item.get("source") or "").strip()

    if url.startswith("/watchlist"):
        return "old_positions"
    if url.startswith("/opportunities"):
        return "new_positions"

    if "持仓" in source:
        return "old_positions"
    if any(token in source for token in ("早盘", "午盘", "机会")):
        return "new_positions"
    return "stand_down"


def build_today_next_steps(action_groups: list[dict[str, Any]], *, links: dict[str, str]) -> dict[str, Any]:
    grouped = {str(group.get("key") or ""): group for group in action_groups}
    urgent_items = (grouped.get("do-now") or {}).get("items") or []
    urgent_old_positions = 0
    urgent_new_positions = 0
    urgent_stand_down = 0
    for item in urgent_items:
        lane = classify_today_urgent_lane(item)
        if lane == "old_positions":
            urgent_old_positions += 1
        elif lane == "new_positions":
            urgent_new_positions += 1
        else:
            urgent_stand_down += 1

    old_positions_count = urgent_old_positions
    new_positions_count = urgent_new_positions
    stand_down_count = urgent_stand_down + len((grouped.get("avoid") or {}).get("items") or [])

    if old_positions_count > 0:
        current = "old_positions"
    elif new_positions_count > 0:
        current = "new_positions"
    else:
        current = "stand_down"

    items = [
        {
            "key": "old_positions",
            "label": "先处理旧仓",
            "detail": f"先把持仓动作收束（{old_positions_count} 条）。",
            "href": links.get("watchlist"),
            "active": current == "old_positions",
        },
        {
            "key": "new_positions",
            "label": "再看新仓",
            "detail": f"再看观察池与观察名单（{new_positions_count} 条）。",
            "href": links.get("opportunities"),
            "active": current == "new_positions",
        },
        {
            "key": "stand_down",
            "label": "先站住",
            "detail": f"优先处理回避和等待纪律（{stand_down_count} 条）。",
            "href": links.get("review"),
            "active": current == "stand_down",
        },
    ]
    current_item = next((item for item in items if item["active"]), items[-1])
    return {
        "title": "下一步动作",
        "current_key": current_item["key"],
        "current_label": current_item["label"],
        "current_href": current_item.get("href"),
        "items": items,
    }


def latest_source_freshness(source_cards: list[dict[str, Any]]) -> str:
    snapshots: list[datetime] = []
    for item in source_cards:
        parsed = parse_timestamp(item.get("value"))
        if parsed:
            snapshots.append(parsed)
    if not snapshots:
        return "-"
    return max(snapshots).strftime("%m-%d %H:%M:%S")


def build_topline_meta_pills(
    *,
    freshness: Any,
    position: Any,
    risk_boundary: Any,
) -> list[dict[str, Any]]:
    return [
        {"label": "交易日", "value": detail_value(freshness)},
        {"label": "仓位建议", "value": normalize_position_guidance(position, "待定")},
        {"label": "风险边界", "value": normalize_stock_result_copy(risk_boundary, "先守纪律边界")},
    ]


def build_detail_topline(
    *,
    badge: str,
    title: Any,
    summary: Any,
    meta_pills: list[dict[str, Any]],
    cta_links: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "verdict_badge": detail_value(badge, "当前判断"),
        "verdict_title": normalize_main_conclusion(title),
        "verdict_summary": normalize_stock_result_copy(summary, "先看当前主结论，再决定是否展开更多细节。"),
        "meta_pills": [
            {
                "label": detail_value(item.get("label"), "指标"),
                "value": normalize_stock_result_copy(item.get("value")),
            }
            for item in (meta_pills or [])
            if item
        ],
        "cta_links": [
            {
                "label": detail_value(item.get("label"), "查看详情"),
                "href": detail_value(item.get("href"), "#"),
            }
            for item in (cta_links or [])
            if item and item.get("href")
        ],
    }


def build_today_dispatch_topline(
    *,
    trade_date: str,
    hero: dict[str, Any],
    next_steps: dict[str, Any],
    links: dict[str, str],
) -> dict[str, Any]:
    dispatch_titles = {
        "old_positions": "今天先处理旧仓，再决定是否看新仓",
        "new_positions": "今天先看观察名单，需要动作也只轻仓",
        "stand_down": "今天先收手，优先等承接",
    }
    verdict_title = dispatch_titles.get(
        str(next_steps.get("current_key") or ""),
        detail_value(hero.get("title"), "今天先处理旧仓，再决定是否看新仓"),
    )
    return {
        "verdict_badge": "一句总判断",
        "verdict_title": verdict_title,
        "verdict_summary": f"先按「{next_steps.get('current_label') or '先站住'}」往下看，再看其余信息。",
        "meta_pills": build_topline_meta_pills(
            freshness=trade_date,
            position=hero.get("position_cap"),
            risk_boundary=hero.get("gate_label"),
        ),
        "cta_links": [
            {"label": "去持仓看动作", "href": links.get("watchlist")},
            {"label": "去看观察池", "href": links.get("opportunities")},
            {"label": "去问一只股票", "href": links.get("ask")},
        ],
    }


def research_review_sort_key(path: Path) -> tuple[str, str, int, str]:
    match = re.search(r"review_(\d{8})_(\d{8})(?:(_rerun))?$", path.stem)
    if not match:
        return ("", "", 0, path.stem)
    start_date = match.group(1)
    end_date = match.group(2)
    rerun_flag = 1 if match.group(3) else 0
    return (end_date, start_date, rerun_flag, path.stem)


def list_research_review_files() -> list[Path]:
    files = list(RESEARCH_REPORTS_DIR.glob("research_backfill_review_*.md"))
    return sorted(files, key=research_review_sort_key, reverse=True)


def resolve_review_option_path(identifier: str | None) -> Path | None:
    if not identifier:
        return None
    target = str(identifier).strip()
    for path in list_research_review_files():
        if path.name == target or path.stem == target:
            return path
    return None


def review_option_label(path: Path) -> str:
    match = re.search(r"review_(\d{8})_(\d{8})(?:(_rerun))?$", path.stem)
    if not match:
        return path.stem
    start = datetime.strptime(match.group(1), "%Y%m%d").strftime("%Y-%m-%d")
    end = datetime.strptime(match.group(2), "%Y%m%d").strftime("%Y-%m-%d")
    suffix = " · rerun" if match.group(3) else ""
    return f"{start} -> {end}{suffix}"


REVIEW_DETAIL_SECTIONS = {
    "ai_bucket_rows": "AI 分桶",
    "ai_regime_rows": "AI 环境",
    "ai_gate_rows": "AI 阀门",
    "ai_tier_rows": "AI 分层",
    "scan_regime_rows": "扫描环境",
    "scan_gate_rows": "扫描阀门",
    "scan_bucket_rows": "扫描策略",
}

REVIEW_RESEARCH_STALE_AFTER_SECONDS = 14 * 24 * 60 * 60
REVIEW_LIFECYCLE_STALE_AFTER_SECONDS = 2 * 24 * 60 * 60


def age_seconds_from_timestamp(value: str | None, *, now: datetime | None = None) -> int | None:
    parsed = parse_timestamp(value)
    if not parsed:
        return None
    return max(int(((now or datetime.now()) - parsed).total_seconds()), 0)


def source_age_label(seconds: int | None) -> str:
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
    return f"{hours // 24} 天前"


def build_review_source_card(
    *,
    key: str,
    label: str,
    value: str | None,
    detail: str,
    stale_after_seconds: int,
    stale_reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    value_text = detail_value(value)
    age_seconds = age_seconds_from_timestamp(value, now=now)
    available = value_text != "-"
    stale = (not available) or age_seconds is None or age_seconds > stale_after_seconds
    stale_reasons: list[str] = []
    if not available:
        stale_reasons.append("missing_source")
    elif age_seconds is None:
        stale_reasons.append("unparseable_timestamp")
    elif stale:
        stale_reasons.append(stale_reason)
    return {
        "key": key,
        "label": label,
        "value": value_text,
        "detail": detail,
        "available": available,
        "stale": stale,
        "age_seconds": age_seconds,
        "age_label": source_age_label(age_seconds),
        "stale_after_seconds": stale_after_seconds,
        "stale_reasons": stale_reasons,
    }


def build_review_source_cards(
    *,
    latest_lifecycle: dict[str, Any] | None,
    active_lifecycle: dict[str, Any] | None,
    baseline_review: dict[str, Any] | None,
    latest_review: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    now = datetime.now()
    return [
        build_review_source_card(
            key="lifecycle_latest",
            label="最新回放",
            value=(latest_lifecycle or {}).get("generated_at"),
            detail=f"{(latest_lifecycle or {}).get('activity_count') or 0} 条变化",
            stale_after_seconds=REVIEW_LIFECYCLE_STALE_AFTER_SECONDS,
            stale_reason="lifecycle_snapshot_expired",
            now=now,
        ),
        build_review_source_card(
            key="lifecycle_active",
            label="最近有动作",
            value=(active_lifecycle or {}).get("generated_at"),
            detail=f"{(active_lifecycle or {}).get('activity_count') or 0} 条变化",
            stale_after_seconds=REVIEW_LIFECYCLE_STALE_AFTER_SECONDS,
            stale_reason="lifecycle_snapshot_expired",
            now=now,
        ),
        build_review_source_card(
            key="review_baseline",
            label="基准研究",
            value=(baseline_review or {}).get("generated_at"),
            detail=review_window_text(baseline_review),
            stale_after_seconds=REVIEW_RESEARCH_STALE_AFTER_SECONDS,
            stale_reason="research_review_expired",
            now=now,
        ),
        build_review_source_card(
            key="review_latest",
            label="对比窗口",
            value=(latest_review or {}).get("generated_at"),
            detail=review_window_text(latest_review),
            stale_after_seconds=REVIEW_RESEARCH_STALE_AFTER_SECONDS,
            stale_reason="research_review_expired",
            now=now,
        ),
    ]


def build_review_freshness_alerts(source_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stale_cards = [card for card in source_cards if card.get("stale")]
    if not stale_cards:
        return []

    alerts: list[dict[str, Any]] = []
    stale_research = [card for card in stale_cards if str(card.get("key") or "").startswith("review_")]
    stale_lifecycle = [card for card in stale_cards if str(card.get("key") or "").startswith("lifecycle_")]

    if stale_research:
        windows = " / ".join(str(detail_value(card.get("detail"))) for card in stale_research[:2])
        oldest = max((int(card.get("age_seconds") or 0) for card in stale_research), default=0)
        alerts.append(
            {
                "title": "历史 research 回看不是今天的实时环境",
                "action": f"最久 {source_age_label(oldest)}",
                "trigger": windows or "research backfill",
                "reason": "AI/Scan 统计来自本地 research backfill 历史报告，只适合做规则校准。",
                "risk": "不要把这组胜率和阀门当成今天的即时行情结论；需要更新时要单独重跑 research backfill。",
                "freshness": ", ".join(str(card.get("value") or "-") for card in stale_research[:2]),
                "tone": "warning",
            }
        )

    if stale_lifecycle:
        newest = min((int(card.get("age_seconds") or 0) for card in stale_lifecycle), default=0)
        alerts.append(
            {
                "title": "变化回放快照未跟上当前数据链路",
                "action": f"最近 {source_age_label(newest)}",
                "trigger": ", ".join(str(card.get("value") or "-") for card in stale_lifecycle[:2]),
                "reason": "页面展示的进出池、升级和午盘交接来自旧 lifecycle 快照。",
                "risk": "已让早盘进攻流程产出 lifecycle；如果这里仍旧，先重跑进攻型选股。",
                "freshness": ", ".join(str(card.get("value") or "-") for card in stale_lifecycle[:2]),
                "tone": "risk",
            }
        )

    return alerts


def _jsonl_count(path: Path) -> int:
    try:
        with path.open(encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    except Exception:
        return 0


def _latest_shadow_signal_manifest() -> Path | None:
    manifests = sorted(
        SHADOW_REPLAY_ROOT.glob("*/shadow_signal_manifest.json"),
        key=lambda path: (path.parent.name, path.stat().st_mtime if path.exists() else 0),
        reverse=True,
    )
    return manifests[0] if manifests else None


def _shadow_path_from_output(value: Any, *, base: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate
    workspace_candidate = WORKSPACE_ROOT / candidate
    if workspace_candidate.exists():
        return workspace_candidate
    return base / candidate


def build_shadow_replay_review_summary() -> dict[str, Any]:
    """Compact Review payload for historical shadow sample status.

    This intentionally summarizes the local JSONL artifacts instead of
    loading sample rows into the Review response.  The samples are research
    inputs, not live Decision Ledger records.
    """

    manifest_path = _latest_shadow_signal_manifest()
    if not manifest_path:
        return {
            "status": "missing",
            "title": "2025 影子样本未生成",
            "summary": "还没有可用于 Review 的 shadow replay 样本。",
            "warning": "不会影响真实 Decision Ledger；这里只显示研究样本状态。",
            "cards": [
                {"label": "样本", "value": "0", "detail": "尚未生成", "tone": "stale"},
                {"label": "标签", "value": "0", "detail": "尚未生成", "tone": "stale"},
            ],
            "artifacts": [],
        }

    manifest = load_json(manifest_path) or {}
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}
    args = manifest.get("args") if isinstance(manifest.get("args"), dict) else {}
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    root = manifest_path.parent

    panel_path = _shadow_path_from_output(outputs.get("panel"), base=root)
    labels_path = _shadow_path_from_output(outputs.get("labels"), base=root)
    report_path = _shadow_path_from_output(outputs.get("report"), base=root)
    backfill_manifest_path = root / "manifest.json"
    backfill_manifest = load_json(backfill_manifest_path) or {}
    backfill_summary = (
        backfill_manifest.get("summary")
        if isinstance(backfill_manifest.get("summary"), dict)
        else {}
    )

    panel_rows = int(summary.get("panel_rows") or (_jsonl_count(panel_path) if panel_path else 0))
    label_rows = int(summary.get("label_rows") or (_jsonl_count(labels_path) if labels_path else 0))
    available_labels = int(summary.get("available_labels") or 0)
    trade_dates = int(summary.get("trade_dates_with_samples") or 0)
    sample_codes = int(summary.get("sample_codes") or 0)
    price_files = int(backfill_summary.get("price_files_available") or 0)
    price_rows = int(backfill_summary.get("price_rows_available") or 0)
    universe_codes = int(backfill_summary.get("unique_universe_codes") or 0)
    bucket_counts = dict(summary.get("bucket_counts") or {})
    action_counts = dict(summary.get("action_counts") or {})
    classification_counts = dict(summary.get("classification_counts") or {})
    setup_counts = dict(summary.get("setup_counts") or {})
    start_date = str(args.get("start_date") or summary.get("start_date") or "")[:10]
    end_date = str(args.get("end_date") or summary.get("end_date") or "")[:10]

    artifacts = []
    for title, path, key in (
        ("影子样本面板 JSONL", panel_path, "shadow_signal_panel"),
        ("影子样本 outcome JSONL", labels_path, "shadow_forward_labels"),
        ("影子样本报告", report_path, "shadow_signal_report"),
        ("影子样本 manifest", manifest_path, "shadow_signal_manifest"),
        ("影子原料 manifest", backfill_manifest_path, "shadow_replay_manifest"),
    ):
        item = artifact_from_path(title, path, key=key)
        if item:
            artifacts.append(item)

    return {
        "status": "ready" if panel_rows and available_labels else "partial",
        "title": "2025 价格影子样本",
        "summary": (
            f"{start_date or '-'} 至 {end_date or '-'}，"
            f"{trade_dates} 个交易日，{panel_rows} 条样本，{available_labels} 条 T+1/T+3/T+5 标签。"
        ),
        "warning": "研究专用：price-signal baseline，不是正式 Prism AI 回放；universe 为 current_constituents_approx。",
        "sample_origin": "historical_shadow",
        "source_lane": "shadow_price_signal_baseline",
        "universe_policy": "current_constituents_approx",
        "start_date": start_date,
        "end_date": end_date,
        "cards": [
            {"label": "影子样本", "value": str(panel_rows), "detail": f"{sample_codes} 只股票", "tone": "info"},
            {"label": "Outcome 标签", "value": str(available_labels), "detail": f"总标签 {label_rows}", "tone": "positive" if available_labels else "stale"},
            {"label": "交易日", "value": str(trade_dates), "detail": f"{start_date} -> {end_date}", "tone": "watch"},
            {"label": "日线原料", "value": str(price_files), "detail": f"{price_rows} 行 / universe {universe_codes}", "tone": "info"},
        ],
        "bucket_counts": bucket_counts,
        "action_counts": action_counts,
        "classification_counts": classification_counts,
        "setup_counts": setup_counts,
        "artifacts": artifacts,
        "generated_at": manifest.get("generated_at"),
        "report_path": workspace_relative(report_path) if report_path else None,
        "panel_path": workspace_relative(panel_path) if panel_path else None,
        "labels_path": workspace_relative(labels_path) if labels_path else None,
    }


def review_detail_url(
    section_key: str,
    label: str,
    baseline_id: str | None = None,
    window_id: str | None = None,
    *,
    api: bool = False,
) -> str:
    base = "/api/review/detail" if api else review_page_url()
    params = [
        f"section={quote(str(section_key), safe='')}",
        f"label={quote(str(label), safe='')}",
    ]
    if baseline_id:
        params.append(f"baseline={quote(str(baseline_id), safe='')}")
    if window_id:
        params.append(f"window={quote(str(window_id), safe='')}")
    return f"{base}?{'&'.join(params)}"


def review_section_title(section_key: str) -> str:
    return REVIEW_DETAIL_SECTIONS.get(section_key, section_key)


def review_section_rows(review: dict[str, Any] | None, section_key: str) -> list[dict[str, Any]]:
    return (((review or {}).get("sections") or {}).get(section_key) or [])


def review_row_by_label(rows: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("label") == label:
            return row
    return None


def review_row_lookup(review: dict[str, Any] | None, section_key: str, label: str) -> dict[str, Any] | None:
    return review_row_by_label(review_section_rows(review, section_key), label)


def resolve_review_pair(baseline_id: str | None = None, window_id: str | None = None) -> dict[str, Any]:
    selected_baseline_path = resolve_review_option_path(baseline_id)
    selected_window_path = resolve_review_option_path(window_id)
    baseline_review = safe_canonical_load(
        load_research_review,
        path=str(selected_baseline_path) if selected_baseline_path else None,
        prefer_baseline=selected_baseline_path is None,
    )
    latest_review = safe_canonical_load(
        load_research_review,
        path=str(selected_window_path) if selected_window_path else None,
        prefer_baseline=False,
    )
    return {
        "baseline_review": baseline_review,
        "latest_review": latest_review,
        "active_baseline_id": Path((baseline_review or {}).get("path") or "").stem if (baseline_review or {}).get("path") else None,
        "active_window_id": Path((latest_review or {}).get("path") or "").stem if (latest_review or {}).get("path") else None,
        "available_reviews": list_research_review_files(),
    }


def review_delta(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None:
        return None
    return current - baseline


def review_delta_label(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}pct"


def signed_pct(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number:+.{digits}f}%"


def review_row_net_pct(row: dict[str, Any] | None, period: str = "day5") -> float | None:
    try:
        value = ((row or {}).get(period) or {}).get("net_pct")
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def review_row_line(row: dict[str, Any] | None) -> str:
    if not row:
        return "-"
    return " | ".join(
        [
            f"样本 {detail_value(row.get('sample_count'))}",
            f"次日净 {signed_pct(review_row_net_pct(row, 'next_day'))}",
            f"3日净 {signed_pct(review_row_net_pct(row, 'day3'))}",
            f"5日净 {signed_pct(review_row_net_pct(row, 'day5'))}",
        ]
    )


def review_win_net_pct(row: dict[str, Any] | None, period: str = "day5") -> float | None:
    try:
        value = ((row or {}).get(period) or {}).get("win_net_pct")
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def review_window_text(review: dict[str, Any] | None) -> str:
    start_date = (review or {}).get("start_date")
    end_date = (review or {}).get("end_date")
    if start_date and end_date:
        return f"{start_date} -> {end_date}"
    return detail_value((review or {}).get("window_label"))


def lifecycle_group_tone(group_key: str) -> str:
    return {
        "entered": "positive",
        "upgraded": "positive",
        "downgraded": "risk",
        "exited": "risk",
        "handed_off": "watch",
    }.get(group_key, "watch")


def lifecycle_group_title(group_key: str) -> str:
    return {
        "entered": "新进入",
        "upgraded": "升级",
        "downgraded": "降级",
        "exited": "退出",
        "handed_off": "午盘交接",
    }.get(group_key, group_key)


def lifecycle_item_metrics(item: dict[str, Any], group_key: str) -> list[str]:
    if group_key == "entered":
        return [
            f"层级 {detail_value(item.get('tier'))}",
            f"状态 {candidate_status_label(item.get('screening_status'))}",
            f"分数 {detail_value(item.get('score'))}",
        ]
    if group_key == "upgraded":
        return [
            f"层级 {detail_value(item.get('prev_tier'))} -> {detail_value(item.get('curr_tier'))}",
            (
                "状态 "
                f"{candidate_status_label(item.get('prev_screening_status'))}"
                f" -> {candidate_status_label(item.get('curr_screening_status'))}"
            ),
            f"分数变化 {detail_value(item.get('score_delta'))}",
        ]
    if group_key == "downgraded":
        return [
            f"当前层级 {detail_value(item.get('curr_tier'))}",
            f"当前状态 {candidate_status_label(item.get('curr_screening_status'))}",
            f"分数变化 {detail_value(item.get('score_delta'))}",
        ]
    if group_key == "exited":
        return [
            f"最后分数 {detail_value(item.get('score'))}",
            f"主题 {detail_value(item.get('theme'))}",
            f"最后出现 {detail_value(item.get('last_seen'))}",
        ]
    return [
        f"早盘层级 {detail_value(item.get('tier'))}",
        f"午盘状态 {candidate_status_label(item.get('status'))}",
        f"仍在当前池 {'是' if item.get('in_current_shortlist') else '否'}",
    ]


def lifecycle_item_copy(item: dict[str, Any], group_key: str) -> str:
    if group_key == "entered":
        return detail_value(item.get("entry_reason") or item.get("theme"), "进入原因待补")
    if group_key == "upgraded":
        return detail_value(item.get("theme"), "升级原因待补")
    if group_key == "downgraded":
        return detail_value(item.get("reason") or item.get("theme"), "降级原因待补")
    if group_key == "exited":
        return "已从当前 shortlist 退出，后续只保留历史留痕。"
    return detail_value(item.get("reason"), "已进入午盘承接观察。")


def lifecycle_item_foot(item: dict[str, Any], group_key: str) -> str:
    if group_key == "entered":
        return detail_value(item.get("main_risk"), "等待次日承接验证")
    if group_key == "upgraded":
        return detail_value(item.get("theme"), "强度正在抬升")
    if group_key == "downgraded":
        return detail_value(item.get("reason"), "需要重新评估承接")
    if group_key == "exited":
        return detail_value(item.get("theme"), "不再进入当前执行名单")
    return detail_value(item.get("current_screening_status"), "已完成午盘交接")


def build_lifecycle_group(group_key: str, lifecycle: dict[str, Any] | None) -> dict[str, Any]:
    items = (((lifecycle or {}).get("groups") or {}).get(group_key) or [])
    cards = [
        {
            "name": item.get("name") or item.get("code"),
            "code": item.get("code"),
            "tone": lifecycle_group_tone(group_key),
            "status": lifecycle_group_title(group_key),
            "copy": lifecycle_item_copy(item, group_key),
            "metrics": lifecycle_item_metrics(item, group_key),
            "foot": lifecycle_item_foot(item, group_key),
        }
        for item in items
    ]
    return {
        "key": group_key,
        "title": lifecycle_group_title(group_key),
        "subtitle": {
            "entered": "新增进入当前观察池的名字",
            "upgraded": "同一批次里强度或状态更好的名字",
            "downgraded": "盘中承接变弱，需要降级对待",
            "exited": "已经从当前 shortlist 离开的名字",
            "handed_off": "从早盘进入午盘承接观察的名字",
        }.get(group_key, "最近变化"),
        "count": len(cards),
        "cards": cards,
        "empty": f"当前没有{lifecycle_group_title(group_key)}记录。",
    }


def resolve_lifecycle_context() -> dict[str, Any]:
    latest_lifecycle = safe_canonical_load(load_lifecycle)
    active_lifecycle = safe_canonical_load(load_lifecycle, require_activity=True)
    display_lifecycle = latest_lifecycle
    lifecycle_note = "当前直接展示最新变化回放快照。"
    if (
        latest_lifecycle
        and active_lifecycle
        and (latest_lifecycle.get("activity_count") or 0) == 0
        and latest_lifecycle.get("path") != active_lifecycle.get("path")
    ):
        display_lifecycle = active_lifecycle
        lifecycle_note = (
            "最新变化回放文件没有动作，页面已诚实回退到最近一次有动作的快照，避免把空白文件误当成“没有故事”。"
        )
    return {
        "latest_lifecycle": latest_lifecycle,
        "active_lifecycle": active_lifecycle,
        "display_lifecycle": display_lifecycle,
        "lifecycle_note": lifecycle_note,
    }


def build_today_change_group(
    group_key: str,
    lifecycle: dict[str, Any] | None,
    *,
    limit: int = 2,
) -> dict[str, Any]:
    group = build_lifecycle_group(group_key, lifecycle)
    cards = group.get("cards") or []
    hidden_count = max(0, len(cards) - limit)
    return {
        **group,
        "cards": cards[:limit],
        "hidden_count": hidden_count,
    }


def build_today_change_view(lifecycle: dict[str, Any] | None, *, links: dict[str, Any], note: str) -> dict[str, Any]:
    display_summary = (lifecycle or {}).get("summary") or {}
    total_changes = int((lifecycle or {}).get("activity_count") or 0)
    page_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    replay_timestamp = detail_value((lifecycle or {}).get("current_timestamp"), "-")
    positive_total = sum(
        len((((lifecycle or {}).get("groups") or {}).get(key) or []))
        for key in ("entered", "upgraded")
    )
    risk_total = sum(
        len((((lifecycle or {}).get("groups") or {}).get(key) or []))
        for key in ("downgraded", "exited")
        )
    handoff_total = len((((lifecycle or {}).get("groups") or {}).get("handed_off") or []))

    groups = []
    for key in ("downgraded", "entered", "upgraded", "handed_off", "exited"):
        group = build_today_change_group(key, lifecycle)
        if group["count"]:
            groups.append(group)
        if len(groups) >= 3:
            break

    if not groups:
        groups = [
            {
                "key": "none",
                "title": "暂无显著变化",
                "subtitle": "当前展示的变化回放里没有新增、升级、降级或退出。",
                "count": 0,
                "cards": [],
                "hidden_count": 0,
                "empty": "今天还没有需要特别上提的结构变化，保持按主判断和行动清单执行即可。",
            }
        ]

    return {
        "title": "最近变化",
        "subtitle": "只上提和上一轮不一样的名字，避免把整页从头再读一遍。",
        "note": note,
        "summary_cards": [
            {
                "label": "总变化",
                "value": str(total_changes),
                "detail": "和上一轮相比有动作的名字",
            },
            {
                "label": "新增 / 升级",
                "value": str(positive_total),
                "detail": "更值得重新关注的变化",
            },
            {
                "label": "降级 / 退出",
                "value": str(risk_total),
                "detail": "需要先收手或降级处理",
            },
            {
                "label": "当前池",
                "value": str(display_summary.get("current_pool_size") or 0),
                "detail": (
                    f"上一轮 {detail_value(display_summary.get('previous_pool_size'), '0')}"
                    f" | 午盘交接 {handoff_total}"
                ),
            },
        ],
        "groups": groups,
        "meta_tags": [
            f"展示源 {('最近有动作快照' if note.startswith('最新变化回放文件没有动作') else '最新快照')}",
            f"午盘匹配 {'是' if (lifecycle or {}).get('midday_matches_current_ai') else '否'}",
            f"页面时间 {page_timestamp}",
            f"回放时间 {replay_timestamp}",
        ],
        "links": {
            "review": links.get("review"),
        },
    }


def build_review_group_entries(
    review: dict[str, Any] | None,
    section_key: str,
    *,
    baseline_id: str | None,
    window_id: str | None,
) -> list[dict[str, Any]]:
    return [
        {
            "label": row.get("label") or "-",
            "summary": review_row_line(row),
            "detail_url": review_detail_url(section_key, row.get("label") or "-", baseline_id, window_id),
        }
        for row in review_section_rows(review, section_key)
    ]


def review_row_detail_link(
    row: dict[str, Any] | None,
    section_key: str,
    baseline_id: str | None,
    window_id: str | None,
) -> str | None:
    label = (row or {}).get("label")
    if not label:
        return None
    return review_detail_url(section_key, label, baseline_id, window_id)


def build_review_selector_groups(
    active_baseline_id: str | None,
    active_window_id: str | None,
    available_reviews: list[Path],
    *,
    url_builder,
) -> list[dict[str, Any]]:
    return [
        {
            "title": "基准窗口",
            "subtitle": "选择一份历史研究报告作为基准，和右侧对比窗口保持同一统计口径。",
            "options": [
                {
                    "label": review_option_label(path),
                    "url": url_builder(path.stem, active_window_id),
                    "active": path.stem == active_baseline_id,
                }
                for path in available_reviews
            ],
        },
        {
            "title": "对比窗口",
            "subtitle": "默认是最新时间窗切片，用来观察优势是否在改善或继续走弱。",
            "options": [
                {
                    "label": review_option_label(path),
                    "url": url_builder(active_baseline_id, path.stem),
                    "active": path.stem == active_window_id,
                }
                for path in available_reviews
            ],
        },
    ]


def build_review_panel(
    review: dict[str, Any] | None,
    *,
    eyebrow: str,
    title: str,
    baseline_id: str | None,
    window_id: str | None,
) -> dict[str, Any]:
    summary = (review or {}).get("summary") or {}
    ai_overall = summary.get("ai_overall")
    scan_overall = summary.get("scan_overall")
    best_regime = summary.get("ai_best_regime_day5")
    best_gate = summary.get("ai_best_gate_day5")
    worst_gate = summary.get("ai_worst_gate_day5")
    best_strategy = summary.get("scan_best_strategy_day5")

    return {
        "eyebrow": eyebrow,
        "title": title,
        "summary": (
            f"{review_window_text(review)}，AI 5日净 {signed_pct(review_row_net_pct(ai_overall, 'day5'))}，"
            f"扫描 5日净 {signed_pct(review_row_net_pct(scan_overall, 'day5'))}。"
        ),
        "metric_cards": [
            {
                "label": "AI 5日净",
                "value": signed_pct(review_row_net_pct(ai_overall, "day5")),
                "detail": review_row_line(ai_overall),
            },
            {
                "label": "扫描 5日净",
                "value": signed_pct(review_row_net_pct(scan_overall, "day5")),
                "detail": review_row_line(scan_overall),
            },
            {
                "label": "最佳环境",
                "value": signed_pct(review_row_net_pct(best_regime, "day5")),
                "detail": detail_value((best_regime or {}).get("label"), "暂无"),
                "detail_url": review_row_detail_link(best_regime, "ai_regime_rows", baseline_id, window_id),
                "detail_link_text": f"查看 {detail_value((best_regime or {}).get('label'), '对应分组')}",
            },
            {
                "label": "最优阀门",
                "value": signed_pct(review_row_net_pct(best_gate, "day5")),
                "detail": detail_value((best_gate or {}).get("label"), "暂无"),
                "detail_url": review_row_detail_link(best_gate, "ai_gate_rows", baseline_id, window_id),
                "detail_link_text": f"查看 {detail_value((best_gate or {}).get('label'), '对应分组')}",
            },
            {
                "label": "最差阀门",
                "value": signed_pct(review_row_net_pct(worst_gate, "day5")),
                "detail": detail_value((worst_gate or {}).get("label"), "暂无"),
                "detail_url": review_row_detail_link(worst_gate, "ai_gate_rows", baseline_id, window_id),
                "detail_link_text": f"查看 {detail_value((worst_gate or {}).get('label'), '对应分组')}",
            },
            {
                "label": "最优策略",
                "value": signed_pct(review_row_net_pct(best_strategy, "day5")),
                "detail": detail_value((best_strategy or {}).get("label"), "暂无"),
                "detail_url": review_row_detail_link(best_strategy, "scan_bucket_rows", baseline_id, window_id),
                "detail_link_text": f"查看 {detail_value((best_strategy or {}).get('label'), '对应分组')}",
            },
        ],
        "groups": [
            {
                "title": "AI 分桶",
                "entries": build_review_group_entries(
                    review,
                    "ai_bucket_rows",
                    baseline_id=baseline_id,
                    window_id=window_id,
                ),
                "empty": "暂无 AI 分桶统计。",
            },
            {
                "title": "AI 环境",
                "entries": build_review_group_entries(
                    review,
                    "ai_regime_rows",
                    baseline_id=baseline_id,
                    window_id=window_id,
                ),
                "empty": "暂无 AI 环境统计。",
            },
            {
                "title": "AI 阀门",
                "entries": build_review_group_entries(
                    review,
                    "ai_gate_rows",
                    baseline_id=baseline_id,
                    window_id=window_id,
                ),
                "empty": "暂无 AI 阀门统计。",
            },
            {
                "title": "AI 分层",
                "entries": build_review_group_entries(
                    review,
                    "ai_tier_rows",
                    baseline_id=baseline_id,
                    window_id=window_id,
                ),
                "empty": "暂无 AI 分层统计。",
            },
            {
                "title": "扫描环境",
                "entries": build_review_group_entries(
                    review,
                    "scan_regime_rows",
                    baseline_id=baseline_id,
                    window_id=window_id,
                ),
                "empty": "暂无扫描环境统计。",
            },
            {
                "title": "扫描阀门",
                "entries": build_review_group_entries(
                    review,
                    "scan_gate_rows",
                    baseline_id=baseline_id,
                    window_id=window_id,
                ),
                "empty": "暂无扫描阀门统计。",
            },
            {
                "title": "扫描策略",
                "entries": build_review_group_entries(
                    review,
                    "scan_bucket_rows",
                    baseline_id=baseline_id,
                    window_id=window_id,
                ),
                "empty": "暂无扫描策略统计。",
            },
            {
                "title": "压测备注",
                "entries": [
                    {"label": normalize_review_note_text(item), "summary": "", "detail_url": None}
                    for item in text_items((review or {}).get("notes"))[:4]
                ],
                "empty": "暂无额外备注。",
            },
        ],
        "artifact_url": artifact_url((review or {}).get("path")),
        "artifact_path": (review or {}).get("path"),
    }


def build_review_row_cards(row: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not row:
        return []
    next_day = (row.get("next_day") or {})
    day3 = (row.get("day3") or {})
    day5 = (row.get("day5") or {})
    return [
        {
            "label": "总样本",
            "value": detail_value(row.get("sample_count")),
            "detail": detail_value(row.get("valid_samples")),
        },
        {
            "label": "次日净",
            "value": signed_pct(next_day.get("net_pct")),
            "detail": f"原始 {signed_pct(next_day.get('raw_pct'))} | 净胜率 {signed_pct(next_day.get('win_net_pct'))}",
        },
        {
            "label": "3日净",
            "value": signed_pct(day3.get("net_pct")),
            "detail": f"原始 {signed_pct(day3.get('raw_pct'))}",
        },
        {
            "label": "5日净",
            "value": signed_pct(day5.get("net_pct")),
            "detail": f"原始 {signed_pct(day5.get('raw_pct'))} | 净胜率 {signed_pct(day5.get('win_net_pct'))}",
        },
    ]


def review_value_tone(value: float | None) -> str:
    if value is None:
        return "watch"
    if value > 0:
        return "positive"
    if value <= -0.5:
        return "risk"
    return "watch"


def build_review_verdict_cards(
    baseline_review: dict[str, Any] | None,
    latest_review: dict[str, Any] | None,
    *,
    baseline_id: str | None,
    window_id: str | None,
) -> list[dict[str, Any]]:
    baseline_summary = (baseline_review or {}).get("summary") or {}
    latest_summary = (latest_review or {}).get("summary") or {}
    baseline_label = "基准"
    latest_label = "对比"

    weak_base = baseline_summary.get("weak_regime_ai")
    weak_latest = latest_summary.get("weak_regime_ai")
    weak_base_value = review_row_net_pct(weak_base, "day5")
    weak_latest_value = review_row_net_pct(weak_latest, "day5")
    weak_delta = review_delta(weak_latest_value, weak_base_value)

    trial_base = baseline_summary.get("trial_regime_ai")
    trial_latest = latest_summary.get("trial_regime_ai")
    trial_base_value = review_row_net_pct(trial_base, "day5")
    trial_latest_value = review_row_net_pct(trial_latest, "day5")
    trial_delta = review_delta(trial_latest_value, trial_base_value)

    attack_base = baseline_summary.get("attack_regime_ai")
    attack_latest = latest_summary.get("attack_regime_ai")
    attack_base_value = review_row_net_pct(attack_base, "day5")
    attack_latest_value = review_row_net_pct(attack_latest, "day5")
    attack_delta = review_delta(attack_latest_value, attack_base_value)

    best_gate_base = baseline_summary.get("ai_best_gate_day5")
    best_gate_latest = latest_summary.get("ai_best_gate_day5")
    worst_gate_base = baseline_summary.get("ai_worst_gate_day5")
    worst_gate_latest = latest_summary.get("ai_worst_gate_day5")
    best_gate_value = review_row_net_pct(best_gate_latest or best_gate_base, "day5")
    worst_gate_value = review_row_net_pct(worst_gate_latest or worst_gate_base, "day5")

    best_strategy_base = baseline_summary.get("scan_best_strategy_day5")
    best_strategy_latest = latest_summary.get("scan_best_strategy_day5")
    best_strategy_base_value = review_row_net_pct(best_strategy_base, "day5")
    best_strategy_latest_value = review_row_net_pct(best_strategy_latest, "day5")
    best_strategy_delta = review_delta(best_strategy_latest_value, best_strategy_base_value)

    weak_is_risk = weak_latest_value is None or weak_latest_value < 0
    trial_tone = review_value_tone(trial_latest_value)
    attack_tone = "watch" if attack_latest is None else review_value_tone(attack_latest_value)
    gate_tone = "positive" if best_gate_value is not None and worst_gate_value is not None and best_gate_value > worst_gate_value else review_value_tone(best_gate_value)
    strategy_tone = review_value_tone(best_strategy_latest_value)

    return [
        {
            "title": "弱环境继续回避" if weak_is_risk else "弱环境边际转暖",
            "subtitle": detail_value((weak_latest or weak_base or {}).get("label"), "弱环境"),
            "status": "回避" if weak_is_risk else "观察",
            "tone": "risk" if weak_is_risk else "watch",
            "copy": (
                f"{review_window_text(latest_review)} 的弱环境 5日净为 {signed_pct(weak_latest_value)}，"
                f"相对基准 {review_delta_label(weak_delta)}。"
            ),
            "metrics": [
                f"{baseline_label} {signed_pct(weak_base_value)}",
                f"{latest_label} {signed_pct(weak_latest_value)}",
                f"变化 {review_delta_label(weak_delta)}",
            ],
            "foot": "只要弱环境没稳定转正，就别把新仓阀门放开。",
            "detail_url": review_row_detail_link(weak_latest or weak_base, "ai_regime_rows", baseline_id, window_id),
        },
        {
            "title": "只在试错环境试单" if trial_latest_value is not None and trial_latest_value > 0 else "试错环境也要轻仓",
            "subtitle": detail_value((trial_latest or trial_base or {}).get("label"), "试错环境"),
            "status": "试错",
            "tone": trial_tone,
            "copy": (
                f"对比窗口最优环境仍落在 {detail_value((trial_latest or trial_base or {}).get('label'), '试错环境')}，"
                f"5日净 {signed_pct(trial_latest_value)}。"
            ),
            "metrics": [
                f"{baseline_label} {signed_pct(trial_base_value)}",
                f"{latest_label} {signed_pct(trial_latest_value)}",
                f"变化 {review_delta_label(trial_delta)}",
            ],
            "foot": "先把试错环境当默认试单区，再回到单票执行质量。",
            "detail_url": review_row_detail_link(trial_latest or trial_base, "ai_regime_rows", baseline_id, window_id),
        },
        {
            "title": "对比窗口没有进攻环境样本" if attack_latest is None else ("进攻环境转暖，但先按阀门控量" if attack_latest_value is not None and attack_latest_value > 0 else "进攻环境别追高"),
            "subtitle": detail_value((attack_latest or attack_base or {}).get("label"), "进攻环境"),
            "status": "缺样本" if attack_latest is None else "进攻",
            "tone": attack_tone,
            "copy": (
                "对比窗口里没有 6-8 进攻环境样本，别把主观进攻冲动当成已经验证过的优势。"
                if attack_latest is None
                else f"对比窗口进攻环境 5日净为 {signed_pct(attack_latest_value)}，需要先看历史是否真的支持升级动作。"
            ),
            "metrics": [
                f"{baseline_label} {signed_pct(attack_base_value)}",
                f"{latest_label} {signed_pct(attack_latest_value)}" if attack_latest is not None else f"{latest_label}无样本",
                f"变化 {review_delta_label(attack_delta)}",
            ],
            "foot": "点进去会看到对比窗口这一侧缺行，而不是被误写成 0。",
            "detail_url": review_row_detail_link(attack_latest or attack_base, "ai_regime_rows", baseline_id, window_id),
        },
        {
            "title": f"阀门优先{detail_value((best_gate_latest or best_gate_base or {}).get('label'), '对比窗口最优档位')}",
            "subtitle": "先决定档位，再讨论情绪",
            "status": "阀门",
            "tone": gate_tone,
            "copy": (
                f"对比窗口最优阀门是 {detail_value((best_gate_latest or best_gate_base or {}).get('label'), '暂无')}，"
                f"最差阀门是 {detail_value((worst_gate_latest or worst_gate_base or {}).get('label'), '暂无')}。"
            ),
            "metrics": [
                f"最好 {signed_pct(best_gate_value)}",
                f"最差 {signed_pct(worst_gate_value)}",
                f"对比 {detail_value((best_gate_latest or best_gate_base or {}).get('label'), '暂无')}",
            ],
            "foot": "与其争论开不开，不如先把最优阀门当默认执行档位。",
            "detail_url": review_row_detail_link(best_gate_latest or best_gate_base, "ai_gate_rows", baseline_id, window_id),
        },
        {
            "title": f"对比窗口优先看{detail_value((best_strategy_latest or best_strategy_base or {}).get('label'), '最优策略')}策略",
            "subtitle": "先沿最优策略筛，再回到单票",
            "status": "策略",
            "tone": strategy_tone,
            "copy": (
                f"{review_window_text(latest_review)} 里最优策略仍是 "
                f"{detail_value((best_strategy_latest or best_strategy_base or {}).get('label'), '暂无')}，"
                f"对比 5日净 {signed_pct(best_strategy_latest_value)}。"
            ),
            "metrics": [
                f"{baseline_label} {signed_pct(best_strategy_base_value)}",
                f"{latest_label} {signed_pct(best_strategy_latest_value)}",
                f"变化 {review_delta_label(best_strategy_delta)}",
            ],
            "foot": "先按策略做第一轮过滤，再去看具体 setup 和执行质量。",
            "detail_url": review_row_detail_link(best_strategy_latest or best_strategy_base, "scan_bucket_rows", baseline_id, window_id),
        },
    ]


def review_action_from_tone(tone: str | None) -> str:
    normalized = (tone or "").strip().lower()
    if normalized in {"positive", "good"}:
        return "按阀门分档"
    if normalized == "risk":
        return "少动，先防守"
    if normalized in {"watch", "warn"}:
        return "轻仓试错"
    return "先等确认"


def review_action_from_card(card: dict[str, Any]) -> str:
    status = str(card.get("status") or "").strip()
    tone = card.get("tone")
    if status == "回避":
        return "少动，先防守"
    if status == "试错":
        return "轻仓试错"
    if status == "缺样本":
        return "先等确认"
    if status == "进攻":
        normalized = str(tone or "").strip().lower()
        return "按阀门分档" if normalized in {"positive", "good"} else "先等确认"
    return review_action_from_tone(tone)


def review_change_tone(value: str | None) -> str:
    text = (value or "").strip()
    if text.startswith("+"):
        return "positive"
    if text.startswith("-"):
        return "risk"
    if any(token in text for token in ("改善", "提升", "转正")):
        return "positive"
    if any(token in text for token in ("走弱", "恶化", "下降")):
        return "risk"
    return "watch"


def build_review_action_rules(verdict_cards: list[dict[str, Any]], *, freshness: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for card in verdict_cards[:3]:
        metrics = card.get("metrics") or []
        trigger = detail_value(
            metrics[1] if len(metrics) > 1 else (metrics[0] if metrics else None),
            detail_value(card.get("subtitle"), "环境口径"),
        )
        rows.append(
            {
                "title": (
                    f"{detail_value(card.get('title'), '环境结论')} · "
                    f"{detail_value(card.get('subtitle'), '环境口径')}"
                ),
                "action": review_action_from_card(card),
                "trigger": trigger,
                "reason": detail_value(card.get("copy"), "先回看明细再决定是否升级动作。"),
                "risk": detail_value(card.get("foot"), "条件变化时降档处理。"),
                "freshness": freshness,
                "url": card.get("detail_url"),
                "tone": card.get("tone") or "watch",
            }
        )

    defaults = [
        {
            "title": "弱环境规则",
            "action": "少动，先防守",
            "trigger": "弱环境未稳定转正",
            "reason": "先控制回撤，再谈开仓。",
            "risk": "把噪音当趋势会放大回撤。",
            "freshness": freshness,
            "url": None,
            "tone": "risk",
        },
        {
            "title": "试错环境规则",
            "action": "轻仓试错",
            "trigger": "试错环境有正反馈",
            "reason": "先验证承接，再逐步放大。",
            "risk": "确认不足时不追高。",
            "freshness": freshness,
            "url": None,
            "tone": "watch",
        },
        {
            "title": "进攻环境规则",
            "action": "先等确认",
            "trigger": "进攻环境样本还不稳定",
            "reason": "先确认样本和阀门，再决定是否升级动作。",
            "risk": "样本缺失时把主观冲动当优势最容易放大回撤。",
            "freshness": freshness,
            "url": None,
            "tone": "positive",
        },
    ]
    while len(rows) < 3:
        rows.append(defaults[len(rows)])
    return rows[:3]


def build_review_change_log(comparison_cards: list[dict[str, Any]]) -> dict[str, Any]:
    entries = []
    for item in comparison_cards:
        entries.append(
            {
                "title": item.get("label") or "变化项",
                "change": item.get("value") or "-",
                "detail": item.get("detail") or "暂无说明。",
                "tone": review_change_tone(item.get("value")),
                "url": item.get("detail_url"),
            }
        )
    return {
        "note": "只看最近窗口相对基准窗口的变化，不把短期噪音误判为长期优势。",
        "entries": entries[:3],
        "empty": "当前没有可比变化。",
    }


def build_review_detail_view(
    section_key: str,
    label: str,
    baseline_id: str | None = None,
    window_id: str | None = None,
) -> dict[str, Any]:
    if section_key not in REVIEW_DETAIL_SECTIONS:
        raise KeyError(f"unknown review section: {section_key}")

    review_pair = resolve_review_pair(baseline_id=baseline_id, window_id=window_id)
    baseline_review = review_pair["baseline_review"]
    latest_review = review_pair["latest_review"]
    active_baseline_id = review_pair["active_baseline_id"]
    active_window_id = review_pair["active_window_id"]
    available_reviews = review_pair["available_reviews"]

    baseline_row = review_row_lookup(baseline_review, section_key, label)
    latest_row = review_row_lookup(latest_review, section_key, label)
    if not baseline_row and not latest_row:
        raise KeyError(f"review row not found: {section_key} / {label}")

    if active_baseline_id and active_window_id and active_baseline_id == active_window_id:
        comparison_note = "当前基准窗口和对比窗口选的是同一份报告，变化值只剩定位作用，更适合先看原始行。"
    else:
        comparison_note = "这页只对比同一个分组；如果某一侧缺行，会明确展示为空，不把缺失误写成 0。"

    if baseline_row and latest_row:
        missing_note = None
    elif baseline_row:
        missing_note = "对比窗口里没有这条分组，说明它在当前切片中已经消失，或样本不足以进入统计。"
    else:
        missing_note = "基准窗口里没有这条分组，说明它是在后续窗口里才出现的新结构。"

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "section_key": section_key,
        "label": label,
        "hero": {
            "eyebrow": review_section_title(section_key),
            "title": f"{review_section_title(section_key)} · {label}",
            "summary": (
                f"同一口径下，对比 {review_window_text(baseline_review)} 与 {review_window_text(latest_review)} 的净收益与胜率变化。"
            ),
        },
        "selector_groups": build_review_selector_groups(
            active_baseline_id,
            active_window_id,
            available_reviews,
            url_builder=lambda baseline, window: review_detail_url(section_key, label, baseline, window),
        ),
        "comparison_note": comparison_note,
        "missing_note": missing_note,
        "source_cards": [
            {
                "label": "基准窗口",
                "value": review_window_text(baseline_review),
                "detail": detail_value((baseline_review or {}).get("generated_at")),
            },
            {
                "label": "对比窗口",
                "value": review_window_text(latest_review),
                "detail": detail_value((latest_review or {}).get("generated_at")),
            },
            {
                "label": "基准样本",
                "value": detail_value((baseline_row or {}).get("sample_count")),
                "detail": review_row_line(baseline_row),
            },
            {
                "label": "对比样本",
                "value": detail_value((latest_row or {}).get("sample_count")),
                "detail": review_row_line(latest_row),
            },
        ],
        "summary_cards": [
            {
                "label": "次日净变化",
                "value": review_delta_label(review_delta(review_row_net_pct(latest_row, "next_day"), review_row_net_pct(baseline_row, "next_day"))),
                "detail": f"{signed_pct(review_row_net_pct(baseline_row, 'next_day'))} -> {signed_pct(review_row_net_pct(latest_row, 'next_day'))}",
            },
            {
                "label": "3日净变化",
                "value": review_delta_label(review_delta(review_row_net_pct(latest_row, "day3"), review_row_net_pct(baseline_row, "day3"))),
                "detail": f"{signed_pct(review_row_net_pct(baseline_row, 'day3'))} -> {signed_pct(review_row_net_pct(latest_row, 'day3'))}",
            },
            {
                "label": "5日净变化",
                "value": review_delta_label(review_delta(review_row_net_pct(latest_row, "day5"), review_row_net_pct(baseline_row, "day5"))),
                "detail": f"{signed_pct(review_row_net_pct(baseline_row, 'day5'))} -> {signed_pct(review_row_net_pct(latest_row, 'day5'))}",
            },
            {
                "label": "5日净胜率变化",
                "value": review_delta_label(review_delta(review_win_net_pct(latest_row, "day5"), review_win_net_pct(baseline_row, "day5"))),
                "detail": f"{signed_pct(review_win_net_pct(baseline_row, 'day5'))} -> {signed_pct(review_win_net_pct(latest_row, 'day5'))}",
            },
        ],
        "comparison_panels": [
            {
                "title": "基准窗口",
                "subtitle": review_window_text(baseline_review),
                "cards": build_review_row_cards(baseline_row),
                "empty": "基准窗口当前没有这条分组。",
                "artifact_url": artifact_url((baseline_review or {}).get("path")),
                "artifact_path": (baseline_review or {}).get("path"),
            },
            {
                "title": "对比窗口",
                "subtitle": review_window_text(latest_review),
                "cards": build_review_row_cards(latest_row),
                "empty": "对比窗口当前没有这条分组。",
                "artifact_url": artifact_url((latest_review or {}).get("path")),
                "artifact_path": (latest_review or {}).get("path"),
            },
        ],
        "links": {
            **today_nav_links(),
            "review": review_page_with_params(active_baseline_id, active_window_id),
            "self": review_detail_url(section_key, label, active_baseline_id, active_window_id),
            "api_self": review_detail_url(section_key, label, active_baseline_id, active_window_id, api=True),
        },
        "artifacts": [
            item
            for item in (
                artifact_from_path("基准研究", (baseline_review or {}).get("path"), key="review_baseline"),
                artifact_from_path("对比研究", (latest_review or {}).get("path"), key="review_latest"),
            )
            if item
        ],
    }


def build_watchlist_manager_view(watchlist: dict[str, Any] | None = None) -> dict[str, Any]:
    active_stocks = list_active_watchlist_stocks()
    archived_stocks = list_archived_watchlist_stocks()
    snapshot_map = {item.get("code"): item for item in ((watchlist or {}).get("stocks") or []) if item.get("code")}
    refresh_run = latest_run_for_task(WATCHLIST_REFRESH_TASK_NAME)
    refresh_progress = watchlist_refresh_progress(refresh_run)

    if refresh_run:
        status = str(refresh_run.get("status") or "unknown")
        status_label = {
            "running": "刷新中",
            "success": "最近完成",
            "failed": "最近失败",
            "unknown": "状态待查",
        }.get(status, "状态待查")
        status_tone = {
            "running": "watch",
            "success": "positive",
            "failed": "risk",
            "unknown": "watch",
        }.get(status, "watch")
        status_value = refresh_run.get("checked_started_at") or refresh_run.get("checked_finished_at") or "-"
        status_detail = refresh_progress.get("summary") or refresh_run.get("summary") or "后台刷新已触发，请稍后刷新页面查看。"
        log_url = artifact_url(refresh_run.get("log_path"))
    else:
        status = "idle"
        status_label = "等待触发"
        status_tone = "watch"
        status_value = detail_value((watchlist or {}).get("generated_at"), "尚未触发")
        status_detail = "添加、恢复或归档后，会自动重跑自选股全流程和总控简报。"
        log_url = None

    active_items = []
    pending_count = 0
    for item in active_stocks:
        code = str(item.get("code") or "").strip()
        snapshot_item = snapshot_map.get(code)
        display_name = detail_value((snapshot_item or {}).get("name") or item.get("name"), code)
        if snapshot_item:
            reason = (
                (snapshot_item.get("hard_flags") or [None])[0]
                or (snapshot_item.get("watch_points") or [None])[0]
                or (snapshot_item.get("positives") or [None])[0]
                or snapshot_item.get("action")
                or "已纳入当前快照"
            )
            state_label = snapshot_item.get("action") or "已纳入当前快照"
            state_detail = f"{reason} | 快照 {detail_value((watchlist or {}).get('generated_at'), '-')}"
            tone = action_tone(snapshot_item.get("action"))
        else:
            pending_count += 1
            state_label = "等待刷新"
            state_detail = "当前快照还没有这只股票，刷新完成后会补上报告、新闻和动作判断。"
            tone = "watch"

        active_items.append(
            {
                "code": code,
                "name": display_name,
                "market": detail_value(item.get("market"), "-").upper(),
                "state_label": state_label,
                "state_detail": state_detail,
                "tone": tone,
                "updated_at": detail_value(item.get("updated_at") or item.get("created_at"), "-"),
            }
        )

    archived_items = [
        {
            "code": str(item.get("code") or "").strip(),
            "name": detail_value(item.get("name"), str(item.get("code") or "").strip()),
            "market": detail_value(item.get("market"), "-").upper(),
            "state_label": f"归档于 {detail_value(item.get('archived_at') or item.get('updated_at'), '-')}",
            "state_detail": "当前页面与后续报告/新闻会隐藏这只股票，历史文件仍然保留。",
            "tone": "risk",
        }
        for item in archived_stocks
        if item.get("code")
    ]

    return {
        "summary": "这里是自选股名单本身。添加后会立即重跑全流程，归档只隐藏当前展示，不删除历史文件。",
        "feedback_hint": "添加新票会自动抓数、更新快照、重生成摘要和总控简报。",
        "active_count": len(active_items),
        "archived_count": len(archived_items),
        "pending_count": pending_count,
        "summary_cards": [
            {
                "label": "活跃中",
                "value": str(len(active_items)),
                "detail": "当前参与自选股链路",
            },
            {
                "label": "待刷新",
                "value": str(pending_count),
                "detail": "名单已变更，等待新快照补齐",
            },
            {
                "label": "已归档",
                "value": str(len(archived_items)),
                "detail": "隐藏当前展示，保留历史",
            },
        ],
        "refresh_status": {
            "status": status,
            "label": status_label,
            "value": status_value,
            "detail": status_detail,
            "tone": status_tone,
            "log_path": str(refresh_run.get("log_path") or "") if refresh_run else "",
            "log_url": log_url,
            "steps": refresh_progress.get("steps") or [],
        },
        "active_items": active_items,
        "archived_items": archived_items,
        "empty_active": "当前没有活跃自选股，先加一只股票开始跑链路。",
        "empty_archived": "当前没有归档股票。",
        "add_api": "/api/watchlist/manage/add",
        "archive_api": "/api/watchlist/manage/archive",
        "restore_api": "/api/watchlist/manage/restore",
    }


def build_watchlist_day_over_day_diff(today: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve the previous dated snapshot and diff it against ``today``.

    The page view always carries a ``diff`` field — when no previous
    snapshot exists, the diff has empty change buckets but still records
    today's trade date so the frontend can render a clean "first day, no
    diff" empty state instead of being missing the field entirely.

    Errors during previous-snapshot load are swallowed deliberately:
    a stale or partially-written prior file should not block today's
    page render.
    """

    if not today:
        return diff_watchlist_snapshots({}, previous=None)

    snapshot_path = today.get("snapshot_path")
    previous_payload: dict[str, Any] | None = None
    if snapshot_path:
        try:
            previous_path = resolve_previous_watchlist_snapshot_path(Path(snapshot_path))
        except Exception:
            previous_path = None
        if previous_path is not None:
            try:
                previous_payload = load_watchlist_snapshot(path=str(previous_path))
            except Exception:
                previous_payload = None
    return diff_watchlist_snapshots(today, previous=previous_payload)


def build_watchlist_page_view() -> dict[str, Any]:
    trade_date_hint = expected_trade_date()
    decision_brief = safe_canonical_load(load_decision_brief, trade_date=trade_date_hint)
    watchlist = load_watchlist_snapshot(trade_date=trade_date_hint)
    screening_batch = safe_canonical_load(load_screening_batch, trade_date=trade_date_hint)
    confirmation = safe_canonical_load(load_confirmation, trade_date=trade_date_hint)
    quality = safe_canonical_load(load_quality_status, lane="watchlist")

    readiness_for_page = compute_readiness(
        watchlist=watchlist,
        screening_batch=screening_batch,
        confirmation=confirmation,
        decision_brief=decision_brief,
        quality_status=safe_canonical_load(load_quality_status, lane="all"),
        account_book=load_account_book(),
        today_action_decisions=load_today_action_decision_store(),
        dataset_freshness=build_dataset_freshness_rows(
            expected_date=trade_date_hint,
            now=datetime.now(),
        ),
    )
    expected_date_w = readiness_for_page["expected_trade_date"]
    trade_date = readiness_for_page["data_trade_date"] or current_trade_date(watchlist, screening_batch, decision_brief)
    brief_trade_date = (decision_brief or {}).get("trade_date")
    brief_is_live = bool(readiness_for_page["brief_is_live"])
    brief_focus = (((decision_brief or {}).get("focus") or {}).get("holding_focus") or []) if brief_is_live else []
    avoid_points = (((decision_brief or {}).get("focus") or {}).get("avoid_points") or []) if brief_is_live else []

    priority_codes = set(watchlist.get("priority_codes") or [])
    follow_codes = set(watchlist.get("follow_codes") or [])
    observe_codes = set(watchlist.get("observe_codes") or [])
    stocks = watchlist.get("stocks") or []

    if brief_is_live:
        hero_title = normalize_stock_ui_copy(((decision_brief or {}).get("summary") or {}).get("watchlist_summary")) or "先处理风险和仓位，再决定是否继续拿"
        hero_summary = "当前页面优先展示完整持仓动作，只回答已有股票今天怎么管。"
        context_note = f"总控持仓焦点：{'、'.join(brief_focus) if brief_focus else '暂无额外焦点'}。"
    else:
        hero_title = "先处理风险和仓位，再决定是否继续拿"
        hero_summary = f"当前页面直接读取最新自选股快照，优先处理 {len(priority_codes)} 只，其余按轻仓跟踪和继续观察展开。"
        context_note = "总控层若未更新到当日，持仓页仍以实时自选股快照为准。"

    groups = []
    for key, title, subtitle, empty_copy in (
        ("priority", "优先处理", "先处理风险和仓位", "当前没有优先处理股票。"),
        ("follow", "跟踪增强", "允许轻仓跟踪的标的", "当前没有进入轻仓跟踪的股票。"),
        ("observe", "继续观察", "暂不动作，等待明确信号", "当前没有继续观察股票。"),
    ):
        if key == "priority":
            target_codes = priority_codes
        elif key == "follow":
            target_codes = follow_codes
        else:
            target_codes = observe_codes

        group_stocks = [item for item in stocks if item.get("code") in target_codes]
        groups.append(
            {
                "key": key,
                "title": title,
                "subtitle": subtitle,
                "count": len(group_stocks),
                "cards": [build_watchlist_stock_card(item, screening_batch, confirmation) for item in group_stocks],
                "empty": empty_copy,
            }
        )

    in_discovery = sum(1 for item in stocks if find_screening_candidate(screening_batch, item.get("code") or ""))
    in_midday = sum(1 for item in stocks if find_confirmation_match(confirmation, item.get("code") or ""))

    artifacts = [
        artifact_from_path("自选股快照 JSON", watchlist.get("snapshot_path"), key="watchlist_snapshot"),
        artifact_from_path("总控简报 JSON", ((decision_brief or {}).get("paths") or {}).get("source_json"), key="decision_brief"),
        artifact_from_path("自选股质检 JSON", (quality or {}).get("path"), key="watchlist_quality"),
    ]
    links = {
        **today_nav_links(),
        "self": watchlist_page_url(),
        "api_self": api_watchlist_page_url(),
    }
    source_cards = [
        {
            "label": "自选股快照",
            "value": watchlist.get("generated_at") or "-",
            "detail": watchlist.get("trade_date") or "暂无快照",
        },
        {
            "label": "总控简报",
            "value": (decision_brief or {}).get("generated_at") or "-",
            "detail": "已同步" if brief_is_live else "数据偏旧",
        },
        {
            "label": "观察池链路",
            "value": str(in_discovery),
            "detail": "进入早盘观察池链路的自选股数量",
        },
        {
            "label": "午盘链路",
            "value": str(in_midday),
            "detail": "进入午盘承接链路的自选股数量",
        },
    ]
    summary_cards = [
        {
            "label": "总股票数",
            "value": str(watchlist.get("stock_count") or 0),
            "detail": "当前自选股快照",
        },
        {
            "label": "优先处理",
            "value": str(len(priority_codes)),
            "detail": "先处理风险与仓位",
        },
        {
            "label": "跟踪增强",
            "value": str(len(follow_codes)),
            "detail": "允许轻仓跟踪",
        },
        {
            "label": "继续观察",
            "value": str(len(observe_codes)),
            "detail": "等待更明确信号",
        },
    ]
    priority_rows = compress_watchlist_group(
        groups[0],
        limit=3,
        fallback_freshness=watchlist.get("generated_at") or "-",
    )
    follow_rows = compress_watchlist_group(
        groups[1],
        limit=3,
        fallback_freshness=watchlist.get("generated_at") or "-",
    )
    observe_rows = compress_watchlist_group(
        groups[2],
        limit=3,
        fallback_freshness=watchlist.get("generated_at") or "-",
    )
    quality_status = (quality or {}).get("validation_status")
    quality_label = quality_status_label(quality_status)
    quality_tone = quality_status_tone(quality_status)
    status_strip = build_status_strip(
        {
            "label": "来源",
            "value": "总控 + 快照" if brief_is_live else "实时快照",
            "note": watchlist.get("generated_at") or "-",
            "tone": "good" if brief_is_live else "warn",
        },
        {
            "label": "质量",
            "value": quality_label,
            "note": ((quality or {}).get("checked_at")) or "待检查",
            "tone": "risk" if quality_tone == "risk" else ("warn" if quality_tone == "watch" else "good"),
        },
        {
            "label": "新鲜度",
            "value": latest_source_freshness(source_cards),
            "note": f"交易日 {trade_date}",
            "tone": "good" if watchlist.get("generated_at") else "warn",
        },
    )
    topline = {
        "verdict_badge": "持仓判断",
        "verdict_title": (
            f"先处理 {len(priority_codes)} 只优先持仓，再看其余观察。"
            if priority_codes
            else "当前无强制优先持仓，先保持观察节奏。"
        ),
        "verdict_summary": (
            "首屏只保留最靠前的持仓动作，其他管理与回源入口全部折叠到后续层。"
        ),
        "meta_pills": [
            {"label": "交易日", "value": trade_date},
            {"label": "持仓总数", "value": str(watchlist.get("stock_count") or 0)},
            {"label": "优先处理", "value": str(len(priority_codes))},
        ],
        "cta_links": [
            {"label": "去看其余持仓", "href": "#watchlist-follow"},
            {"label": "去管理持仓名单", "href": "#watchlist-manager"},
        ],
    }

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "generated_at": generated_at,
        "display_date": current_display_date(),
        "trade_date": trade_date,
        "brief_is_live": brief_is_live,
        "reading_compass": build_reading_compass_cards(
            conclusion=topline.get("verdict_title"),
            conclusion_detail=topline.get("verdict_summary"),
            action_focus="优先处理 Top 3",
            action_detail="先处理优先持仓，再看跟踪与观察，不在首屏把管理层混进来。",
            risk_boundary=(status_strip[1].get("value") if len(status_strip) > 1 else "先核对质量"),
            risk_detail=(status_strip[1].get("note") if len(status_strip) > 1 else "链路未确认前先不要扩动作。"),
            evidence_entry="质检与原始数据",
            evidence_detail="需要回看快照、质检和原始文件时，直接展开证据层。",
        ),
        "hero": {
            "title": hero_title,
            "summary": hero_summary,
            "context_note": context_note,
            "snapshot_time": watchlist.get("generated_at") or "-",
            "stock_count": watchlist.get("stock_count") or 0,
            "priority_count": len(priority_codes),
        },
        "source_cards": source_cards,
        "summary_cards": summary_cards,
        "groups": groups,
        "topline": topline,
        "priority_rows": priority_rows,
        "follow_rows": follow_rows,
        "observe_rows": observe_rows,
        "status_strip": status_strip,
        "follow_observe_count": groups[1]["count"] + groups[2]["count"],
        "focus_tags": text_items(brief_focus),
        "avoid_points": text_items(avoid_points),
        "day_over_day_diff": build_watchlist_day_over_day_diff(watchlist),
        "manager": build_watchlist_manager_view(watchlist),
        "confidence_switch": build_watchlist_confidence_switch(
            decision_brief,
            watchlist,
            quality,
            brief_is_live=brief_is_live,
            links=links,
        ),
        "quality_card": lane_quality_card("自选股质检", quality),
        "artifacts": [item for item in artifacts if item],
        "links": links,
    }


def build_opportunities_view() -> dict[str, Any]:
    trade_date_hint = expected_trade_date()
    decision_brief = safe_canonical_load(load_decision_brief, trade_date=trade_date_hint)
    watchlist = safe_canonical_load(load_watchlist_snapshot, trade_date=trade_date_hint)
    screening_batch = load_screening_batch(trade_date=trade_date_hint)
    confirmation = safe_canonical_load(load_confirmation, trade_date=trade_date_hint)
    aggressive_quality = safe_canonical_load(load_quality_status, lane="aggressive")
    midday_quality = safe_canonical_load(load_quality_status, lane="midday_confirmation")
    learning_index = build_review_learning_memory_index()

    readiness_for_opps = compute_readiness(
        watchlist=watchlist,
        screening_batch=screening_batch,
        confirmation=confirmation,
        decision_brief=decision_brief,
        quality_status=safe_canonical_load(load_quality_status, lane="all"),
        account_book=load_account_book(),
        today_action_decisions=load_today_action_decision_store(),
        dataset_freshness=build_dataset_freshness_rows(
            expected_date=trade_date_hint,
            now=datetime.now(),
        ),
    )
    expected_date_o = readiness_for_opps["expected_trade_date"]
    trade_date = readiness_for_opps["data_trade_date"] or current_trade_date(watchlist, screening_batch, decision_brief)
    brief_trade_date = (decision_brief or {}).get("trade_date")
    brief_is_live = bool(readiness_for_opps["brief_is_live"])
    gate = ((screening_batch.get("market_regime") or {}).get("execution_gate") or {})
    summary = screening_batch.get("screening_summary") or {}
    focus = (((decision_brief or {}).get("focus") or {}).get("opportunity_focus") or []) if brief_is_live else []
    avoid_points = (((decision_brief or {}).get("focus") or {}).get("avoid_points") or []) if brief_is_live else []

    approved = [item for item in (screening_batch.get("candidates") or []) if item.get("screening_status") == "approved"]
    caution = [item for item in (screening_batch.get("candidates") or []) if item.get("screening_status") == "caution"]
    confirmed = (confirmation or {}).get("confirmed") or []
    fresh_candidates = (confirmation or {}).get("fresh_candidates") or []
    downgraded = (confirmation or {}).get("downgraded") or []

    if gate.get("allow_new_positions"):
        hero_title = "今天值得继续盯的名字"
    else:
        hero_title = "阀门关闭，今天只保留观察名单"

    hero_summary = (
        normalize_stock_ui_copy(
            gate.get("summary")
            or (((decision_brief or {}).get("summary") or {}).get("gate_summary"))
        )
        or "这里只展示候选观察，不代表直接推荐开新仓。"
    )
    context_note = (
        f"总控观察焦点：{'、'.join(focus) if focus else '暂无额外焦点'}。"
        if brief_is_live
        else "若总控层未更新到当日，这里仍以实时早盘扫描和午盘确认链路为准。"
    )

    artifacts = [
        artifact_from_path("早盘批次 JSON", screening_batch.get("path"), key="screening_batch"),
        artifact_from_path("午盘确认 JSON", (confirmation or {}).get("path"), key="confirmation"),
        artifact_from_path("总控简报 JSON", ((decision_brief or {}).get("paths") or {}).get("source_json"), key="decision_brief"),
        artifact_from_path("早盘质检 JSON", (aggressive_quality or {}).get("path"), key="aggressive_quality"),
        artifact_from_path("午盘质检 JSON", (midday_quality or {}).get("path"), key="midday_quality"),
    ]
    source_cards = [
        {
            "label": "早盘批次",
            "value": screening_batch.get("generated_at") or "-",
            "detail": screening_batch.get("pool_label") or screening_batch.get("pool") or "暂无批次",
        },
        {
            "label": "午盘确认",
            "value": (confirmation or {}).get("generated_at") or "-",
            "detail": (confirmation or {}).get("validation_status") or "暂无确认",
        },
        {
            "label": "总控简报",
            "value": (decision_brief or {}).get("generated_at") or "-",
            "detail": "已同步" if brief_is_live else "数据偏旧",
        },
        {
            "label": "进攻阀门",
            "value": gate.get("label") or "实时判断",
            "detail": gate.get("position_cap") or "仓位上限待定",
        },
    ]
    groups = [
        {
            "key": "morning",
            "title": "早盘进入",
            "count": len(approved),
            "cards": [build_screening_candidate_card(item, learning_index=learning_index) for item in approved],
            "empty": "当前没有早盘进入候选的名字。",
        },
        {
            "key": "watching",
            "title": "继续观察",
            "count": len(caution),
            "cards": [build_screening_candidate_card(item, learning_index=learning_index) for item in caution],
            "empty": "当前没有继续观察候选。",
        },
        {
            "key": "midday_new",
            "title": "午盘新增",
            "count": len(fresh_candidates),
            "cards": [build_confirmation_candidate_card(item, learning_index=learning_index) for item in fresh_candidates],
            "empty": "当前没有午盘新增观察。",
        },
        {
            "key": "upgrade",
            "title": "可升级",
            "count": len(confirmed),
            "cards": [build_confirmation_candidate_card(item, learning_index=learning_index) for item in confirmed],
            "empty": "当前没有午盘仍可跟踪候选。",
        },
        {
            "key": "eliminated",
            "title": "已淘汰",
            "count": len(downgraded),
            "cards": [build_confirmation_candidate_card(item, learning_index=learning_index) for item in downgraded],
            "empty": "当前没有需要剔除的候选。",
        },
    ]
    quality_cards = [
        lane_quality_card("早盘质检", aggressive_quality),
        lane_quality_card("午盘质检", midday_quality),
    ]

    screening_freshness = screening_batch.get("generated_at") or "-"
    confirmation_freshness = (confirmation or {}).get("generated_at") or screening_freshness
    allow_new_positions = bool(gate.get("allow_new_positions"))
    top_rows = []
    promote_watch = not allow_new_positions
    if allow_new_positions:
        top_rows = compress_opportunity_group(groups[0], limit=3, fallback_freshness=screening_freshness)
        promote_watch = len(top_rows) == 0
    if promote_watch:
        watch_mix = {
            "cards": [
                *(groups[1].get("cards") or []),
                *(groups[2].get("cards") or []),
                *(groups[3].get("cards") or []),
            ]
        }
        top_rows = compress_opportunity_group(watch_mix, limit=3, fallback_freshness=confirmation_freshness)

    if allow_new_positions and not promote_watch:
        verdict_title = "今天继续看观察名单，如要动作也仅限轻仓试错。"
        verdict_summary = "先看最值得继续观察的三只名字，再决定是否扩展到其余观察与午盘承接。"
    elif allow_new_positions:
        verdict_title = "今天先看观察名单，不急着开新仓。"
        verdict_summary = "先看 3 只继续观察的名字，等待更强承接后再决定是否轻仓试错。"
    else:
        verdict_title = "今天先看观察名单，不急着开新仓。"
        verdict_summary = "进攻阀门关闭，先看观察与午盘承接，不主动开新仓。"

    quality_ok = sum(1 for item in quality_cards if str(item.get("status") or "").strip().lower() == "ok")
    quality_tone = "good" if quality_ok >= 2 else ("warn" if quality_ok == 1 else "risk")
    status_strip = build_status_strip(
        {
            "label": "来源",
            "value": "总控 + 实时链路" if brief_is_live else "实时链路",
            "note": (decision_brief or {}).get("generated_at") or screening_batch.get("generated_at") or "-",
            "tone": "good" if brief_is_live else "warn",
        },
        {
            "label": "质量",
            "value": f"{quality_ok}/2 就绪",
            "note": "早盘+午盘质检",
            "tone": quality_tone,
        },
        {
            "label": "新鲜度",
            "value": latest_source_freshness(source_cards),
            "note": f"交易日 {trade_date}",
            "tone": "good" if screening_batch.get("generated_at") else "warn",
        },
    )
    secondary_groups = [
        {
            "title": groups[1]["title"],
            "count": groups[1]["count"],
            "rows": compress_opportunity_group(groups[1], limit=3, fallback_freshness=screening_freshness),
            "empty": groups[1]["empty"],
        },
        {
            "title": groups[2]["title"],
            "count": groups[2]["count"],
            "rows": compress_opportunity_group(groups[2], limit=3, fallback_freshness=confirmation_freshness),
            "empty": groups[2]["empty"],
        },
        {
            "title": groups[3]["title"],
            "count": groups[3]["count"],
            "rows": compress_opportunity_group(groups[3], limit=3, fallback_freshness=confirmation_freshness),
            "empty": groups[3]["empty"],
        },
        {
            "title": groups[4]["title"],
            "count": groups[4]["count"],
            "rows": compress_opportunity_group(groups[4], limit=3, fallback_freshness=confirmation_freshness),
            "empty": groups[4]["empty"],
        },
    ]
    links = {
        **today_nav_links(),
        "self": opportunities_page_url(),
        "api_self": api_opportunities_page_url(),
    }

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "generated_at": generated_at,
        "display_date": current_display_date(),
        "trade_date": trade_date,
        "brief_is_live": brief_is_live,
        "reading_compass": build_reading_compass_cards(
            conclusion=verdict_title,
            conclusion_detail=verdict_summary,
            action_focus="Top 3 继续观察",
            action_detail=(
                "先看优先观察的名字，再决定是否展开观察与午盘承接。"
                if not promote_watch
                else "今天先保留观察与午盘承接，不主动切到新仓执行。"
            ),
            risk_boundary=(gate.get("label") or "实时阀门"),
            risk_detail=(gate.get("position_cap") or "先按阀门控制动作节奏。"),
            evidence_entry="质检与原始数据",
            evidence_detail="主线、质检和原始批次都放在证据层，需要时再展开核对。",
        ),
        "hero": {
            "title": hero_title,
            "summary": hero_summary,
            "context_note": context_note,
            "gate_label": gate.get("label") or "实时阀门",
            "position_cap": gate.get("position_cap") or "-",
            "main_theme": (((screening_batch.get("market_themes") or {}).get("top_theme")) or "暂无主线"),
        },
        "source_cards": source_cards,
        "summary_cards": [
            {
                "label": "必须复核",
                "value": str(len(caution) + len(fresh_candidates) + len(confirmed)),
                "detail": "今天需要看完的观察任务",
            },
            {
                "label": "午盘新增",
                "value": str((confirmation or {}).get("counts", {}).get("fresh_candidates") or len(fresh_candidates)),
                "detail": "午盘新进入观察视野",
            },
            {
                "label": "可升级",
                "value": str((confirmation or {}).get("counts", {}).get("confirmed") or len(confirmed)),
                "detail": "承接仍成立，等待阀门",
            },
            {
                "label": "应剔除",
                "value": str((confirmation or {}).get("counts", {}).get("downgraded") or len(downgraded)),
                "detail": "失效或降级的观察项",
            },
        ],
        "topline": {
            "verdict_badge": "观察池结论",
            "verdict_title": verdict_title,
            "verdict_summary": verdict_summary,
            "meta_pills": [
                {"label": "交易日", "value": trade_date},
                {"label": "进攻阀门", "value": gate.get("label") or "实时判断"},
                {"label": "早盘候选", "value": str(len(groups[0].get("cards") or []))},
            ],
            "cta_links": [
                {"label": "去看其余观察", "href": "#opportunities-secondary"},
                {"label": "去看主线判断", "href": "#opportunities-themes"},
                {"label": "去看证据来源", "href": "#opportunities-support"},
            ],
        },
        "top_rows": top_rows,
        "promote_watch": promote_watch,
        "status_strip": status_strip,
        "learning_memories": global_learning_memories(learning_index, limit=3),
        "learning_memory_summary": {
            "case_count": len(learning_index.get("cases") or []),
            "pattern_count": len(learning_index.get("patterns") or []),
            "error": learning_index.get("error"),
        },
        "secondary_groups": secondary_groups,
        "secondary_total": sum(int(item.get("count") or 0) for item in secondary_groups),
        "theme_cards": build_theme_cards(screening_batch, limit=4),
        "groups": groups,
        "focus_tags": text_items(focus),
        "avoid_points": text_items(avoid_points),
        "confidence_switch": build_opportunities_confidence_switch(
            decision_brief,
            screening_batch,
            aggressive_quality,
            midday_quality,
            brief_is_live=brief_is_live,
            links=links,
        ),
        "quality_cards": quality_cards,
        "artifacts": [item for item in artifacts if item],
        "links": links,
    }


def build_review_view(baseline_id: str | None = None, window_id: str | None = None) -> dict[str, Any]:
    lifecycle_context = resolve_lifecycle_context()
    latest_lifecycle = lifecycle_context["latest_lifecycle"]
    active_lifecycle = lifecycle_context["active_lifecycle"]
    review_pair = resolve_review_pair(baseline_id=baseline_id, window_id=window_id)
    baseline_review = review_pair["baseline_review"]
    latest_review = review_pair["latest_review"]
    active_baseline_id = review_pair["active_baseline_id"]
    active_window_id = review_pair["active_window_id"]
    available_reviews = review_pair["available_reviews"]

    display_lifecycle = lifecycle_context["display_lifecycle"]
    lifecycle_note = lifecycle_context["lifecycle_note"]

    baseline_summary = (baseline_review or {}).get("summary") or {}
    latest_summary = (latest_review or {}).get("summary") or {}
    baseline_ai_day5 = review_row_net_pct(baseline_summary.get("ai_overall"), "day5")
    weak_regime = baseline_summary.get("weak_regime_ai")
    baseline_weak_day5 = review_row_net_pct(weak_regime, "day5")
    baseline_best_regime = baseline_summary.get("ai_best_regime_day5")
    baseline_worst_gate = baseline_summary.get("ai_worst_gate_day5")
    baseline_best_strategy = baseline_summary.get("scan_best_strategy_day5")
    baseline_scan_day5 = review_row_net_pct(baseline_summary.get("scan_overall"), "day5")
    latest_ai_day5 = review_row_net_pct(latest_summary.get("ai_overall"), "day5")
    latest_weak_day5 = review_row_net_pct(latest_summary.get("weak_regime_ai"), "day5")
    latest_trial_day5 = review_row_net_pct(latest_summary.get("trial_regime_ai"), "day5")
    latest_attack_day5 = review_row_net_pct(latest_summary.get("attack_regime_ai"), "day5")
    latest_scan_day5 = review_row_net_pct(latest_summary.get("scan_overall"), "day5")

    if baseline_ai_day5 is not None and baseline_ai_day5 < 0 and (baseline_weak_day5 is None or baseline_weak_day5 <= 0):
        hero_title = "历史优势还没跨过摩擦成本，弱环境必须收手"
    elif baseline_ai_day5 is not None and baseline_ai_day5 > 0:
        hero_title = "历史优势已经转正，但仍要按条件控制节奏"
    else:
        hero_title = "历史优势要分环境看，不能只看总分"

    hero_summary = (
        f"基准窗口 {review_window_text(baseline_review)} AI 5日净 {signed_pct(baseline_ai_day5)}，"
        f"弱环境 {signed_pct(baseline_weak_day5)}；"
        f"对比窗口 {review_window_text(latest_review)} 为 {signed_pct(latest_ai_day5)}。"
    )

    if active_baseline_id and active_window_id and active_baseline_id == active_window_id:
        comparison_note = "当前基准窗口和对比窗口选的是同一份报告，这时更适合看最近变化回放，而不是看变化卡。"
    else:
        comparison_note = "变化卡只用于看同一口径下优势是否改善，不代表实盘可直接放宽执行。"

    artifacts = []
    seen_paths: set[str] = set()
    for title, path, key in (
        ("最新变化回放 JSON", (latest_lifecycle or {}).get("path"), "lifecycle_latest"),
        ("最近有动作的变化回放 JSON", (active_lifecycle or {}).get("path"), "lifecycle_active"),
        ("基准窗口研究", (baseline_review or {}).get("path"), "review_baseline"),
        ("对比窗口研究", (latest_review or {}).get("path"), "review_latest"),
    ):
        item = artifact_from_path(title, path, key=key)
        if not item:
            continue
        if item["path"] in seen_paths:
            continue
        seen_paths.add(item["path"])
        artifacts.append(item)

    selector_groups = build_review_selector_groups(
        active_baseline_id,
        active_window_id,
        available_reviews,
        url_builder=review_page_with_params,
    )
    links = {
        **today_nav_links(),
        "self": review_page_with_params(active_baseline_id, active_window_id),
        "api_self": review_page_with_params(active_baseline_id, active_window_id, api=True),
    }

    verdict_cards = build_review_verdict_cards(
        baseline_review,
        latest_review,
        baseline_id=active_baseline_id,
        window_id=active_window_id,
    )
    comparison_cards = [
        {
            "label": "AI 5日净变化",
            "value": review_delta_label(review_delta(latest_ai_day5, baseline_ai_day5)),
            "detail": f"{signed_pct(baseline_ai_day5)} -> {signed_pct(latest_ai_day5)}",
        },
        {
            "label": "弱环境 5日净变化",
            "value": review_delta_label(review_delta(latest_weak_day5, baseline_weak_day5)),
            "detail": f"{signed_pct(baseline_weak_day5)} -> {signed_pct(latest_weak_day5)}",
            "detail_url": review_row_detail_link(weak_regime, "ai_regime_rows", active_baseline_id, active_window_id),
            "detail_link_text": f"查看 {detail_value((weak_regime or {}).get('label'), '对应分组')}",
        },
        {
            "label": "扫描 5日净变化",
            "value": review_delta_label(review_delta(latest_scan_day5, baseline_scan_day5)),
            "detail": f"{signed_pct(baseline_scan_day5)} -> {signed_pct(latest_scan_day5)}",
        },
        {
            "label": "对比窗口",
            "value": review_window_text(latest_review),
            "detail": "对比窗口当前选中的研究时间窗",
        },
    ]
    action_rules = build_review_action_rules(
        verdict_cards,
        freshness=(latest_review or {}).get("generated_at") or "-",
    )
    change_log = build_review_change_log([item for item in comparison_cards if "变化" in str(item.get("label") or "")])

    latest_window_label = review_window_text(latest_review)
    if latest_weak_day5 is None or latest_weak_day5 < 0:
        topline_title = "历史弱环境仍未转正：规则校准先保持防守。"
        topline_summary = (
            f"对比窗口 {latest_window_label} 的 research 样本显示弱环境未转正；"
            "这里只用于复盘校准，今天动作仍以实时链路和 Decision Ledger 为准。"
        )
    elif latest_attack_day5 is not None and latest_attack_day5 > 0:
        topline_title = "历史试错与进攻环境转正：按阀门分档校准。"
        topline_summary = (
            f"对比窗口 {latest_window_label} 显示优势集中在高分环境；"
            "它能校准规则阈值，但不能直接替代今日行情判断。"
        )
    elif latest_trial_day5 is not None and latest_trial_day5 > 0:
        topline_title = "历史样本只支持试错环境：校准时只放轻仓阀门。"
        topline_summary = (
            f"对比窗口 {latest_window_label} 只在试错环境有正反馈；"
            "今日是否行动仍要回到实时数据、持仓和单票证据。"
        )
    else:
        topline_title = "历史环境优势不稳定：校准时先收紧节奏。"
        topline_summary = (
            f"对比窗口 {latest_window_label} 没有形成稳定优势结构；"
            "这是一条 research 复盘信号，不是今日实盘结论。"
        )

    mini_compare = [
        {
            "label": "基准 AI 5日净",
            "value": signed_pct(baseline_ai_day5),
            "note": review_window_text(baseline_review),
            "tone": review_value_tone(baseline_ai_day5),
        },
        {
            "label": "对比 AI 5日净",
            "value": signed_pct(latest_ai_day5),
            "note": review_window_text(latest_review),
            "tone": review_value_tone(latest_ai_day5),
        },
        {
            "label": "弱环境变化",
            "value": review_delta_label(review_delta(latest_weak_day5, baseline_weak_day5)),
            "note": f"{signed_pct(baseline_weak_day5)} -> {signed_pct(latest_weak_day5)}",
            "tone": review_change_tone(review_delta_label(review_delta(latest_weak_day5, baseline_weak_day5))),
        },
    ]

    lifecycle_groups = [
        build_lifecycle_group("entered", display_lifecycle),
        build_lifecycle_group("upgraded", display_lifecycle),
        build_lifecycle_group("downgraded", display_lifecycle),
        build_lifecycle_group("exited", display_lifecycle),
        build_lifecycle_group("handed_off", display_lifecycle),
    ]
    research_panels = [
        build_review_panel(
            baseline_review,
            eyebrow="基准研究",
            title="基准窗口",
            baseline_id=active_baseline_id,
            window_id=active_window_id,
        ),
        build_review_panel(
            latest_review,
            eyebrow="对比窗口",
            title="对比窗口",
            baseline_id=active_baseline_id,
            window_id=active_window_id,
        ),
    ]
    source_cards = build_review_source_cards(
        latest_lifecycle=latest_lifecycle,
        active_lifecycle=active_lifecycle,
        baseline_review=baseline_review,
        latest_review=latest_review,
    )
    freshness_alerts = build_review_freshness_alerts(source_cards)
    shadow_replay = build_shadow_replay_review_summary()

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "shadow_replay": shadow_replay,
        "freshness_alerts": freshness_alerts,
        "freshness_summary": {
            "stale_count": sum(1 for card in source_cards if card.get("stale")),
            "research_stale": any(
                card.get("stale") and str(card.get("key") or "").startswith("review_")
                for card in source_cards
            ),
            "lifecycle_stale": any(
                card.get("stale") and str(card.get("key") or "").startswith("lifecycle_")
                for card in source_cards
            ),
        },
        "reading_compass": build_reading_compass_cards(
            conclusion=topline_title,
            conclusion_detail=topline_summary,
            conclusion_label="历史研究结论",
            conclusion_default_detail="先确认研究窗口和数据新鲜度，再决定是否展开规则校准。",
            action_focus="三条校准规则",
            action_detail="先看规则校准方向，再决定是否展开变化、窗口和研究明细。",
            risk_boundary=(mini_compare[2].get("value") if len(mini_compare) > 2 else "先看弱环境"),
            risk_detail=(mini_compare[2].get("note") if len(mini_compare) > 2 else "环境变化没看清前，不要放宽执行。"),
            evidence_entry="研究与原始文件",
            evidence_detail="变化回放、研究拆解和原始文件都留在证据层，首屏不抢动作。",
        ),
        "hero": {
            "title": hero_title,
            "summary": hero_summary,
            "context_note": lifecycle_note,
        },
        "topline": {
            "verdict_badge": "历史研究结论",
            "verdict_title": topline_title,
            "verdict_summary": topline_summary,
            "meta_pills": [
                {"label": "弱环境", "value": signed_pct(latest_weak_day5)},
                {"label": "试错环境", "value": signed_pct(latest_trial_day5)},
                {"label": "进攻环境", "value": signed_pct(latest_attack_day5)},
            ],
            "cta_links": [
                {"label": "去看结论变化", "href": "#review-changes"},
                {"label": "去切换研究窗口", "href": "#review-control"},
                {"label": "去看研究证据", "href": "#review-evidence"},
            ],
        },
        "action_rules": action_rules,
        "change_log": change_log,
        "mini_compare": mini_compare,
        "confidence_switch": build_review_confidence_switch(
            baseline_review,
            latest_review,
            latest_lifecycle,
            active_lifecycle,
            active_baseline_id=active_baseline_id,
            active_window_id=active_window_id,
            lifecycle_note=lifecycle_note,
            links=links,
        ),
        "verdict_note": "把基准窗口与对比窗口先翻成当前判断，先看这里，再决定要不要往下拆细节。",
        "verdict_cards": verdict_cards,
        "selector_groups": selector_groups,
        "source_cards": source_cards,
        "summary_cards": [
            {
                "label": "基准 AI 5日净",
                "value": signed_pct(baseline_ai_day5),
                "detail": review_window_text(baseline_review),
            },
            {
                "label": "弱环境 AI 5日净",
                "value": signed_pct(baseline_weak_day5),
                "detail": "最差环境下先求不出手",
                "detail_url": review_row_detail_link(weak_regime, "ai_regime_rows", active_baseline_id, active_window_id),
                "detail_link_text": f"查看 {detail_value((weak_regime or {}).get('label'), '对应分组')}",
            },
            {
                "label": "最佳环境 AI 5日净",
                "value": signed_pct(review_row_net_pct(baseline_best_regime, "day5")),
                "detail": detail_value((baseline_best_regime or {}).get("label"), "暂无"),
                "detail_url": review_row_detail_link(
                    baseline_best_regime,
                    "ai_regime_rows",
                    active_baseline_id,
                    active_window_id,
                ),
                "detail_link_text": f"查看 {detail_value((baseline_best_regime or {}).get('label'), '对应分组')}",
            },
            {
                "label": "最差阀门 AI 5日净",
                "value": signed_pct(review_row_net_pct(baseline_worst_gate, "day5")),
                "detail": detail_value((baseline_worst_gate or {}).get("label"), "暂无"),
                "detail_url": review_row_detail_link(
                    baseline_worst_gate,
                    "ai_gate_rows",
                    active_baseline_id,
                    active_window_id,
                ),
                "detail_link_text": f"查看 {detail_value((baseline_worst_gate or {}).get('label'), '对应分组')}",
            },
            {
                "label": "最优策略扫描 5日净",
                "value": signed_pct(review_row_net_pct(baseline_best_strategy, "day5")),
                "detail": detail_value((baseline_best_strategy or {}).get("label"), "暂无"),
                "detail_url": review_row_detail_link(
                    baseline_best_strategy,
                    "scan_bucket_rows",
                    active_baseline_id,
                    active_window_id,
                ),
                "detail_link_text": f"查看 {detail_value((baseline_best_strategy or {}).get('label'), '对应分组')}",
            },
            {
                "label": "最近变化回放",
                "value": str((display_lifecycle or {}).get("activity_count") or 0),
                "detail": "页面当前展示使用的变化回放快照",
            },
        ],
        "comparison_note": comparison_note,
        "comparison_cards": comparison_cards,
        "lifecycle_note": lifecycle_note,
        "lifecycle_cards": [
            {
                "label": "当前池",
                "value": str((((display_lifecycle or {}).get("summary") or {}).get("current_pool_size")) or 0),
                "detail": "当前 shortlist 大小",
            },
            {
                "label": "上一池",
                "value": str((((display_lifecycle or {}).get("summary") or {}).get("previous_pool_size")) or 0),
                "detail": "上一个对照 snapshot",
            },
            {
                "label": "午盘匹配",
                "value": "是" if (display_lifecycle or {}).get("midday_matches_current_ai") else "否",
                "detail": detail_value((display_lifecycle or {}).get("midday_verification_timestamp"), "暂无午盘对照"),
            },
            {
                "label": "展示源",
                "value": "最近有动作快照"
                if display_lifecycle
                and display_lifecycle.get("path") == (active_lifecycle or {}).get("path")
                and display_lifecycle.get("path") != (latest_lifecycle or {}).get("path")
                else "最新快照",
                "detail": detail_value((display_lifecycle or {}).get("current_timestamp")),
            },
        ],
        "lifecycle_groups": lifecycle_groups,
        "research_panels": research_panels,
        "artifacts": artifacts,
        "links": links,
    }


def build_watchlist_detail_view(code: str) -> dict[str, Any]:
    trade_date_hint = expected_trade_date()
    snapshot = load_watchlist_snapshot(code=code, trade_date=trade_date_hint)
    stocks = snapshot.get("stocks") or []
    if not stocks:
        raise KeyError(f"watchlist stock not found: {code}")

    stock = stocks[0]
    rule_snapshot = stock.get("rule_snapshot") or {}
    trade_levels = stock.get("trade_levels") or {}
    reason = (
        (stock.get("hard_flags") or [None])[0]
        or (stock.get("watch_points") or [None])[0]
        or (stock.get("positives") or [None])[0]
        or rule_snapshot.get("signal")
        or "等待更多确认"
    )

    screening_batch = safe_canonical_load(load_screening_batch, trade_date=trade_date_hint)
    confirmation = safe_canonical_load(load_confirmation, trade_date=trade_date_hint)
    candidate = safe_canonical_load(find_candidate_detail, code=stock.get("code"), trade_date=trade_date_hint)
    confirmation_match = find_confirmation_match(confirmation, stock.get("code") or "")
    learning_index = build_review_learning_memory_index()
    learning_memories = candidate_learning_memories(
        stock,
        lane="watchlist",
        learning_index=learning_index,
        limit=3,
    )

    related_status = [
        {
            "label": "观察池",
            "value": candidate.get("screening_status") if candidate else "未进入当前批次",
            "tone": candidate_tone(candidate) if candidate else "watch",
            "detail": candidate.get("setup_label") if candidate else "当前早盘批次未命中",
        },
        {
            "label": "午盘确认",
            "value": (confirmation_match or {}).get("group_label") or "暂无午盘记录",
            "tone": candidate_tone((confirmation_match or {}).get("item") or {}) if confirmation_match else "watch",
            "detail": ((confirmation_match or {}).get("item") or {}).get("main_risk") or "尚未进入午盘确认链路",
        },
    ]

    artifacts = [
        artifact_from_path("自选股快照 JSON", snapshot.get("snapshot_path"), key="watchlist_snapshot"),
        artifact_from_path("早盘批次 JSON", (screening_batch or {}).get("path"), key="screening_batch"),
        artifact_from_path("午盘确认 JSON", (confirmation or {}).get("path"), key="confirmation"),
    ]
    next_trigger = (stock.get("intraday_triggers") or [None])[0] or {}
    next_step = next_trigger.get("action") or f"先按{detail_value(stock.get('action'), '观望')}纪律处理"
    next_step_detail = next_trigger.get("condition") or "先确认盘中触发条件，再决定是否调整仓位。"

    canonical_decision = build_canonical_decision(
        stock_id=stock.get("code"),
        stock_name=stock.get("name"),
        trade_date=snapshot.get("trade_date"),
        source_scope="holdings",
        main_conclusion=stock.get("action") or "观望",
        action_tier=infer_action_tier(action=next_step, tone=action_tone(stock.get("action")), status=stock.get("action"), title=stock.get("name")),
        position_guidance=stock.get("position") or "-",
        risk_boundary=trade_levels.get("stop_loss") or rule_snapshot.get("signal"),
        why_now=reason,
        continue_condition=(stock.get("watch_points") or [None])[0],
        stop_condition=trade_levels.get("stop_loss") or next_trigger.get("condition") or rule_snapshot.get("signal"),
        next_step=next_step,
        trigger_condition=next_trigger.get("condition") or trade_levels.get("resistance"),
        avoid_action=(stock.get("hard_flags") or [None])[0] or "先不要脱离纪律位硬扛",
        evidence_entry="看盘中触发与原始文件",
        confidence_note="这是今天最直接影响持仓处理的判断。",
        updated_at=snapshot.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": snapshot.get("trade_date"),
        "code": stock.get("code"),
        "name": stock.get("name"),
        "tone": action_tone(stock.get("action")),
        "learning_memories": learning_memories,
        "hero": {
            "title": f"{stock.get('name')} {stock.get('code')}",
            "summary": normalize_stock_result_copy(reason, "先按持仓链路理解这只股票。"),
            "status_label": normalize_main_conclusion(stock.get("action") or "观望"),
            "position": normalize_position_guidance(stock.get("position") or "-"),
        },
        "action_tier_legend": build_action_tier_legend(),
        "canonical_decision": canonical_decision,
        "topline": build_detail_topline(
            badge="持仓结论",
            title=stock.get("action") or "观望",
            summary=reason,
            meta_pills=build_topline_meta_pills(
                freshness=snapshot.get("trade_date"),
                position=stock.get("position") or "-",
                risk_boundary=trade_levels.get("stop_loss") or rule_snapshot.get("signal"),
            ),
            cta_links=[
                {"label": "去看持仓列表", "href": watchlist_page_url()},
                {"label": "去看观察池视角", "href": today_candidate_detail_url(stock.get("code"))} if candidate else None,
                {"label": "继续问这只股票", "href": ask_page_url(stock.get("code"))},
            ],
        ),
        "decision_cards": build_detail_decision_cards(
            conclusion=stock.get("action") or "观望",
            conclusion_detail=reason,
            position=stock.get("position"),
            position_detail="来自持仓快照的当前仓位参考。",
            risk_boundary=trade_levels.get("stop_loss") or rule_snapshot.get("signal"),
            risk_detail=(stock.get("hard_flags") or [None])[0] or "跌破纪律位或核心风险触发时，不再继续原计划。",
            next_step=next_step,
            next_step_detail=next_step_detail,
        ),
        "decision_explanation": build_detail_explanation_block(
            why=reason,
            risk=(stock.get("hard_flags") or [None])[0] or (stock.get("watch_points") or [None])[0],
            invalid=trade_levels.get("stop_loss") or next_trigger.get("condition") or rule_snapshot.get("signal"),
        ),
        "execution_loop": build_execution_loop(
            action_now=next_step,
            action_detail="先按持仓链路的处理顺序看，不先切到别的分析路径。",
            why_now=reason,
            why_detail="这一步最影响今天的持仓处理顺序。",
            trigger=next_trigger.get("condition") or trade_levels.get("support") or trade_levels.get("resistance"),
            trigger_detail="触发这些条件时，再决定是否调整动作强度。",
            avoid=(stock.get("hard_flags") or [None])[0] or "先不要脱离纪律位硬扛",
            avoid_detail="先避开最容易让持仓动作失真的行为。",
            evidence="看盘中触发与原始文件",
            evidence_detail="先看盘中触发，必要时回到快照、早盘批次和午盘确认原件。",
        ),
        "meta_cards": [
            {
                "label": "仓位建议",
                "value": detail_value(stock.get("position")),
                "detail": "来自自选股页面",
            },
            {
                "label": "技术基调",
                "value": detail_value(rule_snapshot.get("tech_base")),
                "detail": f"信号 {detail_value(rule_snapshot.get('signal'))}",
            },
            {
                "label": "资金基调",
                "value": detail_value(rule_snapshot.get("flow_base")),
                "detail": f"流向时间 {detail_value(stock.get('flow_as_of'))}",
            },
            {
                "label": "事件基调",
                "value": detail_value(rule_snapshot.get("event_base")),
                "detail": f"价格时间 {detail_value(stock.get('price_as_of'))}",
            },
        ],
        "level_cards": [
            {"label": "支撑位", "value": detail_value(trade_levels.get("support")), "detail": "防守参考"},
            {"label": "压力位", "value": detail_value(trade_levels.get("resistance")), "detail": "突破观察"},
            {"label": "止损位", "value": detail_value(trade_levels.get("stop_loss")), "detail": "纪律边界"},
            {
                "label": "规则分",
                "value": detail_value(rule_snapshot.get("score")),
                "detail": detail_value(rule_snapshot.get("score_kind")),
            },
        ],
        "related_status": related_status,
        "insight_groups": [
            {
                "title": "硬风险",
                "items": text_items(stock.get("hard_flags")),
                "empty": "当前没有硬风险标签。",
            },
            {
                "title": "观察点",
                "items": text_items(stock.get("watch_points")),
                "empty": "当前没有额外观察点。",
            },
            {
                "title": "正向因素",
                "items": text_items(stock.get("positives")),
                "empty": "当前没有额外正向因素。",
            },
        ],
        "triggers": stock.get("intraday_triggers") or [],
        "artifacts": [item for item in artifacts if item],
        "links": {
            **today_nav_links(),
            "self": today_watchlist_detail_url(stock.get("code")),
            "api_self": api_today_watchlist_detail_url(stock.get("code")),
            "ask": ask_page_url(stock.get("code")),
            "candidate_detail": today_candidate_detail_url(stock.get("code")) if candidate else None,
        },
    }


def build_candidate_detail_view(code: str) -> dict[str, Any]:
    trade_date_hint = expected_trade_date()
    candidate = find_candidate_detail(code=code, trade_date=trade_date_hint)
    screening_batch = safe_canonical_load(load_screening_batch, trade_date=trade_date_hint)
    confirmation = safe_canonical_load(load_confirmation, trade_date=trade_date_hint)
    watchlist = safe_canonical_load(load_watchlist_snapshot, trade_date=trade_date_hint)
    learning_index = build_review_learning_memory_index()

    watchlist_stock = find_watchlist_stock(watchlist, candidate.get("code") or "")
    confirmation_match = find_confirmation_match(confirmation, candidate.get("code") or "")
    execution_quality = candidate.get("execution_quality") or {}
    consistency = candidate.get("consistency") or {}
    capital_flow = candidate.get("capital_flow") or {}
    entry_plan = candidate.get("entry_plan") or {}
    in_screening = any(item.get("code") == candidate.get("code") for item in ((screening_batch or {}).get("candidates") or []))
    summary = (
        candidate.get("entry_reason")
        or candidate.get("screening_note")
        or candidate.get("main_risk")
        or candidate.get("watch_condition")
        or "等待更多确认"
    )

    artifacts = [
        artifact_from_path("早盘批次 JSON", (screening_batch or {}).get("path"), key="screening_batch") if in_screening else None,
        artifact_from_path("午盘确认 JSON", (confirmation or {}).get("path"), key="confirmation") if confirmation_match else None,
        artifact_from_path("自选股快照 JSON", (watchlist or {}).get("snapshot_path"), key="watchlist_snapshot") if watchlist_stock else None,
    ]


    canonical_decision = build_canonical_decision(
        stock_id=candidate.get("code"),
        stock_name=candidate.get("name"),
        trade_date=current_trade_date(watchlist, screening_batch, None),
        source_scope=("holdings" if watchlist_stock else "opportunity"),
        main_conclusion=(confirmation_match or {}).get("group_label")
        or candidate_status_label(candidate.get("screening_status"))
        or "继续观察",
        action_tier=infer_action_tier(
            action=entry_plan.get("action") or candidate.get("screening_status"),
            tone=candidate_tone((confirmation_match or {}).get("item") or candidate),
            status=(confirmation_match or {}).get("group_label") or candidate_status_label(candidate.get("screening_status")),
            title=candidate.get("name"),
        ),
        position_guidance=entry_plan.get("sizing") or (watchlist_stock or {}).get("position") or "轻仓试错",
        risk_boundary=(entry_plan.get("invalidate") or ((entry_plan.get("levels") or {}).get("invalidate")) or candidate.get("main_risk")),
        why_now=summary,
        continue_condition=entry_plan.get("trigger") or candidate.get("watch_condition"),
        stop_condition=entry_plan.get("invalidate") or ((entry_plan.get("levels") or {}).get("invalidate")) or candidate.get("main_risk"),
        next_step=entry_plan.get("action") or entry_plan.get("trigger") or "先观察，不急着执行",
        trigger_condition=entry_plan.get("trigger") or candidate.get("watch_condition"),
        avoid_action=entry_plan.get("avoid") or candidate.get("main_risk"),
        evidence_entry="看动作计划与原始文件",
        confidence_note="先用入选主因判断今天值不值得继续跟。",
        updated_at=(screening_batch or {}).get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": current_trade_date(watchlist, screening_batch, None),
        "code": candidate.get("code"),
        "name": candidate.get("name"),
        "tone": candidate_tone((confirmation_match or {}).get("item") or candidate),
        "learning_memories": candidate_learning_memories(
            (confirmation_match or {}).get("item") or candidate,
            lane="midday_confirmation" if confirmation_match else "aggressive",
            learning_index=learning_index,
            limit=3,
        ),
        "hero": {
            "title": f"{candidate.get('name')} {candidate.get('code')}",
            "summary": normalize_stock_result_copy(summary, "先按观察池链路理解这只股票。"),
            "status_label": normalize_main_conclusion(
                (confirmation_match or {}).get("group_label")
                or candidate_status_label(candidate.get("screening_status"))
                or "候选"
            ),
            "setup_label": candidate.get("setup_label") or candidate.get("setup_type") or "待确认",
        },
        "action_tier_legend": build_action_tier_legend(),
        "canonical_decision": canonical_decision,
        "topline": build_detail_topline(
            badge="观察池结论",
            title=(confirmation_match or {}).get("group_label")
            or candidate_status_label(candidate.get("screening_status"))
            or "继续观察",
            summary=summary,
            meta_pills=build_topline_meta_pills(
                freshness=current_trade_date(watchlist, screening_batch, None),
                position=entry_plan.get("sizing") or (watchlist_stock or {}).get("position") or "轻仓试错",
                risk_boundary=(entry_plan.get("invalidate") or ((entry_plan.get("levels") or {}).get("invalidate")) or candidate.get("main_risk")),
            ),
            cta_links=[
                {"label": "去看观察池", "href": opportunities_page_url()},
                {"label": "去看持仓视角", "href": today_watchlist_detail_url(candidate.get("code"))} if watchlist_stock else None,
                {"label": "继续问这只股票", "href": ask_page_url(candidate.get("code"))},
            ],
        ),
        "decision_cards": build_detail_decision_cards(
            conclusion=(confirmation_match or {}).get("group_label")
            or candidate_status_label(candidate.get("screening_status"))
            or "继续观察",
            conclusion_detail=summary,
            position=(entry_plan.get("sizing") or (watchlist_stock or {}).get("position") or "轻仓试错"),
            position_detail="按动作计划控仓，没进持仓前默认以试错仓参考。",
            risk_boundary=(entry_plan.get("invalidate") or ((entry_plan.get("levels") or {}).get("invalidate")) or candidate.get("main_risk")),
            risk_detail=(entry_plan.get("avoid") or candidate.get("main_risk") or "触发回避条件后，取消这次执行计划。"),
            next_step=entry_plan.get("action") or entry_plan.get("trigger") or "先观察，不急着执行",
            next_step_detail=entry_plan.get("trigger") or candidate.get("watch_condition") or "先等触发条件更清晰，再决定是否执行。",
        ),
        "decision_explanation": build_detail_explanation_block(
            why=summary,
            risk=entry_plan.get("avoid") or candidate.get("main_risk"),
            invalid=entry_plan.get("invalidate") or ((entry_plan.get("levels") or {}).get("invalidate")) or candidate.get("main_risk"),
        ),
        "execution_loop": build_execution_loop(
            action_now=entry_plan.get("action") or "先观察，不急着执行",
            action_detail="先按候选动作计划排序，不因为分数高就贸然升级动作。",
            why_now=summary,
            why_detail="先用入选主因判断今天值不值得继续跟。",
            trigger=entry_plan.get("trigger") or candidate.get("watch_condition"),
            trigger_detail="满足触发条件后，再把观察升级成下一步动作。",
            avoid=entry_plan.get("avoid") or candidate.get("main_risk"),
            avoid_detail="这些情况先不做，避免把候选误当成直接推荐。",
            evidence="看动作计划与原始文件",
            evidence_detail="先看动作计划和资金承接，需要时回到批次、自选股或午盘确认原件。",
        ),
        "source_cards": [
            {
                "label": "早盘批次",
                "value": detail_value((screening_batch or {}).get("generated_at") if in_screening else None, "未进入"),
                "detail": detail_value(candidate.get("screening_status") if in_screening else "当前批次未命中"),
            },
            {
                "label": "午盘确认",
                "value": detail_value((confirmation or {}).get("generated_at") if confirmation_match else None, "暂无"),
                "detail": detail_value((confirmation_match or {}).get("group_label"), "尚未进入午盘确认"),
            },
            {
                "label": "自选股",
                "value": detail_value((watchlist_stock or {}).get("action"), "未进入"),
                "detail": detail_value((watchlist_stock or {}).get("position"), "当前不在自选股快照"),
            },
        ],
        "metric_cards": [
            {
                "label": "优先分",
                "value": detail_value(candidate.get("priority_score") or candidate.get("best_score")),
                "detail": detail_value(candidate.get("tier"), "未分层"),
            },
            {
                "label": "执行质量",
                "value": detail_value(execution_quality.get("label"), "未评级"),
                "detail": detail_value(execution_quality.get("score")),
            },
            {
                "label": "一致性",
                "value": detail_value(consistency.get("label"), "待补充"),
                "detail": detail_value(consistency.get("score")),
            },
            {
                "label": "涨幅",
                "value": detail_value(candidate.get("change_pct")),
                "detail": f"成交 {detail_value(candidate.get('amount_yi'))} 亿",
            },
        ],
        "plan_rows": [
            {"label": "动作", "value": detail_value(entry_plan.get("action"), "当前没有单独动作计划")},
            {"label": "触发", "value": detail_value(entry_plan.get("trigger"), candidate.get("watch_condition"))},
            {"label": "回避", "value": detail_value(entry_plan.get("avoid"), candidate.get("main_risk"))},
            {"label": "失效", "value": detail_value(entry_plan.get("invalidate"))},
            {"label": "仓位", "value": detail_value(entry_plan.get("sizing"))},
        ],
        "plan_levels": [
            {"label": "触发位", "value": detail_value(((entry_plan.get("levels") or {}).get("trigger")))},
            {"label": "回踩位", "value": detail_value(((entry_plan.get("levels") or {}).get("pullback")))},
            {"label": "失效位", "value": detail_value(((entry_plan.get("levels") or {}).get("invalidate")))},
        ],
        "insight_groups": [
            {
                "title": "主题标签",
                "items": text_items(candidate.get("themes")),
                "empty": "当前没有主题标签。",
            },
            {
                "title": "策略标签",
                "items": text_items(candidate.get("strategy_labels")),
                "empty": "当前没有策略标签。",
            },
            {
                "title": "风险提示",
                "items": text_items(candidate.get("risk_flags")),
                "empty": "当前没有额外风险提示。",
            },
            {
                "title": "一致性说明",
                "items": text_items(consistency.get("notes")),
                "empty": "当前没有一致性补充说明。",
            },
            {
                "title": "执行加分项",
                "items": text_items(execution_quality.get("positives")),
                "empty": "当前没有执行加分项。",
            },
            {
                "title": "执行警示",
                "items": text_items(execution_quality.get("warnings")),
                "empty": "当前没有执行警示。",
            },
        ],
        "capital_cards": [
            {
                "label": "资金趋势",
                "value": detail_value(capital_flow.get("trend")),
                "detail": f"今日 {detail_value(capital_flow.get('today_yi') or capital_flow.get('flow_today_yi'))} 亿",
            },
            {
                "label": "5日累计",
                "value": detail_value(capital_flow.get("five_day_total_yi")),
                "detail": detail_value((confirmation_match or {}).get("group_label"), "暂无午盘标签"),
            },
        ],
        "artifacts": [item for item in artifacts if item],
        "links": {
            **today_nav_links(),
            "self": today_candidate_detail_url(candidate.get("code")),
            "api_self": api_today_candidate_detail_url(candidate.get("code")),
            "ask": ask_page_url(candidate.get("code")),
            "watchlist_detail": today_watchlist_detail_url(candidate.get("code")) if watchlist_stock else None,
        },
    }


def build_stock_profile_view(code: str) -> dict[str, Any]:
    normalized_code = str(code or "").strip()
    if not normalized_code:
        raise KeyError("stock code missing")

    trade_date_hint = expected_trade_date()
    decision_brief = safe_canonical_load(load_decision_brief, trade_date=trade_date_hint)
    watchlist = safe_canonical_load(load_watchlist_snapshot, trade_date=trade_date_hint)
    screening_batch = safe_canonical_load(load_screening_batch, trade_date=trade_date_hint)
    confirmation = safe_canonical_load(load_confirmation, trade_date=trade_date_hint)
    quality_status = safe_canonical_load(load_quality_status, lane="all")
    account_book = load_account_book()
    today_action_decisions = load_today_action_decision_store()
    readiness = compute_readiness(
        watchlist=watchlist,
        screening_batch=screening_batch,
        confirmation=confirmation,
        decision_brief=decision_brief,
        quality_status=quality_status,
        account_book=account_book,
        today_action_decisions=today_action_decisions,
        dataset_freshness=build_dataset_freshness_rows(
            expected_date=trade_date_hint,
            now=datetime.now(),
        ),
    )
    action_groups = build_today_action_groups(
        watchlist,
        screening_batch,
        confirmation,
        decision_brief,
        quality_status,
        brief_is_live=bool(readiness.get("brief_is_live")),
        gate=(((screening_batch or {}).get("market_regime") or {}).get("execution_gate") or {}),
    )
    profile_trade_date = readiness.get("data_trade_date") or current_trade_date(watchlist, screening_batch, decision_brief)
    today_context = {
        "trade_date": profile_trade_date,
        "expected_trade_date": readiness.get("expected_trade_date"),
        "action_queue": build_today_action_queue(
            action_groups,
            profile_trade_date,
            account_book=account_book,
            expected_trade_date=str(readiness.get("expected_trade_date") or ""),
            readiness_mode=str(readiness.get("readiness_mode") or "blocked"),
            readiness_ready=bool(readiness.get("ready")),
        ),
        "action_groups": action_groups,
    }

    errors: dict[str, str] = {}
    watchlist_detail: dict[str, Any] | None = None
    opportunity_detail: dict[str, Any] | None = None

    try:
        watchlist_detail = build_watchlist_detail_view(normalized_code)
    except Exception as exc:
        errors["watchlist"] = str(exc)

    try:
        opportunity_detail = build_candidate_detail_view(normalized_code)
    except Exception as exc:
        errors["opportunity"] = str(exc)

    primary_source = "watchlist" if watchlist_detail else ("opportunity" if opportunity_detail else None)
    primary_detail = watchlist_detail or opportunity_detail
    catalog_entry = (build_stock_catalog(watchlist, screening_batch, confirmation).get(normalized_code) or {})
    recent_entry = next(
        (
            item
            for item in reversed(load_ask_recent_store().get("items") or [])
            if str((item or {}).get("code") or "").strip() == normalized_code
        ),
        {},
    )
    profile_name = first_text(
        (primary_detail or {}).get("name"),
        catalog_entry.get("name") if catalog_entry.get("name") != normalized_code else None,
        recent_entry.get("name") if recent_entry.get("name") != normalized_code else None,
        (load_ask_case_cache(normalized_code) or {}).get("name"),
    )
    today_action = build_today_action_context(normalized_code, today=today_context, account_book=account_book)
    available_sources = [
        key
        for key, detail in (
            ("watchlist", watchlist_detail),
            ("opportunity", opportunity_detail),
        )
        if detail
    ]

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "code": normalized_code,
        "name": profile_name,
        "trade_date": (primary_detail or {}).get("trade_date"),
        "expected_trade_date": readiness.get("expected_trade_date"),
        "data_trade_date": readiness.get("data_trade_date"),
        "readiness": readiness,
        "primary_source": primary_source,
        "primary_source_label": {
            "watchlist": "自选股链路",
            "opportunity": "观察池链路",
        }.get(str(primary_source or ""), "未命中详情"),
        "primary_detail": primary_detail,
        "available_sources": available_sources,
        "watchlist": watchlist_detail,
        "opportunity": opportunity_detail,
        "today_action": today_action,
        "errors": errors,
        "links": {
            "self": f"/stock/{normalized_code}",
            "api_self": f"/api/stock/{normalized_code}",
            "watchlist_detail": today_watchlist_detail_url(normalized_code) if watchlist_detail else None,
            "opportunity_detail": today_candidate_detail_url(normalized_code) if opportunity_detail else None,
            "ask": ask_page_url(normalized_code),
        },
    }


def build_screening_batch_view() -> dict[str, Any]:
    screening_batch = load_screening_batch(trade_date=expected_trade_date())
    quality = safe_canonical_load(load_quality_status, lane="aggressive")
    gate = ((screening_batch.get("market_regime") or {}).get("execution_gate") or {})
    themes = ((screening_batch.get("market_themes") or {}).get("themes") or [])[:5]
    candidates = screening_batch.get("candidates") or []

    artifacts = [
        artifact_from_path("早盘批次 JSON", screening_batch.get("path"), key="screening_batch"),
        artifact_from_path("质检 JSON", (quality or {}).get("path"), key="quality_json"),
    ]

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "kind": "screener",
        "hero": {
            "eyebrow": "早盘候选",
            "title": "早盘批次详情",
            "summary": detail_value(gate.get("summary"), "当前展示的是最新可用早盘批次。"),
            "status_label": detail_value(gate.get("label"), "实时阀门"),
        },
        "meta_cards": [
            {
                "label": "生成时间",
                "value": detail_value(screening_batch.get("generated_at")),
                "detail": detail_value(screening_batch.get("pool_label") or screening_batch.get("pool")),
            },
            {
                "label": "候选总数",
                "value": detail_value(screening_batch.get("candidate_count")),
                "detail": f"进入候选 {detail_value(screening_batch.get('approved_count'))} / 继续观察 {detail_value(screening_batch.get('caution_count'))}",
            },
            {
                "label": "排除数量",
                "value": detail_value(screening_batch.get("excluded_count")),
                "detail": detail_value((screening_batch.get("screening_summary") or {}).get("execution_gate_status")),
            },
            {
                "label": "主线",
                "value": detail_value((screening_batch.get("market_themes") or {}).get("top_theme")),
                "detail": detail_value((screening_batch.get("market_themes") or {}).get("summary")),
            },
        ],
        "theme_cards": [
            {
                "title": item.get("theme") or "其他",
                "score": detail_value(item.get("score")),
                "detail": detail_value(((item.get("persistence") or {}).get("summary"))),
                "leaders": text_items(item.get("leader_codes")),
            }
            for item in themes
        ],
        "candidate_groups": [
            {
                "title": "候选列表",
                "count": len(candidates),
                "cards": [build_screening_candidate_card(item) for item in candidates],
                "footer_link": {"title": "进入午盘确认批次", "url": today_batch_detail_url("confirmation")},
            }
        ],
        "artifacts": [item for item in artifacts if item],
        "links": {
            **today_nav_links(),
            "self": today_batch_detail_url("screener"),
            "api_self": api_today_batch_detail_url("screener"),
        },
        "quality": {
            "status": detail_value((quality or {}).get("validation_status"), "unknown"),
            "checked_at": detail_value((quality or {}).get("checked_at")),
            "expected_timestamp": detail_value((quality or {}).get("expected_timestamp")),
        },
    }


def build_confirmation_view() -> dict[str, Any]:
    confirmation = load_confirmation(trade_date=expected_trade_date())
    quality = safe_canonical_load(load_quality_status, lane="midday_confirmation")

    artifacts = [
        artifact_from_path("午盘确认 JSON", confirmation.get("path"), key="confirmation"),
        artifact_from_path("质检 JSON", (quality or {}).get("path"), key="quality_json"),
    ]

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "kind": "confirmation",
        "hero": {
            "eyebrow": "午盘确认",
            "title": "午盘确认详情",
            "summary": "以早盘基线为锚，检查承接、降级和新增观察。",
            "status_label": detail_value(confirmation.get("validation_status"), "unknown"),
        },
        "meta_cards": [
            {
                "label": "生成时间",
                "value": detail_value(confirmation.get("generated_at")),
                "detail": f"对照 {detail_value(confirmation.get('verified_against_scan_timestamp'))}",
            },
            {
                "label": "仍可跟踪",
                "value": detail_value((confirmation.get("counts") or {}).get("confirmed")),
                "detail": "维持原计划",
            },
            {
                "label": "降级",
                "value": detail_value((confirmation.get("counts") or {}).get("downgraded")),
                "detail": "强度回落",
            },
            {
                "label": "新增观察",
                "value": detail_value((confirmation.get("counts") or {}).get("fresh_candidates")),
                "detail": f"晨间锚点 {detail_value(confirmation.get('source_morning_timestamp'))}",
            },
        ],
        "theme_cards": [],
        "candidate_groups": [
            {
                "title": "仍可跟踪",
                "count": len(confirmation.get("confirmed") or []),
                "cards": [build_confirmation_candidate_card(item) for item in (confirmation.get("confirmed") or [])],
                "footer_link": None,
            },
            {
                "title": "降级",
                "count": len(confirmation.get("downgraded") or []),
                "cards": [build_confirmation_candidate_card(item) for item in (confirmation.get("downgraded") or [])],
                "footer_link": None,
            },
            {
                "title": "新增观察",
                "count": len(confirmation.get("fresh_candidates") or []),
                "cards": [build_confirmation_candidate_card(item) for item in (confirmation.get("fresh_candidates") or [])],
                "footer_link": {"title": "回看早盘批次", "url": today_batch_detail_url("screener")},
            },
        ],
        "artifacts": [item for item in artifacts if item],
        "links": {
            **today_nav_links(),
            "self": today_batch_detail_url("confirmation"),
            "api_self": api_today_batch_detail_url("confirmation"),
        },
        "quality": {
            "status": detail_value((quality or {}).get("validation_status"), "unknown"),
            "checked_at": detail_value((quality or {}).get("checked_at")),
            "expected_timestamp": detail_value((quality or {}).get("expected_timestamp")),
        },
    }


def build_today_view() -> dict[str, Any]:
    ensure_runtime_dirs()
    trade_date_hint = expected_trade_date()
    decision_brief = safe_canonical_load(load_decision_brief, trade_date=trade_date_hint)
    watchlist = safe_canonical_load(load_watchlist_snapshot, trade_date=trade_date_hint)
    screening_batch = safe_canonical_load(load_screening_batch, trade_date=trade_date_hint)
    confirmation = safe_canonical_load(load_confirmation, trade_date=trade_date_hint)
    quality_status = safe_canonical_load(load_quality_status, lane="all")
    lifecycle_context = resolve_lifecycle_context()
    account_book = load_account_book()
    today_action_decisions = load_today_action_decision_store()

    readiness = compute_readiness(
        watchlist=watchlist,
        screening_batch=screening_batch,
        confirmation=confirmation,
        decision_brief=decision_brief,
        quality_status=quality_status,
        account_book=account_book,
        today_action_decisions=today_action_decisions,
        dataset_freshness=build_dataset_freshness_rows(
            expected_date=trade_date_hint,
            now=datetime.now(),
        ),
    )

    expected_date = readiness["expected_trade_date"]
    data_trade_date = readiness["data_trade_date"]
    trade_date = data_trade_date or current_trade_date(watchlist, screening_batch, decision_brief)
    brief_trade_date = (decision_brief or {}).get("trade_date")
    # Fail-closed: brief is only ``live`` when readiness is fully green AND
    # the brief itself is aligned with the expected trade date.
    brief_is_live = bool(readiness["brief_is_live"])

    gate = (((screening_batch or {}).get("market_regime") or {}).get("execution_gate") or {})
    brief_summary = (decision_brief or {}).get("summary") or {}
    main_theme = (
        brief_summary.get("main_theme")
        or (((screening_batch or {}).get("market_themes") or [{}])[0] or {}).get("theme")
        or (screening_batch or {}).get("top_theme")
        or "暂无主线"
    )

    if brief_is_live:
        hero_title = normalize_stock_ui_copy(brief_summary.get("open_new_positions")) or (
            "今天先处理旧仓，再决定是否看新仓" if gate.get("allow_new_positions") else "今天先观察，不急着开新仓"
        )
        hero_summary = normalize_stock_ui_copy(brief_summary.get("gate_summary")) or "当前判断已由总控层收束。"
        hero_gate_label = brief_summary.get("gate_label") or gate.get("label") or "总控已更新"
        position_cap = brief_summary.get("position_cap") or gate.get("position_cap") or "-"
        context_note = f"当前页面基于 {(decision_brief or {}).get('generated_at') or '-'} 的总控简报。"
    else:
        if readiness["readiness_mode"] == "blocked":
            hero_title = "数据未就绪：请先把核心链路刷新到当日"
        elif gate.get("allow_new_positions"):
            hero_title = "可以继续看新仓，但先只保留少量观察名单"
        else:
            hero_title = "先观察，不急着开新仓"
        hero_summary = normalize_stock_ui_copy(gate.get("summary")) or "当前页面已回退到实时链路数据。"
        hero_gate_label = gate.get("label") or "实时链路判断"
        position_cap = gate.get("position_cap") or "-"
        if readiness["readiness_mode"] == "blocked":
            top_blocker = (readiness["blockers"] or [{}])[0]
            blocker_msg = top_blocker.get("message") or "请回到任务列表刷新当日链路。"
            context_note = f"当前数据未就绪：{blocker_msg}（应为 {expected_date}）。在恢复实盘前不要按页面建议执行真钱操作。"
        elif readiness["readiness_mode"] == "shadow_only":
            context_note = (
                f"当前页面仅作影子盘观察：{(readiness['warnings'] or [{}])[0].get('message') or '关键链路尚未完全到位'}。"
            )
        elif decision_brief:
            context_note = f"最新总控简报停留在 {brief_trade_date}，页面主判断已回退到实时自选股 / 早盘扫描 / 午盘确认数据。"
        else:
            context_note = "尚未生成总控简报，当前页面完全基于实时链路数据。"

    watchlist_priority = len((watchlist or {}).get("priority_codes") or [])
    screening_summary = (screening_batch or {}).get("screening_summary") or {}
    quality_lanes = (quality_status or {}).get("lanes") or {}
    quality_ok = sum(1 for lane in quality_lanes.values() if lane.get("validation_status") == "ok")
    quality_timely = sum(1 for item in readiness["quality_freshness"] if item.get("timely"))
    quality_total = len(readiness["quality_freshness"]) or 3
    confirmation_counts = (confirmation or {}).get("counts") or {}
    action_groups = build_today_action_groups(
        watchlist,
        screening_batch,
        confirmation,
        decision_brief,
        quality_status,
        brief_is_live=brief_is_live,
        gate=gate,
    )
    action_queue = build_today_action_queue(
        action_groups,
        trade_date,
        account_book=account_book,
        expected_trade_date=expected_date,
        readiness_mode=str(readiness.get("readiness_mode") or "blocked"),
        readiness_ready=bool(readiness.get("ready")),
    )

    source_freshness_map = {item["key"]: item for item in readiness["source_freshness"]}

    def _augment_source(card: dict[str, Any], freshness_key: str) -> dict[str, Any]:
        freshness = source_freshness_map.get(freshness_key) or {}
        merged = dict(card)
        merged.setdefault("key", freshness_key)
        merged["available"] = freshness.get("available", merged.get("value") not in (None, "", "-"))
        merged["stale"] = bool(freshness.get("stale", False))
        merged["age_seconds"] = freshness.get("age_seconds")
        merged["age_label"] = freshness.get("age_label", "-")
        merged["stale_after_seconds"] = freshness.get("stale_after_seconds")
        merged["trade_date"] = freshness.get("trade_date")
        merged["stale_reasons"] = freshness.get("stale_reasons", [])
        return merged

    source_cards = [
        _augment_source(
            {
                "label": "自选股",
                "value": (watchlist or {}).get("generated_at") or "-",
                "detail": (watchlist or {}).get("trade_date") or "暂无快照",
            },
            "watchlist",
        ),
        _augment_source(
            {
                "label": "观察池基线",
                "value": (screening_batch or {}).get("generated_at") or "-",
                "detail": ((screening_batch or {}).get("pool_label") or (screening_batch or {}).get("pool") or "暂无批次"),
            },
            "screening",
        ),
        _augment_source(
            {
                "label": "午盘确认",
                "value": (confirmation or {}).get("generated_at") or "-",
                "detail": (confirmation or {}).get("validation_status") or "暂无确认",
            },
            "confirmation",
        ),
        _augment_source(
            {
                "label": "总控简报",
                "value": (decision_brief or {}).get("generated_at") or "-",
                "detail": "已同步" if brief_is_live else "数据偏旧",
            },
            "decision_brief",
        ),
    ]

    summary_cards = [
        {
            "label": "持仓先处理",
            "value": str(watchlist_priority),
            "detail": "来自自选股页面",
        },
        {
            "label": "观察池候选",
            "value": str(screening_summary.get("approved_count") or screening_summary.get("shortlisted_count") or 0),
            "detail": (gate.get("label") or "来自观察池"),
        },
        {
            "label": "午盘新增观察",
            "value": str(confirmation_counts.get("fresh_candidates") or 0),
            "detail": "来自午盘确认",
        },
        {
            "label": "质检就绪",
            "value": f"{quality_timely}/{quality_total}",
            "detail": "核心链路状态",
            "tone": "positive" if quality_timely == quality_total else "warning",
        },
    ]

    artifacts = {
        "decision_brief": {
            "path": ((decision_brief or {}).get("paths") or {}).get("source_json"),
            "url": artifact_url(((decision_brief or {}).get("paths") or {}).get("source_json")),
            "label": "总控 JSON",
        },
        "watchlist_snapshot": {
            "path": ((decision_brief or {}).get("paths") or {}).get("watchlist_snapshot") or (watchlist or {}).get("snapshot_path"),
            "url": artifact_url(((decision_brief or {}).get("paths") or {}).get("watchlist_snapshot") or (watchlist or {}).get("snapshot_path")),
            "label": "自选股快照",
        },
        "screening_batch": {
            "path": ((decision_brief or {}).get("paths") or {}).get("screening_batch") or (screening_batch or {}).get("path"),
            "url": artifact_url(((decision_brief or {}).get("paths") or {}).get("screening_batch") or (screening_batch or {}).get("path")),
            "label": "早盘批次",
        },
        "confirmation": {
            "path": ((decision_brief or {}).get("paths") or {}).get("confirmation") or (confirmation or {}).get("path"),
            "url": artifact_url(((decision_brief or {}).get("paths") or {}).get("confirmation") or (confirmation or {}).get("path")),
            "label": "午盘确认",
        },
    }
    links = today_nav_links()
    next_steps = build_today_next_steps(action_groups, links=links)
    top_rows = compress_today_actions(action_queue)
    change_view = build_today_change_view(
        lifecycle_context["display_lifecycle"],
        links=links,
        note=lifecycle_context["lifecycle_note"],
    )
    primary_actions = build_today_primary_actions(top_rows)
    holdings_rows = build_today_trusted_group_rows(action_queue, "do-now", ("watchlist:",))
    opportunity_rows = build_today_trusted_group_rows(action_queue, "watch", ("screening:", "confirmation:"))
    risk_rows = build_today_risk_rows(change_view, action_groups)
    evidence_rows = build_today_evidence_rows(source_cards)
    command_hero = build_today_command_hero(
        trade_date=trade_date,
        hero={
            "title": hero_title,
            "summary": hero_summary,
            "context_note": context_note,
        },
        top_rows=top_rows,
        brief_is_live=brief_is_live,
        readiness_mode=str(readiness.get("readiness_mode") or "blocked"),
    )
    radar_cards = build_today_radar_cards(
        position_cap=position_cap,
        main_theme=main_theme,
        quality_ok=quality_timely,
        confirmation_counts=confirmation_counts,
        brief_is_live=brief_is_live,
    )
    evidence_hint = build_today_evidence_hint(
        brief_is_live=brief_is_live,
        source_cards=source_cards,
    )

    quality_freshness_map = {item["key"]: item for item in readiness["quality_freshness"]}
    quality_cards = []
    for card in quality_lane_cards(quality_status):
        # quality_lane_cards uses Chinese titles; map back via the (key, title)
        # pairs to enrich each card with timely / stale_reasons metadata.
        title = card.get("title") or ""
        match_key = next(
            (k for k, t in (("watchlist", "自选股"), ("aggressive", "进攻型早盘"), ("midday_confirmation", "午盘确认")) if t == title),
            "",
        )
        merged = dict(card)
        meta = quality_freshness_map.get(match_key) or {}
        merged["key"] = match_key or card.get("key") or title
        merged["timely"] = bool(meta.get("timely", card.get("status") == "ok"))
        merged["stale_reasons"] = meta.get("stale_reasons", [])
        merged["age_label"] = meta.get("age_label", "-")
        if not merged["timely"] and card.get("tone") == "positive":
            # downgrade misleading positive tone when readiness disagrees
            merged["tone"] = "watch"
        quality_cards.append(merged)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    command_brief_error: str | None = None
    try:
        command_brief = build_today_command_brief(
            trade_date=trade_date,
            readiness=readiness,
            gate=gate,
            decision_brief=decision_brief,
            watchlist=watchlist,
            screening_batch=screening_batch,
            confirmation=confirmation,
            action_groups=action_groups,
            action_queue=action_queue,
            refresh_status=None,
        )
    except Exception as exc:  # fail-soft so downstream rendering can degrade
        command_brief = None
        command_brief_error = str(exc)

    return {
        "generated_at": generated_at,
        "display_date": current_display_date(),
        "trade_date": trade_date,
        "expected_trade_date": expected_date,
        "data_trade_date": data_trade_date,
        "brief_is_live": brief_is_live,
        "readiness": readiness,
        "hero": {
            "title": hero_title,
            "summary": hero_summary,
            "gate_label": hero_gate_label,
            "position_cap": position_cap,
            "main_theme": main_theme,
            "context_note": context_note,
        },
        "command_hero": command_hero,
        "command_brief": command_brief,
        "command_brief_error": command_brief_error,
        "radar_cards": radar_cards,
        "evidence_hint": evidence_hint,
        "action_groups": action_groups,
        "action_queue": action_queue,
        "next_steps": next_steps,
        "top_rows": top_rows,
        "primary_actions": primary_actions,
        "holdings_rows": holdings_rows,
        "opportunity_rows": opportunity_rows,
        "risk_rows": risk_rows,
        "evidence_rows": evidence_rows,
        "confidence_switch": build_today_confidence_switch(
            decision_brief,
            quality_status,
            brief_is_live=brief_is_live,
            gate=gate,
            links=links,
        ),
        "change_view": change_view,
        "source_cards": source_cards,
        "summary_cards": summary_cards,
        "watchlist_cards": pick_watchlist_cards(watchlist),
        "opportunity_cards": pick_opportunity_cards(screening_batch),
        "midday_cards": pick_midday_cards(confirmation),
        "quality_cards": quality_cards,
        "artifacts": artifacts,
        "links": links,
        "counts": {
            "watchlist_priority": watchlist_priority,
            "watchlist_total": (watchlist or {}).get("stock_count") or 0,
            "candidate_total": (screening_batch or {}).get("candidate_count") or 0,
            "confirmed": confirmation_counts.get("confirmed") or 0,
            "downgraded": confirmation_counts.get("downgraded") or 0,
            "fresh_candidates": confirmation_counts.get("fresh_candidates") or 0,
        },
    }


# ---------------------------------------------------------------------------
# Portfolio account view (live readiness, real positions, real cash)
# ---------------------------------------------------------------------------


def _portfolio_code_aliases(value: Any) -> set[str]:
    code = str(value or "").strip().lower()
    if not code:
        return set()
    aliases = {code}
    bare = code[2:] if len(code) == 8 and code[:2].isalpha() else code
    aliases.add(bare)
    if len(bare) == 6 and bare.isdigit():
        aliases.add(f"sh{bare}" if bare.startswith("6") else f"sz{bare}")
    return aliases


def _portfolio_name_is_code_like(name: Any, code: Any) -> bool:
    text = str(name or "").strip().lower()
    if not text:
        return True
    aliases = _portfolio_code_aliases(code)
    return text in aliases or text in {"未命名标的", "unknown"}


def _portfolio_quote_index(
    codes: list[str],
    *,
    trade_date: str,
    refresh_quotes: bool,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    normalized_codes: list[str] = []
    for code in codes:
        try:
            normalized = normalize_code(code)
        except ValueError:
            continue
        if normalized not in normalized_codes:
            normalized_codes.append(normalized)

    empty_status = {
        "enabled": bool(refresh_quotes),
        "status": "not_requested" if not refresh_quotes else "no_positions",
        "message": "未刷新行情。" if not refresh_quotes else "当前没有持仓代码可刷新。",
        "requested_codes": normalized_codes,
        "updated_at": "",
        "trade_date": trade_date,
        "provider": "",
        "freshness_status": "",
        "live_small_allowed": False,
        "data_path": "",
        "manifest_path": "",
        "errors": [],
    }
    if not refresh_quotes or not normalized_codes:
        return {}, empty_status

    try:
        result = get_data_gateway().fetch_quotes_batch(
            normalized_codes,
            trade_date=trade_date,
            key="portfolio-quotes",
            allow_fallback=True,
        )
    except Exception as exc:
        return {}, {
            **empty_status,
            "status": "failed",
            "message": f"行情刷新失败：{exc}",
            "errors": [str(exc)],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    manifest = dict(result.manifest or {})
    rows = result.data if isinstance(result.data, list) else []
    quote_index: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        aliases: set[str] = set()
        for raw in (row.get("symbol"), row.get("code")):
            try:
                aliases.add(normalize_code(raw))
            except ValueError:
                continue
        price = round_money(row.get("price"))
        if price <= 0:
            continue
        quote = {
            "code": next(iter(aliases), str(row.get("code") or "")),
            "name": str(row.get("name") or ""),
            "price": price,
            "change": optional_round_money(row.get("change")),
            "change_pct": optional_round_money(row.get("change_pct")),
            "trade_date": str(row.get("trade_date") or manifest.get("trade_date") or trade_date),
            "timestamp": str(row.get("timestamp") or manifest.get("asof") or manifest.get("fetched_at") or ""),
            "provider": str(manifest.get("provider") or ""),
        }
        for alias in aliases:
            quote_index[alias] = quote

    errors = []
    provider_error = result.provider_result.error
    if provider_error:
        errors.append(str(provider_error))
    missing = [code for code in normalized_codes if code not in quote_index]
    status = "ok" if quote_index and not missing else "partial" if quote_index else "failed"
    return quote_index, {
        **empty_status,
        "status": status,
        "message": "行情已刷新。" if status == "ok" else "部分持仓未取到行情。" if status == "partial" else "未取到可用行情。",
        "updated_at": str(manifest.get("fetched_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "trade_date": str(manifest.get("trade_date") or trade_date),
        "provider": str(manifest.get("provider") or ""),
        "freshness_status": str(manifest.get("freshness_status") or ""),
        "live_small_allowed": bool(manifest.get("live_small_allowed")),
        "row_count": len(rows),
        "priced_count": len({quote["code"] for quote in quote_index.values()}),
        "missing_codes": missing,
        "data_path": str(result.data_path or ""),
        "manifest_path": str(result.manifest_path or ""),
        "errors": errors,
    }


def _attach_portfolio_market_values(
    positions: list[dict[str, Any]],
    quote_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for pos in positions:
        try:
            normalized = normalize_code(pos.get("code"))
        except ValueError:
            normalized = str(pos.get("code") or "")
        quote = quote_index.get(normalized)
        qty = int(pos.get("qty") or 0)
        cost_basis = round_money(pos.get("cost_basis"))
        realized = round_money(pos.get("realized_pnl"))
        current_price = round_money((quote or {}).get("price")) if quote else None
        market_value = round_money(qty * current_price) if current_price is not None else None
        unrealized = round_money((market_value or 0.0) - cost_basis) if market_value is not None else None
        total_pnl = round_money(realized + unrealized) if unrealized is not None else None
        quote_name = str((quote or {}).get("name") or "").strip()
        display_name = str(pos.get("name") or "").strip()
        if quote_name and _portfolio_name_is_code_like(display_name, pos.get("code")):
            display_name = quote_name
        enriched.append(
            {
                **pos,
                "name": display_name or str(pos.get("code") or ""),
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized,
                "unrealized_pnl_pct": round_money((unrealized / cost_basis) * 100) if unrealized is not None and cost_basis else None,
                "total_pnl": total_pnl,
                "quote_change_pct": (quote or {}).get("change_pct") if quote else None,
                "quote_timestamp": (quote or {}).get("timestamp", "") if quote else "",
                "quote_trade_date": (quote or {}).get("trade_date", "") if quote else "",
                "quote_provider": (quote or {}).get("provider", "") if quote else "",
            }
        )
    return enriched


def _portfolio_latest_execution(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not events:
        return None
    event = max(
        events,
        key=lambda item: str(item.get("created_at") or item.get("trade_date") or ""),
    )
    return {
        "status": event.get("status"),
        "trade_date": event.get("trade_date"),
        "side": event.get("side"),
        "price": event.get("price"),
        "quantity": event.get("quantity"),
        "amount": event.get("amount"),
        "note": event.get("note"),
    }


def _portfolio_latest_outcome(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not events:
        return None
    rank = {"T+5": 3, "T+3": 2, "T+1": 1}
    event = max(
        events,
        key=lambda item: (
            rank.get(str(item.get("window") or "").upper(), 0),
            str(item.get("evaluated_at") or ""),
        ),
    )
    classification = event.get("classification") or {}
    market_data = event.get("market_data") or {}
    return {
        "window": event.get("window"),
        "as_of_trade_date": event.get("as_of_trade_date"),
        "label": classification.get("label"),
        "tone": classification.get("tone"),
        "return_pct": market_data.get("return_pct"),
        "relative_return_pct": market_data.get("relative_return_pct"),
    }


def _portfolio_decision_summary(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    stock = record.get("stock") or {}
    source = record.get("source") or {}
    recommendation = record.get("recommendation") or {}
    status = record.get("status") or {}
    execution_events = [dict(item) for item in (record.get("execution_events") or []) if isinstance(item, dict)]
    outcome_events = [dict(item) for item in (record.get("outcome_events") or []) if isinstance(item, dict)]
    return {
        "decision_id": record.get("decision_id"),
        "trade_date": record.get("trade_date"),
        "code": stock.get("code"),
        "name": stock.get("name"),
        "action": recommendation.get("action"),
        "action_label": recommendation.get("action_label"),
        "lane": source.get("lane"),
        "surface": source.get("surface"),
        "status": status.get("state"),
        "main_conclusion": recommendation.get("main_conclusion"),
        "latest_execution": _portfolio_latest_execution(execution_events),
        "latest_outcome": _portfolio_latest_outcome(outcome_events),
    }


def _portfolio_latest_decisions_by_code() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    try:
        import decision_ledger  # type: ignore

        records, errors = decision_ledger.scan_all_decisions()
    except Exception as exc:
        return {}, [{"message": str(exc)}]
    records = [dict(item) for item in records if isinstance(item, dict)]
    records.sort(
        key=lambda record: (
            str(record.get("trade_date") or ""),
            str(record.get("decision_id") or ""),
        ),
        reverse=True,
    )
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        code = str(((record.get("stock") or {}).get("code")) or "").strip()
        if not code:
            continue
        for alias in _portfolio_code_aliases(code):
            latest.setdefault(alias, record)
    return latest, [dict(item) for item in errors if isinstance(item, dict)]


def _portfolio_watchlist_items(watchlist: dict[str, Any] | None) -> list[dict[str, Any]]:
    stocks = (watchlist or {}).get("stocks") or []
    if isinstance(stocks, dict):
        iterable = stocks.values()
    elif isinstance(stocks, list):
        iterable = stocks
    else:
        iterable = []
    return [dict(stock) for stock in iterable if isinstance(stock, dict)]


def _portfolio_watchlist_index(watchlist: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for stock in _portfolio_watchlist_items(watchlist):
        if not isinstance(stock, dict):
            continue
        for alias in _portfolio_code_aliases(stock.get("code")):
            index[alias] = stock
    return index


def _portfolio_first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            for item in value:
                text = str(item or "").strip()
                if text:
                    return text
            continue
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _portfolio_decision_text(decision: dict[str, Any] | None) -> str:
    recommendation = (decision or {}).get("recommendation") or {}
    return " ".join(
        str(value or "")
        for value in (
            recommendation.get("action"),
            recommendation.get("action_label"),
            recommendation.get("main_conclusion"),
            recommendation.get("risk_summary"),
            recommendation.get("stop_condition"),
        )
    )


def _portfolio_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _portfolio_optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _portfolio_default_plan_rules() -> dict[str, float | int]:
    return {
        "warning_loss_pct": -3.0,
        "defense_reduce_loss_pct": -5.0,
        "clear_loss_pct": -8.0,
        "profit_take_pct": 8.0,
        "max_hold_days": 5,
        "min_progress_pct": 1.0,
    }


def _portfolio_join_tokens(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, dict):
            parts.extend(str(v or "") for v in value.values())
        elif isinstance(value, list):
            parts.extend(str(item or "") for item in value)
        else:
            parts.append(str(value or ""))
    return " ".join(part.strip() for part in parts if part and part.strip())


def _portfolio_trade_level(stock: dict[str, Any] | None, key: str) -> float | None:
    if not stock:
        return None
    levels = stock.get("trade_levels") or {}
    if isinstance(levels, dict):
        value = levels.get(key)
        if value not in (None, ""):
            return _portfolio_optional_float(value)
    return _portfolio_optional_float(stock.get(key))


def _portfolio_market_regime(readiness: Mapping[str, Any] | None) -> str:
    mode = str((readiness or {}).get("readiness_mode") or "")
    session_key = str(((readiness or {}).get("session") or {}).get("key") or "")
    blockers = {str(item.get("code") or "") for item in ((readiness or {}).get("blockers") or []) if isinstance(item, dict)}
    if "account_not_ready" in blockers or mode == "blocked":
        return "blocked"
    if mode == "live_ready" and session_key in {"in_session", "midday", "pre_open"}:
        return "risk_on"
    if mode == "live_ready":
        return "neutral"
    if mode == "shadow_only":
        return "risk_off"
    return "cautious"


def _portfolio_index_context(screening_batch: Mapping[str, Any] | None) -> dict[str, Any]:
    metrics = {
        "hs300_change_pct": None,
        "zz500_change_pct": None,
        "cyb_change_pct": None,
        "market_score": None,
    }
    queue = [screening_batch] if isinstance(screening_batch, Mapping) else []
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        current_id = id(current)
        if current_id in seen:
            continue
        seen.add(current_id)
        for key, value in current.items():
            if isinstance(value, Mapping):
                queue.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping):
                        queue.append(item)
            lower = str(key).lower()
            if metrics["hs300_change_pct"] is None and any(token in lower for token in ("hs300", "沪深300")):
                metrics["hs300_change_pct"] = _portfolio_optional_float(value)
            if metrics["zz500_change_pct"] is None and any(token in lower for token in ("zz500", "中证500")):
                metrics["zz500_change_pct"] = _portfolio_optional_float(value)
            if metrics["cyb_change_pct"] is None and any(token in lower for token in ("cyb", "创业板")):
                metrics["cyb_change_pct"] = _portfolio_optional_float(value)
            if metrics["market_score"] is None and any(token in lower for token in ("market_score", "env_score", "score")):
                maybe = _portfolio_optional_float(value)
                if maybe is not None:
                    metrics["market_score"] = maybe
    return metrics


def _portfolio_news_signals(
    *,
    watchlist_stock: Mapping[str, Any] | None,
    latest_decision: Mapping[str, Any] | None,
) -> dict[str, Any]:
    positives = [str(item).strip() for item in ((watchlist_stock or {}).get("positives") or []) if str(item).strip()]
    hard_flags = [str(item).strip() for item in ((watchlist_stock or {}).get("hard_flags") or []) if str(item).strip()]
    recommendation = (latest_decision or {}).get("recommendation") or {}
    risk_summary = str(recommendation.get("risk_summary") or "").strip()
    event_text = _portfolio_join_tokens(
        (watchlist_stock or {}).get("event_base"),
        positives,
        hard_flags,
        risk_summary,
        recommendation.get("main_conclusion"),
    )
    event_risk = "none"
    if any(token in event_text for token in ("黑天鹅", "问询", "减持", "监管", "诉讼", "爆雷")):
        event_risk = "high"
    elif hard_flags or any(token in event_text for token in ("风险", "偏空", "走弱")):
        event_risk = "medium"
    event_boost = "none"
    if positives or any(token in event_text for token in ("利好", "改善", "回购", "分红", "偏多")):
        event_boost = "medium" if positives else "low"
    return {
        "event_risk": event_risk,
        "event_boost": event_boost,
        "risk_summary": risk_summary,
        "positives": positives,
        "hard_flags": hard_flags,
    }


def _portfolio_stock_script_config(
    position: dict[str, Any],
    *,
    latest_decision: dict[str, Any] | None,
    watchlist_stock: dict[str, Any] | None,
    avg_cost: float,
) -> dict[str, Any]:
    name = str(position.get("name") or (watchlist_stock or {}).get("name") or "")
    code = str(position.get("code") or (watchlist_stock or {}).get("code") or "")
    recommendation = (latest_decision or {}).get("recommendation") or {}
    rule_snapshot = (watchlist_stock or {}).get("rule_snapshot") or {}
    if not isinstance(rule_snapshot, dict):
        rule_snapshot = {}

    action_text = _portfolio_first_text((watchlist_stock or {}).get("action"), recommendation.get("action_label"))
    tech_base = _portfolio_first_text(rule_snapshot.get("tech_base"), (watchlist_stock or {}).get("tech_base"))
    flow_base = _portfolio_first_text(rule_snapshot.get("flow_base"), (watchlist_stock or {}).get("flow_base"))
    event_base = _portfolio_first_text(rule_snapshot.get("event_base"), (watchlist_stock or {}).get("event_base"))
    signal = _portfolio_first_text(rule_snapshot.get("signal"), (watchlist_stock or {}).get("signal"))
    score = _portfolio_optional_float(rule_snapshot.get("score", (watchlist_stock or {}).get("score")))
    hard_flags = [str(item).strip() for item in ((watchlist_stock or {}).get("hard_flags") or []) if str(item).strip()]
    positives = [str(item).strip() for item in ((watchlist_stock or {}).get("positives") or []) if str(item).strip()]
    watch_points = [str(item).strip() for item in ((watchlist_stock or {}).get("watch_points") or []) if str(item).strip()]
    support = _portfolio_trade_level(watchlist_stock, "support")
    resistance = _portfolio_trade_level(watchlist_stock, "resistance")
    stop_loss = _portfolio_trade_level(watchlist_stock, "stop_loss")

    text_blob = _portfolio_join_tokens(
        code,
        name,
        action_text,
        tech_base,
        flow_base,
        event_base,
        signal,
        hard_flags,
        positives,
        watch_points,
        recommendation,
    )
    low_vol_tokens = ("海尔", "美的", "格力", "家电", "白电", "消费", "食品", "饮料", "白酒", "银行", "保险", "电力", "公用")
    high_vol_tokens = ("题材", "AI", "算力", "机器人", "半导体", "芯片", "低空", "军工", "创新药", "证券", "传媒", "游戏")
    cyclical_tokens = ("有色", "煤炭", "钢铁", "化工", "航运", "地产", "光伏", "新能源", "锂", "铜")

    profile_key = "standard"
    profile_label = "常规波动个股"
    profile_detail = "按普通持仓节奏处理；止损和止盈线随成本线动态重算。"
    rules: dict[str, float | int] = _portfolio_default_plan_rules()

    if any(token in text_blob for token in high_vol_tokens):
        profile_key = "high_vol_theme"
        profile_label = "高波动题材"
        profile_detail = "波动大、窗口短；亏损容忍略宽，但时间失败更快触发。"
        rules = {
            "warning_loss_pct": -4.0,
            "defense_reduce_loss_pct": -6.5,
            "clear_loss_pct": -10.0,
            "profit_take_pct": 10.0,
            "max_hold_days": 2,
            "min_progress_pct": 3.0,
        }
    elif any(token in text_blob for token in low_vol_tokens):
        profile_key = "low_vol_consumer_bluechip"
        profile_label = "低波动消费蓝筹"
        profile_detail = "低波动票不靠大回撤换空间；亏损线收紧，观察窗口略放长。"
        rules = {
            "warning_loss_pct": -2.2,
            "defense_reduce_loss_pct": -4.2,
            "clear_loss_pct": -7.0,
            "profit_take_pct": 6.5,
            "max_hold_days": 7,
            "min_progress_pct": 1.2,
        }
    elif any(token in text_blob for token in cyclical_tokens):
        profile_key = "mid_high_vol_cycle"
        profile_label = "中高波动周期"
        profile_detail = "周期票允许更大日内摆动，但必须更快看到价格进展。"
        rules = {
            "warning_loss_pct": -3.5,
            "defense_reduce_loss_pct": -5.5,
            "clear_loss_pct": -8.5,
            "profit_take_pct": 9.0,
            "max_hold_days": 4,
            "min_progress_pct": 2.0,
        }

    levels = _portfolio_plan_levels(avg_cost, rules)
    if support is not None:
        levels["structure_support_price"] = round_money(support)
        if support > 0 and support > levels["defense_reduce_price"]:
            levels["defense_reduce_price"] = round_money(support)
            rules["defense_reduce_loss_pct"] = round(((levels["defense_reduce_price"] / avg_cost) - 1) * 100, 2) if avg_cost else rules["defense_reduce_loss_pct"]
    if stop_loss is not None:
        stop_loss_price = round_money(stop_loss)
        levels["watchlist_stop_loss_price"] = stop_loss_price
        if stop_loss_price > 0:
            levels["clear_exit_price"] = round_money(max(stop_loss_price, levels["clear_exit_price"]))
            rules["clear_loss_pct"] = round(((levels["clear_exit_price"] / avg_cost) - 1) * 100, 2) if avg_cost else rules["clear_loss_pct"]
    if resistance is not None:
        levels["repair_price"] = round_money(resistance)
    else:
        levels["repair_price"] = round_money(max(levels.get("reclaim_price") or avg_cost, avg_cost))

    basis = [f"个股画像：{profile_label}"]
    if action_text:
        basis.append(f"当日观察动作：{action_text}")
    if signal:
        basis.append(f"技术信号：{signal}")
    if flow_base:
        basis.append(f"资金状态：{flow_base}")
    if event_base:
        basis.append(f"事件状态：{event_base}")
    if hard_flags:
        basis.append(f"硬风险：{' / '.join(hard_flags[:3])}")
    if positives:
        basis.append(f"正向证据：{' / '.join(positives[:3])}")

    return {
        "profile_key": profile_key,
        "profile_label": profile_label,
        "profile_detail": profile_detail,
        "rules": rules,
        "levels": levels,
        "basis": basis,
        "evidence": {
            "action": action_text,
            "tech_base": tech_base,
            "flow_base": flow_base,
            "event_base": event_base,
            "signal": signal,
            "score": score,
            "hard_flags": hard_flags,
            "positives": positives,
            "watch_points": watch_points,
            "support": support,
            "resistance": resistance,
            "stop_loss": stop_loss,
        },
    }


def _portfolio_plan_levels(avg_cost: float, rules: dict[str, Any]) -> dict[str, float]:
    return {
        "warning_price": round_money(avg_cost * (1 + _portfolio_float(rules.get("warning_loss_pct"), -3.0) / 100)),
        "defense_reduce_price": round_money(avg_cost * (1 + _portfolio_float(rules.get("defense_reduce_loss_pct"), -5.0) / 100)),
        "clear_exit_price": round_money(avg_cost * (1 + _portfolio_float(rules.get("clear_loss_pct"), -8.0) / 100)),
        "profit_take_price": round_money(avg_cost * (1 + _portfolio_float(rules.get("profit_take_pct"), 8.0) / 100)),
        "reclaim_price": round_money(avg_cost),
        "time_fail_price": round_money(avg_cost * (1 + _portfolio_float(rules.get("min_progress_pct"), 1.0) / 100)),
    }


def _portfolio_find_position_plan(
    position: dict[str, Any],
    position_plans: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    aliases = _portfolio_code_aliases(position.get("code"))
    matches = []
    for plan in position_plans or []:
        if not isinstance(plan, dict):
            continue
        if str(plan.get("status") or "open") != "open":
            continue
        if aliases.intersection(_portfolio_code_aliases(plan.get("code"))):
            matches.append(plan)
    if not matches:
        return None
    matches.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return matches[0]


def _portfolio_runtime_position_plan(
    position: dict[str, Any],
    *,
    latest_decision: dict[str, Any] | None,
    watchlist_stock: dict[str, Any] | None,
) -> dict[str, Any]:
    avg_cost = round_money(position.get("avg_cost") or 0.0)
    rules = _portfolio_default_plan_rules()
    recommendation = (latest_decision or {}).get("recommendation") or {}
    entry_reason = _portfolio_first_text(
        recommendation.get("main_conclusion"),
        recommendation.get("entry_reason"),
        (watchlist_stock or {}).get("reason"),
        (watchlist_stock or {}).get("detail"),
        "Prism 根据已有真实持仓生成默认持仓剧本。",
    )
    return {
        "plan_id": f"runtime:{position.get('code') or ''}",
        "status": "open",
        "source": "auto_runtime_default",
        "created_at": position.get("last_fill_at") or "",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "code": position.get("code"),
        "name": position.get("name"),
        "entry_trade_date": str(position.get("last_fill_at") or "")[:10],
        "entry_price": avg_cost,
        "entry_qty": position.get("qty"),
        "current_qty": position.get("qty"),
        "avg_cost_basis": avg_cost,
        "rules": rules,
        "levels": _portfolio_plan_levels(avg_cost, rules),
        "logic": {
            "entry_reason": entry_reason,
            "risk_model": "Prism 默认持仓剧本：-5% 防守减仓，-8% 清仓退出，+8% 止盈兑现，5 个自然日未达到 +1% 进展则时间失败。",
        },
    }


def _portfolio_effective_position_plan(
    position: dict[str, Any],
    *,
    latest_decision: dict[str, Any] | None,
    watchlist_stock: dict[str, Any] | None,
    position_plans: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    plan = _portfolio_find_position_plan(position, position_plans)
    if plan:
        merged = dict(plan)
        rules = {**_portfolio_default_plan_rules(), **dict(merged.get("rules") or {})}
        avg_cost = round_money(merged.get("avg_cost_basis") or position.get("avg_cost") or 0.0)
        levels = {**_portfolio_plan_levels(avg_cost, rules), **dict(merged.get("levels") or {})}
        merged["rules"] = rules
        merged["levels"] = levels
        merged["avg_cost_basis"] = avg_cost
        return merged
    return _portfolio_runtime_position_plan(
        position,
        latest_decision=latest_decision,
        watchlist_stock=watchlist_stock,
    )


def _portfolio_days_held(entry_trade_date: Any, expected_date: str) -> int | None:
    try:
        start = datetime.strptime(str(entry_trade_date or "")[:10], "%Y-%m-%d")
        end = datetime.strptime(str(expected_date or "")[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return max((end - start).days, 0)


def _portfolio_money_text(value: Any) -> str:
    number = _portfolio_optional_float(value)
    if number is None:
        return "-"
    return f"{number:.2f}"


def _portfolio_pct_text(value: Any) -> str:
    number = _portfolio_optional_float(value)
    if number is None:
        return "-"
    return f"{number:.2f}%"


def _build_holding_review(
    position: dict[str, Any],
    *,
    latest_decision: dict[str, Any] | None,
    watchlist_stock: dict[str, Any] | None,
    position_plan: dict[str, Any],
    expected_date: str,
    readiness: Mapping[str, Any] | None = None,
    screening_batch: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    latest_decision_summary = _portfolio_decision_summary(latest_decision)
    current_price = position.get("current_price")
    unrealized_pct = position.get("unrealized_pnl_pct")
    latest_decision_date = str((latest_decision_summary or {}).get("trade_date") or "")
    decision_is_today = bool(latest_decision_date and latest_decision_date == expected_date)
    avg_cost = round_money(position.get("avg_cost") or position_plan.get("avg_cost_basis") or 0.0)
    script = _portfolio_stock_script_config(
        position,
        latest_decision=latest_decision,
        watchlist_stock=watchlist_stock,
        avg_cost=avg_cost,
    )
    plan_source = str(position_plan.get("source") or "")
    stored_rules = dict(position_plan.get("rules") or {})
    stored_levels = dict(position_plan.get("levels") or {})
    rules = {**_portfolio_default_plan_rules(), **stored_rules, **dict(script.get("rules") or {})}
    levels = {**_portfolio_plan_levels(avg_cost, rules), **dict(script.get("levels") or {})}
    if plan_source and not plan_source.startswith("auto_"):
        levels = {**levels, **stored_levels}
    position_plan = {
        **position_plan,
        "rules": rules,
        "levels": levels,
        "logic": {
            **dict(position_plan.get("logic") or {}),
            "risk_model": f"Prism 个股剧本：{script['profile_label']}｜防守线 {_portfolio_float(rules.get('defense_reduce_loss_pct'), -5.0):.2f}%｜清仓线 {_portfolio_float(rules.get('clear_loss_pct'), -8.0):.2f}%｜止盈线 +{_portfolio_float(rules.get('profit_take_pct'), 8.0):.2f}%｜时间窗口 {int(_portfolio_float(rules.get('max_hold_days'), 5))} 天。",
        },
        "script_profile": {
            "key": script.get("profile_key"),
            "label": script.get("profile_label"),
            "detail": script.get("profile_detail"),
        },
    }
    price_value = _portfolio_optional_float(current_price)
    pnl_pct_value = _portfolio_optional_float(unrealized_pct)
    days_held = _portfolio_days_held(position_plan.get("entry_trade_date"), expected_date)
    qty = int(position.get("qty") or 0)
    reduce_qty = max(1, qty // 2) if qty else 0
    remain_after_reduce = max(qty - reduce_qty, 0)

    warning_loss_pct = _portfolio_float(rules.get("warning_loss_pct"), -3.0)
    defense_loss_pct = _portfolio_float(rules.get("defense_reduce_loss_pct"), -5.0)
    clear_loss_pct = _portfolio_float(rules.get("clear_loss_pct"), -8.0)
    profit_take_pct = _portfolio_float(rules.get("profit_take_pct"), 8.0)
    min_progress_pct = _portfolio_float(rules.get("min_progress_pct"), 1.0)
    max_hold_days = int(_portfolio_float(rules.get("max_hold_days"), 5))
    warning_price = round_money(levels.get("warning_price") or avg_cost * (1 + warning_loss_pct / 100))
    defense_price = round_money(levels.get("defense_reduce_price") or avg_cost * (1 + defense_loss_pct / 100))
    clear_price = round_money(levels.get("clear_exit_price") or avg_cost * (1 + clear_loss_pct / 100))
    profit_price = round_money(levels.get("profit_take_price") or avg_cost * (1 + profit_take_pct / 100))
    reclaim_price = round_money(levels.get("reclaim_price") or avg_cost)
    time_fail_price = round_money(levels.get("time_fail_price") or avg_cost * (1 + min_progress_pct / 100))
    repair_price = round_money(levels.get("repair_price") or reclaim_price)
    support_price = _portfolio_optional_float(levels.get("structure_support_price"))

    script_evidence = dict(script.get("evidence") or {})
    market_regime = _portfolio_market_regime(readiness)
    index_context = _portfolio_index_context(screening_batch)
    news_signals = _portfolio_news_signals(
        watchlist_stock=watchlist_stock,
        latest_decision=latest_decision,
    )
    decision_text = _portfolio_join_tokens(
        _portfolio_decision_text(latest_decision),
        script_evidence.get("action"),
        script_evidence.get("signal"),
        script_evidence.get("hard_flags"),
    )
    decision_says_exit = any(
        token in decision_text
        for token in ("卖出", "减仓", "清仓", "止损", "放弃", "forbid", "reduce", "skip")
    )
    trigger_facts: list[str] = []
    if price_value is not None:
        trigger_facts.append(f"现价 {_portfolio_money_text(price_value)}，成本 {_portfolio_money_text(avg_cost)}，浮盈亏 {_portfolio_pct_text(pnl_pct_value)}。")
        if support_price is not None and price_value <= support_price:
            trigger_facts.append(f"现价已低于结构支撑 {_portfolio_money_text(support_price)}。")
    if script_evidence.get("action"):
        trigger_facts.append(f"当日观察动作：{script_evidence['action']}。")
    if script_evidence.get("signal"):
        trigger_facts.append(f"技术信号：{script_evidence['signal']}。")
    if script_evidence.get("flow_base"):
        trigger_facts.append(f"资金状态：{script_evidence['flow_base']}。")
    if script_evidence.get("event_base"):
        trigger_facts.append(f"事件状态：{script_evidence['event_base']}。")
    if script_evidence.get("hard_flags"):
        trigger_facts.append(f"硬风险：{' / '.join(script_evidence['hard_flags'][:3])}。")

    def _rule_text(*items: Any) -> str:
        return " ".join(str(item).strip() for item in items if str(item or "").strip())

    target_sell_qty = 0
    target_sell_pct = 0.0

    if price_value is None:
        action = "refresh_quote"
        label = "刷新行情"
        tone = "warning"
        category = "行情缺失"
        suggested_action = "刷新行情"
        trigger_rule = "当前持仓没有可用现价，先取回行情再生成动作。"
        execution_rule = "刷新持仓行情；刷新后按个股剧本重新计算防守线、清仓线、止盈线。"
        upgrade_rule = "行情取回后立即重新分层。"
        revoke_rule = "行情取回后撤销此状态。"
        review_tag = "quote_missing"
    elif pnl_pct_value is not None and (pnl_pct_value <= clear_loss_pct or price_value <= clear_price):
        action = "clear_exit"
        label = "清仓退出"
        tone = "sell"
        category = "止损退出"
        suggested_action = "清仓"
        target_sell_qty = qty
        target_sell_pct = 100.0 if qty else 0.0
        trigger_rule = _rule_text(
            f"清仓线 {_portfolio_money_text(clear_price)} 已触发。",
            f"清仓阈值 {clear_loss_pct:.2f}%。",
        )
        execution_rule = f"卖出 {qty} 股（100%）；成交回写后关闭本票持仓剧本。"
        upgrade_rule = "已是最高退出级别。"
        revoke_rule = f"未成交前若现价重新站回防守线 {_portfolio_money_text(defense_price)}，状态降为防守减仓；已成交则不撤销。"
        review_tag = "loss_clear_exit"
    elif (
        decision_says_exit
        or (pnl_pct_value is not None and pnl_pct_value <= defense_loss_pct)
        or price_value <= defense_price
    ):
        action = "defense_reduce"
        label = "防守减仓"
        tone = "sell"
        category = "防守减仓"
        suggested_action = "减仓"
        target_sell_qty = reduce_qty
        target_sell_pct = round((reduce_qty / qty) * 100, 2) if qty else 0.0
        threshold_fact = ""
        if pnl_pct_value is not None and (pnl_pct_value <= defense_loss_pct or price_value <= defense_price):
            threshold_fact = f"防守线 {_portfolio_money_text(defense_price)} / {defense_loss_pct:.2f}% 已触发。"
        signal_fact = "当日观察链出现减仓/止损信号。" if decision_says_exit else ""
        trigger_rule = _rule_text(threshold_fact, signal_fact)
        execution_rule = f"卖出 {reduce_qty} 股（{target_sell_pct:.0f}%）；剩余 {remain_after_reduce} 股只保留到清仓线 {_portfolio_money_text(clear_price)}；今日不补仓。"
        upgrade_rule = f"现价 <= {_portfolio_money_text(clear_price)} 或浮亏 <= {clear_loss_pct:.2f}% 时清仓 {remain_after_reduce} 股。"
        revoke_rule = f"收盘价 >= 修复线 {_portfolio_money_text(repair_price)} 且当日观察动作不含减仓/看空时撤销；否则继续防守。"
        review_tag = "loss_defense_reduce" if threshold_fact else "logic_exit_signal"
    elif pnl_pct_value is not None and (pnl_pct_value >= profit_take_pct or price_value >= profit_price):
        action = "profit_take"
        label = "止盈兑现"
        tone = "positive"
        category = "止盈兑现"
        suggested_action = "止盈"
        target_sell_qty = reduce_qty
        target_sell_pct = round((reduce_qty / qty) * 100, 2) if qty else 0.0
        trigger_rule = f"止盈线 {_portfolio_money_text(profit_price)} / +{profit_take_pct:.2f}% 已触发。"
        execution_rule = f"卖出 {reduce_qty} 股（{target_sell_pct:.0f}%）锁定利润；剩余 {remain_after_reduce} 股防守线抬到成本线 {_portfolio_money_text(reclaim_price)}。"
        upgrade_rule = f"剩余仓位回落到成本线 {_portfolio_money_text(reclaim_price)} 时退出剩余 {remain_after_reduce} 股。"
        revoke_rule = f"未成交前若价格跌回止盈线 {_portfolio_money_text(profit_price)} 以下，状态降回继续持有。"
        review_tag = "profit_take"
    elif days_held is not None and days_held >= max_hold_days and pnl_pct_value is not None and pnl_pct_value < min_progress_pct:
        action = "time_exit"
        label = "时间失败"
        tone = "warning"
        category = "时间失败"
        suggested_action = "减仓"
        target_sell_qty = reduce_qty
        target_sell_pct = round((reduce_qty / qty) * 100, 2) if qty else 0.0
        trigger_rule = f"持有 {days_held} 个自然日，收益 {_portfolio_pct_text(pnl_pct_value)} 未达到 {min_progress_pct:.2f}% 的进展线。"
        execution_rule = f"卖出 {reduce_qty} 股（{target_sell_pct:.0f}%）；剩余 {remain_after_reduce} 股只在时间达标线 {_portfolio_money_text(time_fail_price)} 上方保留。"
        upgrade_rule = f"现价 <= {_portfolio_money_text(defense_price)} 时转为防守减仓。"
        revoke_rule = f"价格 >= 时间达标线 {_portfolio_money_text(time_fail_price)} 时撤销时间失败。"
        review_tag = "time_failure"
    elif pnl_pct_value is not None and (pnl_pct_value <= warning_loss_pct or price_value <= warning_price):
        action = "loss_warning"
        label = "亏损预警"
        tone = "warning"
        category = "亏损预警"
        suggested_action = "不加仓"
        trigger_rule = f"预警线 {_portfolio_money_text(warning_price)} / {warning_loss_pct:.2f}% 已触发。"
        execution_rule = "不买入、不加仓；持仓数量保持不变。"
        upgrade_rule = f"现价 <= {_portfolio_money_text(defense_price)} 或浮亏 <= {defense_loss_pct:.2f}% 时执行防守减仓。"
        revoke_rule = f"价格 >= 修复线 {_portfolio_money_text(repair_price)} 时撤销预警。"
        review_tag = "loss_warning"
    else:
        action = "hold"
        label = "继续持有"
        tone = "positive"
        category = "继续持有"
        suggested_action = "持有"
        trigger_rule = f"现价位于防守线 {_portfolio_money_text(defense_price)} 与止盈线 {_portfolio_money_text(profit_price)} 之间，未触发动作。"
        execution_rule = "持仓保持不变；不新增仓位。"
        upgrade_rule = f"现价 <= {_portfolio_money_text(defense_price)} 转防守减仓；现价 >= {_portfolio_money_text(profit_price)} 转止盈兑现。"
        revoke_rule = "无需撤销。"
        review_tag = "hold"

    instruction = f"{category}｜建议动作：{suggested_action}"
    has_current_watchlist = bool(watchlist_stock)
    evidence_pack = {
        "stock": {
            "code": position.get("code"),
            "name": position.get("name"),
            "profile": script.get("profile_label"),
        },
        "position": {
            "qty": qty,
            "position_pct": None,
            "avg_cost": avg_cost,
            "current_price": price_value,
            "pnl_pct": pnl_pct_value,
            "pnl_amount": _portfolio_optional_float(position.get("unrealized_pnl")),
            "days_held": days_held,
            "entry_date": position_plan.get("entry_trade_date"),
            "last_action": position_plan.get("source"),
            "last_action_price": _portfolio_optional_float(position_plan.get("entry_price")),
        },
        "script": {
            "base_action": action,
            "base_action_label": label,
            "defense_line": defense_price,
            "clear_line": clear_price,
            "repair_line": repair_price,
            "profit_line": profit_price,
            "warning_line": warning_price,
            "time_fail_line": time_fail_price,
            "suggested_sell_qty": target_sell_qty,
            "suggested_sell_pct": target_sell_pct,
            "rule_floor_action": action,
        },
        "price_action": {
            "change_pct_today": _portfolio_optional_float(position.get("quote_change_pct")),
            "range_position_20d": "near_low" if support_price is not None and price_value is not None and price_value <= support_price else "mid",
            "ma5_relation": "below" if price_value is not None and price_value < reclaim_price else "above_or_equal",
            "ma10_relation": "below" if price_value is not None and price_value < repair_price else "above_or_equal",
            "ma20_relation": "below" if price_value is not None and price_value < avg_cost else "above_or_equal",
            "drawdown_from_repair_pct": round(((price_value / repair_price) - 1) * 100, 2) if price_value is not None and repair_price else None,
            "break_levels": [item for item in ("below_support" if support_price is not None and price_value is not None and price_value <= support_price else "", "below_defense_line" if price_value is not None and price_value <= defense_price else "", "below_clear_line" if price_value is not None and price_value <= clear_price else "") if item],
            "volatility_profile": script.get("profile_key"),
        },
        "flow": {
            "flow_direction": script_evidence.get("flow_base"),
            "flow_persistence_days": 5 if script_evidence.get("flow_base") else None,
            "main_signal": script_evidence.get("signal"),
            "score": script_evidence.get("score"),
        },
        "market_context": {
            "market_regime": market_regime,
            "attack_gate": "closed" if market_regime in {"risk_off", "blocked", "cautious"} else "open",
            "hs300_change_pct": index_context.get("hs300_change_pct"),
            "zz500_change_pct": index_context.get("zz500_change_pct"),
            "cyb_change_pct": index_context.get("cyb_change_pct"),
            "market_score": index_context.get("market_score"),
            "session": ((readiness or {}).get("session") or {}).get("label"),
        },
        "events": {
            "event_risk": news_signals.get("event_risk"),
            "event_boost": news_signals.get("event_boost"),
            "risk_summary": news_signals.get("risk_summary"),
            "positive_flags": news_signals.get("positives") or [],
            "risk_flags": news_signals.get("hard_flags") or [],
        },
        "prism_history": [
            {
                "date": (latest_decision_summary or {}).get("trade_date"),
                "action": (latest_decision_summary or {}).get("action"),
                "action_label": (latest_decision_summary or {}).get("action_label"),
                "conclusion": (latest_decision_summary or {}).get("main_conclusion"),
                "outcome_label": ((latest_decision_summary or {}).get("latest_outcome") or {}).get("label"),
                "outcome_return_pct": ((latest_decision_summary or {}).get("latest_outcome") or {}).get("return_pct"),
            }
        ] if latest_decision_summary else [],
        "evidence": {
            "price": trigger_facts[:2],
            "flow": [f"资金状态：{script_evidence['flow_base']}"] if script_evidence.get("flow_base") else [],
            "technical": [f"技术信号：{script_evidence['signal']}"] if script_evidence.get("signal") else [],
            "event": [f"事件状态：{script_evidence['event_base']}"] if script_evidence.get("event_base") else [],
            "risk_flags": news_signals.get("hard_flags") or [],
            "positive_flags": news_signals.get("positives") or [],
        },
        "constraints": {
            "rule_floor_action": action,
            "can_relax_below_rule": False,
            "can_suggest_tighten": True,
            "manual_execution_only": True,
            "max_sell_qty": qty,
            "recommended_sell_qty": target_sell_qty,
        },
    }

    return {
        "code": position.get("code"),
        "name": position.get("name"),
        "qty": position.get("qty"),
        "avg_cost": position.get("avg_cost"),
        "cost_basis": position.get("cost_basis"),
        "current_price": current_price,
        "market_value": position.get("market_value"),
        "unrealized_pnl": position.get("unrealized_pnl"),
        "unrealized_pnl_pct": unrealized_pct,
        "quote_trade_date": position.get("quote_trade_date"),
        "quote_timestamp": position.get("quote_timestamp"),
        "last_fill_at": position.get("last_fill_at"),
        "today_action": action,
        "action_label": label,
        "action_tone": tone,
        "action_instruction": instruction,
        "must_review": action != "hold",
        "missing_plan": False,
        "missing_analysis": not (decision_is_today or has_current_watchlist),
        "decision_is_today": decision_is_today,
        "stop_condition": f"清仓线 {_portfolio_money_text(clear_price)} / {clear_loss_pct:.2f}%",
        "reduce_condition": f"防守减仓线 {_portfolio_money_text(defense_price)} / {defense_loss_pct:.2f}%",
        "continue_condition": f"修复线 {_portfolio_money_text(repair_price)}；止盈线 {_portfolio_money_text(profit_price)}",
        "position_plan": position_plan,
        "holding_evidence_pack": evidence_pack,
        "holding_decision": {
            "category": category,
            "suggested_action": suggested_action,
            "trigger_rule": trigger_rule,
            "execution_rule": execution_rule,
            "upgrade_rule": upgrade_rule,
            "revoke_rule": revoke_rule,
            "review_tag": review_tag,
            "target_sell_qty": target_sell_qty,
            "target_sell_pct": target_sell_pct,
            "days_held": days_held,
            "price": price_value,
            "avg_cost": avg_cost,
            "pnl_pct": pnl_pct_value,
            "trigger_facts": trigger_facts,
            "script": {
                "profile_key": script.get("profile_key"),
                "profile_label": script.get("profile_label"),
                "profile_detail": script.get("profile_detail"),
                "basis": script.get("basis") or [],
                "rule_summary": f"防守 {defense_loss_pct:.2f}%｜清仓 {clear_loss_pct:.2f}%｜止盈 +{profit_take_pct:.2f}%｜时间 {max_hold_days} 天",
            },
            "evidence": script_evidence,
            "levels": {
                "warning_price": warning_price,
                "defense_reduce_price": defense_price,
                "clear_exit_price": clear_price,
                "profit_take_price": profit_price,
                "reclaim_price": reclaim_price,
                "time_fail_price": time_fail_price,
                "repair_price": repair_price,
                "structure_support_price": support_price,
            },
            "rules": rules,
        },
        "latest_decision": latest_decision_summary,
        "latest_execution": (latest_decision_summary or {}).get("latest_execution"),
        "latest_outcome": (latest_decision_summary or {}).get("latest_outcome"),
        "review_reason": category,
    }


def _build_holding_reviews(
    positions: list[dict[str, Any]],
    *,
    watchlist: dict[str, Any] | None,
    position_plans: list[dict[str, Any]] | None,
    expected_date: str,
    readiness: Mapping[str, Any] | None = None,
    screening_batch: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    latest_decisions, errors = _portfolio_latest_decisions_by_code()
    watchlist_index = _portfolio_watchlist_index(watchlist)
    reviews: list[dict[str, Any]] = []
    for position in positions:
        aliases = _portfolio_code_aliases(position.get("code"))
        latest_decision = next((latest_decisions.get(alias) for alias in aliases if alias in latest_decisions), None)
        watchlist_stock = next((watchlist_index.get(alias) for alias in aliases if alias in watchlist_index), None)
        position_plan = _portfolio_effective_position_plan(
            position,
            latest_decision=latest_decision,
            watchlist_stock=watchlist_stock,
            position_plans=position_plans,
        )
        reviews.append(
            _build_holding_review(
                position,
                latest_decision=latest_decision,
                watchlist_stock=watchlist_stock,
                position_plan=position_plan,
                expected_date=expected_date,
                readiness=readiness,
                screening_batch=screening_batch,
            )
        )

    action_order = {
        "clear_exit": 0,
        "defense_reduce": 1,
        "profit_take": 2,
        "time_exit": 3,
        "loss_warning": 4,
        "refresh_quote": 5,
        "hold": 5,
    }
    reviews.sort(
        key=lambda item: (
            action_order.get(str(item.get("today_action") or ""), 99),
            float(item.get("unrealized_pnl_pct") or 0.0),
            str(item.get("code") or ""),
        )
    )
    counts: dict[str, int] = {}
    for item in reviews:
        action = str(item.get("today_action") or "hold")
        counts[action] = counts.get(action, 0) + 1
    summary = {
        "total": len(reviews),
        "must_review": sum(1 for item in reviews if item.get("must_review")),
        "clear_exit": counts.get("clear_exit", 0),
        "defense_reduce": counts.get("defense_reduce", 0),
        "profit_take": counts.get("profit_take", 0),
        "time_exit": counts.get("time_exit", 0),
        "loss_warning": counts.get("loss_warning", 0),
        "refresh_quote": counts.get("refresh_quote", 0),
        "review_sell": counts.get("clear_exit", 0) + counts.get("defense_reduce", 0) + counts.get("profit_take", 0) + counts.get("time_exit", 0),
        "reduce_watch": counts.get("loss_warning", 0),
        "evidence_blocked": counts.get("refresh_quote", 0),
        "missing_plan": 0,
        "missing_analysis": counts.get("missing_analysis", 0),
        "hold": counts.get("hold", 0),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expected_trade_date": expected_date,
        "errors": errors,
    }
    if summary["clear_exit"]:
        summary["title"] = f"{summary['clear_exit']} 只持仓触发清仓退出"
        summary["tone"] = "sell"
    elif summary["defense_reduce"]:
        summary["title"] = f"{summary['defense_reduce']} 只持仓触发防守减仓"
        summary["tone"] = "sell"
    elif summary["profit_take"]:
        summary["title"] = f"{summary['profit_take']} 只持仓触发止盈兑现"
        summary["tone"] = "positive"
    elif summary["time_exit"]:
        summary["title"] = f"{summary['time_exit']} 只持仓触发时间失败"
        summary["tone"] = "warning"
    elif summary["must_review"]:
        summary["title"] = f"{summary['must_review']} 只持仓需要动作"
        summary["tone"] = "warning"
    elif reviews:
        summary["title"] = "持仓按剧本继续"
        summary["tone"] = "positive"
    else:
        summary["title"] = "暂无真实持仓"
        summary["tone"] = "info"
    return reviews, summary


def _holding_ai_is_precise(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    return bool(
        re.search(r"\d", value)
        or any(
            token in value
            for token in (
                "防守线",
                "清仓线",
                "止盈线",
                "修复线",
                "现价",
                "浮亏",
                "卖出",
                "减仓",
                "清仓",
                "持有",
                "刷新行情",
                "收盘",
                "站回",
                "跌破",
            )
        )
    )


def _holding_ai_normalize_fact(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "当前未进入观察池链路" in text:
        return ""
    replacements = (
        ("risk_on", "大盘风险偏好回暖"),
        ("risk_off", "大盘偏弱"),
        ("blocked", "大盘未放行"),
        ("base_action为refresh_quote", "当前缺现价，先刷新行情"),
        ("无价格数据", "当前缺现价"),
        ("attack_gate", "进攻阀门"),
        ("closed", "关闭"),
        ("open", "打开"),
    )
    for source, target in replacements:
        text = text.replace(source, target)
    text = text.replace("市场状态大盘风险偏好回暖", "大盘风险偏好回暖")
    text = text.replace("市场环境大盘风险偏好回暖", "大盘风险偏好回暖")
    text = text.replace("事件状态：偏多", "事件面偏多")
    text = text.replace("事件状态偏多", "事件面偏多")
    text = text.replace("大盘 大盘", "大盘")
    text = re.sub(r"\s+", " ", text).strip("；;，,。 ")
    if text.startswith("市场 "):
        text = text.replace("市场 ", "大盘 ", 1)
    if text in {"无事件风险", "现价未触发任何动作线"}:
        return ""
    return text


def _holding_ai_fact_list(items: Any, *, limit: int, action: str = "") -> list[str]:
    facts: list[str] = []
    for item in items or []:
        text = _holding_ai_normalize_fact(item)
        if not text or text in facts:
            continue
        if action == "refresh_quote" and any(token in text for token in ("MA5/10/20", "未触发任何动作线")):
            continue
        facts.append(text)
        if len(facts) >= limit:
            break
    return facts


def _holding_ai_evidence_sides(review: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    decision = dict((review.get("holding_decision") or {}))
    evidence = dict((decision.get("evidence") or {}))
    action = str(review.get("today_action") or "")
    trigger_facts = _holding_ai_fact_list(decision.get("trigger_facts") or [], limit=5, action=action)
    signal = _holding_ai_normalize_fact(evidence.get("signal"))
    flow = _holding_ai_normalize_fact(f"资金{evidence.get('flow_base')}" if evidence.get("flow_base") else "")
    hard_flags = _holding_ai_fact_list(evidence.get("hard_flags") or [], limit=2, action=action)
    positives = _holding_ai_fact_list(evidence.get("positives") or [], limit=2, action=action)
    event_base = str(evidence.get("event_base") or "").strip()

    bearish: list[str] = []
    if trigger_facts:
        bearish.extend(trigger_facts)
    if signal:
        bearish.append(f"技术{signal}" if not signal.startswith("技术") else signal)
    if flow:
        bearish.append(flow)
    if hard_flags:
        bearish.extend(hard_flags)

    buffers: list[str] = []
    if event_base == "偏多":
        buffers.append("事件面偏多")
    buffers.extend(positives)

    if action in {"clear_exit", "defense_reduce", "time_exit", "loss_warning"}:
        return _holding_ai_fact_list(bearish, limit=4, action=action), _holding_ai_fact_list(buffers, limit=3, action=action)
    if action == "profit_take":
        return _holding_ai_fact_list(trigger_facts or ["止盈线已触发"], limit=3, action=action), _holding_ai_fact_list(buffers, limit=2, action=action)
    if action == "refresh_quote":
        unconfirmed = ["当前缺现价，先刷新行情"]
        if signal or flow or hard_flags:
            unconfirmed.extend([item for item in [signal, flow, *hard_flags] if item])
        return _holding_ai_fact_list(unconfirmed, limit=4, action=action), _holding_ai_fact_list(buffers, limit=3, action=action)
    return _holding_ai_fact_list(trigger_facts or ["仍在剧本区间内"], limit=3, action=action), _holding_ai_fact_list(bearish, limit=3, action=action)


def _holding_ai_merge_facts(primary: list[str], secondary: list[str], *, limit: int, action: str) -> list[str]:
    merged: list[str] = []
    seen_keys: set[str] = set()
    for item in [*primary, *secondary]:
        text = _holding_ai_normalize_fact(item)
        if not text:
            continue
        if text == "看空（评分-40）":
            text = "技术看空（评分-40）"
        if action == "refresh_quote" and text in {
            "大盘风险偏好回暖",
            "MA5/10/20均线之上",
            "市场评分4.0",
            "当前价格数据缺失，无法触发任何动作",
        }:
            continue
        normalized_key = re.sub(r"[：:，,。；;\\s]+", "", text)
        normalized_key = normalized_key.replace("事件状态偏多", "事件面偏多")
        normalized_key = normalized_key.replace("事件偏多", "事件面偏多")
        if normalized_key in seen_keys:
            continue
        if any(text == existing or text in existing or existing in text for existing in merged):
            continue
        merged.append(text)
        seen_keys.add(normalized_key)
        if len(merged) >= limit:
            break
    return merged


def _holding_ai_default_copy(review: Mapping[str, Any]) -> dict[str, str]:
    decision = dict((review.get("holding_decision") or {}))
    evidence = dict((decision.get("evidence") or {}))
    levels = dict((decision.get("levels") or {}))
    action = str(review.get("today_action") or "")
    qty = int(_portfolio_float(review.get("qty"), 0))
    sell_qty = int(_portfolio_float(decision.get("target_sell_qty"), 0))
    remain_qty = max(qty - sell_qty, 0)
    defense_line = _portfolio_money_text(levels.get("defense_reduce_price"))
    clear_line = _portfolio_money_text(levels.get("clear_exit_price"))
    repair_line = _portfolio_money_text(levels.get("repair_price") or levels.get("reclaim_price"))
    profit_line = _portfolio_money_text(levels.get("profit_take_price"))
    time_fail_line = _portfolio_money_text(levels.get("time_fail_price"))
    signal = _holding_ai_normalize_fact(evidence.get("signal"))
    flow = _holding_ai_normalize_fact(f"资金{evidence.get('flow_base')}" if evidence.get("flow_base") else "")
    hard_flags = _holding_ai_fact_list(evidence.get("hard_flags") or [], limit=2, action=action)
    event_base = str(evidence.get("event_base") or "").strip()

    evidence_bits: list[str] = []
    if signal:
        evidence_bits.append(f"技术{signal}" if not signal.startswith("技术") else signal)
    if flow:
        evidence_bits.append(flow)
    if hard_flags:
        evidence_bits.append("风险项 " + " / ".join(hard_flags))
    if event_base == "偏多":
        evidence_bits.append("事件面有对冲")

    def _join(bits: list[str], fallback: str) -> str:
        compact = [item for item in bits if item]
        return "；".join(compact[:3]) if compact else fallback

    if action == "refresh_quote":
        return {
            "scene_label": "待行情确认",
            "action_rewrite": "现在先刷新行情；拿到现价后再决定是否减仓或退出。",
            "next_watch": f"先刷新行情。现价低于 {defense_line} 转防守减仓；现价低于 {clear_line} 转清仓退出。",
            "risk_summary": _join(
                evidence_bits,
                "当前缺现价；拿到现价前不放松剧本。",
            ),
            "adjustment_reason": "缺现价时先补行情，规则不放松。",
            "counter_evidence_label": "待确认点",
        }
    if action == "clear_exit":
        return {
            "scene_label": "清仓线触发",
            "action_rewrite": f"现在按清仓处理，卖出 {sell_qty} 股；未成交前不做加仓。",
            "next_watch": f"未成交前站回 {defense_line}，降为防守减仓；成交完成后，本票退出跟踪。",
            "risk_summary": _join(
                [f"价格已击穿清仓线 {clear_line}"] + evidence_bits,
                f"价格已击穿清仓线 {clear_line}。",
            ),
            "adjustment_reason": "清仓线已触发，先退出，再谈修复。",
            "counter_evidence_label": "缓冲证据",
        }
    if action == "defense_reduce":
        return {
            "scene_label": "防守线触发",
            "action_rewrite": f"现在先减仓 {sell_qty} 股；剩余 {remain_qty} 股只保留到清仓线 {clear_line}。",
            "next_watch": f"跌破 {clear_line} 清掉余仓；收回 {repair_line} 且当日信号转强，撤销防守。",
            "risk_summary": _join(
                [f"价格已压到防守线 {defense_line} 下方"] + evidence_bits,
                f"价格已压到防守线 {defense_line} 下方。",
            ),
            "adjustment_reason": "防守线已触发，先减仓，再看能否修复。",
            "counter_evidence_label": "缓冲证据",
        }
    if action == "profit_take":
        return {
            "scene_label": "止盈线触发",
            "action_rewrite": f"现在先止盈 {sell_qty} 股；剩余 {remain_qty} 股防守线抬到成本线 {repair_line}。",
            "next_watch": f"若余仓回落到成本线 {repair_line}，退出剩余仓位；若继续上行，按止盈后余仓跟踪。",
            "risk_summary": _join(
                [f"利润已到止盈线 {profit_line}"] + evidence_bits,
                f"利润已到止盈线 {profit_line}。",
            ),
            "adjustment_reason": "利润先兑现，避免回吐。",
            "counter_evidence_label": "回吐风险",
        }
    if action == "time_exit":
        return {
            "scene_label": "时间窗口失效",
            "action_rewrite": f"现在先减仓 {sell_qty} 股；剩余 {remain_qty} 股只在时间达标线 {time_fail_line} 上方保留。",
            "next_watch": f"若仍站不上时间达标线 {time_fail_line}，继续退出；若再跌破防守线 {defense_line}，转防守减仓。",
            "risk_summary": _join(
                ["持仓时间已超过剧本窗口"] + evidence_bits,
                "持仓时间已超过剧本窗口。",
            ),
            "adjustment_reason": "时间成本已经高于继续死扛的收益。",
            "counter_evidence_label": "缓冲证据",
        }
    if action == "loss_warning":
        return {
            "scene_label": "防守预警",
            "action_rewrite": "现在不卖也不加仓；仓位先保持不动。",
            "next_watch": f"若跌破防守线 {defense_line}，转防守减仓；若收回修复线 {repair_line}，撤销预警。",
            "risk_summary": _join(
                [f"价格已进入预警区，离防守线 {defense_line} 不远"] + evidence_bits,
                f"价格已进入预警区，离防守线 {defense_line} 不远。",
            ),
            "adjustment_reason": "还没到卖点，但已经不能加仓。",
            "counter_evidence_label": "缓冲证据",
        }
    return {
            "scene_label": "剧本内持有",
            "action_rewrite": "现在不卖不加，按原仓位继续持有。",
        "next_watch": f"跌破 {defense_line} 转防守减仓；上破 {profit_line} 转止盈兑现。",
        "risk_summary": _join(
            [f"价格仍在剧本区间内，真正的风险是跌回防守线 {defense_line} 下方"] + evidence_bits,
            f"价格仍在剧本区间内，真正的风险是跌回防守线 {defense_line} 下方。",
        ),
        "adjustment_reason": "还没触发防守线或止盈线，剧本暂不改。",
        "counter_evidence_label": "风险证据",
    }


def _holding_ai_cache_key(review: Mapping[str, Any], expected_date: str) -> str:
    code = str(review.get("code") or "")
    timestamp = str(review.get("quote_timestamp") or "")
    action = str(review.get("today_action") or "")
    script_profile = str((((review.get("holding_decision") or {}).get("script") or {}).get("profile_key")) or "")
    return f"{_HOLDING_AI_REVIEW_VERSION}:{expected_date}:{code}:{timestamp}:{action}:{script_profile}"


def _holding_ai_prompt_payload(review: Mapping[str, Any]) -> dict[str, Any]:
    pack = dict((review.get("holding_evidence_pack") or {}))
    if pack:
        return pack
    return {
        "stock": {
            "code": review.get("code"),
            "name": review.get("name"),
        },
        "position": {
            "qty": review.get("qty"),
            "avg_cost": review.get("avg_cost"),
            "current_price": review.get("current_price"),
            "pnl_pct": review.get("unrealized_pnl_pct"),
        },
        "script": {
            "base_action": review.get("today_action"),
        },
        "constraints": {
            "manual_execution_only": True,
            "can_relax_below_rule": False,
        },
    }


def _holding_ai_review_prompt(review: Mapping[str, Any]) -> tuple[str, str]:
    system_prompt = (
        "你是 Prism 的持仓执行副手。"
        "你的任务不是重新决定买卖权限，而是基于给定 evidence pack 复核当前持仓剧本、"
        "识别场景、列出支持与反向证据，并决定剧本应保持/收紧/放宽。"
        "必须遵守 constraints。若 can_relax_below_rule=false，则不得建议低于 rule_floor_action 的更宽松动作。"
        "输出必须像交易桌指令，不要写成研究摘要。"
        "避免含糊词：接近、关注、留意、考虑、可能、偏强、偏弱、等待观察。"
        "如果有价格线、仓位或阈值，必须直接写出来。"
        "只返回一个 JSON object，不要输出额外解释。"
    )
    example = {
        "scene": "price_break_with_weak_flow",
        "scene_label": "价格破位 + 资金偏弱",
        "confidence": 0.82,
        "evidence_strength": "high",
        "verdict": "keep",
        "verdict_label": "维持原剧本",
        "action_rewrite": "海尔智家已触发防守减仓，执行 150 股减仓；剩余仓位只保留到 20.30。",
        "supporting_evidence": ["现价低于防守线", "观察链减仓观望"],
        "opposing_evidence": ["事件状态偏多"],
        "script_adjustment": {
            "adjustment": "keep",
            "adjustment_label": "保持",
            "defense_line": "keep",
            "clear_line": "keep",
            "time_window": "keep",
            "reason": "价格和资金弱势已经足够确认防守动作。"
        },
        "next_watch": "收盘不能回到修复线之上，则继续防守。",
        "risk_summary": "当前主要风险来自价格破位和连续弱势。",
        "evidence_used": ["现价 20.44 低于防守线 20.84"],
        "human_note": "手工执行，系统不会自动交易。"
    }
    user_prompt = (
        "请基于以下 holding evidence pack 生成结构化持仓 AI review。"
        "字段至少包括：scene, scene_label, confidence, evidence_strength, verdict, verdict_label, "
        "action_rewrite, supporting_evidence, opposing_evidence, script_adjustment, next_watch, risk_summary, evidence_used, human_note。"
        "script_adjustment.adjustment 只能是 keep/tighten/loosen，但若 constraints.can_relax_below_rule=false，"
        "当 base_action 是 clear_exit/defense_reduce/time_exit/profit_take 时，不得输出 loosen。"
        "confidence 为 0-1 数字，evidence_strength 只能 low/medium/high。"
        "action_rewrite 必须回答‘现在怎么做’，一句话内写清动作和数量。"
        "next_watch 必须回答‘下一条线看什么’，优先写防守线、清仓线、修复线、止盈线。"
        "supporting_evidence / opposing_evidence 每条只写一个事实，不要写空泛判断。"
        "scene_label 用 4-10 个汉字，优先使用：待行情确认 / 防守线触发 / 清仓线触发 / 止盈线触发 / 时间窗口失效 / 剧本内持有 / 防守预警。"
        "输出示例：\n"
        f"{json.dumps(example, ensure_ascii=False, sort_keys=True)}\n"
        "输入 JSON：\n"
        f"{json.dumps(_holding_ai_prompt_payload(review), ensure_ascii=False, sort_keys=True)}"
    )
    return system_prompt, user_prompt


def _sanitize_holding_ai_review(
    *,
    review: Mapping[str, Any],
    raw: Mapping[str, Any],
    fallback_reason: str = "",
) -> dict[str, Any]:
    decision = dict((review.get("holding_decision") or {}))
    evidence_pack = dict((review.get("holding_evidence_pack") or {}))
    base_action = str(review.get("today_action") or "")
    defaults = _holding_ai_default_copy(review)
    raw_verdict = str(raw.get("verdict") or "keep").strip().lower()
    verdict = raw_verdict if raw_verdict in {"keep", "tighten", "loosen"} else "keep"
    can_relax = bool(((evidence_pack.get("constraints") or {}).get("can_relax_below_rule")))
    if not can_relax and verdict == "loosen":
        verdict = "keep"
    confidence = _portfolio_optional_float(raw.get("confidence"))
    if confidence is None:
        confidence = 0.35 if fallback_reason else 0.68
    confidence = max(0.0, min(confidence, 1.0))
    strength = str(raw.get("evidence_strength") or "").strip().lower()
    if strength not in {"low", "medium", "high"}:
        strength = "medium" if confidence >= 0.55 else "low"
    default_supporting, default_opposing = _holding_ai_evidence_sides(review)
    raw_supporting = _holding_ai_fact_list(raw.get("supporting_evidence") or [], limit=6, action=base_action)
    raw_opposing = _holding_ai_fact_list(raw.get("opposing_evidence") or [], limit=4, action=base_action)
    supporting = _holding_ai_merge_facts(default_supporting, raw_supporting, limit=4, action=base_action)
    opposing = _holding_ai_merge_facts(default_opposing, raw_opposing, limit=3, action=base_action)
    evidence_used = _holding_ai_merge_facts(
        _holding_ai_fact_list(raw.get("evidence_used") or [], limit=8, action=base_action),
        supporting,
        limit=8,
        action=base_action,
    )
    if not supporting:
        supporting = _holding_ai_fact_list(decision.get("trigger_facts") or [], limit=4, action=base_action)
    adjustment = dict(raw.get("script_adjustment") or {})
    adjustment_mode = str(adjustment.get("adjustment") or verdict).strip().lower()
    if adjustment_mode not in {"keep", "tighten", "loosen"}:
        adjustment_mode = verdict
    if not can_relax and adjustment_mode == "loosen":
        adjustment_mode = "keep"
    raw_scene_label = _holding_ai_normalize_fact(raw.get("scene_label"))
    scene_label = raw_scene_label if raw_scene_label and raw_scene_label not in {"规则触发场景", "规则触发", "多空信号混杂", "无触发信号", "无需操作"} and base_action != "refresh_quote" else defaults["scene_label"]
    raw_risk_summary = _holding_ai_normalize_fact(raw.get("risk_summary"))
    risk_summary = raw_risk_summary if _holding_ai_is_precise(raw_risk_summary) else defaults["risk_summary"]
    raw_reason = _holding_ai_normalize_fact(adjustment.get("reason"))
    adjustment_reason = raw_reason if _holding_ai_is_precise(raw_reason) else defaults["adjustment_reason"]
    return {
        "scene": str(raw.get("scene") or "rule_trigger").strip() or "rule_trigger",
        "scene_label": scene_label,
        "confidence": round(confidence, 2),
        "evidence_strength": strength,
        "verdict": verdict,
        "verdict_label": str(raw.get("verdict_label") or {"keep": "维持原剧本", "tighten": "收紧剧本", "loosen": "放宽剧本"}[verdict]).strip(),
        "action_rewrite": defaults["action_rewrite"],
        "supporting_evidence": supporting,
        "opposing_evidence": opposing,
        "script_adjustment": {
            "adjustment": adjustment_mode,
            "adjustment_label": str(adjustment.get("adjustment_label") or {"keep": "保持", "tighten": "收紧", "loosen": "放宽"}[adjustment_mode]).strip(),
            "defense_line": str(adjustment.get("defense_line") or "keep").strip(),
            "clear_line": str(adjustment.get("clear_line") or "keep").strip(),
            "time_window": str(adjustment.get("time_window") or "keep").strip(),
            "reason": adjustment_reason,
        },
        "next_watch": defaults["next_watch"],
        "risk_summary": risk_summary,
        "evidence_used": evidence_used or supporting,
        "counter_evidence_label": defaults["counter_evidence_label"],
        "human_note": str(raw.get("human_note") or "手工执行，系统不会自动交易。").strip(),
        "provider": str((raw.get("_provider_meta") or {}).get("provider") or ("heuristic" if fallback_reason else _provider_config().provider)),
        "model": str((raw.get("_provider_meta") or {}).get("model") or ""),
        "fallback_reason": fallback_reason,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "base_action": base_action,
    }


def _heuristic_holding_ai_review(review: Mapping[str, Any]) -> dict[str, Any]:
    decision = dict((review.get("holding_decision") or {}))
    evidence = dict((decision.get("evidence") or {}))
    defaults = _holding_ai_default_copy(review)
    scene = "rule_trigger"
    scene_label = defaults["scene_label"]
    if str(review.get("today_action") or "") == "defense_reduce":
        scene = "price_break_with_weak_flow"
        scene_label = "价格破位 + 资金偏弱"
    elif str(review.get("today_action") or "") == "clear_exit":
        scene = "hard_stop_triggered"
        scene_label = "硬止损触发"
    elif str(review.get("today_action") or "") == "profit_take":
        scene = "profit_target_reached"
        scene_label = "止盈目标触发"
    elif str(review.get("today_action") or "") == "refresh_quote":
        scene = "quote_missing"
        scene_label = "行情缺失"
    supporting, opposing = _holding_ai_evidence_sides(review)
    return {
        "scene": scene,
        "scene_label": scene_label,
        "confidence": 0.58,
        "evidence_strength": "medium",
        "verdict": "keep",
        "verdict_label": "维持原剧本",
        "action_rewrite": defaults["action_rewrite"],
        "supporting_evidence": supporting,
        "opposing_evidence": opposing,
        "script_adjustment": {
            "adjustment": "keep",
            "adjustment_label": "保持",
            "defense_line": "keep",
            "clear_line": "keep",
            "time_window": "keep",
            "reason": defaults["adjustment_reason"],
        },
        "next_watch": defaults["next_watch"],
        "risk_summary": defaults["risk_summary"],
        "evidence_used": supporting,
        "counter_evidence_label": defaults["counter_evidence_label"],
        "human_note": "手工执行，系统不会自动交易。",
    }


def _provider_holding_ai_review(review: Mapping[str, Any]) -> dict[str, Any]:
    config: AttributionProviderConfig = _provider_config()
    if not config.configured:
        raise DecisionLedgerError("AI provider not configured")
    system_prompt, user_prompt = _holding_ai_review_prompt(review)
    try:
        import httpx  # type: ignore

        body = {
            "model": config.model,
            "temperature": 0.1,
            "max_tokens": 1600,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if config.provider == "deepseek":
            body["response_format"] = {"type": "json_object"}
            body["thinking"] = {"type": "disabled"}

        with httpx.Client(timeout=config.timeout_seconds, trust_env=False) as client:
            response = client.post(
                _chat_completions_url(config),
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        response.raise_for_status()
        payload = response.json()
        content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        draft = _extract_json_object(content)
    except Exception as exc:
        raise DecisionLedgerError(f"holding AI provider unavailable: {exc}") from exc
    draft["_provider_meta"] = {
        "provider": config.provider,
        "model": config.model,
        "base_url": config.base_url,
    }
    return draft


def _attach_holding_ai_reviews(
    reviews: list[dict[str, Any]],
    *,
    expected_date: str,
) -> list[dict[str, Any]]:
    if not reviews:
        return reviews
    store = _holding_ai_review_store()
    cache = dict(store.get("items") or {}) if isinstance(store.get("items"), dict) else {}
    changed = False
    attached: list[dict[str, Any]] = []
    for review in reviews:
        cache_key = _holding_ai_cache_key(review, expected_date)
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            attached.append({**review, "holding_ai_review": cached})
            continue
        fallback_reason = ""
        try:
            raw = _provider_holding_ai_review(review)
        except DecisionLedgerError as exc:
            fallback_reason = str(exc)
            raw = _heuristic_holding_ai_review(review)
        sanitized = _sanitize_holding_ai_review(
            review=review,
            raw=raw,
            fallback_reason=fallback_reason,
        )
        cache[cache_key] = sanitized
        changed = True
        attached.append({**review, "holding_ai_review": sanitized})
    if changed:
        keys = sorted(cache.keys(), reverse=True)[:200]
        trimmed = {key: cache[key] for key in keys if key in cache}
        _holding_ai_review_save(
            {
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "items": trimmed,
            }
        )
    return attached


def build_portfolio_account_view(*, refresh_quotes: bool = False) -> dict[str, Any]:
    """Build the canonical account-state view for the Portfolio page.

    Combines:
    * the canonical account book (mode, cash, fills, positions),
    * the today-action-decisions store so we can surface unreconciled
      "done" actions inline, and
    * a fresh ``compute_readiness`` payload so the front-end can render
      the same fail-closed gate it shows on the Today page.
    """

    ensure_runtime_dirs()
    trade_date_hint = expected_trade_date()
    decision_brief = safe_canonical_load(load_decision_brief, trade_date=trade_date_hint)
    watchlist = safe_canonical_load(load_watchlist_snapshot, trade_date=trade_date_hint)
    screening_batch = safe_canonical_load(load_screening_batch, trade_date=trade_date_hint)
    confirmation = safe_canonical_load(load_confirmation, trade_date=trade_date_hint)
    quality_status = safe_canonical_load(load_quality_status, lane="all")
    account_book = load_account_book()
    today_action_decisions = load_today_action_decision_store()

    readiness = compute_readiness(
        watchlist=watchlist,
        screening_batch=screening_batch,
        confirmation=confirmation,
        decision_brief=decision_brief,
        quality_status=quality_status,
        account_book=account_book,
        today_action_decisions=today_action_decisions,
        dataset_freshness=build_dataset_freshness_rows(
            expected_date=trade_date_hint,
            now=datetime.now(),
        ),
    )
    account_view = compute_account_view(account_book)
    cash_balance = float(account_view.get("cash_balance") or 0.0)

    # Resolve names for positions where we only stored the code.
    watchlist_index: dict[str, str] = {}

    def _code_aliases(value: Any) -> set[str]:
        code = str(value or "").strip().lower()
        if not code:
            return set()
        aliases = {code}
        bare = code[2:] if len(code) == 8 and code[:2].isalpha() else code
        aliases.add(bare)
        if len(bare) == 6 and bare.isdigit():
            aliases.add(f"sh{bare}" if bare.startswith("6") else f"sz{bare}")
        return aliases

    for stock in _portfolio_watchlist_items(watchlist):
        code = str(stock.get("code") or "").lower()
        name = str(stock.get("name") or "").strip()
        if code and name:
            for alias in _code_aliases(code):
                watchlist_index[alias] = name

    def _resolve_name(code: str, fallback: str) -> str:
        for alias in _code_aliases(code):
            if alias in watchlist_index:
                return watchlist_index[alias]
        return fallback or code

    open_positions = []
    for pos in account_view["open_positions"]:
        code = pos["code"]
        open_positions.append({**pos, "name": _resolve_name(code, pos.get("name") or code)})

    closed_positions = []
    for pos in account_view["closed_positions"]:
        code = pos["code"]
        closed_positions.append({**pos, "name": _resolve_name(code, pos.get("name") or code)})

    fills = [
        {**fill, "name": _resolve_name(str(fill.get("code") or ""), str(fill.get("name") or ""))}
        for fill in account_view["fills"]
    ]
    recent_fills = sorted(fills, key=lambda f: f.get("ts", ""), reverse=True)[:25]

    quote_index, market_status = _portfolio_quote_index(
        [str(pos.get("code") or "") for pos in open_positions],
        trade_date=str(readiness.get("expected_trade_date") or expected_trade_date()),
        refresh_quotes=refresh_quotes,
    )
    open_positions = _attach_portfolio_market_values(open_positions, quote_index)
    review_trade_date = str(readiness.get("expected_trade_date") or expected_trade_date())
    holding_reviews, holding_action_summary = _build_holding_reviews(
        open_positions,
        watchlist=watchlist,
        position_plans=account_view.get("position_plans") or [],
        expected_date=review_trade_date,
        readiness=readiness,
        screening_batch=screening_batch,
    )
    holding_reviews = _attach_holding_ai_reviews(
        holding_reviews,
        expected_date=review_trade_date,
    )
    market_value = round_money(sum(float(p.get("market_value") or 0.0) for p in open_positions if p.get("market_value") is not None))
    unrealized_pnl = round_money(sum(float(p.get("unrealized_pnl") or 0.0) for p in open_positions if p.get("unrealized_pnl") is not None))
    total_pnl = round_money(float(account_view["realized_pnl"]) + unrealized_pnl)
    missing_quote_count = len(market_status.get("missing_codes") or [])
    quote_value_detail = f"{len(open_positions)} 只持仓，未刷新行情"
    if market_status["status"] == "ok":
        quote_value_detail = f"{len(open_positions)} 只持仓，已按行情估值"
    elif market_status["status"] == "partial":
        quote_value_detail = f"{len(open_positions)} 只持仓，部分行情估值，缺 {missing_quote_count} 只"
    book_value = round_money(cash_balance + (market_value if market_status["status"] in {"ok", "partial"} else float(account_view["equity_at_cost"])))

    summary_cards = [
        {
            "label": "运行模式",
            "value": account_view["mode_label"],
            "detail": account_view.get("mode_updated_at") or "未设置",
            "tone": account_view["mode_tone"],
        },
        {
            "label": "可用现金",
            "value": f"¥{cash_balance:,.2f}",
            "detail": f"起始 ¥{account_view['starting_cash']:,.2f}",
            "tone": "risk" if cash_balance < 0 else "info",
        },
        {
            "label": "持仓市值",
            "value": f"¥{market_value:,.2f}" if market_status["status"] in {"ok", "partial"} else f"¥{account_view['equity_at_cost']:,.2f}",
            "detail": quote_value_detail,
            "tone": "watch" if open_positions else "info",
        },
        {
            "label": "总盈亏",
            "value": f"¥{total_pnl:,.2f}",
            "detail": f"浮盈亏 ¥{unrealized_pnl:,.2f} / 已实现 ¥{account_view['realized_pnl']:,.2f}",
            "tone": "positive" if total_pnl >= 0 else "risk",
        },
    ]

    account_state = readiness.get("account_state") or {}
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": readiness.get("expected_trade_date"),
        "expected_trade_date": readiness.get("expected_trade_date"),
        "data_trade_date": readiness.get("data_trade_date"),
        "readiness": readiness,
        "account": {
            **account_view,
            "book_value": book_value,
            "market_value": market_value if market_status["status"] in {"ok", "partial"} else None,
            "unrealized_pnl": unrealized_pnl if market_status["status"] in {"ok", "partial"} else None,
            "total_pnl": total_pnl,
            "open_positions": open_positions,
            "closed_positions": closed_positions,
            "available_modes": list(ACCOUNT_MODES),
        },
        "market_quotes": market_status,
        "holding_reviews": holding_reviews,
        "holding_action_summary": holding_action_summary,
        "summary_cards": summary_cards,
        "recent_fills": recent_fills,
        "unreconciled_intents": account_state.get("unreconciled_intents", []),
        "reconciliation": account_state.get("reconciliation", {}),
        "ready_for_live_small": bool(account_state.get("ready_for_live_small")),
        "links": {
            "today": "/today",
            "watchlist": "/watchlist",
            "portfolio": "/portfolio",
        },
    }
