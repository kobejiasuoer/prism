# 棱镜 · 前端重设计方案

> 评估日期：2026-04-24 | 分支：codex/ask-v2

---

## 一、现状诊断

### 当前技术栈

| 层 | 技术 | 问题 |
|---|---|---|
| 后端 | FastAPI + Jinja2 SSR | 后端同时承担数据组装和 HTML 渲染，view builder 已膨胀到 8000+ 行 |
| 前端 | 原生 HTML + 6 个独立 JS 文件（共 ~1000 行） | 无组件化，无状态管理，页面间大量重复 DOM 结构 |
| 样式 | 单个 CSS 文件 4600+ 行 | 无设计系统，样式和布局耦合，改一处牵一片 |
| 交互 | 手写 fetch + DOM 操作 | 无 loading 状态、无 optimistic update、无路由过渡 |

### 核心体验问题

1. **信息架构扁平**：7 个顶级页面平铺在导航栏，用户不知道"今天该先看哪里"
2. **页面之间割裂**：同一只股票在 today / watchlist / opportunities / ask 四个入口有四种展示，没有统一的股票 profile
3. **交互是 2010 年水平**：全页刷新、无骨架屏、无动画过渡、表单提交后整页重载
4. **数据密度失控**：每个页面都试图把所有信息一次性铺完，没有渐进式披露
5. **移动端不可用**：纯桌面布局，手机上完全无法操作

### 后端 API 评估

好消息是：后端已经有完整的 JSON API 层，每个页面路由都有对应的 `/api/*` 端点。这意味着前后端分离的改造成本很低，不需要重写后端。

**现有 API 清单（25 个端点）：**

| 分类 | 端点 | 用途 |
|---|---|---|
| 总览 | `GET /api/overview` | 系统健康、任务、运行历史 |
| 今日 | `GET /api/today` | 当日决策全景 |
| 今日 | `POST /api/today/actions/decision` | 更新动作决策状态 |
| 问股 | `GET /api/ask?q=` | 单股分析 |
| 问股 | `GET /api/ask/suggest?q=` | 搜索联想 |
| 问股 | `POST /api/ask/followup` | 追问对话 |
| 持仓 | `GET /api/watchlist` | 持仓全景 |
| 持仓 | `GET /api/watchlist/{code}` | 单股持仓详情 |
| 持仓管理 | `POST /api/watchlist/manage/add\|archive\|restore` | 增删改 |
| 观察池 | `GET /api/opportunities` | 候选全景 |
| 观察池 | `GET /api/opportunities/{code}` | 单股候选详情 |
| 观察池 | `GET /api/opportunities/batch/{kind}` | 批次详情 |
| 复盘 | `GET /api/review` | 历史优势分析 |
| 复盘 | `GET /api/review/detail` | 分组明细 |
| 参数 | `GET /api/parameters` | 参数配置 |
| 参数 | `POST /api/parameters` | 保存参数 |
| 刷新 | `GET /api/refresh/status?page=` | 数据新鲜度 |
| 刷新 | `POST /api/refresh/trigger` | 触发后台刷新 |
| 任务 | `GET /api/runs` | 运行列表 |
| 任务 | `POST /api/tasks/{name}/run` | 启动任务 |
| 任务 | `GET /api/runs/{id}` | 运行详情 |
| 任务 | `GET /api/runs/{id}/log` | 运行日志 |
| 预览 | `GET /api/preview?path=` | 文件预览 |
| 文件 | `GET /artifacts?path=` | 原始文件下载 |
| 健康 | `GET /healthz` | 健康检查 |

---

## 二、重设计目标

### 设计原则

1. **一屏一决策**：每个视图只回答一个问题，不堆砌
2. **股票为中心**：不管从哪个入口进来，同一只股票有统一的 profile 页
3. **渐进式披露**：先给结论，点开看原因，再点开看证据
4. **实时感**：数据轮询、骨架屏、过渡动画，让用户感知系统是活的
5. **移动优先**：手机上能完成 80% 的日常操作

### 视觉方向

不再追求"极简高级感"这种模糊的方向。具体参考：

- **Linear**（任务管理）：信息密度高但不乱，暗色主题，键盘优先
- **Raycast**（效率工具）：Command-K 搜索范式，快速跳转
- **Bloomberg Terminal 的现代化版本**：金融数据的专业感，但用现代 UI 语言表达

色彩策略：暗色为主（交易软件用户习惯），用色彩编码替代文字标签（涨绿跌红、风险橙、安全蓝）。

---

## 三、信息架构重设计

### 现有结构（扁平）

```
导航：今日 | 问股 | 持仓 | 观察池 | 复盘 | 参数 | 控制台
```

### 新结构（分层）

```
Command Bar (⌘K 全局搜索/跳转)
│
├── 🏠 Command Center（首页/今日）
│   ├── Hero: 今日一句话结论 + 市场状态
│   ├── Action Queue: 今天要处理的事（可勾选完成）
│   ├── Radar: 4 张关键指标卡
│   └── Quick Links: 跳转到持仓/观察池/复盘
│
├── 📊 Stock Profile（统一股票页，替代 4 个分散入口）
│   ├── Header: 股票名 + 代码 + 实时状态 badge
│   ├── Decision Tab: 当前结论 + 动作计划
│   ├── Holdings Tab: 持仓视角（仓位、止损、触发）
│   ├── Discovery Tab: 观察池视角（筛选分、一致性、资金）
│   ├── History Tab: 历史变化回放
│   └── Chat Tab: 追问对话（原 ask followup）
│
├── 📋 Portfolio（持仓管理）
│   ├── Priority / Follow / Observe 三栏看板
│   ├── 拖拽调整优先级
│   └── 快速添加/归档
│
├── 🔭 Discovery（观察池）
│   ├── Pipeline 视图：候选 → 观察 → 确认 → 入选
│   ├── Theme Radar: 主线热力图
│   └── Batch Detail: 早盘/午盘批次
│
├── 📈 Review（复盘）
│   ├── 环境仪表盘：弱/试错/进攻三档
│   ├── 变化时间线
│   └── 研究对比面板
│
└── ⚙️ Settings（参数 + 控制台合并）
    ├── Parameters: JSON 编辑器（Monaco Editor）
    ├── Tasks: 任务运行器
    └── System: 健康状态 + 运行日志
```

### 关键变化

1. **问股页消失**：搜索功能上升为全局 Command Bar，搜索结果直接打开 Stock Profile
2. **4 个股票入口合并**：`/stock/{code}` 一个页面，tab 切换不同视角
3. **参数和控制台合并**：都是运维类功能，放在 Settings 下
4. **Action Queue 成为核心**：首页不再是信息展示板，而是待办清单

---

## 四、技术选型

### 推荐方案：Next.js (App Router) + shadcn/ui

| 维度 | 选择 | 理由 |
|---|---|---|
| 框架 | Next.js 15 (App Router) | SSR/SSG 灵活切换，API route 可做 BFF 代理 |
| UI 库 | shadcn/ui + Tailwind CSS 4 | 组件质量高、可定制、不引入运行时依赖 |
| 状态 | TanStack Query (React Query) | 专为 API 数据缓存设计，自带轮询、乐观更新、骨架屏 |
| 图表 | Recharts 或 Lightweight Charts | 金融数据可视化 |
| 编辑器 | Monaco Editor (参数页) | VS Code 同款，JSON 编辑体验好 |
| 搜索 | cmdk (Command Menu) | Linear/Raycast 风格的 ⌘K 搜索 |
| 动画 | Framer Motion | 页面过渡、列表动画 |
| 类型 | TypeScript | 后端 API 返回结构复杂，类型安全是刚需 |

### 为什么不选其他方案

| 方案 | 不选的原因 |
|---|---|
| 继续 Jinja2 + 原生 JS | 已经证明天花板太低，无法实现目标体验 |
| Vue / Nuxt | 生态和组件库不如 React 丰富，shadcn/ui 没有官方 Vue 版 |
| Svelte / SvelteKit | 生态较小，金融类组件库少 |
| 纯 Vite + React SPA | 没有 SSR，首屏加载慢，SEO 不重要但 SSR 对性能有帮助 |

### 架构图

```
┌─────────────────────────────────────────────┐
│                  Browser                     │
│  Next.js App (React + TanStack Query)       │
│  ┌─────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ Command  │ │  Stock   │ │  Portfolio   │ │
│  │ Center   │ │ Profile  │ │  Discovery   │ │
│  │          │ │          │ │  Review      │ │
│  │          │ │          │ │  Settings    │ │
│  └────┬─────┘ └────┬─────┘ └──────┬───────┘ │
│       └─────────────┼──────────────┘         │
│                     │                        │
│              TanStack Query                  │
│              (缓存 + 轮询)                    │
└─────────────────────┬───────────────────────┘
                      │ fetch
┌─────────────────────┴───────────────────────┐
│           FastAPI Backend (不改)              │
│                                              │
│  /api/today  /api/ask  /api/watchlist  ...  │
│                                              │
│  dashboard_data.py (8000+ 行 view builder)  │
└──────────────────────────────────────────────┘
```

后端完全不动。Next.js 直接调用现有的 `/api/*` 端点。

---

## 五、页面设计拆解

### 5.1 Command Center（首页）

**回答的问题**：今天该做什么？

```
┌──────────────────────────────────────────────────┐
│ ⌘K 搜索股票/跳转页面                    🌙 ⚙️    │
├──────────────────────────────────────────────────┤
│                                                  │
│  今天先处理旧仓，再决定是否看新仓                    │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                │
│  阀门：允许轻仓试错 · 仓位上限 2 只 · 主线：AI+机器人 │
│                                                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐ │
│  │ 持仓优先 │ │ 观察候选 │ │ 午盘新增 │ │ 质检   │ │
│  │    3    │ │    5    │ │    2    │ │  3/3   │ │
│  └─────────┘ └─────────┘ └─────────┘ └────────┘ │
│                                                  │
│  ── 今日待办 ──────────────────────────────────── │
│  ☐ 宁德时代 300750  减仓至半仓    优先处理  →      │
│  ☐ 比亚迪 002594    止损观察      优先处理  →      │
│  ☐ 中际旭创 300308  轻仓试错      等触发    →      │
│  ☑ 寒武纪 688256    继续持有      已处理           │
│                                                  │
│  ── 风险提醒 ──────────────────────────────────── │
│  ⚠ 弱环境 AI 5日净仍为负，控制新仓节奏              │
│  ⚠ 自选股快照 2 小时前更新，建议刷新                 │
│                                                  │
│  ── 数据源 ─────────────────── 🔄 刷新 (3分钟前) │
│  自选股 09:32 · 观察池 09:15 · 午盘 13:45 · 总控 09:40│
└──────────────────────────────────────────────────┘
```

### 5.2 Stock Profile（统一股票页）

**回答的问题**：这只股票现在该怎么处理？

```
┌──────────────────────────────────────────────────┐
│ ← 返回  宁德时代 300750           减仓至半仓 🔴   │
├──────────────────────────────────────────────────┤
│ [决策] [持仓] [观察池] [追问] [历史]              │
├──────────────────────────────────────────────────┤
│                                                  │
│  主结论：减仓至半仓，跌破 185 全部止损              │
│                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │ 仓位建议  │ │ 止损位   │ │ 下一步    │         │
│  │ 半仓      │ │ ¥185.00 │ │ 等反弹减仓 │         │
│  └──────────┘ └──────────┘ └──────────┘         │
│                                                  │
│  为什么？                                         │
│  技术面偏弱 · 资金 5 日净流出 · 事件面中性           │
│                                                  │
│  ── 动作循环 ──                                   │
│  现在做 → 等反弹到 192 附近减仓                     │
│  触发时 → 跌破 185 全部止损                        │
│  不要做 → 不要在当前位置补仓                        │
│                                                  │
│  ── 追问 ──                                      │
│  💬 输入你的问题...                                │
│                                                  │
└──────────────────────────────────────────────────┘
```

### 5.3 Portfolio（持仓看板）

**回答的问题**：我的持仓现在整体什么状态？

三栏看板布局（类似 Trello/Linear），优先处理 | 跟踪增强 | 继续观察，每张卡片可点击进入 Stock Profile。

### 5.4 Discovery（观察池）

**回答的问题**：有什么新的值得关注的股票？

Pipeline 视图，从左到右：全市场扫描 → 早盘候选 → 午盘确认 → 可执行。顶部是主线热力图。

### 5.5 Review（复盘仪表盘）

**回答的问题**：我的策略历史表现如何？

三个环境仪表盘（弱/试错/进攻），变化时间线，研究对比面板。

### 5.6 Settings（设置）

参数编辑器（Monaco Editor）+ 任务运行器 + 系统健康。

---

## 六、实施计划

### Phase 0：脚手架（1-2 天）

- 初始化 Next.js 项目（`apps/web/`）
- 配置 Tailwind CSS 4 + shadcn/ui
- 配置 TanStack Query + API client
- 定义 TypeScript 类型（从现有 API 响应推导）
- 配置开发代理（Next.js dev server → FastAPI）

### Phase 1：核心骨架（2-3 天）

- 全局 Layout：侧边导航 + Command Bar (⌘K)
- Command Center 首页：Hero + Radar Cards + Action Queue
- 数据轮询 + 骨架屏 + 刷新机制
- 暗色主题基础

### Phase 2：Stock Profile（2-3 天）

- 统一股票页 `/stock/{code}`
- Decision / Holdings / Discovery / Chat tabs
- 整合现有 4 个详情页的数据源
- 追问对话（复用 `/api/ask/followup`）

### Phase 3：列表页（2-3 天）

- Portfolio 看板（三栏拖拽）
- Discovery Pipeline 视图
- 持仓管理（添加/归档/恢复）

### Phase 4：复盘 + 设置（1-2 天）

- Review 仪表盘
- Settings：Monaco Editor 参数编辑 + 任务运行器

### Phase 5：打磨（1-2 天）

- 页面过渡动画
- 移动端适配
- 错误处理 + 空状态
- 性能优化（代码分割、图片优化）

**总计预估：9-15 天**

### 目录结构

```
apps/
├── control-panel/          # 现有后端（保留不动）
│   ├── app.py
│   ├── dashboard_data.py   # 原封不动，继续提供 /api/*
│   ├── templates/          # 旧模板，保留作为回退
│   └── static/             # 旧静态资源
│
└── web/                    # 新前端
    ├── package.json
    ├── next.config.ts
    ├── tailwind.config.ts
    ├── tsconfig.json
    ├── src/
    │   ├── app/
    │   │   ├── layout.tsx          # 全局 Layout
    │   │   ├── page.tsx            # Command Center
    │   │   ├── stock/[code]/
    │   │   │   └── page.tsx        # Stock Profile
    │   │   ├── portfolio/
    │   │   │   └── page.tsx        # 持仓看板
    │   │   ├── discovery/
    │   │   │   └── page.tsx        # 观察池
    │   │   ├── review/
    │   │   │   └── page.tsx        # 复盘
    │   │   └── settings/
    │   │       └── page.tsx        # 设置
    │   ├── components/
    │   │   ├── ui/                 # shadcn/ui 组件
    │   │   ├── command-bar.tsx     # ⌘K 搜索
    │   │   ├── action-queue.tsx    # 待办队列
    │   │   ├── stock-card.tsx      # 股票卡片
    │   │   ├── radar-card.tsx      # 指标卡
    │   │   ├── decision-panel.tsx  # 决策面板
    │   │   ├── pipeline-view.tsx   # Pipeline 视图
    │   │   └── ...
    │   ├── lib/
    │   │   ├── api.ts              # API client
    │   │   ├── types.ts            # TypeScript 类型
    │   │   └── hooks.ts            # 自定义 hooks
    │   └── styles/
    │       └── globals.css         # Tailwind 入口
    └── public/
```

---

## 七、风险与决策点

### 需要你确认的决策

1. **暗色 vs 亮色**：我倾向暗色为主（交易软件习惯），但支持切换。你的偏好？
2. **是否保留旧前端**：建议保留旧的 Jinja2 模板作为回退，新前端跑在不同端口。还是直接替换？
3. **移动端优先级**：是先做好桌面再适配移动，还是从一开始就 mobile-first？
4. **问股合并确认**：把"问股"从独立页面变成全局搜索 + Stock Profile，你觉得可以吗？
5. **实施节奏**：是一次性全部做完再上线，还是按 Phase 逐步替换？

### 技术风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 后端 API 返回结构不稳定 | 前端类型定义频繁变动 | 用 zod 做运行时校验，类型从 API 响应自动推导 |
| dashboard_data.py 太重 | 某些 API 响应慢 | TanStack Query 缓存 + 骨架屏，用户感知不到 |
| 新旧前端并行维护 | 开发成本翻倍 | Phase 完成后尽快切换，不长期并行 |
| Next.js 学习曲线 | 如果你不熟悉 React | 我来写核心代码，你只需要调整数据和业务逻辑 |

---

## 八、总结

这不是一次 CSS 换肤，而是从信息架构、交互范式、技术栈三个层面的重建。核心思路：

- **后端不动**：现有 25 个 API 端点已经足够，直接复用
- **前端推倒重来**：Next.js + React + shadcn/ui，现代化技术栈
- **信息架构重组**：从"7 个平铺页面"变成"以股票为中心 + 待办驱动"
- **体验飞升**：骨架屏、过渡动画、Command Bar、实时轮询、移动端支持

等你确认方向和上面的决策点，我就开始动手。
