# Prism

Chinese version: [README.zh-CN.md](README.zh-CN.md)


Prism is a full-source AI-native investment research system.

This repository publishes the real control panel, real workflow logic, real prompts, real thresholds, and real historical outputs of the Prism system.

It excludes only secrets, login state, proxy credentials, and privacy-sensitive traces.

## Scope

This repository contains the real Prism system, including:

- the control-panel frontend
- screening and review workflows
- report generation logic
- prompts, thresholds, and real decision rules
- historical outputs after secret/privacy scrub

## Layout

- `apps/control-panel/`: FastAPI + Jinja control panel
- `packages/screener/`: real screening and review workflows
- `data/history/`: scrubbed historical artifacts and operating outputs
- `scripts/scrub-secrets.py`: mechanical privacy scrub helper

## Verification

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install pytest
pytest -q
python3 scripts/scrub-secrets.py
```
