import { useState } from "react";

const t = {
  bg: { p: "#0a0a0b", s: "#111113", t: "#18181b", e: "#1c1c1f" },
  bd: { s: "rgba(255,255,255,0.06)", d: "rgba(255,255,255,0.1)", st: "rgba(255,255,255,0.16)" },
  tx: { p: "#f4f4f5", s: "#a1a1aa", t: "#71717a", inv: "#09090b" },
  ac: { blue: "#3b82f6", indigo: "#6366f1" },
  sem: { pos: "#22c55e", neg: "#ef4444", warn: "#f59e0b", info: "#3b82f6" },
  tone: { buy: "#22c55e", sell: "#ef4444", watch: "#f59e0b", hold: "#3b82f6", avoid: "#71717a" },
  r: { sm: 6, md: 8, lg: 12, xl: 16 },
  f: { sans: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif', mono: '"SF Mono", "Fira Code", monospace', display: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", sans-serif' },
};

function Badge({ children, color }) {
  return <span style={{ display: "inline-flex", padding: "2px 10px", borderRadius: 9999, fontSize: 11, fontWeight: 500, background: `${color}18`, color, border: `1px solid ${color}30` }}>{children}</span>;
}

function Sidebar({ active, onNav }) {
  const items = [
    { key: "command", label: "指挥中心", icon: "⌂" },
    { key: "portfolio", label: "持仓管理", icon: "◫" },
    { key: "discovery", label: "观察池", icon: "◎" },
    { key: "review", label: "复盘", icon: "◈" },
  ];
  return (
    <div style={{ width: 220, height: "100vh", background: t.bg.s, borderRight: `1px solid ${t.bd.s}`, padding: "16px 12px", display: "flex", flexDirection: "column", flexShrink: 0, position: "sticky", top: 0 }}>
      <div style={{ padding: "8px 12px", marginBottom: 20 }}>
        <div style={{ fontSize: 11, color: t.tx.t, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.1em" }}>棱镜</div>
        <div style={{ fontSize: 14, fontWeight: 600, color: t.tx.p }}>交易决策台</div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 12px", borderRadius: t.r.md, background: t.bg.t, border: `1px solid ${t.bd.s}`, color: t.tx.t, fontSize: 13, marginBottom: 16, cursor: "pointer" }}>
        <span style={{ opacity: 0.5 }}>⌕</span>
        <span>搜索...</span>
        <span style={{ marginLeft: "auto", fontSize: 11, padding: "1px 5px", borderRadius: 4, background: t.bg.s, border: `1px solid ${t.bd.s}` }}>⌘K</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {items.map(it => (
          <div key={it.key} onClick={() => onNav(it.key)} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: t.r.md, background: active === it.key ? t.bg.t : "transparent", color: active === it.key ? t.tx.p : t.tx.t, fontSize: 13, fontWeight: active === it.key ? 500 : 400, cursor: "pointer" }}>
            <span style={{ fontSize: 16, opacity: active === it.key ? 1 : 0.5 }}>{it.icon}</span>
            {it.label}
          </div>
        ))}
      </div>
      <div style={{ height: 1, background: t.bd.s, margin: "12px 12px" }} />
      <div onClick={() => onNav("settings")} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: t.r.md, background: active === "settings" ? t.bg.t : "transparent", color: active === "settings" ? t.tx.p : t.tx.t, fontSize: 13, cursor: "pointer" }}>
        <span style={{ fontSize: 16, opacity: 0.5 }}>⚙</span>
        设置
      </div>
      <div style={{ marginTop: "auto", padding: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: t.sem.pos }} />
          <span style={{ fontSize: 11, color: t.tx.t }}>系统正常 · 09:45</span>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value, detail, color }) {
  return (
    <div style={{ background: t.bg.t, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 16 }}>
      <div style={{ fontSize: 11, color: t.tx.t, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color: color || t.tx.p, fontFamily: t.f.display, lineHeight: 1.1 }}>{value}</div>
      <div style={{ fontSize: 11, color: t.tx.t, marginTop: 6 }}>{detail}</div>
    </div>
  );
}

function ActionRow({ name, code, action, tier, tone, checked, onToggle }) {
  const toneColor = t.tone[tone] || t.tx.t;
  const tierLabels = { act_now: "优先处理", wait_trigger: "等触发", observe: "仅观察", done: "已处理" };
  const tierColors = { act_now: t.sem.neg, wait_trigger: t.sem.warn, observe: t.ac.blue, done: t.sem.pos };
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 0", borderBottom: `1px solid ${t.bd.s}` }}>
      <div onClick={onToggle} style={{ width: 20, height: 20, borderRadius: t.r.sm, border: checked ? "none" : `2px solid ${t.bd.st}`, background: checked ? t.sem.pos : "transparent", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flexShrink: 0 }}>
        {checked && <span style={{ color: "#fff", fontSize: 12 }}>✓</span>}
      </div>
      <div style={{ width: 3, height: 28, borderRadius: 2, background: toneColor, flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 500, color: checked ? t.tx.t : t.tx.p, textDecoration: checked ? "line-through" : "none" }}>{name}</span>
          <span style={{ fontSize: 11, color: t.tx.t, fontFamily: t.f.mono }}>{code}</span>
        </div>
        <div style={{ fontSize: 12, color: t.tx.t, marginTop: 2 }}>{action}</div>
      </div>
      <Badge color={tierColors[tier] || t.tx.t}>{tierLabels[tier] || tier}</Badge>
      <div style={{ color: t.tx.t, fontSize: 16, cursor: "pointer" }}>›</div>
    </div>
  );
}

function SourceCard({ label, time, status }) {
  const statusColor = status === "fresh" ? t.sem.pos : status === "stale" ? t.sem.warn : t.tx.t;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderRadius: t.r.md, background: t.bg.s, border: `1px solid ${t.bd.s}` }}>
      <div style={{ width: 6, height: 6, borderRadius: "50%", background: statusColor, flexShrink: 0 }} />
      <span style={{ fontSize: 12, color: t.tx.s, flex: 1 }}>{label}</span>
      <span style={{ fontSize: 11, color: t.tx.t, fontFamily: t.f.mono }}>{time}</span>
    </div>
  );
}

function RiskAlert({ text, level }) {
  const color = level === "high" ? t.sem.neg : t.sem.warn;
  return (
    <div style={{ display: "flex", alignItems: "start", gap: 10, padding: "10px 14px", borderRadius: t.r.md, background: `${color}08`, border: `1px solid ${color}20` }}>
      <span style={{ color, fontSize: 14, flexShrink: 0, marginTop: 1 }}>⚠</span>
      <span style={{ fontSize: 13, color: t.tx.s, lineHeight: 1.5 }}>{text}</span>
    </div>
  );
}

function QuickLink({ label, count, href }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", borderRadius: t.r.md, background: t.bg.s, border: `1px solid ${t.bd.s}`, cursor: "pointer" }}>
      <span style={{ fontSize: 13, color: t.tx.s }}>{label}</span>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {count !== undefined && <span style={{ fontSize: 13, fontWeight: 600, color: t.tx.p, fontFamily: t.f.mono }}>{count}</span>}
        <span style={{ color: t.tx.t, fontSize: 14 }}>›</span>
      </div>
    </div>
  );
}

function CommandCenter() {
  const [checks, setChecks] = useState({ a: false, b: false, c: false, d: true });
  const toggle = k => setChecks(prev => ({ ...prev, [k]: !prev[k] }));

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "32px 40px" }}>
      {/* Hero */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
          <div style={{ fontSize: 11, color: t.ac.blue, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.1em" }}>2026-04-24 · 交易时段</div>
          <Badge color={t.sem.pos}>阀门开放</Badge>
        </div>
        <h1 style={{ fontSize: 32, fontWeight: 700, fontFamily: t.f.display, lineHeight: 1.15, marginBottom: 10, color: t.tx.p }}>先处理旧仓，再决定是否看新仓</h1>
        <p style={{ fontSize: 15, color: t.tx.s, maxWidth: 640, lineHeight: 1.6 }}>阀门开放但仓位上限 2 只，主线 AI+机器人。弱环境 5 日净仍为负，控制新仓节奏。</p>
        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 9999, background: t.bg.t, color: t.tx.t, border: `1px solid ${t.bd.s}` }}>仓位上限 2 只</span>
          <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 9999, background: t.bg.t, color: t.tx.t, border: `1px solid ${t.bd.s}` }}>主线 AI+机器人</span>
          <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 9999, background: `${t.sem.warn}18`, color: t.sem.warn, border: `1px solid ${t.sem.warn}30` }}>弱环境偏负</span>
        </div>
      </div>

      {/* Radar Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 32 }}>
        <MetricCard label="持仓优先" value="3" detail="来自自选股页面" color={t.sem.neg} />
        <MetricCard label="观察候选" value="5" detail="来自观察池" color={t.sem.warn} />
        <MetricCard label="午盘新增" value="2" detail="午盘确认" color={t.sem.pos} />
        <MetricCard label="质检就绪" value="3/3" detail="核心链路状态" color={t.sem.pos} />
      </div>

      {/* Action Queue */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>今日待办</div>
            <div style={{ fontSize: 18, fontWeight: 600, color: t.tx.p }}>Action Queue</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 12, color: t.tx.t }}>1/4 已完成</span>
            <div style={{ width: 80, height: 4, borderRadius: 2, background: t.bg.t, overflow: "hidden" }}>
              <div style={{ width: "25%", height: "100%", borderRadius: 2, background: t.sem.pos }} />
            </div>
          </div>
        </div>
        <div style={{ background: t.bg.t, borderRadius: t.r.lg, border: `1px solid ${t.bd.s}`, padding: "4px 16px" }}>
          <ActionRow name="宁德时代" code="300750" action="减仓至半仓 · 跌破 185 全部止损" tier="act_now" tone="sell" checked={checks.a} onToggle={() => toggle("a")} />
          <ActionRow name="比亚迪" code="002594" action="止损观察 · 跌破 255 离场" tier="act_now" tone="sell" checked={checks.b} onToggle={() => toggle("b")} />
          <ActionRow name="中际旭创" code="300308" action="轻仓试错 · 等回踩 85 附近确认" tier="wait_trigger" tone="watch" checked={checks.c} onToggle={() => toggle("c")} />
          <ActionRow name="寒武纪" code="688256" action="继续持有 · 不追高不补仓" tier="done" tone="hold" checked={checks.d} onToggle={() => toggle("d")} />
        </div>
      </div>

      {/* Risk Alerts */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>风险提醒</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <RiskAlert text="弱环境 AI 5日净仍为负（-1.2%），新仓节奏需要收紧，不要因为阀门开放就放松纪律。" level="high" />
          <RiskAlert text="自选股快照 2 小时前更新，建议在午盘前刷新一次以获取最新持仓状态。" level="warn" />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        {/* Quick Links */}
        <div>
          <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>快速跳转</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <QuickLink label="持仓管理" count={8} />
            <QuickLink label="观察池候选" count={5} />
            <QuickLink label="午盘确认" count={2} />
            <QuickLink label="复盘仪表盘" />
          </div>
        </div>

        {/* Data Sources */}
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em" }}>数据源</div>
            <button style={{ fontSize: 12, color: t.ac.blue, background: "none", border: "none", cursor: "pointer", fontFamily: t.f.sans }}>🔄 刷新</button>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <SourceCard label="自选股快照" time="09:32" status="fresh" />
            <SourceCard label="观察池基线" time="09:15" status="fresh" />
            <SourceCard label="午盘确认" time="13:45" status="stale" />
            <SourceCard label="总控简报" time="09:40" status="fresh" />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function CommandCenterPage() {
  const [nav, setNav] = useState("command");
  return (
    <div style={{ display: "flex", minHeight: "100vh", background: t.bg.p, color: t.tx.p, fontFamily: t.f.sans, fontSize: 14, lineHeight: 1.5 }}>
      <Sidebar active={nav} onNav={setNav} />
      <CommandCenter />
    </div>
  );
}
