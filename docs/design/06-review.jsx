import { useState } from "react";

const t = {
  bg: { p: "#0a0a0b", s: "#111113", t: "#18181b", e: "#1c1c1f" },
  bd: { s: "rgba(255,255,255,0.06)", d: "rgba(255,255,255,0.1)", st: "rgba(255,255,255,0.16)" },
  tx: { p: "#f4f4f5", s: "#a1a1aa", t: "#71717a", inv: "#09090b" },
  ac: { blue: "#3b82f6", indigo: "#6366f1" },
  sem: { pos: "#22c55e", neg: "#ef4444", warn: "#f59e0b", info: "#3b82f6" },
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

function GaugeCard({ label, value, baseline, delta, tone }) {
  const color = tone === "pos" ? t.sem.pos : tone === "neg" ? t.sem.neg : t.sem.warn;
  const barWidth = Math.min(Math.max(Math.abs(parseFloat(value) || 0) * 20, 5), 100);
  const isPositive = parseFloat(value) >= 0;
  return (
    <div style={{ background: t.bg.t, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 20 }}>
      <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color, fontFamily: t.f.display, lineHeight: 1.1 }}>{value}</div>
      <div style={{ marginTop: 10, marginBottom: 8 }}>
        <div style={{ height: 4, borderRadius: 2, background: t.bg.s, overflow: "hidden", position: "relative" }}>
          <div style={{ position: "absolute", left: isPositive ? "50%" : `${50 - barWidth / 2}%`, width: `${barWidth / 2}%`, height: "100%", borderRadius: 2, background: color }} />
          <div style={{ position: "absolute", left: "50%", top: -2, width: 1, height: 8, background: t.bd.st }} />
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: t.tx.t }}>
        <span>基准 {baseline}</span>
        <span style={{ color }}>{delta}</span>
      </div>
    </div>
  );
}

function RuleCard({ title, description, action, tone }) {
  const color = tone === "pos" ? t.sem.pos : tone === "neg" ? t.sem.neg : t.sem.warn;
  return (
    <div style={{ background: t.bg.s, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 16, borderLeft: `3px solid ${color}` }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 500, color: t.tx.p }}>{title}</span>
        <Badge color={color}>{action}</Badge>
      </div>
      <div style={{ fontSize: 13, color: t.tx.s, lineHeight: 1.5 }}>{description}</div>
    </div>
  );
}

function TimelineEvent({ date, label, type, detail }) {
  const colors = { entered: t.sem.pos, upgraded: t.ac.blue, downgraded: t.sem.warn, exited: t.sem.neg, handed_off: t.ac.indigo };
  const labels = { entered: "进入", upgraded: "升级", downgraded: "降级", exited: "退出", handed_off: "移交" };
  return (
    <div style={{ display: "flex", gap: 12, padding: "10px 0", borderBottom: `1px solid ${t.bd.s}` }}>
      <span style={{ fontSize: 11, color: t.tx.t, fontFamily: t.f.mono, width: 50, flexShrink: 0, paddingTop: 2 }}>{date}</span>
      <div style={{ width: 8, height: 8, borderRadius: "50%", background: colors[type] || t.tx.t, marginTop: 5, flexShrink: 0 }} />
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 500, color: t.tx.p }}>{label}</span>
          <Badge color={colors[type] || t.tx.t}>{labels[type] || type}</Badge>
        </div>
        <div style={{ fontSize: 12, color: t.tx.t, marginTop: 2 }}>{detail}</div>
      </div>
    </div>
  );
}

function CompareRow({ label, baseline, current, delta, tone }) {
  const color = tone === "pos" ? t.sem.pos : tone === "neg" ? t.sem.neg : t.sem.warn;
  return (
    <div style={{ display: "flex", alignItems: "center", padding: "10px 0", borderBottom: `1px solid ${t.bd.s}` }}>
      <span style={{ fontSize: 13, color: t.tx.s, flex: 1 }}>{label}</span>
      <span style={{ fontSize: 13, fontFamily: t.f.mono, color: t.tx.t, width: 80, textAlign: "right" }}>{baseline}</span>
      <span style={{ fontSize: 13, color: t.tx.t, width: 30, textAlign: "center" }}>→</span>
      <span style={{ fontSize: 13, fontFamily: t.f.mono, color: t.tx.p, width: 80, textAlign: "right" }}>{current}</span>
      <span style={{ fontSize: 13, fontFamily: t.f.mono, color, width: 80, textAlign: "right", fontWeight: 500 }}>{delta}</span>
    </div>
  );
}

function ReviewPage() {
  const [window, setWindow] = useState("latest");
  return (
    <div style={{ flex: 1, overflow: "auto", padding: "32px 40px" }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 11, color: t.ac.blue, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>Review</div>
        <h1 style={{ fontSize: 28, fontWeight: 700, fontFamily: t.f.display, margin: 0, marginBottom: 8 }}>复盘仪表盘</h1>
        <p style={{ fontSize: 14, color: t.tx.s, margin: 0 }}>历史优势要分环境看，不能只看总分。弱环境必须收手。</p>
      </div>

      {/* Environment Gauges */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 32 }}>
        <GaugeCard label="弱环境 · AI 5日净" value="-1.2%" baseline="-2.1%" delta="↑ 改善" tone="neg" />
        <GaugeCard label="试错环境 · AI 5日净" value="+2.8%" baseline="+1.5%" delta="↑ 改善" tone="pos" />
        <GaugeCard label="进攻环境 · AI 5日净" value="+4.5%" baseline="+3.8%" delta="↑ 改善" tone="pos" />
      </div>

      {/* Action Rules */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>校准规则</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <RuleCard title="弱环境仍未转正" description="弱环境 AI 5日净 -1.2%，虽然比基准改善但仍为负。新仓节奏需要收紧，不要因为阀门开放就放松纪律。" action="少动" tone="neg" />
          <RuleCard title="试错环境已转正" description="试错环境 +2.8%，可以做轻仓试单，但严格控制单笔仓位不超过 10%，止损不超过 3%。" action="轻仓试错" tone="pos" />
          <RuleCard title="进攻环境样本充足" description="进攻环境 +4.5%，但需要等弱环境也转正后才能升级到正常仓位。当前仍按试错档处理。" action="等确认" tone="warn" />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        {/* Comparison Panel */}
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em" }}>基准 vs 最新切片</div>
            <div style={{ display: "flex", gap: 4 }}>
              {["q1", "latest"].map(w => (
                <button key={w} onClick={() => setWindow(w)} style={{ padding: "4px 12px", borderRadius: t.r.sm, fontSize: 11, background: window === w ? t.bg.t : "transparent", color: window === w ? t.tx.p : t.tx.t, border: `1px solid ${window === w ? t.bd.s : "transparent"}`, cursor: "pointer", fontFamily: t.f.sans }}>{w === "q1" ? "Q1 基准" : "最新切片"}</button>
              ))}
            </div>
          </div>
          <div style={{ background: t.bg.t, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: "4px 16px" }}>
            <div style={{ display: "flex", alignItems: "center", padding: "8px 0", borderBottom: `1px solid ${t.bd.s}`, fontSize: 11, color: t.tx.t }}>
              <span style={{ flex: 1 }}>指标</span>
              <span style={{ width: 80, textAlign: "right" }}>基准</span>
              <span style={{ width: 30 }} />
              <span style={{ width: 80, textAlign: "right" }}>当前</span>
              <span style={{ width: 80, textAlign: "right" }}>变化</span>
            </div>
            <CompareRow label="AI 5日净" baseline="-0.8%" current="+1.2%" delta="↑ +2.0%" tone="pos" />
            <CompareRow label="弱环境" baseline="-2.1%" current="-1.2%" delta="↑ +0.9%" tone="warn" />
            <CompareRow label="试错环境" baseline="+1.5%" current="+2.8%" delta="↑ +1.3%" tone="pos" />
            <CompareRow label="进攻环境" baseline="+3.8%" current="+4.5%" delta="↑ +0.7%" tone="pos" />
            <CompareRow label="扫描 5日净" baseline="+0.3%" current="+1.1%" delta="↑ +0.8%" tone="pos" />
          </div>
        </div>

        {/* Change Timeline */}
        <div>
          <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>变化回放</div>
          <div style={{ background: t.bg.t, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: "4px 16px" }}>
            <TimelineEvent date="04-24" label="中际旭创 300308" type="entered" detail="从全市场扫描进入观察池" />
            <TimelineEvent date="04-24" label="光迅科技 002281" type="upgraded" detail="从继续观察升级为进入候选" />
            <TimelineEvent date="04-23" label="隆基绿能 601012" type="downgraded" detail="从跟踪增强降级为优先处理（减仓）" />
            <TimelineEvent date="04-23" label="拓维信息 002261" type="entered" detail="午盘新增观察" />
            <TimelineEvent date="04-22" label="景嘉微 300474" type="exited" detail="跌破失效位，退出观察池" />
            <TimelineEvent date="04-21" label="宁德时代 300750" type="handed_off" detail="从观察池移交至持仓管理" />
          </div>
        </div>
      </div>

      {/* Research Panels */}
      <div style={{ marginTop: 32 }}>
        <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>研究面板</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {["Q1 校正基准", "最新切片"].map((title, i) => (
            <div key={i} style={{ background: t.bg.t, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 20 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                <div>
                  <div style={{ fontSize: 11, color: t.ac.blue, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>{i === 0 ? "基准研究" : "最近切片"}</div>
                  <div style={{ fontSize: 16, fontWeight: 600, color: t.tx.p }}>{title}</div>
                </div>
                <button style={{ fontSize: 12, color: t.ac.blue, background: "none", border: "none", cursor: "pointer", fontFamily: t.f.sans }}>展开 →</button>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {[
                  { label: "AI 总体", value: i === 0 ? "-0.8%" : "+1.2%", color: i === 0 ? t.sem.neg : t.sem.pos },
                  { label: "弱环境", value: i === 0 ? "-2.1%" : "-1.2%", color: t.sem.neg },
                  { label: "最佳环境", value: i === 0 ? "+3.8%" : "+4.5%", color: t.sem.pos },
                  { label: "最差阀门", value: i === 0 ? "-1.5%" : "-0.8%", color: t.sem.neg },
                ].map((m, j) => (
                  <div key={j} style={{ padding: "8px 10px", borderRadius: t.r.md, background: t.bg.s, border: `1px solid ${t.bd.s}` }}>
                    <div style={{ fontSize: 10, color: t.tx.t, marginBottom: 2 }}>{m.label}</div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: m.color, fontFamily: t.f.mono }}>{m.value}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ReviewFullPage() {
  return (
    <div style={{ display: "flex", minHeight: "100vh", background: t.bg.p, color: t.tx.p, fontFamily: t.f.sans, fontSize: 14, lineHeight: 1.5 }}>
      <Sidebar active="review" />
      <ReviewPage />
    </div>
  );
}
