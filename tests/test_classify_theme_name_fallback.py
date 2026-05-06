"""Theme classification — name-fallback layer regression coverage.

These tests pin the behaviour of the name-fallback rules in
:func:`packages.screener.scan.classify_theme`. The name layer only fires
when `industry` and `concept` are both empty — the very situation we
observed in production scans where ~48 of 51 stocks classified as `其他`
had no `industry` or `concept` data attached.

The goal of these tests is *not* to expand the taxonomy beyond what the
current 15 themes cover. We add a name rule only when it maps cleanly to
an existing theme, and we keep an explicit "still other" set for stocks
that genuinely don't fit any current theme. That way, expanding the
taxonomy later doesn't quietly reclassify stocks behind operators' backs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"

for path in (REPO_ROOT, PACKAGES_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def _stock(name: str, industry: str = "", concept: str = "") -> dict:
    """A scan stock with the minimum shape `classify_theme` reads."""
    return {
        "name": name,
        "fundamentals": {"industry": industry, "concept": concept},
    }


def _classify():
    from screener.scan import classify_theme
    return classify_theme


# --- Regression: existing 15-theme behaviour must not change ---


def test_industry_match_still_wins_over_name():
    classify_theme = _classify()
    # An AI硬件链 industry should win even when the name hints at
    # something else.
    s = _stock("国轩高科", industry="半导体", concept="")
    assert classify_theme(s) == "AI硬件链"


def test_concept_match_still_wins_over_name():
    classify_theme = _classify()
    s = _stock("Some Random Co", industry="", concept="光伏 TOPCon 钙钛矿")
    assert classify_theme(s) == "光伏链"


def test_unrelated_name_still_falls_through_to_other():
    classify_theme = _classify()
    # A name that matches no rule with no industry/concept stays in 其他.
    s = _stock("XYZ控股", industry="", concept="")
    assert classify_theme(s) == "其他"


# --- New: name-fallback for AI硬件链 (semiconductor / PCB / memory) ---


@pytest.mark.parametrize(
    "name",
    [
        "兆易创新",       # memory chips
        "紫光国微",       # IC design
        "中瓷电子",       # ceramic IC packaging
        "深科技",         # electronic mfg
        "深圳华强",       # semiconductor distribution
        "世运电路",       # PCB
        "广合科技",       # PCB
        "光迅科技",       # optical modules
        "水晶光电",       # optics
        "烽火通信",       # telecom equipment
        "方正科技",       # PC / electronics
    ],
)
def test_ai_hardware_chain_name_fallback(name: str):
    classify_theme = _classify()
    assert classify_theme(_stock(name)) == "AI硬件链"


# --- New: name-fallback for AI信息链 (telecom services / satellites / IT) ---


@pytest.mark.parametrize(
    "name",
    [
        "中国卫通",   # satellite communications
        "中国卫星",   # satellite
        "拓维信息",   # IT services
        "岩山科技",   # AI
    ],
)
def test_ai_info_chain_name_fallback(name: str):
    classify_theme = _classify()
    assert classify_theme(_stock(name)) == "AI信息链"


# --- New: name-fallback for 有色资源链 (rare metals / tungsten / silver / tin) ---


@pytest.mark.parametrize(
    "name",
    [
        "兴业银锡",   # silver + tin
        "中钨高新",   # tungsten
        "中国稀土",   # rare earth
        "锡业股份",   # tin
        "厦门钨业",   # tungsten
        "盛和资源",   # rare earth
        "海亮股份",   # copper
        "藏格矿业",   # potash / lithium
    ],
)
def test_nonferrous_chain_name_fallback(name: str):
    classify_theme = _classify()
    assert classify_theme(_stock(name)) == "有色资源链"


# --- New: name-fallback for 新能源链 (wind / battery materials / power utilities) ---


@pytest.mark.parametrize(
    "name",
    [
        "金风科技",     # wind turbines
        "节能风电",     # wind power
        "国轩高科",     # battery
        "天赐材料",     # li-battery materials
        "兖矿能源",     # coal / energy
        "中国能建",     # power-grid construction
        "中国电建",     # power-grid construction
        "中国核电",     # nuclear
        "陕西煤业",     # coal
        "华阳股份",     # coal / energy
    ],
)
def test_new_energy_chain_name_fallback(name: str):
    classify_theme = _classify()
    assert classify_theme(_stock(name)) == "新能源链"


# --- New: name-fallback for 军工链 ---


@pytest.mark.parametrize(
    "name",
    [
        "高德红外",     # military infrared
        "航天电器",     # space-grade connectors
    ],
)
def test_military_chain_name_fallback(name: str):
    classify_theme = _classify()
    assert classify_theme(_stock(name)) == "军工链"


# --- New: name-fallback for 游戏传媒链 ---


@pytest.mark.parametrize(
    "name",
    [
        "完美世界",
        "中国电影",
    ],
)
def test_gaming_media_name_fallback(name: str):
    classify_theme = _classify()
    assert classify_theme(_stock(name)) == "游戏传媒链"


# --- Sanity: stocks we deliberately do not reclassify stay 其他 ---


@pytest.mark.parametrize(
    "name",
    [
        "中国东航",   # airline — no current theme covers airlines
        "盈峰环境",   # environmental services
        "衢州发展",   # local-state holding
    ],
)
def test_genuinely_uncategorized_names_stay_other(name: str):
    classify_theme = _classify()
    assert classify_theme(_stock(name)) == "其他"
