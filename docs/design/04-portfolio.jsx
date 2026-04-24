import { useState } from "react";

const t = {
  bg: { p: "#0a0a0b", s: "#111113", t: "#18181b", e: "#1c1c1f" },
  bd: { s: "rgba(255,255,255,0.06)", d: "rgba(255,255,255,0.1)", st: "rgba(255,255,255,0.16)" },
  tx: { p: "#f4f4f5", s: "#a1a1aa", t: "#71717a", inv: "#09090b" },
  ac: { blue: "#3b82f6" },
  sem: { pos: "#22c55e", neg: "#ef4444", warn: "#f59e0b", info: "#3b82f6" },
  tone: { buy: "#22c55e", sell: "#ef4444", watch: "#f59e0b", hold: "#3b82f6", avoid: "#71717a" },
  r: { sm: 6, md: 8, lg: 12, xl: 16 },
  f: { sans: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif', mono: '"SF Mono", "Fira Code", monospace', display: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", sans-serif' },
};

function Badge({ children, color }) {
  return <span style={{ display: "inline-flex", padding: "2px 10px", borderRadius: 9999, fontSize: 11, fontWeight: 500, background: `${color}18`, color, border: `1px solid ${color}30` }}>{children}</span>;
}

function Sidebar({ active }) {
  const items = [
    { key: "command", label: "指挥中心", icon: "⌂" },
    { key: "portfolio", label: "持仓管理", icon: "◫" },
    { key: "discovery", label: "观察池", icon: "◎" },
    { key: "review", label: "复盘", icon: "◈" },
  ];
  return (
    <div style={{ width: 220, height: "100vh", background: t.bg.s, borderRight: `1px solid ${t.bd.s}`, padding: "16px 12px", flexShrink: 0, position: "sticky", top: 0 }}>
      <div style={{ padding: "8px 12px", marginBottom: 20 }}>
        <div style={{ fontSize: 11, color: t.tx.t, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.1em" }}>棱镜</div>
        <div style={{ fontSize: 14, fontWeight: 600, color: t.tx.p }}>交易决策台</div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 12px", borderRadius: t.r.md, background: t.bg.t, border: `1px solid ${t.bd.s}`, color: t.tx.t, fontSize: 13, marginBottom: 16, cursor: "pointer" }}>
        <span style={{ opacity: 0.5 }}>⌕</span><span>搜索...</span>
        <span style={{ marginLeft: "auto", fontSize: 11, padding: "1px 5px", borderRadius: 4, background: t.bg.s, border: `1px solid ${t.bd.s}` }}>⌘K</span>
      </div>
      {items.map(it => (
        <div key={it.key} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: t.r.md, background: active === it.key ? t.bg.t : "transparent", color: active === it.key ? t.tx.p : t.tx.t, fontSize: 13, fontWeight: active === it.key ? 500 : 400, cursor: "pointer" }}>
          <span style={{ fontSize: 16, opacity: active === it.key ? 1 : 0.5 }}>{it.icon}</span>{it.label}
        </div>
      ))}
      <div style={{ height: 1, background: t.bd.s, margin: "12px" }} />
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", color: t.tx.t, fontSize: 13, cursor: "pointer" }}>
        <span style={{ fontSize: 16, opacity: 0.5 }}>⚙</span>设置
      </div>
    </div>
  );
}

function StockCard({ name, code, action, position, tone, price, change }) {
  const toneColor = t.tone[tone] || t.tx.t;
  return (
    <div style={{ background: t.bg.s, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 16, cursor: "pointer", borderLeft: `3px solid ${toneColor}` }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 500, color: t.tx.p }}>{name}</span>
          <span style={{ fontSize: 11, color: t.tx.t, fontFamily: t.f.mono }}>{code}</span>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 13, fontWeight: 500, fontFamily: t.f.mono, color: t.tx.p }}>{price}</div>
          <div style={{ fontSize: 11, fontFamily: t.f.mono, color: toneColor }}>{change}</div>
        </div>
      </div>
      <div style={{ fontSize: 12, color: t.tx.s, marginBottom: 8 }}>{action}</div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 11, color: t.tx.t }}>仓位 {position}</span>
        <Badge color={toneColor}>{tone === "sell" ? "减仓" : tone === "hold" ? "持有" : tone === "watch" ? "观察" : tone === "buy" ? "加仓" : "回避"}</Badge>
      </div>
    </div>
  );
}

function KanbanColumn({ title, subtitle, count, color, children }) {
  return (
    <div style={{ flex: 1, minWidth: 280 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16, padding: "0 4px" }}>
        <div style={{ width: 10, height: 10, borderRadius: "50%", background: color }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: t.tx.p }}>{title}</span>
        <span style={{ fontSize: 12, color: t.tx.t, fontFamily: t.f.mono, background: t.bg.t, padding: "1px 8px", borderRadius: 9999 }}>{count}</span>
      </div>
      <div style={{ fontSize: 12, color: t.tx.t, marginBottom: 12, padding: "0 4px" }}>{subtitle}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>{children}</div>
    </div>
  );
}

function PortfolioPage() {
  const [showAdd, setShowAdd] = useState(false);
  return (
    <div style={{ flex: 1, overflow: "auto", padding: "32px 40px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "start", justifyContent: "space-between", marginBottom: 32 }}>
        <div>
          <div style={{ fontSize: 11, color: t.ac.blue, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>Portfolio</div>
          <h1 style={{ fontSize: 28, fontWeight: 700, fontFamily: t.f.display, margin: 0, marginBottom: 8 }}>持仓管理</h1>
          <p style={{ fontSize: 14, color: t.tx.s, margin: 0 }}>先处理 3 只优先持仓，再看其余观察。总计 8 只股票。</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button style={{ padding: "8px 16px", borderRadius: t.r.md, background: "transparent", border: `1px solid ${t.bd.d}`, color: t.tx.p, fontSize: 13, cursor: "pointer", fontFamily: t.f.sans }}>🔄 刷新</button>
          <button onClick={() => setShowAdd(!showAdd)} style={{ padding: "8px 16px", borderRadius: t.r.md, background: t.tx.p, border: "none", color: t.tx.inv, fontSize: 13, fontWeight: 500, cursor: "pointer", fontFamily: t.f.sans }}>+ 添加股票</button>
        </div>
      </div>

      {/* Add Stock Form */}
      {showAdd && (
        <div style={{ background: t.bg.t, border: `1px solid ${t.bd.d}`, borderRadius: t.r.lg, padding: 20, marginBottom: 24, display: "flex", gap: 12, alignItems: "end" }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, color: t.tx.t, marginBottom: 6 }}>股票代码</div>
            <input placeholder="输入代码，如 300750" style={{ width: "100%", padding: "8px 12px", borderRadius: t.r.md, background: t.bg.s, border: `1px solid ${t.bd.d}`, color: t.tx.p, fontSize: 13, fontFamily: t.f.sans, outline: "none", boxSizing: "border-box" }} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, color: t.tx.t, marginBottom: 6 }}>名称（可选）</div>
            <input placeholder="自动识别" style={{ width: "100%", padding: "8px 12px", borderRadius: t.r.md, background: t.bg.s, border: `1px solid ${t.bd.d}`, color: t.tx.p, fontSize: 13, fontFamily: t.f.sans, outline: "none", boxSizing: "border-box" }} />
          </div>
          <button style={{ padding: "8px 20px", borderRadius: t.r.md, background: t.sem.pos, border: "none", color: "#fff", fontSize: 13, fontWeight: 500, cursor: "pointer", fontFamily: t.f.sans, whiteSpace: "nowrap" }}>添加并刷新</button>
        </div>
      )}

      {/* Summary Strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 32 }}>
        {[
          { label: "总股票数", value: "8", detail: "当前自选股快照" },
          { label: "优先处理", value: "3", detail: "先处理风险与仓位", color: t.sem.neg },
          { label: "跟踪增强", value: "3", detail: "允许轻仓跟踪", color: t.ac.blue },
          { label: "继续观察", value: "2", detail: "等待更明确信号", color: t.tx.t },
        ].map((c, i) => (
          <div key={i} style={{ background: t.bg.t, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 14 }}>
            <div style={{ fontSize: 11, color: t.tx.t, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>{c.label}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: c.color || t.tx.p, fontFamily: t.f.display }}>{c.value}</div>
            <div style={{ fontSize: 11, color: t.tx.t, marginTop: 4 }}>{c.detail}</div>
          </div>
        ))}
      </div>

      {/* Kanban Board */}
      <div style={{ display: "flex", gap: 20 }}>
        <KanbanColumn title="优先处理" subtitle="先处理风险和仓位" count={3} color={t.sem.neg}>
          <StockCard name="宁德时代" code="300750" action="减仓至半仓 · 跌破185止损" position="满仓" tone="sell" price="¥192.50" change="-2.35%" />
          <StockCard name="比亚迪" code="002594" action="止损观察 · 跌破255离场" position="半仓" tone="sell" price="¥252.30" change="-1.80%" />
          <StockCard name="隆基绿能" code="601012" action="清仓 · 趋势已破" position="轻仓" tone="sell" price="¥18.45" change="-3.12%" />
        </KanbanColumn>

        <KanbanColumn title="跟踪增强" subtitle="允许轻仓跟踪的标的" count={3} color={t.ac.blue}>
          <StockCard name="中际旭创" code="300308" action="轻仓试错 · 等回踩确认" position="轻仓" tone="watch" price="¥88.60" change="+3.21%" />
          <StockCard name="寒武纪" code="688256" action="继续持有 · 不追高" position="轻仓" tone="hold" price="¥312.00" change="-0.48%" />
          <StockCard name="紫光股份" code="000938" action="持有观察 · 等突破" position="轻仓" tone="hold" price="¥42.80" change="+0.94%" />
        </KanbanColumn>

        <KanbanColumn title="继续观察" subtitle="暂不动作，等待明确信号" count={2} color={t.tx.t}>
          <StockCard name="海光信息" code="688041" action="纯观察 · 不建仓" position="-" tone="avoid" price="¥98.20" change="+1.56%" />
          <StockCard name="中芯国际" code="688981" action="等回调 · 不追高" position="-" tone="avoid" price="¥78.50" change="+0.38%" />
        </KanbanColumn>
      </div>
    </div>
  );
}

export default function PortfolioFullPage() {
  return (
    <div style={{ display: "flex", minHeight: "100vh", background: t.bg.p, color: t.tx.p, fontFamily: t.f.sans, fontSize: 14, lineHeight: 1.5 }}>
      <Sidebar active="portfolio" />
      <PortfolioPage />
    </div>
  );
}
