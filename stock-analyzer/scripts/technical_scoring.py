"""Repo-owned technical scoring helper for the stock-analyzer pipeline.

This module replaces the missing sibling `backtest.py` that
`stock-analyzer/scripts/fetch.py` previously imported dynamically. It exposes
a narrow, deterministic API:

  * indicator helpers — :func:`calc_macd`, :func:`calc_kdj`, :func:`calc_boll`
  * a deterministic scorer — :func:`calc_score_detail`
  * a stable bias classifier — :func:`classify_score`
  * thresholds — :data:`BULL_THRESHOLD`, :data:`BEAR_THRESHOLD`

Failure mode is explicit. If there is not enough price history to compute an
indicator or score, the helper raises :class:`InsufficientHistory`. Callers
must catch this exception explicitly — they should not paper over a generic
``Exception``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


BULL_THRESHOLD = 30
BEAR_THRESHOLD = -30

# Minimum history requirements for each indicator.
MIN_HISTORY_MACD = 35  # 26-period EMA + 9-period DEA + 1 for `prev_*`.
MIN_HISTORY_KDJ = 11  # n=9 + 1 for current + 1 for prev.
MIN_HISTORY_BOLL = 20


class InsufficientHistory(ValueError):
    """Raised when there is not enough price history to compute a value."""


def classify_score(score: int) -> str:
    """Map a numeric technical score to a bull/bear/neutral bias label."""

    if score >= BULL_THRESHOLD:
        return "bull"
    if score <= BEAR_THRESHOLD:
        return "bear"
    return "neutral"


def calc_macd(closes: Sequence[float]) -> dict[str, float]:
    """Compute MACD with default 12/26/9 parameters.

    Returns a dict with the latest ``dif``, ``dea``, ``macd`` (histogram),
    plus ``prev_dif`` / ``prev_dea`` so cross detection is reproducible.
    """

    if len(closes) < MIN_HISTORY_MACD:
        raise InsufficientHistory(
            f"calc_macd requires at least {MIN_HISTORY_MACD} closes; got {len(closes)}"
        )

    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    dif = [a - b for a, b in zip(ema12, ema26)]
    dea = _ema_series(dif, 9)
    hist = [2.0 * (d - e) for d, e in zip(dif, dea)]
    return {
        "dif": round(dif[-1], 4),
        "dea": round(dea[-1], 4),
        "macd": round(hist[-1], 4),
        "prev_dif": round(dif[-2], 4),
        "prev_dea": round(dea[-2], 4),
    }


def calc_kdj(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    n: int = 9,
) -> dict[str, float]:
    """Compute KDJ over the standard 9-period window.

    Returns the latest ``k``, ``d``, ``j`` and one-step-earlier ``prev_k`` /
    ``prev_d`` values to support cross-style scoring.
    """

    length = min(len(highs), len(lows), len(closes))
    if length < max(n + 2, MIN_HISTORY_KDJ):
        raise InsufficientHistory(
            f"calc_kdj requires at least {max(n + 2, MIN_HISTORY_KDJ)} samples; got {length}"
        )

    k, d = 50.0, 50.0
    prev_k, prev_d = k, d
    for i in range(n - 1, length):
        prev_k, prev_d = k, d
        low_n = min(lows[i - n + 1 : i + 1])
        high_n = max(highs[i - n + 1 : i + 1])
        rsv = ((closes[i] - low_n) / (high_n - low_n) * 100.0) if high_n != low_n else 50.0
        k = (2.0 / 3.0) * k + (1.0 / 3.0) * rsv
        d = (2.0 / 3.0) * d + (1.0 / 3.0) * k
    j = 3.0 * k - 2.0 * d
    return {
        "k": round(k, 2),
        "d": round(d, 2),
        "j": round(j, 2),
        "prev_k": round(prev_k, 2),
        "prev_d": round(prev_d, 2),
    }


def calc_boll(
    closes: Sequence[float],
    period: int = 20,
    multiplier: float = 2.0,
) -> dict[str, float]:
    """Compute Bollinger Bands over the standard 20-period window."""

    if len(closes) < period:
        raise InsufficientHistory(
            f"calc_boll requires at least {period} closes; got {len(closes)}"
        )

    recent = list(closes[-period:])
    mid = sum(recent) / period
    variance = sum((x - mid) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    return {
        "upper": round(mid + multiplier * std, 4),
        "mid": round(mid, 4),
        "lower": round(mid - multiplier * std, 4),
    }


# --- scoring ---------------------------------------------------------------

# Lookback windows used by :func:`calc_score_detail`.
_TREND_LOOKBACK = 5
_VOLUME_LOOKBACK = 20


def calc_score_detail(
    idx: int,
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float],
    macd_data: dict[str, float],
    kdj_data: dict[str, float],
    boll_data: dict[str, float],
) -> tuple[int, list[tuple[int, str]]]:
    """Combine indicator signals into a deterministic technical score.

    The score is a transparent sum of named components — the caller can
    surface the breakdown to humans. Returned components always satisfy
    ``score == sum(points for points, _ in components)``.

    Raises :class:`InsufficientHistory` when ``closes`` is too short to
    compute the 5-day trend lookback. Volume confirmation simply contributes
    ``0`` when 20-day history is missing — it does not raise.
    """

    if idx < _TREND_LOOKBACK or len(closes) < _TREND_LOOKBACK + 1:
        raise InsufficientHistory(
            f"calc_score_detail needs idx >= {_TREND_LOOKBACK} and "
            f">= {_TREND_LOOKBACK + 1} closes for the trend lookback"
        )

    components: list[tuple[int, str]] = []
    components.append(_score_macd(macd_data))
    components.append(_score_kdj(kdj_data))
    components.append(_score_boll(boll_data, closes[idx]))
    components.append(_score_trend(idx, closes))
    if idx >= _VOLUME_LOOKBACK and len(volumes) > idx:
        components.append(_score_volume(idx, closes, volumes))

    score = sum(points for points, _ in components)
    return score, components


def _score_macd(macd: dict[str, float]) -> tuple[int, str]:
    dif = macd["dif"]
    dea = macd["dea"]
    prev_dif = macd["prev_dif"]
    prev_dea = macd["prev_dea"]

    if prev_dif <= prev_dea and dif > dea:
        return 30, "MACD 金叉"
    if prev_dif >= prev_dea and dif < dea:
        return -30, "MACD 死叉"
    if dif > dea and dif > 0:
        return 10, "MACD 多头运行"
    if dif < dea and dif < 0:
        return -10, "MACD 空头运行"
    return 0, "MACD 中性"


def _score_kdj(kdj: dict[str, float]) -> tuple[int, str]:
    k = kdj["k"]
    d = kdj["d"]
    if k > d:
        return 20, f"KDJ K({k:.1f}) 上穿 D({d:.1f})"
    if k < d:
        return -20, f"KDJ K({k:.1f}) 下穿 D({d:.1f})"
    return 0, "KDJ 中性"


def _score_boll(boll: dict[str, float], close: float) -> tuple[int, str]:
    mid = boll["mid"]
    if close > mid:
        return 10, f"价格({close:.2f}) 高于布林中轨({mid:.2f})"
    if close < mid:
        return -10, f"价格({close:.2f}) 低于布林中轨({mid:.2f})"
    return 0, "价格贴近布林中轨"


def _score_trend(idx: int, closes: Sequence[float]) -> tuple[int, str]:
    base = closes[idx - _TREND_LOOKBACK]
    latest = closes[idx]
    if latest > base:
        return 10, f"近 {_TREND_LOOKBACK} 日上行 ({base:.2f} → {latest:.2f})"
    if latest < base:
        return -10, f"近 {_TREND_LOOKBACK} 日下行 ({base:.2f} → {latest:.2f})"
    return 0, f"近 {_TREND_LOOKBACK} 日横盘"


def _score_volume(idx: int, closes: Sequence[float], volumes: Sequence[float]) -> tuple[int, str]:
    window = volumes[idx - _VOLUME_LOOKBACK + 1 : idx + 1]
    if not window:
        return 0, "成交量参考不足"
    avg_vol = sum(window) / len(window)
    today_vol = volumes[idx]
    if avg_vol <= 0 or today_vol < 1.2 * avg_vol or idx == 0:
        return 0, "成交量未明显放量"
    if closes[idx] > closes[idx - 1]:
        return 5, "放量上涨"
    if closes[idx] < closes[idx - 1]:
        return -5, "放量下跌"
    return 0, "成交量未配合方向"


# --- internals -------------------------------------------------------------


def _ema_series(values: Sequence[float], period: int) -> list[float]:
    """Standard EMA series. ``ema[0]`` is seeded as ``values[0]``."""

    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    ema = [float(values[0])]
    for value in values[1:]:
        ema.append(alpha * float(value) + (1.0 - alpha) * ema[-1])
    return ema
