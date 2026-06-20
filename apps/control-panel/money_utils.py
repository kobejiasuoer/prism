"""Money/price rounding helpers. Leaf module to break the dashboard_data/portfolio_view cycle."""
from __future__ import annotations
from typing import Any
def round_money(value: Any) -> float:
    try: return round(float(value), 2)
    except (TypeError, ValueError): return 0.0
def optional_round_money(value: Any) -> float | None:
    try: return round(float(value), 2)
    except (TypeError, ValueError): return None
