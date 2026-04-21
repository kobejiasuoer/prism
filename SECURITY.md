# Security Policy

Prism is a public full-source repository for a real AI-native investment research system. Because the repo publishes real workflow code and scrubbed historical artifacts, security here is closely tied to privacy hygiene.

## Supported Scope

Please report issues involving:

- accidental secret exposure
- incomplete privacy scrub coverage
- personal identifier leakage
- unsafe publication of browser, proxy, or machine-local traces
- vulnerabilities in the public control panel code
- supply-chain or dependency concerns that materially affect the public repo

## Out Of Scope

Please do not use the security channel for:

- general product ideas
- requests for investment advice
- minor documentation typos
- theoretical issues with no plausible impact on this public repository

## How To Report

If you believe you found a security or privacy issue, please report it privately to the repository maintainer instead of opening a public issue with sensitive details.

Use one of these paths:

- GitHub private security advisory or private maintainer contact, if enabled
- direct maintainer contact through the repository profile

When reporting, include:

- a short description of the issue
- the affected file, feature, or workflow
- how the issue could be reproduced or observed
- what kind of data or boundary may be affected
- any suggested mitigation if you already have one

## Please Avoid Public Disclosure First

Do not paste live secrets, tokens, cookies, or private personal identifiers into a public issue.

If the problem is about scrubbed artifacts, point to the artifact type and location without reposting the sensitive value.

## Project-Specific Risk Areas

Areas that deserve extra attention in Prism include:

- `scripts/scrub-secrets.py` coverage gaps
- newly added logs, reports, or snapshots under `data/history/`
- control-panel features that serialize request or environment data
- workflow code that may emit machine-local paths or private endpoints
- sample configuration or `.env` examples that drift toward real values

## Response Principles

The maintainer will try to:

- confirm receipt
- assess whether the report affects public exposure or exploitability
- fix or scrub the problem before broad disclosure when possible
- document the resolution once it is safe to do so

## Safe Contribution Reminder

Before publishing changes, contributors should run:

```bash
pytest -q
python3 scripts/scrub-secrets.py
```

Passing tests do not replace manual judgment. If a change adds a new kind of exported artifact, scrub coverage should be reviewed explicitly.
