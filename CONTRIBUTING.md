# Contributing to Prism

Thanks for contributing to Prism.

This repository is the public full-source version of a real AI-native investment research system. That means contribution quality matters in two directions at the same time:

- changes should improve clarity, reliability, or maintainability
- changes must not weaken the repository's privacy scrub boundary

## Before You Start

Please read these files first:

- `README.md`
- `README.zh-CN.md` if you prefer Chinese
- `docs/architecture/system.md`
- `SECURITY.md`

## What Kinds Of Contributions Are Welcome

Good contributions include:

- bug fixes in the control panel or workflow code
- documentation improvements
- test improvements
- privacy scrub improvements
- refactors that make module boundaries easier to understand
- repository hygiene improvements that help public readers understand the system

Less useful contributions usually look like:

- large speculative rewrites without a clear problem statement
- changes that remove real workflow detail and turn the repo back into a toy demo
- changes that introduce secrets, personal identifiers, or machine-local traces

## Development Setup

Create a virtual environment and install the current public dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r apps/control-panel/requirements.txt
python -m pip install pytest
```

Run the current verification commands before opening a pull request:

```bash
pytest -q
python3 scripts/scrub-secrets.py
```

## Contribution Workflow

1. Fork the repository and create a focused branch.
2. Keep the scope small enough that the intent is obvious from the diff.
3. Add or update tests when behavior changes.
4. Run the verification commands locally.
5. Open a pull request with a clear summary of what changed and why.

## Pull Request Expectations

A good pull request should explain:

- the problem being solved
- the exact files or modules affected
- whether user-facing behavior changed
- whether privacy scrub behavior changed
- what verification was run

If your change touches the open-source boundary, say that explicitly in the PR description.

## Privacy And Publication Rules

This is the most important project-specific rule.

Do not commit:

- API keys, tokens, cookies, or webhook values
- browser session traces or login state
- proxy credentials or private endpoints
- personal recipient identifiers
- machine-local absolute paths that have not been scrubbed
- raw artifacts that have not passed the repository scrub expectations

If you add new artifact types, log formats, or export files, make sure `scripts/scrub-secrets.py` still covers them.

## Scope Guidance

Prism is intentionally published as a real system, not a reduced demo shell. Please preserve that principle.

Contributions should move the public repo toward one or more of these outcomes:

- clearer architecture
- safer publishing workflow
- more reliable workflow execution
- better operator readability
- easier future modularization

## Documentation Style

Prefer direct writing over marketing language.

Useful documentation usually answers:

- what this component does
- where it sits in the runtime chain
- what inputs and outputs it owns
- what privacy assumptions apply

## Reporting Bugs

If you found a normal bug, open an issue or pull request.

If you found a security, privacy, or data-exposure problem, do not open a public issue first. Follow the process in `SECURITY.md`.
