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

function PipelineStage({ title, count, color, active, onClick }) {
  return (
    <div onClick={onClick} style={{ flex: 1, padding: "14px 16px", borderRadius: t.r.lg, background: active ? t.bg.t : t.bg.s, border: `1px solid ${active ? t.bd.d : t.bd.s}`, cursor: "pointer", textAlign: "center", borderBottom: `3px solid ${active ? color : "transparent"}` }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: active ? color : t.tx.s, fontFamily: t.f.display }}>{count}</div>
      <div style={{ fontSize: 12, color: active ? t.tx.s : t.tx.t, marginTop: 4 }}>{title}</div>
    </div>
  );
}

function CandidateRow({ name, code, score, status, statusColor, setup, change, risk, onClick }) {
  return (
    <div onClick={onClick} style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 16px", borderRadius: t.r.md, background: t.bg.s, border: `1px solid ${t.bd.s}`, cursor: "pointer", marginBottom: 8 }}>
      <div style={{ width: 3, height: 36, borderRadius: 2, background: statusColor, flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <span style={{ fontSize: 14, fontWeight: 500, color: t.tx.p }}>{name}</span>
          <span style={{ fontSize: 11, color: t.tx.t, fontFamily: t.f.mono }}>{code}</span>
          <Badge color={statusColor}>{status}</Badge>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ fontSize: 12, color: t.tx.t }}>Setup: {setup}</span>
          <span style={{ fontSize: 12, color: t.tx.t }}>风险: {risk}</span>
        </div>
      </div>
      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: t.tx.p, fontFamily: t.f.mono }}>{score}</div>
        <div style={{ fontSize: 11, color: parseFloat(change) >= 0 ? t.sem.pos : t.sem.neg, fontFamily: t.f.mono }}>{change}</div>
      </div>
      <div style={{ color: t.tx.t, fontSize: 16 }}>›</div>
    </div>
  );
}

function ThemeCard({ theme, heat, stocks }) {
  const heatColor = heat === "hot" ? t.sem.neg : heat === "warm" ? t.sem.warn : t.ac.blue;
  return (
    <div style={{ background: t.bg.s, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 500, color: t.tx.p }}>{theme}</span>
        <Badge color={heatColor}>{heat === "hot" ? "热门" : heat === "warm" ? "活跃" : "平稳"}</Badge>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {stocks.map((s, i) => (
          <span key={i} style={{ fontSize: 11, padding: "2px 8px", borderRadius: 9999, background: t.bg.t, color: t.tx.s, border: `1px solid ${t.bd.s}` }}>{s}</span>
        ))}
      </div>
    </div>
  );
}

function DiscoveryPage() {
  const [stage, setStage] = useState("approved");

  const stages = [
    { key: "all", title: "全部候选", count: 12, color: t.tx.s },
    { key: "approved", title: "早盘进入", count: 5, color: t.sem.pos },
    { key: "caution", title: "继续观察", count: 4, color: t.sem.warn },
    { key: "fresh", title: "午盘新增", count: 2, color: t.ac.blue },
    { key: "confirmed", title: "午盘确认", count: 1, color: t.ac.indigo },
  ];

  const candidates = {
    approved: [
      { name: "中际旭创", code: "300308", score: "87", status: "进入候选", statusColor: t.sem.pos, setup: "突破回踩", change: "+3.21%", risk: "板块轮动" },
      { name: "光迅科技", code: "002281", score: "82", status: "进入候选", statusColor: t.sem.pos, setup: "底部放量", change: "+5.67%", risk: "业绩不确定" },
      { name: "新易盛", code: "300502", score: "79", status: "进入候选", statusColor: t.sem.pos, setup: "趋势延续", change: "+2.15%", risk: "估值偏高" },
      { name: "天孚通信", code: "300394", score: "75", status: "进入候选", statusColor: t.sem.pos, setup: "均线多头", change: "+1.88%", risk: "成交量不足" },
      { name: "沪电股份", code: "002463", score: "71", status: "进入候选", statusColor: t.sem.pos, setup: "资金流入", change: "+0.95%", risk: "行业周期" },
    ],
    caution: [
      { name: "海光信息", code: "688041", score: "68", status: "继续观察", statusColor: t.sem.warn, setup: "等回调", change: "+1.56%", risk: "估值过高" },
      { name: "中芯国际", code: "688981", score: "65", status: "继续观察", statusColor: t.sem.warn, setup: "底部震荡", change: "+0.38%", risk: "政策风险" },
      { name: "澜起科技", code: "688008", score: "62", status: "继续观察", statusColor: t.sem.warn, setup: "缩量整理", change: "-0.72%", risk: "需求不明" },
      { name: "景嘉微", code: "300474", score: "58", status: "继续观察", statusColor: t.sem.warn, setup: "等确认", change: "-1.23%", risk: "竞争加剧" },
    ],
    fresh: [
      { name: "拓维信息", code: "002261", score: "73", status: "午盘新增", statusColor: t.ac.blue, setup: "午盘放量", change: "+6.82%", risk: "追高风险" },
      { name: "科大讯飞", code: "002230", score: "69", status: "午盘新增", statusColor: t.ac.blue, setup: "消息驱动", change: "+4.35%", risk: "持续性存疑" },
    ],
    confirmed: [
      { name: "中际旭创", code: "300308", score: "87", status: "午盘确认", statusColor: t.ac.indigo, setup: "承接确认", change: "+3.21%", risk: "板块轮动" },
    ],
  };

  const allCandidates = [...(candidates.approved || []), ...(candidates.caution || []), ...(candidates.fresh || []), ...(candidates.confirmed || [])];
  const displayList = stage === "all" ? allCandidates : (candidates[stage] || []);

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "32px 40px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "start", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 11, color: t.ac.blue, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>Discovery</div>
          <h1 style={{ fontSize: 28, fontWeight: 700, fontFamily: t.f.display, margin: 0, marginBottom: 8 }}>观察池</h1>
          <p style={{ fontSize: 14, color: t.tx.s, margin: 0 }}>今天值得继续盯的名字。阀门开放，仓位上限 2 只。</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Badge color={t.sem.pos}>阀门开放</Badge>
          <button style={{ padding: "8px 16px", borderRadius: t.r.md, background: "transparent", border: `1px solid ${t.bd.d}`, color: t.tx.p, fontSize: 13, cursor: "pointer", fontFamily: t.f.sans }}>🔄 刷新</button>
        </div>
      </div>

      {/* Pipeline Stages */}
      <div style={{ display: "flex", gap: 8, marginBottom: 32 }}>
        {stages.map(s => (
          <PipelineStage key={s.key} title={s.title} count={s.count} color={s.color} active={stage === s.key} onClick={() => setStage(s.key)} />
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 24 }}>
        {/* Candidate List */}
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: t.tx.p }}>{stages.find(s => s.key === stage)?.title || "全部"}</div>
            <span style={{ fontSize: 12, color: t.tx.t }}>{displayList.length} 只</span>
          </div>
          {displayList.map((c, i) => (
            <CandidateRow key={i} {...c} />
          ))}
          {displayList.length === 0 && (
            <div style={{ padding: 40, textAlign: "center", color: t.tx.t, fontSize: 13 }}>当前阶段没有候选</div>
          )}
        </div>

        {/* Sidebar: Themes + Gate */}
        <div>
          {/* Gate Info */}
          <div style={{ background: t.bg.t, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 16, marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10 }}>进攻阀门</div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: t.sem.pos }} />
              <span style={{ fontSize: 14, fontWeight: 500, color: t.tx.p }}>允许轻仓试错</span>
            </div>
            <div style={{ fontSize: 12, color: t.tx.t, marginBottom: 12 }}>仓位上限 2 只，主线 AI+机器人</div>
            <div style={{ display: "flex", gap: 8 }}>
              <div style={{ flex: 1, padding: "8px 10px", borderRadius: t.r.md, background: t.bg.s, border: `1px solid ${t.bd.s}`, textAlign: "center" }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: t.tx.p }}>2</div>
                <div style={{ fontSize: 10, color: t.tx.t }}>仓位上限</div>
              </div>
              <div style={{ flex: 1, padding: "8px 10px", borderRadius: t.r.md, background: t.bg.s, border: `1px solid ${t.bd.s}`, textAlign: "center" }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: t.sem.warn }}>弱</div>
                <div style={{ fontSize: 10, color: t.tx.t }}>环境评级</div>
              </div>
            </div>
          </div>

          {/* Quality */}
          <div style={{ background: t.bg.t, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 16, marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10 }}>质检状态</div>
            {[
              { label: "早盘质检", status: "ok" },
              { label: "午盘质检", status: "ok" },
            ].map((q, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 0", borderBottom: i === 0 ? `1px solid ${t.bd.s}` : "none" }}>
                <span style={{ fontSize: 13, color: t.tx.s }}>{q.label}</span>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 6, height: 6, borderRadius: "50%", background: q.status === "ok" ? t.sem.pos : t.sem.neg }} />
                  <span style={{ fontSize: 12, color: q.status === "ok" ? t.sem.pos : t.sem.neg }}>{q.status === "ok" ? "就绪" : "异常"}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Theme Radar */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10 }}>主线热力</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <ThemeCard theme="AI + 算力" heat="hot" stocks={["中际旭创", "光迅科技", "寒武纪"]} />
              <ThemeCard theme="机器人" heat="warm" stocks={["拓维信息", "科大讯飞"]} />
              <ThemeCard theme="半导体" heat="cool" stocks={["海光信息", "中芯国际"]} />
            </div>
          </div>

          {/* Data Sources */}
          <div style={{ background: t.bg.t, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 16 }}>
            <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10 }}>数据源</div>
            {[
              { label: "早盘批次", time: "09:15", fresh: true },
              { label: "午盘确认", time: "13:45", fresh: true },
              { label: "总控简报", time: "09:40", fresh: true },
              { label: "进攻阀门", time: "实时", fresh: true },
            ].map((s, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 0" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 5, height: 5, borderRadius: "50%", background: s.fresh ? t.sem.pos : t.sem.warn }} />
                  <span style={{ fontSize: 12, color: t.tx.s }}>{s.label}</span>
                </div>
                <span style={{ fontSize: 11, color: t.tx.t, fontFamily: t.f.mono }}>{s.time}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function DiscoveryFullPage() {
  return (
    <div style={{ display: "flex", minHeight: "100vh", background: t.bg.p, color: t.tx.p, fontFamily: t.f.sans, fontSize: 14, lineHeight: 1.5 }}>
      <Sidebar active="discovery" />
      <DiscoveryPage />
    </div>
  );
}
