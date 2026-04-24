# Prism

English version: [README.md](README.md)

Prism 是一个完整开源的 AI Native 投研系统。

这个仓库公开 Prism 的真实控制台页面、真实工作流逻辑、真实 prompt、真实参数和真实历史运行产物。

它只排除密钥、登录态、代理凭证和隐私敏感痕迹。

## 为什么要有这个仓库

很多开源投研仓库只公开 demo，或者只公开零散脚本。Prism 的目标不一样，它公开的是一个 AI Native 投研系统的真实运行形态。

这个仓库想回答的不是“某个脚本怎么写”，而是：

- 控制台如何触发工作流
- 筛选器如何逐步收敛候选股票
- AI 二筛和午盘确认如何进一步约束判断
- 报告和运行产物如何生成
- 历史产物如何在脱敏后保留下来

## 这里公开了什么

这个仓库公开的是 Prism 的真实公共版本，包括：

- 基于 FastAPI + Jinja 的控制台前端
- 已落地的 `Today v2` 与 `Ask v2` 决策型页面
- 真实的选股与复核工作流脚本
- 真实使用中的 prompt、阈值和判断规则
- 股票分析验收评估基准、评分产物和一键启动脚本
- 报告生成逻辑与消息格式化逻辑
- 脱敏后的历史运行产物、日志、简报和快照

## 这里没有公开什么

Prism 选择完整开源，但不会泄露秘密。

这个仓库**不会**公开：

- API key、token、cookie、webhook
- 登录态和浏览器会话痕迹
- 代理凭证和私有接口地址
- 个人接收人标识
- 脱敏前的本机绝对路径

## 仓库结构

```text
prism/
├── apps/control-panel/        # FastAPI + Jinja 控制台
├── packages/screener/         # 真实选股 / 复核工作流
├── data/history/              # 脱敏后的历史运行产物
├── docs/architecture/         # 系统结构说明
├── scripts/scrub-secrets.py   # 机械化脱敏脚本
├── tests/                     # 仓库级验证
└── README.md                  # 英文 README
```

几个重要目录：

- `apps/control-panel/`：操作台、模板、静态资源和测试
- `packages/screener/`：扫描、AI 二筛、午盘确认、候选生命周期、消息生成
- `data/history/`：真实归档产物，包括 `ai_history/`、`quality_gates/`、`cron_logs/`、`reports/`、`command_brief/`、`daily_snapshots/`
- `docs/architecture/system.md`：更完整的公开仓架构说明

## 系统流程图

```mermaid
flowchart LR
    CP[控制台
FastAPI + Jinja] --> SC[scan.py
候选池生成]
    SC --> AI[ai_screening.py
Shortlist 与判断上下文]
    AI --> MV[midday_verify.py
午盘二次确认]
    MV --> LC[candidate_lifecycle.py
进入 / 升级 / 退出]
    LC --> RP[报告与消息
generate_feishu_message.py]
    RP --> HS[data/history
脱敏后的历史产物]
```

这张图展示的是公开版 Prism 的主运行链路，强调的是从触发工作流到生成判断、报告以及脱敏归档的核心路径。

如果你想顺着这条主链路继续看模块边界和数据边界，可以直接看 [docs/architecture/system.md](docs/architecture/system.md)。

## 当前产品页面

当前公开分支已经包含这些面向操作员的页面和能力：

- `Today v2`，路径是 `/today`：一个结论优先的日内指挥台，首屏固定按“今日指令、优先动作、环境雷达、持仓动作、机会动作、证据入口”的顺序组织信息。
- `Ask v2`，路径是 `/ask`：一个单票结论页，先直接回答这只股票现在该 `买 / 持有 / 卖 / 观察`，再给出边界三联、执行层、系统关系和继续追问。
- `Watchlist` 及详情页：把今日总览和单票判断接回持仓管理、自选股操作和原始证据入口。
- `股票分析验收基准`：一套可复现的内部评估层，可以给 Prism 当前股票分析能力打分，并执行 `professional_usable` 或 `product_ready` 的门槛检查。

## 典型工作流

可以把 Prism 的运行主链路理解成这样：

1. 控制台或 shell 脚本触发一个工作流。
2. `scan.py` 生成候选股票池。
3. `ai_screening.py` 进一步压缩成 shortlist，并附带判断上下文。
4. `midday_verify.py` 在午盘重新验证晨间结论。
5. `candidate_lifecycle.py` 跟踪进入、升级、降级和退出。
6. `generate_feishu_message.py` 负责把结果整理成操作报告。
7. 产物和日志在脱敏后保留到 `data/history/`。

## 快速开始

先创建虚拟环境，并安装控制台依赖和测试工具：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r apps/control-panel/requirements.txt
python -m pip install pytest
```

运行测试：

```bash
pytest -q
```

运行脱敏检查：

```bash
python3 scripts/scrub-secrets.py
```

如果你想本地看控制台，可以直接一键启动：

```bash
./start_prism.sh
```

默认地址是 `http://127.0.0.1:8000`。

几个常用页面：

- `http://127.0.0.1:8000/today`：Today v2 日内总览
- `http://127.0.0.1:8000/ask`：Ask v2 单票问答页
- `http://127.0.0.1:8000/watchlist`：持仓与自选股管理页

### Windows 启动方式

Windows 下建议使用 PowerShell，直接通过 `uvicorn` 启动 FastAPI 应用：

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r apps/control-panel/requirements.txt
python -m pip install pytest
python -m uvicorn control_panel.app:app --host 127.0.0.1 --port 8000
```

如果 PowerShell 阻止虚拟环境激活，可以只对当前窗口放开脚本执行权限：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

如果本机没有 `py -3.14`，请先安装 Python 3.14 或更新版本。Python 3.8 可以作为本地预览的临时兜底方案，但不是项目声明的正式运行版本；此时需要额外安装类型标注兼容包：

```powershell
python -m pip install eval_type_backport
python -m uvicorn control_panel.app:app --host 127.0.0.1 --port 8000
```

启动后可以用下面的命令确认服务健康：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/healthz
```

服务启动成功后，直接在浏览器里打开前端页面：

```text
http://127.0.0.1:8000
```

常用前端页面：

- `http://127.0.0.1:8000/today`：今日作战页
- `http://127.0.0.1:8000/ask`：问股页
- `http://127.0.0.1:8000/watchlist`：自选股页
- `http://127.0.0.1:8000/opportunities`：机会页
- `http://127.0.0.1:8000/review`：复盘页

也可以在 PowerShell 里直接打开浏览器：

```powershell
Start-Process http://127.0.0.1:8000/today
```

如果 `8000` 端口已被占用，把启动命令里的 `--port 8000` 改成 `--port 8001` 即可。

`start_prism.sh` 这类 shell 启动脚本需要 Bash、WSL 或 Git Bash。纯 PowerShell 环境下，直接使用上面的 `uvicorn` 命令即可。

如果你想刷新股票分析验收报告，可以直接用一键脚本：

```bash
./start_stock_evaluation.sh
./start_stock_evaluation.sh professional
./start_stock_evaluation.sh product
```

三种模式分别是：

- `baseline`：只刷新最新评估报告
- `professional`：要求至少达到 `professional_usable`，并在硬门槛失败时直接报错
- `product`：要求达到 `product_ready`，并在硬门槛失败时直接报错

## 数据与脱敏模型

这个仓库包含的不是示例数据，而是真实运行后的历史产物。这是 Prism 开源边界的一部分，而不是附赠演示素材。

当前公开的历史桶包括：

- `data/history/ai_history/`：AI 二筛归档快照
- `data/history/quality_gates/`：质量闸门和校验结果
- `data/history/cron_logs/`：工作流执行日志
- `data/history/stale_outputs/`：被新产物替换但保留审计价值的旧结果
- `data/history/reports/`：生成出来的 Markdown / 文本报告
- `data/history/command_brief/`：控制台决策简报 JSON
- `data/history/control_panel_runs/`：控制台任务运行元数据与日志
- `data/history/daily_snapshots/`：决策所引用的自选股快照输入

在公开前，仓库会通过 `scripts/scrub-secrets.py` 做机械化脱敏，主要处理：

- 本机路径
- 代理地址
- 用户接收人标识
- 需要人工复查的敏感标记

## 当前验证状态

公共仓当前使用下面两条命令做验证：

```bash
pytest -q
python3 scripts/scrub-secrets.py
./start_stock_evaluation.sh professional
```

最近一次公开迁移发布前，这两项验证都已通过。

## 架构说明

Prism 当前采用 monorepo 结构，把真实控制台、真实工作流和历史产物放在同一个公开代码库里，方便一次性理解系统全貌。

如果你想看更正式一点的架构说明，包括模块边界、运行链路和公开数据模型，可以直接看 [docs/architecture/system.md](docs/architecture/system.md)。

## 当前阶段

这个仓库对应的是 Prism 的第一个完整公开版本。

当前重点是：

- 交付命令优先的 `Today v2` 和结论优先的 `Ask v2`
- 给 UI 和评估流程都补上一键启动入口
- 把股票分析改造纳入带层级门槛的验收流程
- 公开真实系统，而不是保留一个演示壳子
- 保留工作流透明度
- 让脱敏过程尽量机械化、可复查
- 先把仓库公开完整，再逐步做后续模块化整理

## 参与与安全

如果你想参与这个仓库，先看 [CONTRIBUTING.md](CONTRIBUTING.md)。

如果你发现的是安全或隐私问题，请按 [SECURITY.md](SECURITY.md) 的方式私下报告，不要先把敏感细节公开发到 issue。

## License

Prism 使用 [LICENSE](LICENSE) 中提供的许可证。
