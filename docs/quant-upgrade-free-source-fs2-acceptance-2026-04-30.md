# Prism Free-Source FS-2 独立验收报告

Date: 2026-04-30
Role: independent acceptance reviewer
Scope: FS-2 provider contract mapping
Status: passed

## 0. 验收边界

本次只读验收检查 FS-2 文件：

- `packages/quant/free_sources/provider_contracts.py`
- `packages/quant/free_sources/canonical_mapping.py`
- `tests/test_quant_free_source_mapping.py`
- `tests/test_quant_free_source_guardrails.py`

并只读核对 FS-1 文件：

- `packages/quant/free_sources/__init__.py`
- `packages/quant/free_sources/manifest.py`
- `packages/quant/free_sources/contracts.py`
- `packages/quant/free_sources/redaction.py`
- `tests/test_quant_free_source_manifest.py`

本次没有修改代码，没有调用 BaoStock / AKShare，没有安装依赖，没有写 `data/quant`，没有写 raw vendor data 或 repo 外 raw archive，没有生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest，也没有接生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。

本报告是本次验收唯一新增产物，位于 `docs/`。

## 1. 总体验收结论

结论：**通过**。

是否允许进入 **FS-3 repo-external live smoke planning**：**允许**。

是否允许直接 FS-3 代码或 live provider call：**不允许**。FS-3 必须先规划、验收，再由单独审批决定是否允许 repo-external live smoke。

FS-2 验收结论：FS-2 已保持 **no-network、synthetic-only、no `data/quant`、no provider imports**。

## 2. 执行验证

按要求运行：

```text
PYTHONPATH=packages .venv/bin/python -m pytest \
  tests/test_quant_free_source_manifest.py \
  tests/test_quant_free_source_mapping.py \
  tests/test_quant_free_source_guardrails.py \
  -q
```

结果：

```text
49 passed in 0.03s
```

精确 `git status --short --untracked-files=all` 检查显示，free-source 相关 git-visible 文件为 FS-1 五个文件和 FS-2 四个文件；未显示 `data/quant`、依赖文件、lockfile 或 venv 变更。测试运行产生/已有的 `__pycache__` 命中 `.gitignore`，不属于可提交 FS-2 产物。

## 3. 十六项重点验收

| # | 检查项 | 结果 | 验收意见 |
| --- | --- | --- | --- |
| 1 | 是否只新增/修改允许的 FS-2 文件；如改 FS-1 是否有说明 | 通过 | FS-2 git-visible 新文件为 `provider_contracts.py`、`canonical_mapping.py` 和两个 FS-2 测试文件。FS-1 文件仍处于此前 FS-1 未跟踪基线；当前 FS-2 未依赖修改 FS-1 文件或导出 FS-2 symbols。 |
| 2 | 是否没有调用 BaoStock / AKShare | 通过 | `provider_contracts.py` 仅含 dataclass metadata；`canonical_mapping.py` 仅查询内存 tuple；无 provider call。 |
| 3 | 是否没有 import `baostock` / `akshare` | 通过 | AST guardrail 测试覆盖 provider imports；源码中仅出现 provider enum / 测试禁用列表字符串。 |
| 4 | 是否没有 import 网络库 | 通过 | 未导入 `requests`、`urllib`、`httpx`、`socket`、`curl_cffi` 等网络库；guardrail 测试覆盖。 |
| 5 | 是否没有安装依赖、修改 lockfile、修改 venv | 通过 | 状态检查未发现 dependency / lockfile / `.venv` / `venv` 变更。 |
| 6 | 是否没有写 `data/quant` | 通过 | 状态检查未发现 `data/quant` 变更；guardrail 测试确认 mapping access 不改动 `data/quant`。 |
| 7 | 是否没有写 raw vendor data 或 repo 外 raw archive | 通过 | FS-2 模块没有 raw archive / raw response / output terms；未创建 repo-external smoke 或 raw writer。 |
| 8 | `provider_contracts.py` 是否只包含 metadata | 通过 | 文件只包含 `ProviderFieldMapping` dataclass、BaoStock / AKShare field mapping tuples、blocked capability set；内容是字段名、endpoint 字符串、canonical candidate、status、notes。 |
| 9 | BaoStock mapping 是否覆盖必要 layer | 通过 | 覆盖 calendar、stock basic、raw daily、qfq candidate、index daily、`tradestatus` / `isST`。 |
| 10 | AKShare mapping 是否覆盖必要 layer | 通过 | 覆盖 raw daily cross-check、qfq candidate cross-check、index daily supplement、suspend event event-only。 |
| 11 | `canonical_mapping.py` 是否只是纯查询 helper | 通过 | 仅提供 `all_provider_mappings`、provider/layer/status 查询和 canonical candidate 查询；不读写文件、不读环境变量、不做 provider call。 |
| 12 | qfq / benchmark / execution fields 是否仍为 candidate / research_only / partial | 通过 | qfq 为 `RESEARCH_ONLY`，index daily 为 `CANDIDATE`，BaoStock `tradestatus` / `isST` 为 `CANDIDATE`，AKShare suspend event 为 `PARTIAL`。 |
| 13 | formal / execution blockers 是否继续 blocked | 通过 | formal adjusted return、formal excess return、formal labels、execution-realistic backtest、limit up/down、failed order、partial fill 仍由 blocked capabilities 覆盖。 |
| 14 | tests 是否 synthetic-only、no-network、不需要 provider 安装 | 通过 | 测试只访问内存 metadata 和 AST；pytest 通过且无 provider dependency。 |
| 15 | 是否没有影响生产排序、A/B/C、页面、Prism Edge、Expected 5D、ML、现有 report 逻辑 | 通过 | FS-2 模块未导入 apps、stock modules、scorer、backtest、label、factor、health、report 或 page modules。 |
| 16 | 是否没有创建 live adapter / runner / report generator | 通过 | `baostock_adapter.py`、`akshare_adapter.py`、`run_field_poc.py`、`report_generator.py` 均不存在。 |

## 4. 保留条件

进入 FS-3 前继续保留：

1. FS-3 只能先做 repo-external live smoke planning，不得直接写 live provider code。
2. 不得直接调用 BaoStock / AKShare。
3. 不得安装 BaoStock / AKShare 或修改依赖文件、lockfile、venv。
4. 不得写 `data/quant`。
5. 不得写 raw vendor data、repo 外 raw archive 或 scratch output，除非 FS-3 planning 和审批明确允许。
6. 不得创建或提交 `baostock_adapter.py`、`akshare_adapter.py`、`run_field_poc.py`、`report_generator.py`。
7. qfq、benchmark、execution fields 仍只能是 candidate / research_only / partial。
8. formal adjusted return、formal excess return、formal labels、execution-realistic backtest、limit up/down、failed order、partial fill 继续 blocked。
9. 生产排序、A/B/C、页面、Prism Edge、Expected 5D、ML 和既有 factor/backtest/health/report 逻辑继续不得触碰。
10. 不得提交 `__pycache__`、`.pytest_cache` 或其他运行产物。

## 5. 下一步建议

建议下一步新增 **FS-3 repo-external live smoke planning** 文档，先明确：

- 是否允许 repo-external venv。
- 是否允许安装 BaoStock / AKShare 到 repo 外 scratch。
- raw archive root、hash、retention、deletion 和 redacted manifest 规则。
- live smoke 的 endpoint、样本、频率、网络错误处理和授权边界。
- 仍然禁止 `data/quant`、production pipeline、formal outputs、页面、Prism Edge、Expected 5D、ML。

FS-3 planning 独立验收和明确审批通过前，不应开始 FS-3 代码或 live provider call。

## 6. 最终裁决

FS-2 验收结论：**通过**。

允许进入：**FS-3 repo-external live smoke planning**。

不允许进入：**直接 FS-3 代码或 live provider call**。

核心判断：FS-2 已按计划实现 synthetic-only provider contract mapping；没有真实 provider、网络、依赖、`data/quant`、raw vendor data、formal output 或生产 / 页面 / ML 影响。
