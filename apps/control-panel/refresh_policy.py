"""Central refresh policy for Prism control-panel auto refresh.

The policy here is intentionally data-only plus small pure helpers.  FastAPI
endpoints can use it for status, manual trigger validation, and auto-refresh
decisions without scattering task/window/cooldown rules across handlers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Sequence


MarketMode = str

STALE_TRIGGER_REASONS = {
    "manifest_missing",
    "freshness_stale",
    "freshness_expired",
    "freshness_unknown",
    "live_small_not_allowed",
    "fallback_not_allowed",
    "trade_date_mismatch",
    "trade_date_unknown",
    "missing",
}


@dataclass(frozen=True)
class TimeWindow:
    key: str
    label: str
    start: str
    end: str

    def contains(self, value: datetime) -> bool:
        start_minutes = _clock_minutes(self.start)
        end_minutes = _clock_minutes(self.end)
        current = value.hour * 60 + value.minute
        return start_minutes <= current <= end_minutes

    def as_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "start": self.start,
            "end": self.end,
        }


@dataclass(frozen=True)
class TaskPolicy:
    task_name: str
    title: str
    kind: str
    cooldown_seconds: int
    auto_windows: tuple[str, ...] = ("trading", "standby")
    manifest_dependencies: tuple[str, ...] = ()
    stale_reasons: tuple[str, ...] = tuple(sorted(STALE_TRIGGER_REASONS))
    auto_enabled: bool = True
    fixed_cron_only: bool = False
    same_family: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_name": self.task_name,
            "title": self.title,
            "kind": self.kind,
            "cooldown_seconds": self.cooldown_seconds,
            "auto_windows": list(self.auto_windows),
            "manifest_dependencies": list(self.manifest_dependencies),
            "stale_reasons": list(self.stale_reasons),
            "auto_enabled": self.auto_enabled,
            "fixed_cron_only": self.fixed_cron_only,
            "same_family": self.same_family or self.task_name,
        }


@dataclass(frozen=True)
class PagePolicy:
    page: str
    allowed_tasks: tuple[str, ...]
    related_tasks: tuple[str, ...]
    poll_seconds: Mapping[MarketMode, int]
    stale_after_seconds: Mapping[MarketMode, int]
    auto_on_open: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "allowed_tasks": list(self.allowed_tasks),
            "related_tasks": list(self.related_tasks),
            "poll_seconds": dict(self.poll_seconds),
            "stale_after_seconds": dict(self.stale_after_seconds),
            "auto_on_open": self.auto_on_open,
        }


@dataclass(frozen=True)
class CronJobPolicy:
    task_name: str
    name: str
    cron_expr: str
    command: tuple[str, ...]
    delivery_default: bool = True
    fixed_window: bool = True

    def as_openclaw_job(self, *, target: str = "") -> dict[str, Any]:
        command = " ".join(self.command)
        message = (
            f"执行 {self.name}。发往飞书的消息由 shell runner 自己完成；"
            "最终回复只允许写 `DONE` 或 `FAILED: ...`。\n\n"
            f"直接执行：`SEND_TO_FEISHU=1 FEISHU_TARGET={target} {command}`\n"
            "如果 runner 已在运行或返回 running 状态，禁止重复执行。"
        )
        return {
            "agentId": "invest",
            "sessionKey": "agent:invest:main",
            "name": self.name,
            "enabled": True,
            "schedule": {
                "kind": "cron",
                "expr": self.cron_expr,
                "tz": "Asia/Shanghai",
            },
            "sessionTarget": "isolated",
            "wakeMode": "now",
            "payload": {
                "kind": "agentTurn",
                "message": message,
                "timeoutSeconds": 600,
                "toolsAllow": ["exec"],
                "thinking": "off",
                "lightContext": True,
            },
            "delivery": {
                "mode": "none",
                "channel": "feishu",
                "to": target,
            },
            "state": {},
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_name": self.task_name,
            "name": self.name,
            "cron_expr": self.cron_expr,
            "command": list(self.command),
            "delivery_default": self.delivery_default,
            "fixed_window": self.fixed_window,
        }


AUTO_WINDOWS: dict[str, TimeWindow] = {
    "premarket": TimeWindow("premarket", "盘前准备窗口", "09:00", "09:24"),
    "morning": TimeWindow("morning", "早盘交易窗口", "09:25", "11:30"),
    "midday": TimeWindow("midday", "午盘刷新窗口", "11:30", "13:20"),
    "afternoon": TimeWindow("afternoon", "午后交易窗口", "13:00", "15:00"),
    "preclose": TimeWindow("preclose", "收盘前风险窗口", "14:40", "14:59"),
    "postclose": TimeWindow("postclose", "收盘后总控窗口", "15:00", "15:30"),
}


TASK_POLICIES: dict[str, TaskPolicy] = {
    "quotes_light": TaskPolicy(
        task_name="quotes_light",
        title="轻量行情补刷",
        kind="lightweight",
        cooldown_seconds=90,
        auto_windows=("premarket", "morning", "midday", "afternoon", "preclose"),
        manifest_dependencies=("quotes.batch",),
        same_family="lightweight_market_data",
    ),
    "capital_flow_light": TaskPolicy(
        task_name="capital_flow_light",
        title="轻量资金流补刷",
        kind="lightweight",
        cooldown_seconds=360,
        auto_windows=("morning", "midday", "afternoon", "preclose"),
        manifest_dependencies=("capital_flow.batch",),
        same_family="lightweight_market_data",
    ),
    "watchlist_refresh": TaskPolicy(
        task_name="watchlist_refresh",
        title="自选股全流程刷新",
        kind="heavyweight",
        cooldown_seconds=15 * 60,
        auto_windows=("premarket", "morning", "afternoon", "preclose"),
        manifest_dependencies=("watchlist.snapshot", "quotes.snapshot", "bars.daily", "capital_flow.daily", "capital_flow.batch"),
        same_family="watchlist_refresh",
    ),
    "command_brief": TaskPolicy(
        task_name="command_brief",
        title="投资总控简报",
        kind="heavyweight",
        cooldown_seconds=12 * 60,
        auto_windows=("morning", "midday", "afternoon", "preclose", "postclose"),
        manifest_dependencies=("decision_brief.snapshot", "watchlist.snapshot", "screening.batch", "screening.confirmation"),
        same_family="command_brief",
    ),
    "aggressive": TaskPolicy(
        task_name="aggressive",
        title="进攻型早盘扫描",
        kind="heavyweight",
        cooldown_seconds=35 * 60,
        auto_windows=("morning",),
        manifest_dependencies=("screening.scan_result", "screening.batch", "quotes.batch", "capital_flow.batch"),
        same_family="aggressive_pipeline",
    ),
    "midday_refresh": TaskPolicy(
        task_name="midday_refresh",
        title="进攻型午盘刷新",
        kind="heavyweight",
        cooldown_seconds=20 * 60,
        auto_windows=("midday",),
        manifest_dependencies=("screening.scan_result", "screening.batch"),
        same_family="aggressive_pipeline",
    ),
    "midday_confirmation": TaskPolicy(
        task_name="midday_confirmation",
        title="进攻型午盘确认",
        kind="heavyweight",
        cooldown_seconds=15 * 60,
        auto_windows=("midday", "afternoon"),
        manifest_dependencies=("screening.confirmation", "screening.batch", "screening.scan_result"),
        same_family="midday_confirmation",
    ),
    "preclose_risk_refresh": TaskPolicy(
        task_name="preclose_risk_refresh",
        title="收盘前风险刷新",
        kind="heavyweight",
        cooldown_seconds=30 * 60,
        auto_windows=("preclose",),
        manifest_dependencies=("watchlist.snapshot", "screening.batch", "decision_brief.snapshot"),
        auto_enabled=False,
        fixed_cron_only=True,
        same_family="command_brief",
    ),
    "postclose_command_brief": TaskPolicy(
        task_name="postclose_command_brief",
        title="收盘后总控简报",
        kind="heavyweight",
        cooldown_seconds=30 * 60,
        auto_windows=("postclose",),
        manifest_dependencies=("decision_brief.snapshot",),
        auto_enabled=False,
        fixed_cron_only=True,
        same_family="command_brief",
    ),
}


PAGE_POLICIES: dict[str, PagePolicy] = {
    "today": PagePolicy(
        page="today",
        allowed_tasks=(
            "quotes_light",
            "capital_flow_light",
            "watchlist_refresh",
            "command_brief",
            "midday_refresh",
            "midday_confirmation",
            "aggressive",
        ),
        related_tasks=(
            "quotes_light",
            "capital_flow_light",
            "watchlist_refresh",
            "watchlist",
            "command_brief",
            "aggressive",
            "midday_refresh",
            "midday_confirmation",
        ),
        poll_seconds={"trading": 45, "standby": 60, "off": 300},
        stale_after_seconds={"trading": 2700, "standby": 5400, "off": 14_400},
    ),
    "watchlist": PagePolicy(
        page="watchlist",
        allowed_tasks=("quotes_light", "capital_flow_light", "watchlist_refresh", "watchlist"),
        related_tasks=("quotes_light", "capital_flow_light", "watchlist_refresh", "watchlist", "command_brief"),
        poll_seconds={"trading": 60, "standby": 90, "off": 300},
        stale_after_seconds={"trading": 3600, "standby": 7200, "off": 14_400},
    ),
    "opportunities": PagePolicy(
        page="opportunities",
        allowed_tasks=("quotes_light", "capital_flow_light", "midday_refresh", "aggressive", "midday_confirmation"),
        related_tasks=("quotes_light", "capital_flow_light", "aggressive", "midday_refresh", "midday_confirmation"),
        poll_seconds={"trading": 40, "standby": 60, "off": 300},
        stale_after_seconds={"trading": 1800, "standby": 3600, "off": 10_800},
    ),
    "review": PagePolicy(
        page="review",
        allowed_tasks=("command_brief",),
        related_tasks=("command_brief",),
        poll_seconds={"trading": 120, "standby": 180, "off": 600},
        stale_after_seconds={"trading": 7200, "standby": 14_400, "off": 86_400},
        auto_on_open=False,
    ),
}


CRON_POLICIES: tuple[CronJobPolicy, ...] = (
    CronJobPolicy(
        task_name="watchlist_refresh",
        name="自选股早盘分析",
        cron_expr="50 9 * * 1-5",
        command=("bash", "apps/scripts/run_watchlist_refresh.sh"),
    ),
    CronJobPolicy(
        task_name="aggressive",
        name="进攻型选股-早盘",
        cron_expr="30 10 * * 1-5",
        command=(
            "bash",
            "packages/screener/run_full_workflow_cron.sh",
            "--pool",
            "aggressive",
            "--top",
            "10",
            "--handoff-analyzer",
            "--handoff-top",
            "3",
            "--handoff-min-consistency",
            "6",
        ),
    ),
    CronJobPolicy(
        task_name="midday_refresh",
        name="进攻型选股-午盘",
        cron_expr="10 13 * * 1-5",
        command=("bash", "packages/screener/run_midday_refresh_cron.sh", "--pool", "aggressive", "--top", "10"),
    ),
    CronJobPolicy(
        task_name="midday_confirmation",
        name="进攻型选股-午盘确认",
        cron_expr="45 13 * * 1-5",
        command=("bash", "packages/screener/run_midday_confirmation_cron.sh", "--pool", "aggressive", "--top", "10"),
    ),
    CronJobPolicy(
        task_name="preclose_risk_refresh",
        name="收盘前风险刷新",
        cron_expr="50 14 * * 1-5",
        command=("bash", "apps/scripts/run_command_brief.sh"),
    ),
    CronJobPolicy(
        task_name="postclose_command_brief",
        name="收盘后总控简报",
        cron_expr="5 15 * * 1-5",
        command=("bash", "apps/scripts/run_command_brief.sh"),
    ),
)


def _clock_minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def current_market_mode(now: datetime | None = None) -> tuple[str, str]:
    current = now or datetime.now()
    if current.weekday() >= 5:
        return "off", "周末休市"

    clock = current.hour * 60 + current.minute
    if (570 <= clock < 690) or (780 <= clock < 900):
        return "trading", "交易时段"
    if (540 <= clock < 570) or (690 <= clock < 780) or (900 <= clock < 930):
        return "standby", "盘前/午间/收盘过渡"
    return "off", "非交易时段"


def active_auto_windows(now: datetime | None = None) -> list[dict[str, str]]:
    current = now or datetime.now()
    if current.weekday() >= 5:
        return []
    return [window.as_dict() for window in AUTO_WINDOWS.values() if window.contains(current)]


def task_policy(task_name: str) -> TaskPolicy | None:
    normalized = normalize_task_name(task_name)
    return TASK_POLICIES.get(normalized)


def page_policy(page: str) -> PagePolicy | None:
    return PAGE_POLICIES.get(str(page or "").strip().lower())


def normalize_task_name(task_name: Any) -> str:
    text = str(task_name or "").strip()
    if text == "watchlist":
        return "watchlist_refresh"
    return text


def task_family(task_name: str) -> str:
    policy = task_policy(task_name)
    return (policy.same_family if policy else None) or normalize_task_name(task_name)


def task_is_running(task_name: str, running: Sequence[Mapping[str, Any]]) -> bool:
    family = task_family(task_name)
    for item in running:
        if task_family(str(item.get("task_name") or "")) == family:
            return True
    return False


def cooldown_state(
    *,
    task_name: str,
    state: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now()
    policy = task_policy(task_name)
    seconds = int(policy.cooldown_seconds if policy else 900)
    last = find_last_trigger(task_name=task_name, state=state)
    last_trigger_at = str((last or {}).get("last_trigger_at") or "").strip()
    last_dt = parse_timestamp(last_trigger_at)
    if not last_dt:
        remaining = 0
        next_allowed_at = ""
    else:
        elapsed = max(int((current - last_dt).total_seconds()), 0)
        remaining = max(seconds - elapsed, 0)
        next_allowed_at = (last_dt + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")
    last_task_name = ""
    if last:
        last_task_name = str(last.get("task_name") or normalize_task_name(task_name))
    return {
        "seconds": seconds,
        "remaining_seconds": remaining,
        "ready": remaining == 0,
        "next_allowed_at": next_allowed_at,
        "last_trigger_at": last_trigger_at,
        "last_task_name": last_task_name,
        "last_run_id": str((last or {}).get("run_id") or ""),
        "last_reason": str((last or {}).get("reason") or ""),
        "last_decision": (last or {}).get("decision") or {},
    }


def page_cooldown_state(
    *,
    page: str,
    task_name: str,
    state: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    cooldown = cooldown_state(task_name=task_name, state=state, now=now)
    pages = state.get("pages") if isinstance(state, Mapping) else {}
    page_state = pages.get(page) if isinstance(pages, Mapping) and isinstance(pages.get(page), Mapping) else {}
    if page_state and normalize_task_name(page_state.get("task_name")) == normalize_task_name(task_name):
        cooldown["page_last_trigger_at"] = str(page_state.get("last_trigger_at") or "")
        cooldown["page_last_run_id"] = str(page_state.get("run_id") or "")
    return cooldown


def find_last_trigger(*, task_name: str, state: Mapping[str, Any]) -> Mapping[str, Any] | None:
    tasks = state.get("tasks") if isinstance(state, Mapping) else {}
    normalized = normalize_task_name(task_name)
    family = task_family(normalized)
    candidates: list[Mapping[str, Any]] = []
    if isinstance(tasks, Mapping):
        exact = tasks.get(normalized)
        if isinstance(exact, Mapping):
            candidates.append(exact)
        for key, value in tasks.items():
            if not isinstance(value, Mapping):
                continue
            if task_family(str(key)) == family:
                candidates.append(value)
    pages = state.get("pages") if isinstance(state, Mapping) else {}
    if isinstance(pages, Mapping):
        for value in pages.values():
            if isinstance(value, Mapping) and task_family(str(value.get("task_name") or "")) == family:
                candidates.append(value)
    if not candidates:
        return None
    return max(candidates, key=lambda item: parse_timestamp(str(item.get("last_trigger_at") or "")) or datetime.min)


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def manifest_trigger_reasons(freshness: Iterable[Mapping[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for item in freshness:
        for reason in item.get("stale_reasons") or []:
            reason_text = str(reason or "").strip()
            if reason_text in STALE_TRIGGER_REASONS and reason_text not in reasons:
                reasons.append(reason_text)
    return reasons


def source_key_task(source_key: str, *, now: datetime | None = None) -> str:
    key = str(source_key or "").strip()
    if key == "watchlist":
        return "watchlist_refresh"
    if key == "screening":
        return "midday_refresh" if _in_window("midday", now or datetime.now()) else "aggressive"
    if key == "confirmation":
        return "midday_confirmation"
    if key == "decision_brief":
        return "command_brief"
    return "command_brief"


def pick_recommended_task(
    *,
    page: str,
    freshness: Sequence[Mapping[str, Any]],
    market_mode: str,
    readiness_payload: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> str:
    page_cfg = page_policy(page)
    allowed = set(page_cfg.allowed_tasks if page_cfg else ())
    readiness_tasks = [
        normalize_task_name(name)
        for name in ((readiness_payload or {}).get("recommended_tasks") or [])
        if normalize_task_name(name)
    ]
    if readiness_payload and not readiness_payload.get("ready"):
        for candidate in readiness_tasks:
            if not allowed or candidate in allowed:
                return candidate

    stale_items = [item for item in freshness if item.get("stale")]
    for item in stale_items:
        candidate = source_key_task(str(item.get("key") or ""), now=now)
        if not allowed or candidate in allowed:
            return candidate

    if page == "watchlist":
        return "watchlist_refresh"
    if page == "opportunities":
        return "midday_refresh" if market_mode != "off" else "aggressive"
    if page == "review":
        return "command_brief"
    return "command_brief"


def eligible_lightweight_task(
    *,
    page: str,
    freshness: Sequence[Mapping[str, Any]],
    allowed_tasks: Iterable[str],
) -> str | None:
    allowed = {normalize_task_name(item) for item in allowed_tasks}
    if "quotes_light" in allowed and any(_source_needs_quote_refresh(item) for item in freshness):
        return "quotes_light"
    if "capital_flow_light" in allowed and any(_source_needs_capital_refresh(item) for item in freshness):
        return "capital_flow_light"
    return None


def evaluate_auto_refresh(
    *,
    page: str,
    recommended_task: str,
    freshness: Sequence[Mapping[str, Any]],
    readiness_payload: Mapping[str, Any] | None,
    running: Sequence[Mapping[str, Any]],
    cooldown: Mapping[str, Any],
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now()
    page_cfg = page_policy(page)
    task_name = normalize_task_name(recommended_task)
    policy = task_policy(task_name)
    manifest_reasons = manifest_trigger_reasons(freshness)
    stale_count = sum(1 for item in freshness if item.get("stale"))
    auto_windows = active_auto_windows(current)
    active_window_keys = {item["key"] for item in auto_windows}
    reasons: list[str] = []
    blockers: list[str] = []

    if page_cfg is None:
        blockers.append("unsupported_page")
    elif task_name not in {normalize_task_name(item) for item in page_cfg.allowed_tasks}:
        blockers.append("task_not_allowed_for_page")

    if policy is None:
        blockers.append("unknown_task_policy")
    else:
        if not policy.auto_enabled and not force:
            blockers.append("fixed_cron_or_manual_only")
        if policy.fixed_cron_only and not force:
            blockers.append("fixed_cron_only")
        if not active_window_keys.intersection(policy.auto_windows) and not force:
            blockers.append("outside_auto_window")
        if not stale_count and not force:
            blockers.append("manifest_not_stale")
        if not manifest_reasons and policy.kind == "heavyweight" and not force:
            blockers.append("no_manifest_trigger")

    if not (page_cfg and page_cfg.auto_on_open) and not force:
        blockers.append("page_auto_disabled")
    if task_is_running(task_name, running):
        blockers.append("running")
    if int(cooldown.get("remaining_seconds") or 0) > 0 and not force:
        blockers.append("cooldown")
    if any("provider_failure" in set(item.get("stale_reasons") or []) for item in freshness):
        blockers.append("provider_failure")
    if readiness_payload and readiness_payload.get("provider_failure"):
        blockers.append("provider_failure")

    if manifest_reasons:
        reasons.extend(manifest_reasons)
    elif stale_count:
        reasons.append("source_stale")
    elif force:
        reasons.append("manual_force")
    else:
        reasons.append("no_stale_manifest")

    allowed = not blockers
    decision = {
        "enabled": bool(page_cfg.auto_on_open if page_cfg else False),
        "allowed": allowed,
        "should_trigger": allowed,
        "force": bool(force),
        "page": page,
        "task_name": task_name,
        "task_kind": policy.kind if policy else "unknown",
        "reason_codes": _unique(reasons),
        "blocked_reasons": _unique(blockers),
        "active_windows": auto_windows,
        "required_windows": list(policy.auto_windows if policy else ()),
        "manifest_reasons": manifest_reasons,
        "stale_count": stale_count,
        "cooldown_remaining_seconds": int(cooldown.get("remaining_seconds") or 0),
        "next_allowed_at": str(cooldown.get("next_allowed_at") or ""),
        "summary": "",
    }
    decision["summary"] = summarize_auto_decision(decision)
    return decision


def summarize_auto_decision(decision: Mapping[str, Any]) -> str:
    task_name = str(decision.get("task_name") or "")
    title = (task_policy(task_name).title if task_policy(task_name) else task_name) or "刷新任务"
    if decision.get("should_trigger"):
        reasons = ", ".join(decision.get("reason_codes") or [])
        return f"自动触发 {title}：{reasons or '策略允许'}。"
    blocked = list(decision.get("blocked_reasons") or [])
    if not blocked:
        return "没有自动刷新：当前没有需要补刷的 stale/expired manifest。"
    labels = {
        "cooldown": "冷却未结束",
        "running": "同类任务运行中",
        "outside_auto_window": "不在允许自动刷新窗口",
        "manifest_not_stale": "manifest 未 stale/expired",
        "no_manifest_trigger": "没有 manifest 触发原因",
        "fixed_cron_only": "仅固定 cron 或手动触发",
        "fixed_cron_or_manual_only": "仅固定 cron 或手动触发",
        "page_auto_disabled": "该页面未开启打开即自动刷新",
        "task_not_allowed_for_page": "当前页面不允许该任务",
        "provider_failure": "上游 provider 失败",
    }
    return "没有自动刷新：" + "，".join(labels.get(item, item) for item in blocked) + "。"


def build_policy_payload() -> dict[str, Any]:
    return {
        "tasks": {key: value.as_dict() for key, value in TASK_POLICIES.items()},
        "pages": {key: value.as_dict() for key, value in PAGE_POLICIES.items()},
        "windows": {key: value.as_dict() for key, value in AUTO_WINDOWS.items()},
        "cron": [item.as_dict() for item in CRON_POLICIES],
    }


def validate_cron_policies(cron_jobs: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    expected = {item.name: item for item in CRON_POLICIES}
    actual_by_name: dict[str, Mapping[str, Any]] = {}
    for job in cron_jobs or []:
        name = str(job.get("name") or "").strip()
        if name:
            actual_by_name[name] = job

    missing = []
    mismatched = []
    for name, policy in expected.items():
        job = actual_by_name.get(name)
        if not job:
            missing.append(name)
            continue
        schedule = job.get("schedule") if isinstance(job.get("schedule"), Mapping) else {}
        expr = str(schedule.get("expr") or "").strip()
        tz = str(schedule.get("tz") or "").strip()
        if expr != policy.cron_expr or tz != "Asia/Shanghai":
            mismatched.append(
                {
                    "name": name,
                    "expected_expr": policy.cron_expr,
                    "actual_expr": expr,
                    "expected_tz": "Asia/Shanghai",
                    "actual_tz": tz,
                }
            )
    return {
        "ok": not missing and not mismatched,
        "missing": missing,
        "mismatched": mismatched,
        "expected": [item.as_dict() for item in CRON_POLICIES],
    }


def _source_needs_quote_refresh(item: Mapping[str, Any]) -> bool:
    reasons = {str(reason) for reason in item.get("stale_reasons") or []}
    key = str(item.get("key") or "")
    return (key.startswith("quotes.") or key in {"watchlist", "screening"}) and bool(reasons & STALE_TRIGGER_REASONS)


def _source_needs_capital_refresh(item: Mapping[str, Any]) -> bool:
    reasons = {str(reason) for reason in item.get("stale_reasons") or []}
    key = str(item.get("key") or "")
    text = " ".join([str(item.get("key") or ""), str(item.get("label") or ""), str(item.get("detail") or "")]).lower()
    return bool(reasons & STALE_TRIGGER_REASONS) and (key.startswith("capital_flow.") or "capital" in text or "资金" in text)


def _in_window(key: str, current: datetime) -> bool:
    window = AUTO_WINDOWS.get(key)
    return bool(window and current.weekday() < 5 and window.contains(current))


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


__all__ = [
    "AUTO_WINDOWS",
    "CRON_POLICIES",
    "PAGE_POLICIES",
    "TASK_POLICIES",
    "active_auto_windows",
    "build_policy_payload",
    "cooldown_state",
    "current_market_mode",
    "eligible_lightweight_task",
    "evaluate_auto_refresh",
    "normalize_task_name",
    "page_cooldown_state",
    "page_policy",
    "pick_recommended_task",
    "summarize_auto_decision",
    "task_family",
    "task_is_running",
    "task_policy",
    "validate_cron_policies",
]
