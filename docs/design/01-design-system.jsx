import { useState } from "react";

const tokens = {
  colors: {
    bg: { primary: "#0a0a0b", secondary: "#111113", tertiary: "#18181b", elevated: "#1c1c1f" },
    border: { subtle: "rgba(255,255,255,0.06)", default: "rgba(255,255,255,0.1)", strong: "rgba(255,255,255,0.16)" },
    text: { primary: "#f4f4f5", secondary: "#a1a1aa", tertiary: "#71717a", inverse: "#09090b" },
    accent: { blue: "#3b82f6", indigo: "#6366f1", violet: "#8b5cf6" },
    semantic: { positive: "#22c55e", negative: "#ef4444", warning: "#f59e0b", info: "#3b82f6" },
    tone: { buy: "#22c55e", sell: "#ef4444", watch: "#f59e0b", hold: "#3b82f6", avoid: "#71717a" },
  },
  radius: { sm: 6, md: 8, lg: 12, xl: 16, full: 9999 },
  spacing: [0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80],
  font: {
    sans: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Noto Sans SC", sans-serif',
    mono: '"SF Mono", "Fira Code", "JetBrains Mono", monospace',
    display: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", sans-serif',
  },
  fontSize: { xs: 11, sm: 13, base: 14, md: 16, lg: 20, xl: 24, "2xl": 32, "3xl": 40 },
  fontWeight: { normal: 400, medium: 500, semibold: 600, bold: 700 },
};

function ColorSwatch({ name, value }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0" }}>
      <div style={{ width: 40, height: 40, borderRadius: tokens.radius.md, background: value, border: `1px solid ${tokens.colors.border.default}`, flexShrink: 0 }} />
      <div>
        <div style={{ fontSize: tokens.fontSize.sm, color: tokens.colors.text.primary, fontWeight: 500 }}>{name}</div>
        <div style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary, fontFamily: tokens.font.mono }}>{value}</div>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 48 }}>
      <h2 style={{ fontSize: tokens.fontSize.lg, fontWeight: tokens.fontWeight.semibold, color: tokens.colors.text.primary, marginBottom: 20, paddingBottom: 12, borderBottom: `1px solid ${tokens.colors.border.subtle}`, fontFamily: tokens.font.display }}>{title}</h2>
      {children}
    </div>
  );
}

function Badge({ children, tone = "info" }) {
  const toneColors = { positive: tokens.colors.semantic.positive, negative: tokens.colors.semantic.negative, warning: tokens.colors.semantic.warning, info: tokens.colors.semantic.info, buy: tokens.colors.tone.buy, sell: tokens.colors.tone.sell, watch: tokens.colors.tone.watch, hold: tokens.colors.tone.hold, avoid: tokens.colors.tone.avoid };
  const c = toneColors[tone] || toneColors.info;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", padding: "2px 10px", borderRadius: tokens.radius.full, fontSize: tokens.fontSize.xs, fontWeight: tokens.fontWeight.medium, background: `${c}18`, color: c, border: `1px solid ${c}30` }}>{children}</span>
  );
}

function Button({ children, variant = "primary", size = "md" }) {
  const styles = {
    primary: { background: tokens.colors.text.primary, color: tokens.colors.text.inverse, border: "none" },
    secondary: { background: "transparent", color: tokens.colors.text.primary, border: `1px solid ${tokens.colors.border.default}` },
    ghost: { background: "transparent", color: tokens.colors.text.secondary, border: "none" },
    danger: { background: `${tokens.colors.semantic.negative}18`, color: tokens.colors.semantic.negative, border: `1px solid ${tokens.colors.semantic.negative}30` },
  };
  const sizes = { sm: { padding: "4px 12px", fontSize: tokens.fontSize.xs }, md: { padding: "8px 16px", fontSize: tokens.fontSize.sm }, lg: { padding: "10px 24px", fontSize: tokens.fontSize.base } };
  return (
    <button style={{ ...styles[variant], ...sizes[size], borderRadius: tokens.radius.md, fontWeight: tokens.fontWeight.medium, cursor: "pointer", fontFamily: tokens.font.sans, transition: "all 0.15s ease" }}>{children}</button>
  );
}

function Card({ children, padding = 20 }) {
  return (
    <div style={{ background: tokens.colors.bg.tertiary, border: `1px solid ${tokens.colors.border.subtle}`, borderRadius: tokens.radius.lg, padding }}>{children}</div>
  );
}

function MetricCard({ label, value, detail, tone }) {
  const toneColor = tone ? (tokens.colors.tone[tone] || tokens.colors.semantic[tone]) : null;
  return (
    <Card>
      <div style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary, marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: tokens.fontSize.xl, fontWeight: tokens.fontWeight.bold, color: toneColor || tokens.colors.text.primary, fontFamily: tokens.font.display, lineHeight: 1.2 }}>{value}</div>
      {detail && <div style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary, marginTop: 6 }}>{detail}</div>}
    </Card>
  );
}

function StockRow({ name, code, action, tone, price, change }) {
  const toneColor = tokens.colors.tone[tone] || tokens.colors.text.secondary;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", borderRadius: tokens.radius.md, background: tokens.colors.bg.secondary, border: `1px solid ${tokens.colors.border.subtle}`, cursor: "pointer", transition: "all 0.15s ease" }}>
      <div style={{ width: 3, height: 32, borderRadius: 2, background: toneColor, flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: tokens.fontSize.base, fontWeight: tokens.fontWeight.medium, color: tokens.colors.text.primary }}>{name}</span>
          <span style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary, fontFamily: tokens.font.mono }}>{code}</span>
        </div>
        <div style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary, marginTop: 2 }}>{action}</div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div style={{ fontSize: tokens.fontSize.sm, fontWeight: tokens.fontWeight.medium, color: tokens.colors.text.primary, fontFamily: tokens.font.mono }}>{price}</div>
        <div style={{ fontSize: tokens.fontSize.xs, color: toneColor, fontFamily: tokens.font.mono }}>{change}</div>
      </div>
      <div style={{ color: tokens.colors.text.tertiary, fontSize: 16 }}>›</div>
    </div>
  );
}

function NavItem({ label, active, icon }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: tokens.radius.md, background: active ? tokens.colors.bg.tertiary : "transparent", color: active ? tokens.colors.text.primary : tokens.colors.text.tertiary, fontSize: tokens.fontSize.sm, fontWeight: active ? tokens.fontWeight.medium : tokens.fontWeight.normal, cursor: "pointer", transition: "all 0.15s ease" }}>
      <span style={{ fontSize: 16, opacity: active ? 1 : 0.5 }}>{icon}</span>
      {label}
    </div>
  );
}

function InputField({ placeholder, icon }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 14px", borderRadius: tokens.radius.md, background: tokens.colors.bg.secondary, border: `1px solid ${tokens.colors.border.subtle}`, color: tokens.colors.text.tertiary, fontSize: tokens.fontSize.sm }}>
      {icon && <span style={{ opacity: 0.5 }}>{icon}</span>}
      <span>{placeholder}</span>
      <span style={{ marginLeft: "auto", fontSize: tokens.fontSize.xs, padding: "2px 6px", borderRadius: 4, background: tokens.colors.bg.tertiary, border: `1px solid ${tokens.colors.border.subtle}` }}>⌘K</span>
    </div>
  );
}

function ActionItem({ label, sublabel, tone, checked }) {
  const toneColor = tokens.colors.tone[tone] || tokens.colors.text.secondary;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: `1px solid ${tokens.colors.border.subtle}` }}>
      <div style={{ width: 18, height: 18, borderRadius: tokens.radius.sm, border: checked ? "none" : `2px solid ${tokens.colors.border.strong}`, background: checked ? tokens.colors.semantic.positive : "transparent", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, cursor: "pointer" }}>
        {checked && <span style={{ color: "#fff", fontSize: 11 }}>✓</span>}
      </div>
      <div style={{ flex: 1 }}>
        <span style={{ fontSize: tokens.fontSize.sm, color: checked ? tokens.colors.text.tertiary : tokens.colors.text.primary, textDecoration: checked ? "line-through" : "none" }}>{label}</span>
      </div>
      <Badge tone={tone}>{sublabel}</Badge>
    </div>
  );
}

function TabBar({ tabs, active, onSelect }) {
  return (
    <div style={{ display: "flex", gap: 2, padding: 3, background: tokens.colors.bg.secondary, borderRadius: tokens.radius.md, border: `1px solid ${tokens.colors.border.subtle}` }}>
      {tabs.map(t => (
        <button key={t} onClick={() => onSelect(t)} style={{ padding: "6px 16px", borderRadius: tokens.radius.sm, fontSize: tokens.fontSize.sm, fontWeight: active === t ? tokens.fontWeight.medium : tokens.fontWeight.normal, background: active === t ? tokens.colors.bg.tertiary : "transparent", color: active === t ? tokens.colors.text.primary : tokens.colors.text.tertiary, border: active === t ? `1px solid ${tokens.colors.border.subtle}` : "1px solid transparent", cursor: "pointer", transition: "all 0.15s ease", fontFamily: tokens.font.sans }}>{t}</button>
      ))}
    </div>
  );
}

function ProgressBar({ value, max, color }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div style={{ height: 4, borderRadius: 2, background: tokens.colors.bg.secondary, overflow: "hidden" }}>
      <div style={{ height: "100%", width: `${pct}%`, borderRadius: 2, background: color || tokens.colors.accent.blue, transition: "width 0.3s ease" }} />
    </div>
  );
}

function StatusDot({ status }) {
  const colors = { ok: tokens.colors.semantic.positive, warning: tokens.colors.semantic.warning, error: tokens.colors.semantic.negative, stale: tokens.colors.text.tertiary };
  return <div style={{ width: 8, height: 8, borderRadius: "50%", background: colors[status] || colors.stale }} />;
}

export default function DesignSystem() {
  const [activeTab, setActiveTab] = useState("决策");

  return (
    <div style={{ minHeight: "100vh", background: tokens.colors.bg.primary, color: tokens.colors.text.primary, fontFamily: tokens.font.sans, fontSize: tokens.fontSize.base, lineHeight: 1.6 }}>
      <div style={{ maxWidth: 960, margin: "0 auto", padding: "48px 24px" }}>
        <div style={{ marginBottom: 48 }}>
          <div style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.accent.blue, fontWeight: tokens.fontWeight.medium, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8 }}>Design System</div>
          <h1 style={{ fontSize: tokens.fontSize["3xl"], fontWeight: tokens.fontWeight.bold, fontFamily: tokens.font.display, lineHeight: 1.1, marginBottom: 12 }}>棱镜 · 视觉系统</h1>
          <p style={{ fontSize: tokens.fontSize.md, color: tokens.colors.text.secondary, maxWidth: 600 }}>暗色优先、数据密集型金融决策界面的设计规范。参考 Linear + Bloomberg Terminal 的现代化表达。</p>
        </div>

        <Section title="色彩 · Colors">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 32 }}>
            <div>
              <div style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.05em" }}>背景层级</div>
              <ColorSwatch name="Primary" value={tokens.colors.bg.primary} />
              <ColorSwatch name="Secondary" value={tokens.colors.bg.secondary} />
              <ColorSwatch name="Tertiary" value={tokens.colors.bg.tertiary} />
              <ColorSwatch name="Elevated" value={tokens.colors.bg.elevated} />
            </div>
            <div>
              <div style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.05em" }}>语义色</div>
              <ColorSwatch name="Positive / 涨" value={tokens.colors.semantic.positive} />
              <ColorSwatch name="Negative / 跌" value={tokens.colors.semantic.negative} />
              <ColorSwatch name="Warning / 观察" value={tokens.colors.semantic.warning} />
              <ColorSwatch name="Info / 信息" value={tokens.colors.semantic.info} />
            </div>
            <div>
              <div style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.05em" }}>动作色</div>
              <ColorSwatch name="Buy / 买入" value={tokens.colors.tone.buy} />
              <ColorSwatch name="Sell / 卖出" value={tokens.colors.tone.sell} />
              <ColorSwatch name="Watch / 观察" value={tokens.colors.tone.watch} />
              <ColorSwatch name="Hold / 持有" value={tokens.colors.tone.hold} />
              <ColorSwatch name="Avoid / 回避" value={tokens.colors.tone.avoid} />
            </div>
          </div>
        </Section>

        <Section title="字体 · Typography">
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ fontSize: tokens.fontSize["3xl"], fontWeight: tokens.fontWeight.bold, fontFamily: tokens.font.display }}>Display 40px Bold — 页面标题</div>
            <div style={{ fontSize: tokens.fontSize["2xl"], fontWeight: tokens.fontWeight.semibold, fontFamily: tokens.font.display }}>Heading 32px Semibold — 区块标题</div>
            <div style={{ fontSize: tokens.fontSize.xl, fontWeight: tokens.fontWeight.semibold }}>Title 24px Semibold — 卡片标题</div>
            <div style={{ fontSize: tokens.fontSize.lg, fontWeight: tokens.fontWeight.medium }}>Subtitle 20px Medium — 子标题</div>
            <div style={{ fontSize: tokens.fontSize.md, color: tokens.colors.text.secondary }}>Body 16px Regular — 正文描述</div>
            <div style={{ fontSize: tokens.fontSize.base }}>Base 14px Regular — 默认文本</div>
            <div style={{ fontSize: tokens.fontSize.sm, color: tokens.colors.text.secondary }}>Small 13px — 辅助信息</div>
            <div style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary }}>Caption 11px — 标签/时间戳</div>
            <div style={{ fontSize: tokens.fontSize.sm, fontFamily: tokens.font.mono, color: tokens.colors.accent.blue }}>Mono 13px — 代码/数字 300750.SZ</div>
          </div>
        </Section>

        <Section title="圆角 · Radius">
          <div style={{ display: "flex", gap: 24, alignItems: "end" }}>
            {Object.entries(tokens.radius).filter(([k]) => k !== "full").map(([name, val]) => (
              <div key={name} style={{ textAlign: "center" }}>
                <div style={{ width: 64, height: 64, borderRadius: val, background: tokens.colors.bg.tertiary, border: `1px solid ${tokens.colors.border.default}`, marginBottom: 8 }} />
                <div style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary }}>{name} · {val}px</div>
              </div>
            ))}
            <div style={{ textAlign: "center" }}>
              <div style={{ width: 64, height: 32, borderRadius: tokens.radius.full, background: tokens.colors.bg.tertiary, border: `1px solid ${tokens.colors.border.default}`, marginBottom: 8 }} />
              <div style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary }}>full · pill</div>
            </div>
          </div>
        </Section>

        <Section title="按钮 · Buttons">
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <Button variant="primary" size="lg">主要操作</Button>
            <Button variant="primary" size="md">保存并同步</Button>
            <Button variant="primary" size="sm">确认</Button>
            <Button variant="secondary" size="md">次要操作</Button>
            <Button variant="ghost" size="md">文字按钮</Button>
            <Button variant="danger" size="md">危险操作</Button>
          </div>
        </Section>

        <Section title="徽章 · Badges">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Badge tone="buy">买入</Badge>
            <Badge tone="sell">卖出</Badge>
            <Badge tone="watch">观察</Badge>
            <Badge tone="hold">持有</Badge>
            <Badge tone="avoid">回避</Badge>
            <Badge tone="positive">就绪</Badge>
            <Badge tone="negative">拦截</Badge>
            <Badge tone="warning">警告</Badge>
            <Badge tone="info">信息</Badge>
          </div>
        </Section>

        <Section title="指标卡 · Metric Cards">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            <MetricCard label="持仓优先" value="3" detail="来自自选股页面" />
            <MetricCard label="观察候选" value="5" detail="来自观察池" tone="watch" />
            <MetricCard label="午盘新增" value="2" detail="午盘确认" tone="positive" />
            <MetricCard label="质检就绪" value="3/3" detail="核心链路状态" tone="positive" />
          </div>
        </Section>

        <Section title="股票行 · Stock Rows">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <StockRow name="宁德时代" code="300750" action="减仓至半仓 · 跌破185止损" tone="sell" price="¥192.50" change="-2.35%" />
            <StockRow name="比亚迪" code="002594" action="继续持有 · 等待突破" tone="hold" price="¥268.80" change="+0.75%" />
            <StockRow name="中际旭创" code="300308" action="轻仓试错 · 等回踩确认" tone="watch" price="¥88.60" change="+3.21%" />
            <StockRow name="寒武纪" code="688256" action="回避 · 估值过高" tone="avoid" price="¥312.00" change="-0.48%" />
          </div>
        </Section>

        <Section title="待办项 · Action Items">
          <div style={{ padding: "0 4px" }}>
            <ActionItem label="宁德时代 300750 — 减仓至半仓" sublabel="优先处理" tone="sell" />
            <ActionItem label="比亚迪 002594 — 止损观察" sublabel="优先处理" tone="sell" />
            <ActionItem label="中际旭创 300308 — 轻仓试错" sublabel="等触发" tone="watch" />
            <ActionItem label="寒武纪 688256 — 继续持有" sublabel="已处理" tone="hold" checked />
          </div>
        </Section>

        <Section title="标签页 · Tabs">
          <TabBar tabs={["决策", "持仓", "观察池", "追问", "历史"]} active={activeTab} onSelect={setActiveTab} />
          <div style={{ marginTop: 16, padding: 20, background: tokens.colors.bg.secondary, borderRadius: tokens.radius.lg, border: `1px solid ${tokens.colors.border.subtle}` }}>
            <div style={{ fontSize: tokens.fontSize.sm, color: tokens.colors.text.secondary }}>当前选中：{activeTab}</div>
          </div>
        </Section>

        <Section title="搜索栏 · Command Bar">
          <InputField placeholder="搜索股票、跳转页面..." icon="⌕" />
        </Section>

        <Section title="导航 · Navigation">
          <div style={{ width: 220, padding: 12, background: tokens.colors.bg.secondary, borderRadius: tokens.radius.lg, border: `1px solid ${tokens.colors.border.subtle}` }}>
            <div style={{ padding: "8px 12px", marginBottom: 12 }}>
              <div style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary, fontWeight: tokens.fontWeight.medium, textTransform: "uppercase", letterSpacing: "0.1em" }}>棱镜</div>
              <div style={{ fontSize: tokens.fontSize.sm, fontWeight: tokens.fontWeight.semibold, color: tokens.colors.text.primary }}>交易决策台</div>
            </div>
            <NavItem label="指挥中心" active icon="⌂" />
            <NavItem label="持仓管理" icon="◫" />
            <NavItem label="观察池" icon="◎" />
            <NavItem label="复盘" icon="◈" />
            <div style={{ height: 1, background: tokens.colors.border.subtle, margin: "8px 12px" }} />
            <NavItem label="设置" icon="⚙" />
          </div>
        </Section>

        <Section title="进度条 · Progress">
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary }}>质检进度</span>
                <span style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.semantic.positive }}>3/3</span>
              </div>
              <ProgressBar value={3} max={3} color={tokens.colors.semantic.positive} />
            </div>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.text.tertiary }}>刷新冷却</span>
                <span style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.semantic.warning }}>45%</span>
              </div>
              <ProgressBar value={45} max={100} color={tokens.colors.semantic.warning} />
            </div>
          </div>
        </Section>

        <Section title="状态点 · Status Dots">
          <div style={{ display: "flex", gap: 24 }}>
            {["ok", "warning", "error", "stale"].map(s => (
              <div key={s} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <StatusDot status={s} />
                <span style={{ fontSize: tokens.fontSize.sm, color: tokens.colors.text.secondary }}>{s}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="卡片组合 · Card Composition">
          <Card padding={24}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: tokens.fontSize.xs, color: tokens.colors.accent.blue, fontWeight: tokens.fontWeight.medium, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>今日结论</div>
                <div style={{ fontSize: tokens.fontSize.lg, fontWeight: tokens.fontWeight.semibold }}>先处理旧仓，再决定是否看新仓</div>
              </div>
              <Badge tone="watch">允许轻仓试错</Badge>
            </div>
            <div style={{ fontSize: tokens.fontSize.sm, color: tokens.colors.text.secondary, marginBottom: 16 }}>阀门开放但仓位上限 2 只，主线 AI+机器人。弱环境 5 日净仍为负，控制新仓节奏。</div>
            <div style={{ display: "flex", gap: 8 }}>
              <span style={{ fontSize: tokens.fontSize.xs, padding: "3px 10px", borderRadius: tokens.radius.full, background: tokens.colors.bg.secondary, color: tokens.colors.text.tertiary, border: `1px solid ${tokens.colors.border.subtle}` }}>仓位上限 2 只</span>
              <span style={{ fontSize: tokens.fontSize.xs, padding: "3px 10px", borderRadius: tokens.radius.full, background: tokens.colors.bg.secondary, color: tokens.colors.text.tertiary, border: `1px solid ${tokens.colors.border.subtle}` }}>主线 AI+机器人</span>
              <span style={{ fontSize: tokens.fontSize.xs, padding: "3px 10px", borderRadius: tokens.radius.full, background: `${tokens.colors.semantic.warning}18`, color: tokens.colors.semantic.warning, border: `1px solid ${tokens.colors.semantic.warning}30` }}>弱环境偏负</span>
            </div>
          </Card>
        </Section>
      </div>
    </div>
  );
}
