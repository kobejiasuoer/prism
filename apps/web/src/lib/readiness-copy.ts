import type { ReadinessMode, ReadinessPayload, RefreshStatus, Tone } from "./types";

export const READINESS_MODE_COPY: Record<
  ReadinessMode,
  {
    badge: string;
    title: string;
    detail: string;
    realMoney: string;
    tone: Tone;
    bg: string;
    border: string;
    iconColor: string;
  }
> = {
  live_ready: {
    badge: "Live Ready",
    title: "数据已就绪，可按纪律执行",
    detail: "核心数据已对齐预期交易日，仍需按仓位纪律手工执行。",
    realMoney: "真钱执行：允许按纪律手工执行",
    tone: "positive",
    bg: "color-mix(in srgb, var(--positive) 8%, transparent)",
    border: "color-mix(in srgb, var(--positive) 30%, transparent)",
    iconColor: "var(--positive)",
  },
  shadow_only: {
    badge: "Shadow Only",
    title: "仅影子盘观察，真钱执行：禁止",
    detail: "当前状态只适合观察和复盘，不可把页面动作当作真钱依据。",
    realMoney: "真钱执行：禁止",
    tone: "warning",
    bg: "color-mix(in srgb, var(--warning) 10%, transparent)",
    border: "color-mix(in srgb, var(--warning) 35%, transparent)",
    iconColor: "var(--warning)",
  },
  blocked: {
    badge: "Blocked",
    title: "数据未就绪，先恢复数据链路",
    detail: "关键数据源或质检未对齐，先刷新安全任务并查看日志。",
    realMoney: "真钱执行：禁止",
    tone: "risk",
    bg: "color-mix(in srgb, var(--negative) 10%, transparent)",
    border: "color-mix(in srgb, var(--negative) 40%, transparent)",
    iconColor: "var(--negative)",
  },
};

export const REFRESH_TASK_COPY: Record<
  string,
  {
    title: string;
    category: "safe" | "advanced" | "danger";
    summary: string;
    impact: string;
  }
> = {
  quotes_light: {
    title: "轻量行情补刷",
    category: "safe",
    summary: "只补行情 manifest 相关轻量数据。",
    impact: "不写真实账本，不提交成交。",
  },
  capital_flow_light: {
    title: "轻量资金流补刷",
    category: "safe",
    summary: "只补资金流 manifest 相关轻量数据。",
    impact: "不写真实账本，不提交成交。",
  },
  watchlist: {
    title: "自选股全流程刷新",
    category: "safe",
    summary: "刷新自选股摘要、报告和相关质检。",
    impact: "会重算报告文件；不写真实账本，不自动下单。",
  },
  watchlist_refresh: {
    title: "自选股全流程刷新",
    category: "safe",
    summary: "刷新自选股摘要、报告和相关质检。",
    impact: "会重算报告文件；不写真实账本，不自动下单。",
  },
  command_brief: {
    title: "投资总控简报",
    category: "safe",
    summary: "生成总控简报，用于恢复 Dashboard 口径。",
    impact: "会生成简报 artifact；不写真实账本，不自动下单。",
  },
  aggressive: {
    title: "进攻型早盘扫描",
    category: "advanced",
    summary: "重跑观察池早盘主流程。",
    impact: "会重算候选池和报告，适合确认你需要重跑时手动触发。",
  },
  midday_refresh: {
    title: "进攻型午盘刷新",
    category: "advanced",
    summary: "重跑午盘观察池刷新。",
    impact: "会更新午盘候选数据，不写真实账本。",
  },
  midday_confirmation: {
    title: "进攻型午盘确认",
    category: "advanced",
    summary: "按晨间基线做午盘承接确认。",
    impact: "会更新午盘确认产物，不写真实账本。",
  },
  preclose_risk_refresh: {
    title: "收盘前风险刷新",
    category: "advanced",
    summary: "固定窗口/手动风险刷新。",
    impact: "会更新风险简报产物，不写真实账本。",
  },
  postclose_command_brief: {
    title: "收盘后总控简报",
    category: "advanced",
    summary: "收盘后生成总控简报。",
    impact: "会更新简报产物，不写真实账本。",
  },
  unsafe_apply: {
    title: "强制保存参数",
    category: "danger",
    summary: "绕过参数评估硬拦截。",
    impact: "可能让下游刷新使用高风险参数，必须确认影响范围。",
  },
  allow_unsafe: {
    title: "允许跳过实盘校验",
    category: "danger",
    summary: "绕过 live_small 前置校验。",
    impact: "会影响真钱执行判断，只能在 Portfolio 的独立护栏内使用。",
  },
  portfolio_mode: {
    title: "账户模式切换",
    category: "danger",
    summary: "改变研究态 / 影子盘 / 小额实盘。",
    impact: "会影响 readiness 和真钱执行判断。",
  },
  portfolio_cash: {
    title: "账户现金调整",
    category: "danger",
    summary: "写入账户现金流水。",
    impact: "会影响真实账本视图。",
  },
  portfolio_reconcile: {
    title: "账户对账",
    category: "danger",
    summary: "写入券商现金 / 权益对账记录。",
    impact: "会影响 live_small readiness。",
  },
};

export const REFRESH_REASON_COPY: Record<string, { label: string; detail: string }> = {
  cooldown: { label: "冷却未结束", detail: "刚运行过同类任务，稍后再试。" },
  running: { label: "同类任务运行中", detail: "后台已有任务在跑，避免重复触发。" },
  outside_auto_window: { label: "不在自动刷新窗口", detail: "当前时间不允许自动触发该任务。" },
  manifest_not_stale: { label: "数据未判定过期", detail: "没有 stale/expired manifest 触发自动刷新。" },
  no_manifest_trigger: { label: "缺少 manifest 触发原因", detail: "重任务需要明确的过期原因才会自动触发。" },
  fixed_cron_only: { label: "仅固定排程或手动", detail: "该任务不会由页面自动触发。" },
  fixed_cron_or_manual_only: { label: "仅固定排程或手动", detail: "该任务不会由页面自动触发。" },
  page_auto_disabled: { label: "页面未开启自动刷新", detail: "当前页面只展示状态，不会自动补刷。" },
  task_not_allowed_for_page: { label: "页面不支持该任务", detail: "请切到对应页面或使用安全刷新入口。" },
  provider_failure: { label: "上游数据源失败", detail: "数据源返回失败，自动刷新不会强行放行真钱执行。" },
  manifest_missing: { label: "manifest 缺失", detail: "缺少 freshness 证明，不能作为真钱依据。" },
  freshness_stale: { label: "数据偏旧", detail: "数据已超过新鲜度阈值，不可作为真钱依据。" },
  freshness_expired: { label: "数据过期", detail: "数据已过期，不可作为真钱依据。" },
  freshness_unknown: { label: "新鲜度未知", detail: "无法确认数据是否有效，先按不可用处理。" },
  live_small_not_allowed: { label: "真钱执行未放行", detail: "该数据源明确不允许用于 live_small。" },
  fallback_not_allowed: { label: "回退数据不可实盘", detail: "当前使用回退数据，只能观察。" },
  trade_date_mismatch: { label: "交易日不匹配", detail: "数据交易日与预期交易日不同。" },
  trade_date_unknown: { label: "交易日未知", detail: "无法确认数据属于哪个交易日。" },
  missing: { label: "数据缺失", detail: "缺少必要数据。" },
  source_stale: { label: "来源偏旧", detail: "至少一个数据来源需要刷新。" },
  no_stale_manifest: { label: "无过期 manifest", detail: "当前没有可自动触发的过期证明。" },
  manual_force: { label: "手动强制", detail: "用户选择忽略策略限制手动刷新。" },
};

export function readinessModeCopy(mode?: string) {
  return READINESS_MODE_COPY[(mode || "blocked") as ReadinessMode] || READINESS_MODE_COPY.blocked;
}

export function refreshTaskCopy(taskName?: string) {
  const key = normalizeTaskName(taskName);
  return REFRESH_TASK_COPY[key] || {
    title: key || "刷新任务",
    category: "advanced" as const,
    summary: "后端任务接口定义的刷新任务。",
    impact: "请确认任务用途后再运行；不会由本页自动提交成交。",
  };
}

export function refreshReasonCopy(reason?: string) {
  const key = String(reason || "").trim();
  return REFRESH_REASON_COPY[key] || { label: key || "未知原因", detail: "保留原始原因供日志排查。" };
}

export function refreshReasonLabel(reason?: string) {
  return refreshReasonCopy(reason).label;
}

export function normalizeTaskName(taskName?: string) {
  const key = String(taskName || "").trim();
  return key === "watchlist" ? "watchlist_refresh" : key;
}

export function formatCooldown(seconds?: number) {
  const value = Number(seconds || 0);
  if (value <= 0) {
    return "已就绪";
  }
  if (value < 60) {
    return `${value}s`;
  }
  return `${Math.ceil(value / 60)}m`;
}

export function readinessHasStaleData(readiness?: ReadinessPayload) {
  return Boolean(
    (readiness?.stale_count || 0) > 0 ||
      (readiness?.source_freshness || []).some((item) => item.stale) ||
      (readiness?.data_trade_date &&
        readiness?.expected_trade_date &&
        readiness.data_trade_date !== readiness.expected_trade_date),
  );
}

export function readinessNextStep(readiness?: ReadinessPayload, status?: RefreshStatus) {
  if (!readiness) {
    return {
      title: "等待数据状态",
      detail: "正在读取 readiness，请先不要按页面做真钱执行。",
      taskName: status?.recommended_task?.task_name || "",
      taskTitle: status?.recommended_task?.title || "",
    };
  }

  const stale = readinessHasStaleData(readiness);
  const recommendedTaskName = normalizeTaskName(
    status?.recommended_task?.task_name || readiness.recommended_tasks?.[0],
  );
  const recommendedTaskTitle =
    status?.recommended_task?.title || refreshTaskCopy(recommendedTaskName).title || recommendedTaskName;

  if (stale) {
    return {
      title: "数据偏旧，不可作为真钱依据",
      detail: recommendedTaskName
        ? `先运行安全刷新：${recommendedTaskTitle}。若仍失败，查看最近运行日志。`
        : "先恢复数据链路；若仍失败，查看最近运行日志。",
      taskName: recommendedTaskName,
      taskTitle: recommendedTaskTitle,
    };
  }

  if (readiness.readiness_mode === "live_ready") {
    return {
      title: READINESS_MODE_COPY.live_ready.title,
      detail: "可以进入 Dashboard 或个股页按纪律复核；真实成交仍需外部券商手工完成。",
      taskName: recommendedTaskName,
      taskTitle: recommendedTaskTitle,
    };
  }

  if (readiness.readiness_mode === "shadow_only") {
    return {
      title: READINESS_MODE_COPY.shadow_only.title,
      detail: "只做观察和记录，等待交易日或链路完全就绪。",
      taskName: recommendedTaskName,
      taskTitle: recommendedTaskTitle,
    };
  }

  return {
    title: READINESS_MODE_COPY.blocked.title,
    detail: recommendedTaskName
      ? `推荐先运行：${recommendedTaskTitle}。若失败，打开最近运行日志定位原因。`
      : "先恢复数据链路；若失败，打开最近运行日志定位原因。",
    taskName: recommendedTaskName,
    taskTitle: recommendedTaskTitle,
  };
}
