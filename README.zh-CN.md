# Prism

Prism 是一个完整开源的 AI Native 投研系统。

这个仓库公开 Prism 的真实控制台页面、真实工作流逻辑、真实 prompt、真实参数和真实历史运行产物。

它只排除密钥、登录态、代理凭证和隐私敏感痕迹。

## 范围

这个仓库包含 Prism 的真实系统，包括：

- 控制台前端页面
- 选股与 review 工作流
- 报告生成逻辑
- prompt、阈值和真实判断规则
- 经过 secret/privacy scrub 的历史运行产物

## 目录

- `apps/control-panel/`：基于 FastAPI + Jinja 的控制台
- `packages/screener/`：真实选股与复核工作流
- `data/history/`：脱敏后的历史运行产物与日志
- `scripts/scrub-secrets.py`：机械化隐私清洗脚本

## 验证

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install pytest
pytest -q
python3 scripts/scrub-secrets.py
```
