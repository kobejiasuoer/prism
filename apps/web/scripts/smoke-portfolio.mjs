#!/usr/bin/env node

import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const appRoot = dirname(scriptDir);
const repoRoot = dirname(dirname(appRoot));
const projectsRoot = dirname(repoRoot);

const fallbackNodeModuleRoots = [
  join(appRoot, "node_modules"),
  process.env.PRISM_PLAYWRIGHT_NODE_MODULES || "",
  join(projectsRoot, "prism-open-design", "node_modules"),
].filter(Boolean);

function loadPlaywright() {
  const errors = [];

  for (const nodeModulesRoot of fallbackNodeModuleRoots) {
    try {
      const requireFromPath = createRequire(join(nodeModulesRoot, "package.json"));
      return requireFromPath("@playwright/test");
    } catch (error) {
      errors.push(`${nodeModulesRoot}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  throw new Error(
    [
      "Playwright is not available.",
      "Install @playwright/test in apps/web, or update the fallback path in scripts/smoke-portfolio.mjs.",
      ...errors,
    ].join("\n"),
  );
}

const baseUrl = process.env.PRISM_WEB_ORIGIN || "http://127.0.0.1:8000";
const portfolioUrl = new URL("/portfolio", baseUrl).toString();
const { chromium } = loadPlaywright();
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const consoleProblems = [];
const tradeDate = "2026-05-12";
const recordedPosts = [];
const accountState = {
  mode: "research",
  cashBalance: 0,
  fills: [],
  reconciliations: [],
  noFillIntents: [],
};

function assert(condition, message, detail) {
  if (!condition) {
    const suffix = detail === undefined ? "" : `\n${JSON.stringify(detail, null, 2)}`;
    throw new Error(`${message}${suffix}`);
  }
}

function money(value) {
  return Math.round(Number(value || 0) * 100) / 100;
}

function modeLabel() {
  if (accountState.mode === "live_small") return "小额实盘";
  if (accountState.mode === "shadow") return "影子盘";
  return "研究态";
}

function openPositions() {
  const byCode = new Map();
  for (const fill of accountState.fills) {
    const current = byCode.get(fill.code) || {
      code: fill.code,
      name: fill.name || fill.code,
      qty: 0,
      cost_basis: 0,
      realized_pnl: 0,
      last_fill_at: fill.ts,
      fills: 0,
    };
    current.fills += 1;
    current.last_fill_at = fill.ts;
    if (fill.side === "buy") {
      current.qty += fill.qty;
      current.cost_basis = money(current.cost_basis + fill.notional);
    } else {
      current.qty -= fill.qty;
      current.cost_basis = money(Math.max(0, current.cost_basis - fill.notional));
    }
    current.avg_cost = current.qty ? money(current.cost_basis / current.qty) : 0;
    byCode.set(fill.code, current);
  }
  return [...byCode.values()].filter((position) => position.qty > 0);
}

function reconciliationSummary() {
  const last = accountState.reconciliations.at(-1) || null;
  return {
    count: accountState.reconciliations.length,
    age_seconds: last ? 0 : null,
    age_label: last ? "刚刚" : "未对账",
    fresh_within_seconds: 129_600,
    fresh: Boolean(last),
    last,
  };
}

function readinessPayload() {
  const positions = openPositions();
  const reconciliation = reconciliationSummary();
  const readyForLiveSmall =
    accountState.cashBalance > 0 &&
    reconciliation.fresh &&
    Math.abs(Number(reconciliation.last?.delta_cash || 0)) <= 100 &&
    Math.abs(Number(reconciliation.last?.delta_equity || 0)) <= 200;
  const blockers = accountState.cashBalance < 0
    ? [
        {
          code: "account_cash_negative",
          label: "现金为负",
          message: "本地账本现金为负，请先补录入金。",
          recommended_task: "portfolio_cash",
        },
      ]
    : [];

  return {
    generated_at: `${tradeDate} 09:35:00`,
    trade_date: tradeDate,
    expected_trade_date: tradeDate,
    data_trade_date: tradeDate,
    readiness_mode: readyForLiveSmall ? "live_ready" : "shadow_only",
    stale_count: 0,
    blockers,
    warnings: [],
    source_freshness: [],
    quality_freshness: [],
    recommended_tasks: blockers.map((item) => item.recommended_task),
    session: {
      label: "盘中",
      calendar_status: "open",
    },
    account_state: {
      mode: accountState.mode,
      mode_label: modeLabel(),
      mode_tone: accountState.mode === "live_small" ? "risk" : "info",
      cash_balance: accountState.cashBalance,
      equity_at_cost: money(positions.reduce((sum, position) => sum + position.cost_basis, 0)),
      positions_count: positions.length,
      fills_count: accountState.fills.length,
      reconciliation,
      unreconciled_intents: [],
      blockers,
      warnings: [],
      recommended_tasks: blockers.map((item) => item.recommended_task),
      ready_for_live_small: readyForLiveSmall,
    },
  };
}

function portfolioPayload() {
  const positions = openPositions();
  const equityAtCost = money(positions.reduce((sum, position) => sum + position.cost_basis, 0));
  const account = {
    mode: accountState.mode,
    mode_label: modeLabel(),
    mode_tone: accountState.mode === "live_small" ? "risk" : "info",
    mode_updated_at: `${tradeDate} 09:30:00`,
    currency: "CNY",
    starting_cash: 0,
    cash_balance: accountState.cashBalance,
    deposits_total: Math.max(accountState.cashBalance, 0),
    equity_at_cost: equityAtCost,
    book_value: money(accountState.cashBalance + equityAtCost),
    realized_pnl: 0,
    open_positions: positions,
    closed_positions: [],
    fills: accountState.fills,
    fills_count: accountState.fills.length,
    last_fill_at: accountState.fills.at(-1)?.ts || "",
    reconciliations: accountState.reconciliations,
    no_fill_intents: accountState.noFillIntents,
    available_modes: ["research", "shadow", "live_small"],
    updated_at: `${tradeDate} 09:35:00`,
  };

  return {
    generated_at: `${tradeDate} 09:35:00`,
    trade_date: tradeDate,
    expected_trade_date: tradeDate,
    data_trade_date: tradeDate,
    readiness: readinessPayload(),
    account,
    summary_cards: [
      { label: "运行模式", value: account.mode_label, detail: account.mode_updated_at, tone: account.mode_tone },
      { label: "可用现金", value: `¥${account.cash_balance.toFixed(2)}`, detail: "起始 ¥0.00", tone: account.cash_balance < 0 ? "risk" : "info" },
      { label: "持仓成本", value: `¥${account.equity_at_cost.toFixed(2)}`, detail: `${positions.length} 只持仓`, tone: positions.length ? "watch" : "info" },
      { label: "已实现盈亏", value: "¥0.00", detail: "0 只已平", tone: "positive" },
    ],
    recent_fills: [...accountState.fills].reverse(),
    unreconciled_intents: [],
    reconciliation: reconciliationSummary(),
    ready_for_live_small: readinessPayload().account_state.ready_for_live_small,
    links: {},
  };
}

function jsonResponse(payload) {
  return {
    status: 200,
    contentType: "application/json",
    headers: {
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET,POST,OPTIONS",
      "access-control-allow-headers": "content-type",
    },
    body: JSON.stringify(payload),
  };
}

function overviewPayload() {
  return {
    generated_at: `${tradeDate} 09:35:00`,
    workspace_root: repoRoot,
    kpis: [],
    lanes: [],
    tasks: [],
    runs: [],
    freshness: [],
  };
}

function todayPayload() {
  return {
    generated_at: `${tradeDate} 09:35:00`,
    display_date: tradeDate,
    trade_date: tradeDate,
    expected_trade_date: tradeDate,
    data_trade_date: tradeDate,
    brief_is_live: true,
    readiness: readinessPayload(),
    hero: {},
    command_hero: {},
    radar_cards: [],
    action_queue: {
      title: "今日动作",
      items: [],
      counts: { total: 0, pending: 0, done: 0, watch: 0, skip: 0, no_fill: 0, stale: 0 },
    },
    risk_rows: [],
    source_cards: [],
    summary_cards: [],
    quality_cards: [],
    links: {},
    counts: {
      watchlist_priority: 1,
      watchlist_total: 1,
      candidate_total: 0,
      confirmed: 0,
      downgraded: 0,
      fresh_candidates: 0,
    },
  };
}

function watchlistPayload() {
  return {
    generated_at: `${tradeDate} 09:35:00`,
    display_date: tradeDate,
    trade_date: tradeDate,
    brief_is_live: true,
    groups: [
      {
        key: "priority",
        title: "优先观察",
        count: 1,
        cards: [
          {
            code: "sh600690",
            name: "海尔智家",
            action: "观察",
            tone: "watch",
            reason: "用于 /portfolio smoke 回归。",
            position: "轻仓",
          },
        ],
      },
    ],
    source_cards: [],
    links: {},
  };
}

function watchlistManagerPayload() {
  return {
    manager: {
      summary_cards: [],
      refresh_status: {
        label: "刷新状态",
        detail: "smoke mock",
        steps: [],
      },
      active_items: [],
      archived_items: [],
      empty_active: "暂无活跃自选股。",
      empty_archived: "暂无归档股票。",
    },
  };
}

function readPostBody(request) {
  const raw = request.postData() || "{}";
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

function handlePortfolioPost(pathname, body) {
  if (pathname === "/api/portfolio/fills") {
    const qty = Number(body.qty);
    const price = Number(body.price);
    const fees = Number(body.fees || 0);
    const notional = money(qty * price);
    const cashDelta = body.side === "sell" ? money(notional - fees) : money(-(notional + fees));
    const fill = {
      fill_id: `smoke-fill-${accountState.fills.length + 1}`,
      ts: `${tradeDate} 09:40:00`,
      trade_date: body.trade_date,
      code: body.code,
      name: body.name || "海尔智家",
      side: body.side,
      qty,
      price,
      fees,
      notional,
      cash_delta: cashDelta,
      balance_after: money(accountState.cashBalance + cashDelta),
      broker_ref: body.broker_ref || null,
      intent_key: body.intent_key || null,
      note: body.note || "",
    };
    accountState.cashBalance = fill.balance_after;
    accountState.fills.push(fill);
  }

  if (pathname === "/api/portfolio/cash") {
    accountState.cashBalance = money(accountState.cashBalance + Number(body.delta));
  }

  if (pathname === "/api/portfolio/reconcile") {
    const positions = openPositions();
    const localEquity = money(positions.reduce((sum, position) => sum + position.cost_basis, 0));
    accountState.reconciliations.push({
      ts: `${tradeDate} 09:45:00`,
      trade_date: body.trade_date,
      broker_cash: Number(body.broker_cash),
      broker_equity: Number(body.broker_equity),
      local_cash: accountState.cashBalance,
      local_equity_at_cost: localEquity,
      delta_cash: money(Number(body.broker_cash) - accountState.cashBalance),
      delta_equity: money(Number(body.broker_equity) - localEquity),
      note: body.note || "",
    });
  }

  return portfolioPayload();
}

async function installApiMocks() {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;

    if (request.method() === "OPTIONS") {
      await route.fulfill(jsonResponse({ ok: true }));
      return;
    }

    if (request.method() === "POST") {
      const body = readPostBody(request);
      recordedPosts.push({ pathname, body });
      if (pathname.startsWith("/api/portfolio/")) {
        await route.fulfill(jsonResponse(handlePortfolioPost(pathname, body)));
        return;
      }
    }

    if (pathname === "/api/portfolio/account") {
      await route.fulfill(jsonResponse(portfolioPayload()));
      return;
    }
    if (pathname === "/api/today") {
      await route.fulfill(jsonResponse(todayPayload()));
      return;
    }
    if (pathname === "/api/overview") {
      await route.fulfill(jsonResponse(overviewPayload()));
      return;
    }
    if (pathname === "/api/watchlist") {
      await route.fulfill(jsonResponse(watchlistPayload()));
      return;
    }
    if (pathname === "/api/watchlist/manage") {
      await route.fulfill(jsonResponse(watchlistManagerPayload()));
      return;
    }

    await route.fulfill(jsonResponse({ ok: true }));
  });
}

function panelByTitle(title) {
  return page.locator("section").filter({ has: page.getByRole("heading", { name: title }) }).last();
}

function latestPost(pathname) {
  const match = [...recordedPosts].reverse().find((entry) => entry.pathname === pathname);
  assert(match, `Missing POST ${pathname}`, recordedPosts);
  return match.body;
}

function waitForPost(pathname) {
  return page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === pathname &&
      response.request().method() === "POST" &&
      response.ok(),
    { timeout: 7_500 },
  );
}

async function submitFillForm() {
  const panel = panelByTitle("补录券商成交");
  await panel.getByLabel("我确认这是普通成交录入，并且该成交已在外部券商真实发生。").check();
  await panel.getByLabel("交易日").fill(tradeDate);
  await panel.getByLabel("代码（如 sh600690）").fill("sh600690");
  await panel.getByLabel("名称（可空，自动取 watchlist）").fill("海尔智家");
  await panel.getByLabel("数量").fill("10");
  await panel.getByLabel("成交价").fill("27.50");
  await panel.getByLabel("费用（可空）").fill("4.50");
  await panel.getByLabel("关联意图 key（可空）").fill("smoke-intent-sh600690");
  await panel.getByLabel("券商订单号 / 备注（可空）").fill("smoke-fill-ref");
  await Promise.all([waitForPost("/api/portfolio/fills"), panel.getByRole("button", { name: "录入成交" }).click()]);
  await page.getByText("已录入成交，当前现金").waitFor({ timeout: 5_000 });

  const payload = latestPost("/api/portfolio/fills");
  assert(payload.trade_date === tradeDate, "Fill trade_date mismatch", payload);
  assert(payload.code === "sh600690", "Fill code mismatch", payload);
  assert(payload.name === "海尔智家", "Fill name mismatch", payload);
  assert(payload.side === "buy", "Fill side mismatch", payload);
  assert(payload.qty === 10, "Fill qty mismatch", payload);
  assert(payload.price === 27.5, "Fill price mismatch", payload);
  assert(payload.fees === 4.5, "Fill fees mismatch", payload);
  assert(payload.intent_key === "smoke-intent-sh600690", "Fill intent_key mismatch", payload);
  assert(payload.broker_ref === "smoke-fill-ref", "Fill broker_ref mismatch", payload);
}

async function submitCashForm() {
  const panel = panelByTitle("现金调整");
  await panel.getByRole("button", { name: "预填入金" }).waitFor({ timeout: 5_000 });
  await panel.getByRole("button", { name: "预填入金" }).click();
  await Promise.all([waitForPost("/api/portfolio/cash"), panel.getByRole("button", { name: "记录现金调整" }).click()]);
  await page.getByText("已记录现金调整，当前现金").waitFor({ timeout: 5_000 });

  const payload = latestPost("/api/portfolio/cash");
  assert(payload.delta === 279.5, "Cash delta mismatch", payload);
  assert(payload.reason === "补录券商入金 / 初始现金", "Cash reason mismatch", payload);
}

async function submitReconcileForm() {
  const panel = panelByTitle("对账（按券商真实数据）");
  await panel.getByLabel("对账日").fill(tradeDate);
  await panel.getByLabel("券商现金（从券商 App 复制）").fill("0");
  await panel.getByLabel("券商持仓市值").fill("275");
  await panel.getByLabel("备注").fill("smoke reconcile");
  await Promise.all([waitForPost("/api/portfolio/reconcile"), panel.getByRole("button", { name: "记录对账" }).click()]);
  await page.getByText("已记录对账，现金差异").waitFor({ timeout: 5_000 });

  const payload = latestPost("/api/portfolio/reconcile");
  assert(payload.trade_date === tradeDate, "Reconcile trade_date mismatch", payload);
  assert(payload.broker_cash === 0, "Reconcile broker_cash mismatch", payload);
  assert(payload.broker_equity === 275, "Reconcile broker_equity mismatch", payload);
  assert(payload.note === "smoke reconcile", "Reconcile note mismatch", payload);
}

page.on("pageerror", (error) => {
  consoleProblems.push(`pageerror: ${error.message}`);
});

page.on("console", (message) => {
  if (["error", "warning"].includes(message.type())) {
    consoleProblems.push(`${message.type()}: ${message.text()}`);
  }
});

try {
  await installApiMocks();
  await page.goto(portfolioUrl, { waitUntil: "domcontentloaded", timeout: 15_000 });
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});

  const bodyText = await page.locator("body").innerText({ timeout: 5_000 });
  const buttons = await page
    .locator("button")
    .evaluateAll((items) =>
      items.map((item) => (item.innerText || item.getAttribute("aria-label") || "").trim()).filter(Boolean),
    );

  const requiredText = ["账户控制台", "补录券商成交", "现金调整", "对账", "海尔智家"];
  const missingText = requiredText.filter((text) => !bodyText.includes(text));
  const requiredButtons = ["刷新", "记录现金调整", "记录对账", "录入成交"];
  const missingButtons = requiredButtons.filter((label) => !buttons.some((button) => button.includes(label)));

  if (missingText.length || missingButtons.length || consoleProblems.length) {
    throw new Error(
      JSON.stringify(
        {
          url: page.url(),
          missingText,
          missingButtons,
          consoleProblems: consoleProblems.slice(0, 8),
        },
        null,
        2,
      ),
    );
  }

  await submitFillForm();
  await submitCashForm();
  await submitReconcileForm();

  if (consoleProblems.length) {
    throw new Error(
      JSON.stringify(
        {
          url: page.url(),
          consoleProblems: consoleProblems.slice(0, 8),
        },
        null,
        2,
      ),
    );
  }

  console.log(
    JSON.stringify(
      {
        ok: true,
        url: page.url(),
        title: await page.title(),
        buttonsChecked: requiredButtons,
        postsChecked: recordedPosts
          .filter((entry) =>
            [
              "/api/portfolio/fills",
              "/api/portfolio/cash",
              "/api/portfolio/reconcile",
            ].includes(entry.pathname),
          )
          .map((entry) => entry.pathname),
      },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
}
