# 静默异常可见化 设计文档

- 日期：2026-06-20
- 范围：4 个后端文件里 16 个"静默 except Exception"handler（pass/return None/{} / continue，无任何日志）
- 上游依据：`docs/system-audit-2026-06-19.md`（问题 13：普遍吞异常，多数吞成 pass/return None）

## 问题
后端有 89 处 `except Exception`，其中 16 处是完全静默的（handler 只 pass/return None/return {}/return []/continue，无 log/print）。这让数据缺失/解析失败/网络错误完全不可见——调试时无从下手。

**不动其余 73 处**：它们要么已有日志，要么是 `except Exception as exc:` 且后续用了 exc（有迹可循），要么是有意容错（如 tushare_factors 的"缺失数据永不抛错"设计）。只动 16 个完全静默的。

## 目标
给这 16 个静默 handler 加一行 `logger.debug`/`logger.warning`（带文件上下文 + 异常类型），**不改变任何控制流**（仍 pass/return None）。让静默失败变成"DEBUG 日志里可查"。

## 做法
1. 4 个文件各加模块级 `logger = logging.getLogger(__name__)`。
2. 每个 16 个静默 handler 加一行 log（`logger.debug("...", exc_info=True)` 或 `warning`，视严重度）。
3. **不改 return/pass/continue**——只加观测，不改行为。

## 成功标准
- [ ] 4 个文件有 module-level logger。
- [ ] 16 个静默 handler 各加一行 log。
- [ ] `pytest -q` 全绿（行为不变）。
- [ ] grep 确认无新的静默 except（`except Exception` 后 3 行内无 log 且 handler 是 pass/return None 的）。

## 非目标
- 不重构任何容错逻辑。
- 不动 73 个非静默 handler。
- 不改 tushare_factors 的"永不抛错"设计（只是给它加日志）。
