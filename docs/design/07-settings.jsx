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
        <div key={it.key} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: t.r.md, background: "transparent", color: t.tx.t, fontSize: 13, fontWeight: 400, cursor: "pointer" }}>
          <span style={{ fontSize: 16, opacity: 0.5 }}>{it.icon}</span>{it.label}
        </div>
      ))}
      <div style={{ height: 1, background: t.bd.s, margin: "12px" }} />
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: t.r.md, background: t.bg.t, color: t.tx.p, fontSize: 13, fontWeight: 500, cursor: "pointer" }}>
        <span style={{ fontSize: 16, opacity: 1 }}>⚙</span>设置
      </div>
    </div>
  );
}

function SettingsNav({ active, onNav }) {
  const tabs = [
    { key: "tasks", label: "任务管理", icon: "▶" },
    { key: "params", label: "参数配置", icon: "⚙" },
    { key: "health", label: "系统状态", icon: "♥" },
  ];
  return (
    <div style={{ display: "flex", gap: 2, marginBottom: 32, borderBottom: `1px solid ${t.bd.s}`, paddingBottom: 0 }}>
      {tabs.map(tab => (
        <div key={tab.key} onClick={() => onNav(tab.key)} style={{ display: "flex", alignItems: "center", gap: 6, padding: "10px 20px", fontSize: 13, color: active === tab.key ? t.tx.p : t.tx.t, fontWeight: active === tab.key ? 500 : 400, cursor: "pointer", borderBottom: `2px solid ${active === tab.key ? t.ac.blue : "transparent"}`, marginBottom: -1 }}>
          <span style={{ fontSize: 14 }}>{tab.icon}</span>{tab.label}
        </div>
      ))}
    </div>
  );
}

function TaskCard({ name, description, status, lastRun, nextRun, schedule, onRun }) {
  const statusMap = { idle: { label: "空闲", color: t.tx.t }, running: { label: "运行中", color: t.ac.blue }, success: { label: "成功", color: t.sem.pos }, failed: { label: "失败", color: t.sem.neg }, scheduled: { label: "已排期", color: t.sem.warn } };
  const s = statusMap[status] || statusMap.idle;
  return (
    <div style={{ background: t.bg.s, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 15, fontWeight: 500, color: t.tx.p }}>{name}</span>
          <Badge color={s.color}>{s.label}</Badge>
        </div>
        <button onClick={onRun} style={{ padding: "6px 16px", borderRadius: t.r.md, background: status === "running" ? t.bg.t : t.ac.blue, border: "none", color: status === "running" ? t.tx.t : "#fff", fontSize: 12, fontWeight: 500, cursor: status === "running" ? "not-allowed" : "pointer", fontFamily: t.f.sans, opacity: status === "running" ? 0.5 : 1 }}>
          {status === "running" ? "运行中..." : "▶ 执行"}
        </button>
      </div>
      <div style={{ fontSize: 13, color: t.tx.s, marginBottom: 12, lineHeight: 1.5 }}>{description}</div>
      <div style={{ display: "flex", gap: 24, fontSize: 11, color: t.tx.t }}>
        <span>排期: {schedule}</span>
        <span>上次: {lastRun}</span>
        {nextRun && <span>下次: {nextRun}</span>}
      </div>
      {status === "running" && (
        <div style={{ marginTop: 12 }}>
          <div style={{ height: 3, borderRadius: 2, background: t.bg.t, overflow: "hidden" }}>
            <div style={{ width: "65%", height: "100%", borderRadius: 2, background: t.ac.blue, transition: "width 0.3s" }} />
          </div>
        </div>
      )}
    </div>
  );
}

function ParamGroup({ title, children }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ fontSize: 12, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12, paddingBottom: 8, borderBottom: `1px solid ${t.bd.s}` }}>{title}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>{children}</div>
    </div>
  );
}

function ParamRow({ label, description, value, type }) {
  return (
    <div style={{ display: "flex", alignItems: "start", gap: 16, padding: "8px 0" }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: t.tx.p, marginBottom: 2 }}>{label}</div>
        <div style={{ fontSize: 12, color: t.tx.t }}>{description}</div>
      </div>
      <div style={{ flexShrink: 0, width: 200 }}>
        {type === "toggle" ? (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8 }}>
            <span style={{ fontSize: 12, color: value ? t.sem.pos : t.tx.t }}>{value ? "开启" : "关闭"}</span>
            <div style={{ width: 36, height: 20, borderRadius: 10, background: value ? t.sem.pos : t.bg.t, border: `1px solid ${value ? t.sem.pos : t.bd.st}`, position: "relative", cursor: "pointer" }}>
              <div style={{ width: 14, height: 14, borderRadius: "50%", background: "#fff", position: "absolute", top: 2, left: value ? 19 : 2, transition: "left 0.2s" }} />
            </div>
          </div>
        ) : type === "select" ? (
          <div style={{ padding: "6px 12px", borderRadius: t.r.md, background: t.bg.t, border: `1px solid ${t.bd.d}`, color: t.tx.p, fontSize: 13, fontFamily: t.f.sans, textAlign: "right", cursor: "pointer" }}>
            {value} <span style={{ color: t.tx.t, marginLeft: 4 }}>▾</span>
          </div>
        ) : (
          <input readOnly value={value} style={{ width: "100%", padding: "6px 12px", borderRadius: t.r.md, background: t.bg.t, border: `1px solid ${t.bd.d}`, color: t.tx.p, fontSize: 13, fontFamily: t.f.mono, textAlign: "right", outline: "none", boxSizing: "border-box" }} />
        )}
      </div>
    </div>
  );
}

function HealthRow({ label, status, detail, latency }) {
  const color = status === "ok" ? t.sem.pos : status === "warn" ? t.sem.warn : t.sem.neg;
  const statusLabel = status === "ok" ? "正常" : status === "warn" ? "警告" : "异常";
  return (
    <div style={{ display: "flex", alignItems: "center", padding: "14px 0", borderBottom: `1px solid ${t.bd.s}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
        <div style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
        <span style={{ fontSize: 13, fontWeight: 500, color: t.tx.p }}>{label}</span>
      </div>
      <span style={{ fontSize: 12, color: t.tx.t, width: 200 }}>{detail}</span>
      {latency && <span style={{ fontSize: 12, fontFamily: t.f.mono, color: t.tx.t, width: 80, textAlign: "right" }}>{latency}</span>}
      <Badge color={color}>{statusLabel}</Badge>
    </div>
  );
}

function TasksPanel() {
  const [tasks, setTasks] = useState([
    { name: "总控简报", description: "生成每日总控简报，包含环境评级、阀门状态、持仓优先级排序。", status: "success", lastRun: "09:40", nextRun: "明日 09:30", schedule: "每日 09:30" },
    { name: "自选股快照", description: "抓取自选股列表最新行情，更新持仓管理页面数据。", status: "running", lastRun: "09:32", nextRun: "-", schedule: "手动 / 每2小时" },
    { name: "激进扫描", description: "全市场扫描符合激进策略条件的标的，输出到观察池。", status: "idle", lastRun: "昨日 15:00", nextRun: "明日 09:15", schedule: "每日 09:15" },
    { name: "午盘刷新", description: "午盘开盘后刷新观察池候选状态，标记午盘新增和确认。", status: "scheduled", lastRun: "昨日 13:00", nextRun: "今日 13:00", schedule: "每日 13:00" },
    { name: "午盘确认", description: "午盘收盘前确认早盘候选的承接情况，更新候选状态。", status: "idle", lastRun: "昨日 14:30", nextRun: "今日 14:30", schedule: "每日 14:30" },
  ]);

  const handleRun = (idx) => {
    setTasks(prev => prev.map((t, i) => i === idx ? { ...t, status: "running" } : t));
  };

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 600, color: t.tx.p, marginBottom: 4 }}>任务管理</div>
          <div style={{ fontSize: 13, color: t.tx.s }}>管理数据采集和分析任务的执行与排期</div>
        </div>
        <button style={{ padding: "8px 16px", borderRadius: t.r.md, background: "transparent", border: `1px solid ${t.bd.d}`, color: t.tx.p, fontSize: 13, cursor: "pointer", fontFamily: t.f.sans }}>▶ 全部执行</button>
      </div>

      {/* Summary */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
        {[
          { label: "总任务", value: "5", color: t.tx.p },
          { label: "运行中", value: "1", color: t.ac.blue },
          { label: "已排期", value: "1", color: t.sem.warn },
          { label: "上次全量", value: "09:40", color: t.sem.pos },
        ].map((m, i) => (
          <div key={i} style={{ background: t.bg.t, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 14, textAlign: "center" }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: m.color, fontFamily: t.f.display }}>{m.value}</div>
            <div style={{ fontSize: 11, color: t.tx.t, marginTop: 4 }}>{m.label}</div>
          </div>
        ))}
      </div>

      {/* Task Cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {tasks.map((task, i) => (
          <TaskCard key={i} {...task} onRun={() => handleRun(i)} />
        ))}
      </div>
    </div>
  );
}

function ParamsPanel() {
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 600, color: t.tx.p, marginBottom: 4 }}>参数配置</div>
          <div style={{ fontSize: 13, color: t.tx.s }}>调整策略参数、阀门阈值和系统行为</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button style={{ padding: "8px 16px", borderRadius: t.r.md, background: "transparent", border: `1px solid ${t.bd.d}`, color: t.tx.p, fontSize: 13, cursor: "pointer", fontFamily: t.f.sans }}>↩ 重置</button>
          <button style={{ padding: "8px 16px", borderRadius: t.r.md, background: t.ac.blue, border: "none", color: "#fff", fontSize: 13, fontWeight: 500, cursor: "pointer", fontFamily: t.f.sans }}>保存</button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32 }}>
        <div>
          <ParamGroup title="阀门控制">
            <ParamRow label="进攻阀门" description="是否允许新建仓位" value={true} type="toggle" />
            <ParamRow label="仓位上限" description="同时持有的最大股票数" value="2" type="number" />
            <ParamRow label="单笔上限" description="单只股票最大仓位比例" value="10%" type="number" />
            <ParamRow label="止损阈值" description="单笔最大亏损比例" value="3%" type="number" />
          </ParamGroup>

          <ParamGroup title="环境评级">
            <ParamRow label="弱环境阈值" description="AI 5日净低于此值判定为弱环境" value="-1.0%" type="number" />
            <ParamRow label="进攻环境阈值" description="AI 5日净高于此值判定为进攻环境" value="+2.0%" type="number" />
            <ParamRow label="评级模式" description="环境评级计算方式" value="滚动5日" type="select" />
          </ParamGroup>
        </div>

        <div>
          <ParamGroup title="扫描策略">
            <ParamRow label="激进扫描" description="启用全市场激进策略扫描" value={true} type="toggle" />
            <ParamRow label="最低评分" description="进入观察池的最低综合评分" value="60" type="number" />
            <ParamRow label="主线板块" description="当前关注的主线方向" value="AI+机器人" type="select" />
          </ParamGroup>

          <ParamGroup title="数据刷新">
            <ParamRow label="自动刷新" description="是否启用定时自动刷新" value={true} type="toggle" />
            <ParamRow label="刷新间隔" description="自动刷新的时间间隔" value="120 秒" type="number" />
            <ParamRow label="冷却时间" description="手动刷新后的冷却时间" value="30 秒" type="number" />
          </ParamGroup>

          {/* JSON Editor Preview */}
          <div style={{ marginTop: 8 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontSize: 12, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em" }}>原始 JSON</span>
              <button style={{ fontSize: 11, color: t.ac.blue, background: "none", border: "none", cursor: "pointer", fontFamily: t.f.sans }}>展开编辑器 →</button>
            </div>
            <div style={{ background: t.bg.s, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 16, fontFamily: t.f.mono, fontSize: 11, color: t.tx.s, lineHeight: 1.8, maxHeight: 160, overflow: "hidden" }}>
              <div><span style={{ color: t.tx.t }}>{"{"}</span></div>
              <div style={{ paddingLeft: 16 }}><span style={{ color: t.ac.blue }}>"gate_open"</span>: <span style={{ color: t.sem.pos }}>true</span>,</div>
              <div style={{ paddingLeft: 16 }}><span style={{ color: t.ac.blue }}>"max_positions"</span>: <span style={{ color: t.sem.warn }}>2</span>,</div>
              <div style={{ paddingLeft: 16 }}><span style={{ color: t.ac.blue }}>"max_single_position"</span>: <span style={{ color: t.sem.warn }}>0.10</span>,</div>
              <div style={{ paddingLeft: 16 }}><span style={{ color: t.ac.blue }}>"stop_loss_threshold"</span>: <span style={{ color: t.sem.warn }}>0.03</span>,</div>
              <div style={{ paddingLeft: 16 }}>...</div>
              <div><span style={{ color: t.tx.t }}>{"}"}</span></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function HealthPanel() {
  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 18, fontWeight: 600, color: t.tx.p, marginBottom: 4 }}>系统状态</div>
        <div style={{ fontSize: 13, color: t.tx.s }}>核心服务和数据链路的健康状态</div>
      </div>

      {/* Uptime Banner */}
      <div style={{ background: `${t.sem.pos}08`, border: `1px solid ${t.sem.pos}20`, borderRadius: t.r.lg, padding: 20, marginBottom: 24, display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ width: 48, height: 48, borderRadius: "50%", background: `${t.sem.pos}18`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24 }}>♥</div>
        <div>
          <div style={{ fontSize: 16, fontWeight: 600, color: t.sem.pos }}>系统运行正常</div>
          <div style={{ fontSize: 13, color: t.tx.s, marginTop: 2 }}>所有核心服务在线 · 上次检查 2 分钟前</div>
        </div>
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <div style={{ fontSize: 24, fontWeight: 700, color: t.sem.pos, fontFamily: t.f.display }}>99.8%</div>
          <div style={{ fontSize: 11, color: t.tx.t }}>7日可用率</div>
        </div>
      </div>

      {/* Service Health */}
      <div style={{ background: t.bg.t, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: "4px 20px", marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", padding: "10px 0", borderBottom: `1px solid ${t.bd.s}`, fontSize: 11, color: t.tx.t }}>
          <span style={{ flex: 1 }}>服务</span>
          <span style={{ width: 200 }}>详情</span>
          <span style={{ width: 80, textAlign: "right" }}>延迟</span>
          <span style={{ width: 60, textAlign: "right" }}>状态</span>
        </div>
        <HealthRow label="FastAPI 后端" status="ok" detail="v1.2.0 · PID 12847" latency="12ms" />
        <HealthRow label="数据采集引擎" status="ok" detail="5 个采集器活跃" latency="340ms" />
        <HealthRow label="AI 分析服务" status="ok" detail="Claude API · 配额充足" latency="1.2s" />
        <HealthRow label="行情数据源" status="warn" detail="东方财富 · 偶发超时" latency="890ms" />
        <HealthRow label="本地存储" status="ok" detail="JSON 文件 · 磁盘 42% 已用" latency="2ms" />
      </div>

      {/* Recent Logs */}
      <div>
        <div style={{ fontSize: 12, color: t.tx.t, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>最近日志</div>
        <div style={{ background: t.bg.s, border: `1px solid ${t.bd.s}`, borderRadius: t.r.lg, padding: 16, fontFamily: t.f.mono, fontSize: 11, lineHeight: 2 }}>
          {[
            { time: "09:45:12", level: "INFO", msg: "总控简报生成完成，耗时 8.2s" },
            { time: "09:40:03", level: "INFO", msg: "自选股快照更新成功，8 只股票" },
            { time: "09:32:18", level: "WARN", msg: "行情数据源响应超时，已重试 (890ms)" },
            { time: "09:30:01", level: "INFO", msg: "每日定时任务启动: 总控简报" },
            { time: "09:15:44", level: "INFO", msg: "激进扫描完成，新增 3 只候选" },
            { time: "09:15:02", level: "INFO", msg: "每日定时任务启动: 激进扫描" },
            { time: "09:00:00", level: "INFO", msg: "系统启动，环境评级: 弱环境" },
          ].map((log, i) => {
            const levelColor = log.level === "WARN" ? t.sem.warn : log.level === "ERROR" ? t.sem.neg : t.tx.t;
            return (
              <div key={i} style={{ display: "flex", gap: 12 }}>
                <span style={{ color: t.tx.t, flexShrink: 0 }}>{log.time}</span>
                <span style={{ color: levelColor, flexShrink: 0, width: 40 }}>{log.level}</span>
                <span style={{ color: t.tx.s }}>{log.msg}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function SettingsPage() {
  const [tab, setTab] = useState("tasks");
  return (
    <div style={{ flex: 1, overflow: "auto", padding: "32px 40px" }}>
      <div style={{ marginBottom: 8 }}>
        <div style={{ fontSize: 11, color: t.ac.blue, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>Settings</div>
        <h1 style={{ fontSize: 28, fontWeight: 700, fontFamily: t.f.display, margin: 0, marginBottom: 8 }}>设置</h1>
        <p style={{ fontSize: 14, color: t.tx.s, margin: 0 }}>任务排期、策略参数和系统健康状态</p>
      </div>
      <SettingsNav active={tab} onNav={setTab} />
      {tab === "tasks" && <TasksPanel />}
      {tab === "params" && <ParamsPanel />}
      {tab === "health" && <HealthPanel />}
    </div>
  );
}

export default function SettingsFullPage() {
  return (
    <div style={{ display: "flex", minHeight: "100vh", background: t.bg.p, color: t.tx.p, fontFamily: t.f.sans, fontSize: 14, lineHeight: 1.5 }}>
      <Sidebar active="settings" />
      <SettingsPage />
    </div>
  );
}
