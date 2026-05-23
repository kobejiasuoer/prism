"""Production-style :class:`PriceProvider` implementations.

The audit layer (``decision_ledger.py``) only owns the
:class:`PriceProvider` Protocol and the conservative classification
logic.  Concrete providers live here so their data-layer dependencies
(cache root, future gateway wiring) do not leak back into the audit
module.

The ``PrismCachePriceProvider`` is intentionally **read-only**: it
never fetches over the network, never writes anything, and never
mutates the underlying cache.  When the cache lacks the data we need,
it raises :class:`PriceProviderUnavailable` so the evaluator skips the
window rather than burying a transient cache miss as a permanent
``data_issue`` outcome.  A future network-backed provider can sit
in front of this one and decide that "the network confirmed there is
no data for this delisted code" is the right time to switch from
``PriceProviderUnavailable`` to an empty list.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from decision_ledger import PriceProviderUnavailable


_PREFIXED_CODE_RE = re.compile(r"^[a-z]{2}(\d{6})$")
_PLAIN_CODE_RE = re.compile(r"^\d{6}$")

# Layout: {data_root}/prism_data/datasets/bars.daily/{YYYY-MM-DD}/{code}.json
BARS_DAILY_DATASET = "bars.daily"


def _default_data_root() -> Path:
    """Resolve the on-disk Prism data root.

    Honors ``PRISM_DATA_ROOT`` so tests can redirect the cache to a
    temp directory.  Falls back to ``<repo_root>/data`` which is where
    the rest of the project writes its dataset artifacts.
    """

    override = os.environ.get("PRISM_DATA_ROOT", "").strip()
    if override:
        return Path(override).expanduser()
    # apps/control-panel/decision_ledger_providers.py -> repo_root is parents[2]
    return Path(__file__).resolve().parents[2] / "data"


def _strip_market_prefix(code: Any) -> str | None:
    """Return the plain 6-digit code or ``None`` for unrecognized input.

    Cache filenames use the plain code (``600690.json``), so callers
    handing us ``sh600690`` need normalization before lookup.  The
    market index ``000300`` (CSI 300) already has no prefix and is
    accepted as-is.
    """

    text = str(code or "").strip().lower()
    if not text:
        return None
    m = _PREFIXED_CODE_RE.fullmatch(text)
    if m:
        return m.group(1)
    if _PLAIN_CODE_RE.fullmatch(text):
        return text
    return None


class PrismCachePriceProvider:
    """Read-only :class:`PriceProvider` backed by the bars.daily cache.

    The cache layout is one directory per fetch date:

    .. code-block:: text

        {data_root}/prism_data/datasets/bars.daily/{cache_date}/{code}.json

    Each ``{code}.json`` is a chronological list of daily bars ending
    on ``cache_date``.  To answer a ``[start_date, end_date]`` query we
    pick the most recent ``cache_date >= end_date`` for which a code
    file exists, parse it, and return the rows whose ``trade_date``
    falls inside the window.

    Failure-mode contract:

    * **Found** -- file present, rows cover the window -> return rows.
    * **Cache stale / never warmed for this code+window** ->
      :class:`PriceProviderUnavailable`.  The next cache refresh might
      add the rows, so we refuse to fabricate a permanent
      ``data_issue``.
    * **Corrupt JSON / wrong root shape** ->
      :class:`PriceProviderUnavailable`.  This is almost certainly an
      operator-recoverable situation; we surface it instead of
      silently returning ``[]``.

    A production provider that wants to assert "data really missing"
    (e.g. a network call that confirmed the upstream knows nothing
    about this code) should compose this one and translate
    :class:`PriceProviderUnavailable` into ``[]`` when its own signal
    says terminal-miss.
    """

    def __init__(self, *, data_root: Path | str | None = None) -> None:
        self.data_root = (
            Path(data_root) if data_root is not None else _default_data_root()
        )

    # -- helpers -----------------------------------------------------------

    def _bars_dir(self) -> Path:
        return self.data_root / "prism_data" / "datasets" / BARS_DAILY_DATASET

    def _candidate_cache_dirs(self, end_date: str) -> list[Path]:
        """Cache directories whose name >= ``end_date``, newest first.

        An older cache directory cannot contain rows for our window
        because the file there ends at ``cache_date`` and the window
        extends beyond it.
        """

        bars_dir = self._bars_dir()
        if not bars_dir.exists():
            return []
        out: list[Path] = []
        for entry in bars_dir.iterdir():
            if not entry.is_dir():
                continue
            if entry.name < end_date:
                continue
            out.append(entry)
        out.sort(key=lambda p: p.name, reverse=True)
        return out

    # -- PriceProvider Protocol --------------------------------------------

    def fetch_window(
        self,
        code: str,
        *,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        plain = _strip_market_prefix(code)
        if not plain:
            raise PriceProviderUnavailable(
                f"unrecognized stock code for cache lookup: {code!r}"
            )

        bars_dir = self._bars_dir()
        if not bars_dir.exists():
            raise PriceProviderUnavailable(
                f"bars.daily cache root missing: {bars_dir}"
            )

        candidates = self._candidate_cache_dirs(end_date)
        if not candidates:
            raise PriceProviderUnavailable(
                f"no bars.daily cache covering end_date={end_date} "
                f"under {bars_dir}"
            )

        for cache_dir in candidates:
            path = cache_dir / f"{plain}.json"
            if not path.exists():
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PriceProviderUnavailable(
                    f"corrupt bars.daily cache "
                    f"{plain}@{cache_dir.name}: {exc}"
                ) from exc
            if not isinstance(raw, list):
                raise PriceProviderUnavailable(
                    f"bars.daily cache {plain}@{cache_dir.name} is not a list"
                )
            filtered: list[dict[str, Any]] = []
            for row in raw:
                if not isinstance(row, dict):
                    continue
                trade_date = str(row.get("trade_date") or "").strip()
                if not trade_date:
                    continue
                if start_date <= trade_date <= end_date:
                    filtered.append(dict(row))
            if not filtered:
                # The cache file exists for this code but does not span
                # the requested window -- treat as cache stale so the
                # evaluator re-attempts on the next run.  Persisting a
                # data_issue here would freeze the wrong label in place.
                raise PriceProviderUnavailable(
                    f"bars.daily cache {plain}@{cache_dir.name} "
                    f"does not cover [{start_date}, {end_date}]"
                )
            filtered.sort(key=lambda r: str(r.get("trade_date") or ""))
            return filtered

        raise PriceProviderUnavailable(
            f"no bars.daily cache file for {plain} in any directory "
            f">= {end_date}"
        )


__all__ = ["PrismCachePriceProvider"]
