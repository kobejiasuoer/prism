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

function Card({ children, padding = 20 }) {
  return <div style={{ background: t.bg.t, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding }}>{children}</div>;
}

function TabBar({ tabs, active, onSelect }) {
  return (
    <div style={{ display: "flex", gap: 2, padding: 3, background: t.bg.s, borderRadius: t.r.md, border: `1px solid ${t.bd.s}` }}>
      {tabs.map(tab => (
        <button key={tab.key} onClick={() => onSelect(tab.key)} style={{ padding: "6px 16px", borderRadius: t.r.sm, fontSize: 13, fontWeight: active === tab.key ? 500 : 400, background: active === tab.key ? t.bg.t : "transparent", color: active === tab.key ? t.tx.p : t.tx.t, border: active === tab.key ? `1px solid ${t.bd.s}` : "1px solid transparent", cursor: "pointer", fontFamily: t.f.sans }}>
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function DecisionCard({ label, value, detail, color }) {
  return (
    <div style={{ background: t.bg.s, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 16, flex: 1 }}>
      <div style={{ fontSize: 11, color: t.tx.t, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600, color: color || t.tx.p, lineHeight: 1.2 }}>{value}</div>
      {detail && <div style={{ fontSize: 12, color: t.tx.t, marginTop: 6 }}>{detail}</div>}
    </div>
  );
}

function LoopStep({ icon, title, content, color }) {
  return (
    <div style={{ display: "flex", gap: 14, padding: "14px 0", borderBottom: `1px solid ${t.bd.s}` }}>
      <div style={{ width: 32, height: 32, borderRadius: t.r.md, background: `${color}15`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, flexShrink: 0, color }}>{icon}</div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: t.tx.p, marginBottom: 3 }}>{title}</div>
        <div style={{ fontSize: 12, color: t.tx.s, lineHeight: 1.5 }}>{content}</div>
      </div>
    </div>
  );
}

function InsightGroup({ title, items, empty }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 12, fontWeight: 500, color: t.tx.s, marginBottom: 8 }}>{title}</div>
      {items.length > 0 ? (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {items.map((item, i) => (
            <span key={i} style={{ fontSize: 12, padding: "3px 10px", borderRadius: 9999, background: t.bg.s, color: t.tx.s, border: `1px solid ${t.bd.s}` }}>{item}</span>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: t.tx.t }}>{empty}</div>
      )}
    </div>
  );
}

function MetaRow({ label, value, detail }) {
  return (
    <div style={{ display: "flex", alignItems: "center", padding: "10px 0", borderBottom: `1px solid ${t.bd.s}` }}>
      <span style={{ fontSize: 12, color: t.tx.t, width: 100, flexShrink: 0 }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 500, color: t.tx.p, flex: 1 }}>{value}</span>
      {detail && <span style={{ fontSize: 11, color: t.tx.t }}>{detail}</span>}
    </div>
  );
}

function ChatBubble({ role, text }) {
  const isUser = role === "user";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", marginBottom: 12 }}>
      <div style={{ maxWidth: "75%", padding: "10px 14px", borderRadius: t.r.lg, background: isUser ? t.ac.blue : t.bg.s, color: isUser ? "#fff" : t.tx.s, fontSize: 13, lineHeight: 1.6, border: isUser ? "none" : `1px solid ${t.bd.s}` }}>{text}</div>
    </div>
  );
}

function DecisionTab() {
  return (
    <div>
      {/* Main Conclusion */}
      <Card padding={24}>
        <div style={{ display: "flex", alignItems: "start", justifyContent: "space-between", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 11, color: t.sem.neg, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>持仓结论</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: t.tx.p, fontFamily: t.f.display }}>减仓至半仓</div>
          </div>
          <Badge color={t.sem.neg}>优先处理</Badge>
        </div>
        <p style={{ fontSize: 14, color: t.tx.s, lineHeight: 1.6, marginBottom: 16 }}>技术面偏弱叠加资金 5 日净流出，当前位置不适合继续满仓。跌破 185 全部止损，反弹到 192 附近先减一半。</p>
        <div style={{ display: "flex", gap: 10 }}>
          <DecisionCard label="仓位建议" value="半仓" detail="从满仓减至 50%" />
          <DecisionCard label="止损位" value="¥185.00" detail="跌破即全部离场" color={t.sem.neg} />
          <DecisionCard label="下一步" value="等反弹减仓" detail="反弹到 192 附近执行" color={t.sem.warn} />
        </div>
      </Card>

      {/* Execution Loop */}
      <div style={{ marginTop: 24 }}>
        <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>动作循环</div>
        <Card padding={0}>
          <div style={{ padding: "0 20px" }}>
            <LoopStep icon="→" title="现在做" content="等反弹到 192 附近减仓，不要在当前位置追跌。" color={t.ac.blue} />
            <LoopStep icon="⚡" title="触发时" content="跌破 185 全部止损，不犹豫不补仓。" color={t.sem.warn} />
            <LoopStep icon="✕" title="不要做" content="不要在当前位置补仓，不要因为反弹就取消减仓计划。" color={t.sem.neg} />
            <LoopStep icon="◎" title="为什么" content="技术面偏弱 · 资金 5 日净流出 · 事件面中性。三个维度没有一个给出加仓信号。" color={t.tx.t} />
            <div style={{ padding: "14px 0" }}>
              <LoopStep icon="📎" title="证据" content="看盘中触发与原始文件 → 自选股快照、早盘批次、午盘确认" color={t.ac.indigo} />
            </div>
          </div>
        </Card>
      </div>

      {/* Why - Explanation */}
      <div style={{ marginTop: 24 }}>
        <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>判断依据</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
          <Card padding={14}>
            <div style={{ fontSize: 11, color: t.tx.t, marginBottom: 4 }}>技术基调</div>
            <div style={{ fontSize: 14, fontWeight: 500, color: t.sem.neg }}>偏弱</div>
            <div style={{ fontSize: 11, color: t.tx.t, marginTop: 4 }}>信号 均线空头</div>
          </Card>
          <Card padding={14}>
            <div style={{ fontSize: 11, color: t.tx.t, marginBottom: 4 }}>资金基调</div>
            <div style={{ fontSize: 14, fontWeight: 500, color: t.sem.neg }}>流出</div>
            <div style={{ fontSize: 11, color: t.tx.t, marginTop: 4 }}>5日净流出 3.2亿</div>
          </Card>
          <Card padding={14}>
            <div style={{ fontSize: 11, color: t.tx.t, marginBottom: 4 }}>事件基调</div>
            <div style={{ fontSize: 14, fontWeight: 500, color: t.tx.s }}>中性</div>
            <div style={{ fontSize: 11, color: t.tx.t, marginTop: 4 }}>无重大事件</div>
          </Card>
          <Card padding={14}>
            <div style={{ fontSize: 11, color: t.tx.t, marginBottom: 4 }}>规则分</div>
            <div style={{ fontSize: 14, fontWeight: 500, color: t.sem.warn }}>42</div>
            <div style={{ fontSize: 11, color: t.tx.t, marginTop: 4 }}>综合评分</div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function HoldingsTab() {
  return (
    <div>
      <Card padding={24}>
        <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 16 }}>持仓信息</div>
        <MetaRow label="当前仓位" value="满仓" detail="来自自选股快照" />
        <MetaRow label="优先级" value="优先处理" detail="priority 分组" />
        <MetaRow label="支撑位" value="¥185.00" detail="防守参考" />
        <MetaRow label="压力位" value="¥198.50" detail="突破观察" />
        <MetaRow label="止损位" value="¥185.00" detail="纪律边界" />
        <MetaRow label="规则分" value="42" detail="综合评分" />
      </Card>

      <div style={{ marginTop: 24 }}>
        <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>盘中触发</div>
        <Card padding={0}>
          <div style={{ padding: "0 20px" }}>
            <div style={{ display: "flex", alignItems: "center", padding: "12px 0", borderBottom: `1px solid ${t.bd.s}` }}>
              <span style={{ fontSize: 12, color: t.tx.t, width: 60 }}>触发 1</span>
              <span style={{ fontSize: 13, color: t.tx.p, flex: 1 }}>跌破 185 → 全部止损</span>
              <Badge color={t.sem.neg}>高优</Badge>
            </div>
            <div style={{ display: "flex", alignItems: "center", padding: "12px 0", borderBottom: `1px solid ${t.bd.s}` }}>
              <span style={{ fontSize: 12, color: t.tx.t, width: 60 }}>触发 2</span>
              <span style={{ fontSize: 13, color: t.tx.p, flex: 1 }}>反弹到 192 → 减仓至半仓</span>
              <Badge color={t.sem.warn}>等待</Badge>
            </div>
            <div style={{ display: "flex", alignItems: "center", padding: "12px 0" }}>
              <span style={{ fontSize: 12, color: t.tx.t, width: 60 }}>触发 3</span>
              <span style={{ fontSize: 13, color: t.tx.p, flex: 1 }}>突破 198.5 放量 → 重新评估</span>
              <Badge color={t.ac.blue}>观察</Badge>
            </div>
          </div>
        </Card>
      </div>

      <div style={{ marginTop: 24 }}>
        <InsightGroup title="硬风险" items={["均线空头排列", "资金持续流出"]} empty="" />
        <InsightGroup title="观察点" items={["等待 MACD 底背离", "关注板块联动"]} empty="" />
        <InsightGroup title="正向因素" items={["基本面稳健", "估值合理"]} empty="" />
      </div>
    </div>
  );
}

function DiscoveryTab() {
  return (
    <div>
      <Card padding={24}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em" }}>观察池状态</div>
          <Badge color={t.sem.warn}>继续观察</Badge>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
          <Card padding={14}>
            <div style={{ fontSize: 11, color: t.tx.t, marginBottom: 4 }}>优先分</div>
            <div style={{ fontSize: 18, fontWeight: 600, color: t.tx.p }}>72</div>
          </Card>
          <Card padding={14}>
            <div style={{ fontSize: 11, color: t.tx.t, marginBottom: 4 }}>执行质量</div>
            <div style={{ fontSize: 18, fontWeight: 600, color: t.sem.pos }}>B+</div>
          </Card>
          <Card padding={14}>
            <div style={{ fontSize: 11, color: t.tx.t, marginBottom: 4 }}>一致性</div>
            <div style={{ fontSize: 18, fontWeight: 600, color: t.sem.warn }}>中等</div>
          </Card>
        </div>
      </Card>

      <div style={{ marginTop: 24 }}>
        <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>动作计划</div>
        <Card padding={0}>
          <div style={{ padding: "0 20px" }}>
            <MetaRow label="动作" value="先观察，不急着执行" />
            <MetaRow label="触发" value="回踩 185 附近放量企稳" />
            <MetaRow label="回避" value="不追高，不在压力位附近建仓" />
            <MetaRow label="失效" value="跌破 180 取消观察" />
            <MetaRow label="仓位" value="轻仓试错（10%）" />
          </div>
        </Card>
      </div>

      <div style={{ marginTop: 24 }}>
        <div style={{ fontSize: 11, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>资金承接</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <Card padding={14}>
            <div style={{ fontSize: 11, color: t.tx.t, marginBottom: 4 }}>资金趋势</div>
            <div style={{ fontSize: 14, fontWeight: 500, color: t.sem.neg }}>流出</div>
            <div style={{ fontSize: 11, color: t.tx.t, marginTop: 4 }}>今日 -0.8 亿</div>
          </Card>
          <Card padding={14}>
            <div style={{ fontSize: 11, color: t.tx.t, marginBottom: 4 }}>5日累计</div>
            <div style={{ fontSize: 14, fontWeight: 500, color: t.sem.neg }}>-3.2 亿</div>
            <div style={{ fontSize: 11, color: t.tx.t, marginTop: 4 }}>持续流出</div>
          </Card>
        </div>
      </div>

      <div style={{ marginTop: 24 }}>
        <InsightGroup title="主题标签" items={["新能源", "锂电池", "储能"]} empty="" />
        <InsightGroup title="策略标签" items={["均值回归", "超跌反弹"]} empty="" />
        <InsightGroup title="风险提示" items={["板块轮动风险", "政策不确定性"]} empty="" />
      </div>
    </div>
  );
}

function ChatTab() {
  const [input, setInput] = useState("");
  return (
    <div style={{ display: "flex", flexDirection: "column", height: 480 }}>
      <div style={{ flex: 1, overflow: "auto", padding: "16px 0" }}>
        <ChatBubble role="assistant" text="宁德时代当前技术面偏弱，均线空头排列，资金 5 日净流出 3.2 亿。建议减仓至半仓，跌破 185 全部止损。" />
        <ChatBubble role="user" text="如果明天放量反弹呢？" />
        <ChatBubble role="assistant" text="如果明天放量反弹到 192 以上，可以先减一半仓位锁定利润。但如果是缩量反弹，大概率是诱多，建议继续等待更明确的信号。关键看成交量是否能恢复到 5 日均量以上。" />
        <ChatBubble role="user" text="止损位为什么设在 185？" />
        <ChatBubble role="assistant" text="185 是前期平台支撑位，也是 60 日均线附近。跌破这个位置意味着中期趋势转弱，继续持有的风险收益比不划算。这个位置也是多数机构的成本线附近，跌破后抛压会加速。" />
      </div>
      <div style={{ display: "flex", gap: 8, padding: "12px 0", borderTop: `1px solid ${t.bd.s}` }}>
        <input value={input} onChange={e => setInput(e.target.value)} placeholder="继续追问这只股票..." style={{ flex: 1, padding: "10px 14px", borderRadius: t.r.md, background: t.bg.s, border: `1px solid ${t.bd.s}`, color: t.tx.p, fontSize: 13, fontFamily: t.f.sans, outline: "none" }} />
        <button style={{ padding: "10px 20px", borderRadius: t.r.md, background: t.tx.p, color: t.tx.inv, border: "none", fontSize: 13, fontWeight: 500, cursor: "pointer", fontFamily: t.f.sans }}>发送</button>
      </div>
    </div>
  );
}

function HistoryTab() {
  const events = [
    { date: "04-24", action: "减仓至半仓", tone: "sell", detail: "技术面转弱，资金流出" },
    { date: "04-22", action: "维持满仓", tone: "hold", detail: "等待方向确认" },
    { date: "04-18", action: "加入优先处理", tone: "watch", detail: "从跟踪增强升级" },
    { date: "04-15", action: "跟踪增强", tone: "hold", detail: "基本面确认，轻仓跟踪" },
    { date: "04-10", action: "加入自选股", tone: "buy", detail: "观察池候选转入" },
  ];
  return (
    <div>
      <div style={{ position: "relative", paddingLeft: 24 }}>
        <div style={{ position: "absolute", left: 7, top: 8, bottom: 8, width: 2, background: t.bd.s }} />
        {events.map((ev, i) => (
          <div key={i} style={{ position: "relative", paddingBottom: 24 }}>
            <div style={{ position: "absolute", left: -20, top: 6, width: 12, height: 12, borderRadius: "50%", background: t.tone[ev.tone] || t.tx.t, border: `2px solid ${t.bg.p}` }} />
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
              <span style={{ fontSize: 12, color: t.tx.t, fontFamily: t.f.mono }}>{ev.date}</span>
              <span style={{ fontSize: 13, fontWeight: 500, color: t.tx.p }}>{ev.action}</span>
              <Badge color={t.tone[ev.tone] || t.tx.t}>{ev.tone}</Badge>
            </div>
            <div style={{ fontSize: 12, color: t.tx.t }}>{ev.detail}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Sidebar() {
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
      {[{ l: "指挥中心", i: "⌂" }, { l: "持仓管理", i: "◫" }, { l: "观察池", i: "◎" }, { l: "复盘", i: "◈" }].map(n => (
        <div key={n.l} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: t.r.md, color: t.tx.t, fontSize: 13, cursor: "pointer" }}>
          <span style={{ fontSize: 16, opacity: 0.5 }}>{n.i}</span>{n.l}
        </div>
      ))}
      <div style={{ height: 1, background: t.bd.s, margin: "12px" }} />
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", color: t.tx.t, fontSize: 13, cursor: "pointer" }}>
        <span style={{ fontSize: 16, opacity: 0.5 }}>⚙</span>设置
      </div>
    </div>
  );
}

export default function StockProfilePage() {
  const [tab, setTab] = useState("decision");
  const tabs = [
    { key: "decision", label: "决策" },
    { key: "holdings", label: "持仓" },
    { key: "discovery", label: "观察池" },
    { key: "chat", label: "追问" },
    { key: "history", label: "历史" },
  ];

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: t.bg.p, color: t.tx.p, fontFamily: t.f.sans, fontSize: 14, lineHeight: 1.5 }}>
      <Sidebar />
      <div style={{ flex: 1, overflow: "auto", padding: "32px 40px" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <span style={{ fontSize: 13, color: t.ac.blue, cursor: "pointer" }}>← 返回</span>
        </div>
        <div style={{ display: "flex", alignItems: "start", justifyContent: "space-between", marginBottom: 24 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
              <h1 style={{ fontSize: 28, fontWeight: 700, fontFamily: t.f.display, margin: 0 }}>宁德时代</h1>
              <span style={{ fontSize: 14, color: t.tx.t, fontFamily: t.f.mono }}>300750</span>
              <Badge color={t.sem.neg}>减仓至半仓</Badge>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <span style={{ fontSize: 22, fontWeight: 600, fontFamily: t.f.mono, color: t.tx.p }}>¥192.50</span>
              <span style={{ fontSize: 14, fontFamily: t.f.mono, color: t.sem.neg }}>-4.65 (-2.35%)</span>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button style={{ padding: "8px 16px", borderRadius: t.r.md, background: "transparent", border: `1px solid ${t.bd.d}`, color: t.tx.p, fontSize: 13, cursor: "pointer", fontFamily: t.f.sans }}>加入自选</button>
            <button style={{ padding: "8px 16px", borderRadius: t.r.md, background: t.tx.p, border: "none", color: t.tx.inv, fontSize: 13, fontWeight: 500, cursor: "pointer", fontFamily: t.f.sans }}>标记已处理</button>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ marginBottom: 24 }}>
          <TabBar tabs={tabs} active={tab} onSelect={setTab} />
        </div>

        {/* Tab Content */}
        {tab === "decision" && <DecisionTab />}
        {tab === "holdings" && <HoldingsTab />}
        {tab === "discovery" && <DiscoveryTab />}
        {tab === "chat" && <ChatTab />}
        {tab === "history" && <HistoryTab />}
      </div>
    </div>
  );
}
