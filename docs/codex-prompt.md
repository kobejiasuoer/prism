# Codex Task: 棱镜前端重建 — Phase 0 + Phase 1

> 历史任务记录：这份文档记录的是启动 Next.js 重建时的原始任务书。当前 Prism 已经完成迁移，正式前端是 `apps/web`，FastAPI 位于 `apps/control-panel` 且只作为后端 API。

## 背景

棱镜（Prism）是一个 A 股交易决策辅助系统。当前正式前端是 Next.js + React，位于 `apps/web`；FastAPI 后端 API 位于 `apps/control-panel`。

所有设计规范和交互原型已经写好，在 `docs/design/` 目录下：
- `docs/design/README.md` — 完整设计规范（设计令牌、组件定义、页面布局、API 映射）
- `docs/design/01-design-system.jsx` — 视觉设计系统原型（色彩、字体、组件库）
- `docs/design/02-command-center.jsx` — 指挥中心首页原型
- `docs/design/03-stock-profile.jsx` — 个股档案页原型（5 Tab）
- `docs/design/04-portfolio.jsx` — 持仓管理看板原型
- `docs/design/05-discovery.jsx` — 观察池原型
- `docs/design/06-review.jsx` — 复盘仪表盘原型
- `docs/design/07-settings.jsx` — 设置页原型（任务/参数/系统状态）
- `docs/frontend-redesign-proposal.md` — 技术选型和架构方案

**请先仔细阅读 `docs/design/README.md` 和 `docs/frontend-redesign-proposal.md`，理解设计意图后再动手。**

## 现有后端 API

后端是 FastAPI，开发栈中默认运行在 `http://127.0.0.1:8001`，Next 前端默认运行在 `http://127.0.0.1:8000` 并通过 rewrites 代理 API。关键端点：

| 端点 | 用途 |
|------|------|
| `GET /api/today` | 指挥中心数据（hero、action_queue、radar、risk_alerts、sources） |
| `GET /api/overview` | 系统总览（健康、任务、运行历史） |
| `GET /api/watchlist` | 持仓列表（分组：优先处理/跟踪增强/继续观察） |
| `GET /api/watchlist/{code}` | 单股持仓详情 |
| `GET /api/opportunities` | 观察池候选列表 |
| `GET /api/opportunities/{code}` | 单股候选详情 |
| `GET /api/review` | 复盘数据（环境仪表、校准规则、对比） |
| `GET /api/ask?q={query}` | 单股分析 |
| `GET /api/ask/suggest?q={query}` | 搜索联想 |
| `POST /api/ask/followup` | 追问对话 |
| `POST /api/today/actions/decision` | 更新 Action Queue 勾选状态 |
| `GET /api/parameters` | 获取参数配置 |
| `POST /api/parameters` | 保存参数配置 |
| `POST /api/tasks/{name}/run` | 启动后台任务 |
| `GET /api/runs` | 任务运行列表 |
| `GET /api/refresh/status?page={page}` | 数据新鲜度 |
| `POST /api/refresh/trigger` | 触发刷新 |
| `GET /healthz` | 健康检查 |

## 你的任务

在 `apps/web/` 目录下创建全新的 Next.js 前端项目，实现 Phase 0（脚手架）和 Phase 1（核心骨架 + 指挥中心首页）。

### Phase 0: 项目脚手架

1. 初始化 Next.js 15 项目（App Router，TypeScript）
2. 安装并配置依赖：
   - `tailwindcss` v4 + `@tailwindcss/postcss`
   - `@tanstack/react-query` — API 数据管理
   - `cmdk` — Command Bar (⌘K)
   - `framer-motion` — 动画
   - `lucide-react` — 图标
   - `clsx` + `tailwind-merge` — 样式工具
3. 配置 `next.config.ts`：
   - 开发环境代理 `/api/*` 到 `PRISM_BACKEND_ORIGIN`，默认 `http://127.0.0.1:8001`
4. 创建设计令牌：
   - 在 `src/styles/globals.css` 中定义 CSS 变量，对应 `docs/design/README.md` 中的设计令牌
   - 背景层级：`--bg-primary: #0a0a0b`, `--bg-secondary: #111113`, `--bg-tertiary: #18181b`, `--bg-elevated: #1c1c1f`
   - 边框：`--border-subtle: rgba(255,255,255,0.06)`, `--border-default: rgba(255,255,255,0.1)`, `--border-strong: rgba(255,255,255,0.16)`
   - 文字：`--text-primary: #f4f4f5`, `--text-secondary: #a1a1aa`, `--text-tertiary: #71717a`
   - 语义色：`--positive: #22c55e`, `--negative: #ef4444`, `--warning: #f59e0b`, `--info: #3b82f6`
   - 交易色调：`--tone-buy: #22c55e`, `--tone-sell: #ef4444`, `--tone-watch: #f59e0b`, `--tone-hold: #3b82f6`, `--tone-avoid: #71717a`
5. 创建 TypeScript 类型定义 `src/lib/types.ts`：
   - 从后端 API 响应结构推导类型（参考 `apps/control-panel/dashboard_data.py` 中的 `build_today_view` 等函数）
6. 创建 API client `src/lib/api.ts`：
   - 封装 fetch，统一错误处理
   - 为每个 API 端点创建函数
7. 创建 TanStack Query hooks `src/lib/hooks.ts`：
   - `useTodayData()` — 获取指挥中心数据
   - `useOverview()` — 获取系统总览
   - `useWatchlist()` — 获取持仓列表
   - `useOpportunities()` — 获取观察池
   - `useReview()` — 获取复盘数据
   - 配置合理的 staleTime 和 refetchInterval

### Phase 1: 全局 Layout + 指挥中心

1. **全局 Layout** (`src/app/layout.tsx`):
   - 暗色背景 `#0a0a0b`
   - 字体：SF Pro Text / PingFang SC
   - TanStack Query Provider

2. **侧边栏** (`src/components/sidebar.tsx`):
   - 固定宽度 220px，sticky
   - 顶部品牌：「棱镜 · 交易决策台」
   - 搜索框（点击触发 ⌘K Command Bar）
   - 导航项：⌂ 指挥中心 / ◫ 持仓管理 / ◎ 观察池 / ◈ 复盘
   - 底部：⚙ 设置 + 系统状态指示灯
   - 参考 `docs/design/02-command-center.jsx` 中的 `Sidebar` 组件

3. **Command Bar** (`src/components/command-bar.tsx`):
   - 基于 `cmdk` 库
   - ⌘K 快捷键触发
   - 支持：股票搜索（调用 `/api/ask/suggest`）、页面跳转
   - 浮层形式，ESC 关闭

4. **指挥中心首页** (`src/app/page.tsx`):
   - 数据来源：`useTodayData()` hook
   - 布局严格参考 `docs/design/02-command-center.jsx`：
     - **Hero 区域**：日期 + 阀门状态 Badge + 今日主线标题（32px 粗体）+ 描述 + 约束标签（药丸形）
     - **Radar Cards**：4 张指标卡（持仓优先/观察候选/午盘新增/质检就绪），grid 4 列
     - **Action Queue**：可勾选的待办列表，每行有：勾选框 + 色条（交易动作色调）+ 股票名/代码 + 动作描述 + 优先级 Badge + 箭头跳转
     - **Risk Alerts**：红/黄警告条
     - **Quick Links + Data Sources**：两列 grid，快速跳转 + 数据源新鲜度指示灯

5. **共享组件**：
   - `Badge` — 药丸形徽章，接受 color prop
   - `MetricCard` — 三行指标卡（标签/数值/说明）
   - `ActionRow` — Action Queue 行项
   - `RiskAlert` — 风险提醒条
   - `SourceCard` — 数据源状态卡
   - 所有组件的视觉细节参考 `docs/design/01-design-system.jsx`

## 视觉规范（关键）

- 暗色优先，背景 4 层灰阶递进
- 无渐变、无阴影，用边框和间距建立结构
- 圆角：sm=6px, md=8px, lg=12px, xl=16px
- 字体：正文 SF Pro Text / PingFang SC，数据 SF Mono / Fira Code，标题 SF Pro Display
- Badge：border-radius 9999px，背景色为语义色 10% 透明度，边框 20% 透明度
- 语义色贯穿全局：绿=正面/上涨，红=负面/下跌，黄=警告/观察，蓝=信息/持有
- 交易动作色调：buy=绿, sell=红, watch=黄, hold=蓝, avoid=灰

## 目录结构

```
apps/web/
├── package.json
├── next.config.ts
├── postcss.config.mjs
├── tsconfig.json
├── src/
│   ├── app/
│   │   ├── layout.tsx              # 全局 Layout + QueryProvider
│   │   ├── page.tsx                # 指挥中心首页
│   │   ├── portfolio/page.tsx      # 占位（Phase 2）
│   │   ├── discovery/page.tsx      # 占位（Phase 2）
│   │   ├── review/page.tsx         # 占位（Phase 2）
│   │   ├── settings/page.tsx       # 占位（Phase 2）
│   │   └── stock/[code]/page.tsx   # 占位（Phase 2）
│   ├── components/
│   │   ├── sidebar.tsx
│   │   ├── command-bar.tsx
│   │   ├── badge.tsx
│   │   ├── metric-card.tsx
│   │   ├── action-row.tsx
│   │   ├── risk-alert.tsx
│   │   └── source-card.tsx
│   ├── lib/
│   │   ├── api.ts                  # API client
│   │   ├── types.ts                # TypeScript 类型
│   │   └── hooks.ts                # TanStack Query hooks
│   └── styles/
│       └── globals.css             # Tailwind + CSS 变量
└── public/
```

## 注意事项

1. **后端定位**：`apps/control-panel/` 是 API 后端，不再承载旧前端页面
2. **不要修改 `docs/` 下的设计文件**：这些是设计规范，只读参考
3. **页面状态**：Portfolio、Discovery、Review、Settings、Stock Profile 已进入 Next 前端
4. **API 代理**：开发时 Next.js 默认跑在 8000 端口，通过 rewrites 代理 `/api/*` 到 FastAPI 的 8001 端口
5. **确保能跑起来**：完成后 `./start_prism.sh` 应该能同时启动前端和后端，访问 `localhost:8000` 能看到指挥中心页面
6. **代码质量**：TypeScript strict mode，组件拆分合理，不要把所有东西写在一个文件里
