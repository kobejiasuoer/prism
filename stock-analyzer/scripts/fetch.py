#!/usr/bin/env python3
"""
stock-analyzer 数据采集脚本
数据源：
  1. 新浪财经 — 实时行情 + K线数据（技术指标）
  2. 东方财富 — 个股新闻 + 公告 + 主力资金流向 + 基本面数据
  3. 雪球 — 个股讨论（需登录 cookie，可选增强，由 cron agent 通过浏览器补充）
"""

import json
import math
import os
import re
import socket
import sys
import time
import warnings
import argparse
from glob import glob
from datetime import datetime, timedelta
from urllib.parse import quote, urlparse

import requests

# 清除代理环境变量 — 手动按需启用显式 proxies
for k in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'no_proxy', 'NO_PROXY']:
    os.environ.pop(k, None)

# 代理配置：新浪直连，东方财富默认直连；只有显式配置代理时才回退
_EM_PROXY_URL = os.getenv("OPENCLAW_EASTMONEY_PROXY") or os.getenv("EASTMONEY_PROXY_URL")
_NO_PROXY = {"http": None, "https": None}

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.abspath(os.path.join(SKILL_ROOT, ".."))
PACKAGES_ROOT = os.path.join(REPO_ROOT, "packages")
DATA_DIR = os.path.join(SKILL_ROOT, "data")
SNAPSHOT_DIR = os.path.join(DATA_DIR, "daily_snapshots")
REPORTS_DIR = os.path.join(SKILL_ROOT, "reports")
FUNDAMENTALS_CACHE_DIR = os.path.join(DATA_DIR, "fundamentals_cache")

if SKILL_ROOT not in sys.path:
    sys.path.insert(0, SKILL_ROOT)
if PACKAGES_ROOT not in sys.path:
    sys.path.insert(0, PACKAGES_ROOT)

from stock_parameters import WATCHLIST_RULE_THRESHOLDS, assess_flow_confidence
from screener.capital_flow_contract import UNIT_WAN_YUAN, build_capital_flow_payload, resolve_amount_wan, wan_to_yi, yuan_to_wan
from watchlist_registry import infer_market_from_code, infer_sina_code, list_active_watchlist_stocks

warnings.filterwarnings("ignore")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _proxy_dict(url):
    return {"http": url, "https": url}


def _port_open(host, port, timeout=0.2):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _proxy_available(url):
    parsed = urlparse(url or "")
    if not parsed.hostname or not parsed.port:
        return False
    return _port_open(parsed.hostname, parsed.port)


def _eastmoney_proxy_candidates():
    candidates = [_NO_PROXY]
    if _EM_PROXY_URL and _proxy_available(_EM_PROXY_URL):
        candidates.append(_proxy_dict(_EM_PROXY_URL))
    return candidates


def eastmoney_get(url, referer="https://data.eastmoney.com", timeout=10):
    last_error = None
    for proxies in _eastmoney_proxy_candidates():
        try:
            resp = requests.get(
                url,
                headers={**HEADERS, "Referer": referer},
                timeout=timeout,
                proxies=proxies,
            )
            resp.raise_for_status()
            if not resp.text or not resp.text.strip():
                raise ValueError("empty response")
            return resp
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"东方财富请求失败: {last_error}")


def _previous_business_day(day):
    current = day - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _latest_completed_trade_date(now=None):
    now = now or datetime.now()
    today = now.date()
    if today.weekday() >= 5:
        return _previous_business_day(today)
    minute_of_day = now.hour * 60 + now.minute
    if minute_of_day < 15 * 60 + 5:
        return _previous_business_day(today)
    return today


def _is_intraday_session(now=None):
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    minute_of_day = now.hour * 60 + now.minute
    return 9 * 60 + 15 <= minute_of_day <= 15 * 60 + 5


def _is_fund_flow_history_fresh(history, now=None):
    if not history:
        return False
    latest = history[-1].get("date")
    if not latest:
        return False
    return latest >= _latest_completed_trade_date(now).strftime("%Y-%m-%d")


def load_config(selected_codes=None):
    config = json.load(open(os.path.join(SKILL_ROOT, "config", "stocks.json")))
    config["stocks"] = list_active_watchlist_stocks(config)
    if selected_codes:
        selected = []
        existing = set()
        for stock in config.get("stocks", []):
            code = stock.get("code")
            if code in selected_codes:
                selected.append(stock)
                existing.add(code)

        for code in selected_codes:
            if code in existing:
                continue
            market = infer_market_from_code(code)
            selected.append(
                {
                    "code": code,
                    "name": code,
                    "market": market,
                    "sina": infer_sina_code(code, market),
                }
            )
        config["stocks"] = selected
    return config


def fetch_realtime(sina_code):
    """从新浪财经获取实时行情"""
    url = f"https://hq.sinajs.cn/list={sina_code}"
    resp = requests.get(url, headers={**HEADERS, "Referer": "https://finance.sina.com.cn"}, timeout=10, proxies=_NO_PROXY)
    m = re.search(r'"(.+)"', resp.text)
    if not m:
        raise ValueError(f"新浪行情解析失败: {sina_code}")
    f = m.group(1).split(",")
    return {
        "name": f[0],
        "open": float(f[1]),
        "prev_close": float(f[2]),
        "price": float(f[3]),
        "high": float(f[4]),
        "low": float(f[5]),
        "volume": int(f[8]),       # 手
        "amount": float(f[9]),     # 元
        "change_pct": round((float(f[3]) - float(f[2])) / float(f[2]) * 100, 2) if float(f[2]) else 0,
        "buy1_vol": int(f[10]), "buy1_price": float(f[11]),
        "sell1_vol": int(f[20]), "sell1_price": float(f[21]),
        "date": f[30], "time": f[31],
    }


def fetch_news(name, code, count=5):
    """从东方财富API拉个股新闻"""
    url = (
        "https://search-api-web.eastmoney.com/search/jsonp"
        f"?cb=jQuery&param=%7B%22uid%22%3A%22%22%2C%22keyword%22%3A%22{quote(name + code)}%22"
        f"%2C%22type%22%3A%5B%22cmsArticleWebOld%22%5D%2C%22client%22%3A%22web%22"
        f"%2C%22clientType%22%3A%22web%22%2C%22clientVersion%22%3A%22curr%22"
        f"%2C%22param%22%3A%7B%22cmsArticleWebOld%22%3A%7B%22searchScope%22%3A%22default%22"
        f"%2C%22sort%22%3A%22default%22%2C%22pageIndex%22%3A1%2C%22pageSize%22%3A{count}"
        f"%2C%22preTag%22%3A%22%22%2C%22postTag%22%3A%22%22%7D%7D%7D"
    )
    try:
        resp = eastmoney_get(url, referer="https://so.eastmoney.com", timeout=10)
        m = re.search(r"jQuery\((.*)\)", resp.text, re.S)
        if m:
            data = json.loads(m.group(1))
            articles = data.get("result", {}).get("cmsArticleWebOld", [])
            return [
                {"date": a.get("date", "")[:10], "title": a.get("title", ""),
                 "content": a.get("content", "")[:150], "source": a.get("mediaName", "")}
                for a in articles[:count]
            ]
    except Exception as e:
        print(f"[WARN] 新闻获取失败: {e}", file=sys.stderr)
    return []


def fetch_announcements(code, count=5):
    """从东方财富API拉个股公告（无需登录）"""
    url = (
        "https://np-anotice-stock.eastmoney.com/api/security/ann"
        f"?sr=-1&page_size={count}&page_index=1"
        f"&ann_type=A&client_source=web&stock_list={code}"
    )
    try:
        resp = eastmoney_get(url, timeout=10)
        data = resp.json()
        items = data.get("data", {}).get("list", [])
        result = []
        for item in items[:count]:
            title = item.get("title", "")
            # 清理标题前缀（如 "长安汽车:"）
            clean_title = re.sub(r"^[\w\u4e00-\u9fff]+[:：]", "", title).strip()
            result.append({
                "date": item.get("notice_date", "")[:10],
                "title": clean_title or title,
                "source": item.get("source", "东方财富"),
            })
        return result
    except Exception as e:
        print(f"[WARN] 公告获取失败: {e}", file=sys.stderr)
    return []


def fetch_kline(sina_code, days=60):
    """从新浪财经获取日K线数据"""
    url = (
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
        f"?symbol={sina_code}&scale=240&ma=no&datalen={days}"
    )
    resp = requests.get(url, headers={**HEADERS, "Referer": "https://finance.sina.com.cn"}, timeout=10, proxies=_NO_PROXY)
    text = resp.text.strip()
    if not text or text == "null":
        raise ValueError(f"K线数据获取失败: {sina_code}")
    # 新浪返回的是类JSON但key没有引号，需要修复
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 修复无引号的key
        fixed = re.sub(r'(\w+):', r'"\1":', text)
        data = json.loads(fixed)
    return data


def calc_ema(series, period):
    """计算EMA（指数移动平均）"""
    if len(series) < period:
        return series[-1] if series else 0
    k = 2 / (period + 1)
    ema = sum(series[:period]) / period
    for val in series[period:]:
        ema = val * k + ema * (1 - k)
    return ema


def calc_sma(series, period):
    """计算SMA（简单移动平均）"""
    if len(series) < period:
        return series[-1] if series else 0
    return sum(series[-period:]) / period


def calc_ema_series(series, period):
    """计算完整的EMA序列"""
    if len(series) < period:
        return [0] * len(series)
    k = 2 / (period + 1)
    result = [0] * (period - 1)
    ema = sum(series[:period]) / period
    result.append(ema)
    for val in series[period:]:
        ema = val * k + ema * (1 - k)
        result.append(ema)
    return result


def calc_macd(closes):
    """计算MACD指标: DIF, DEA, MACD柱"""
    if len(closes) < 35:
        return None
    ema12 = calc_ema_series(closes, 12)
    ema26 = calc_ema_series(closes, 26)
    dif = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    dea = calc_ema_series(dif, 9)
    macd = [2 * (d - e) for d, e in zip(dif, dea)]
    return {
        "dif": round(dif[-1], 4),
        "dea": round(dea[-1], 4),
        "macd": round(macd[-1], 4),
        "prev_dif": round(dif[-2], 4) if len(dif) >= 2 else 0,
        "prev_dea": round(dea[-2], 4) if len(dea) >= 2 else 0,
    }


def calc_kdj(closes, highs, lows, n=9):
    """计算KDJ指标"""
    if len(closes) < n + 1:
        return None
    k, d = 50, 50
    for i in range(n, len(closes)):
        low_n = min(lows[i - n + 1:i + 1])
        high_n = max(highs[i - n + 1:i + 1])
        rsv = (closes[i] - low_n) / (high_n - low_n) * 100 if high_n != low_n else 50
        k = 2 / 3 * k + 1 / 3 * rsv
        d = 2 / 3 * d + 1 / 3 * k
    j = 3 * k - 2 * d
    return {"k": round(k, 2), "d": round(d, 2), "j": round(j, 2)}


def calc_bollinger(closes, period=20, multiplier=2):
    """计算布林带"""
    if len(closes) < period:
        return None
    recent = closes[-period:]
    mid = sum(recent) / period
    variance = sum((x - mid) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    return {
        "mid": round(mid, 2),
        "upper": round(mid + multiplier * std, 2),
        "lower": round(mid - multiplier * std, 2),
    }


def calc_ma(closes, periods=None):
    """计算多条均线"""
    if periods is None:
        periods = [5, 10, 20, 60]
    result = {}
    for p in periods:
        if len(closes) >= p:
            result[f"MA{p}"] = round(sum(closes[-p:]) / p, 2)
    return result


def fetch_technical_indicators(sina_code, days=60):
    """获取并计算技术指标，包含 calc_score 回测评分"""
    kline = fetch_kline(sina_code, days)
    closes = [float(d["close"]) for d in kline]
    highs = [float(d["high"]) for d in kline]
    lows = [float(d["low"]) for d in kline]
    volumes = [float(d["volume"]) for d in kline]

    result = {}

    # === calc_score 回测评分 ===
    try:
        # 动态导入 backtest 模块（同级目录）
        import importlib.util
        bt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest.py")
        spec = importlib.util.spec_from_file_location("backtest", bt_path)
        bt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bt)

        macd_data = bt.calc_macd(closes)
        kdj_data = bt.calc_kdj(highs, lows, closes)
        boll_data = bt.calc_boll(closes)

        score, components = bt.calc_score_detail(
            len(closes) - 1, closes, highs, lows, volumes,
            macd_data, kdj_data, boll_data
        )
        bias = bt.classify_score(score)
        result["backtest_score"] = score
        result["backtest_bias"] = bias
        result["backtest_thresholds"] = {
            "bull": bt.BULL_THRESHOLD,
            "bear": bt.BEAR_THRESHOLD,
        }
        result["backtest_components"] = [
            {"points": points, "reason": reason}
            for points, reason in components
        ]
        if bias == "bull":
            result["backtest_signal"] = f"看多（评分{score}）"
        elif bias == "bear":
            result["backtest_signal"] = f"看空（评分{score}）"
        else:
            result["backtest_signal"] = f"中性（评分{score}）"
    except Exception as e:
        print(f"[WARN] calc_score 计算失败: {e}", file=sys.stderr)

    # MACD
    macd = calc_macd(closes)
    if macd:
        result["macd"] = macd
        # 信号判断
        if macd["prev_dif"] < macd["prev_dea"] and macd["dif"] > macd["dea"]:
            result["macd_signal"] = "金叉"
        elif macd["prev_dif"] > macd["prev_dea"] and macd["dif"] < macd["dea"]:
            result["macd_signal"] = "死叉"
        elif macd["dif"] > 0 and macd["dea"] > 0:
            result["macd_signal"] = "多头运行"
        elif macd["dif"] < 0 and macd["dea"] < 0:
            result["macd_signal"] = "空头运行"
        else:
            result["macd_signal"] = "震荡"

    # KDJ
    kdj = calc_kdj(closes, highs, lows)
    if kdj:
        result["kdj"] = kdj
        if kdj["j"] > 100:
            result["kdj_signal"] = "超买"
        elif kdj["j"] < 0:
            result["kdj_signal"] = "超卖"
        elif kdj["k"] > kdj["d"] and kdj["k"] < 80:
            result["kdj_signal"] = "偏多"
        elif kdj["k"] < kdj["d"] and kdj["k"] > 20:
            result["kdj_signal"] = "偏空"
        else:
            result["kdj_signal"] = "中性"

    # 布林带
    boll = calc_bollinger(closes)
    if boll:
        result["boll"] = boll
        price = closes[-1]
        if price >= boll["upper"]:
            result["boll_signal"] = "触及上轨"
        elif price <= boll["lower"]:
            result["boll_signal"] = "触及下轨"
        else:
            result["boll_signal"] = "中轨区间"

    # 均线
    result["ma"] = calc_ma(closes)

    # 价格位置
    if closes:
        recent_high = max(closes[-20:]) if len(closes) >= 20 else max(closes)
        recent_low = min(closes[-20:]) if len(closes) >= 20 else min(closes)
        price = closes[-1]
        result["price_position"] = {
            "price": price,
            "high_20d": recent_high,
            "low_20d": recent_low,
            "pct_from_high": round((price - recent_high) / recent_high * 100, 2),
            "pct_from_low": round((price - recent_low) / recent_low * 100, 2),
        }

    return result


def _fund_flow_cache_path(code, market):
    sina_code = f"{market}{code}"
    return os.path.join(os.path.dirname(__file__), '..', 'data', 'fund_flow_cache', f'{sina_code}.json')


def _load_fund_flow_cache(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            cached = json.load(f)
        return cached if isinstance(cached, list) and cached else None
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


FLOW_AMOUNT_FIELDS = ("main_net", "super_net", "mid_large_net", "retail_net", "small_net")


def _normalize_watchlist_flow_row(row, source_unit=UNIT_WAN_YUAN):
    if not isinstance(row, dict):
        return None

    date = row.get("date")
    if not date:
        return None

    normalized = {"date": date, "unit": UNIT_WAN_YUAN}
    for field in FLOW_AMOUNT_FIELDS:
        amount_wan = resolve_amount_wan(
            row,
            wan_keys=(f"{field}_wan",),
            yi_keys=(f"{field}_yi",),
            legacy_keys=(field,),
            source_unit=source_unit,
        )
        normalized[field] = amount_wan
        normalized[f"{field}_wan"] = amount_wan
        normalized[f"{field}_yi"] = wan_to_yi(amount_wan)
    return normalized


def _merge_fund_flow_rows(*row_sets, limit=None):
    merged = {}
    for rows in row_sets:
        for row in rows or []:
            normalized_row = _normalize_watchlist_flow_row(row)
            if not normalized_row:
                continue
            merged[normalized_row["date"]] = normalized_row
    ordered = [merged[date] for date in sorted(merged)]
    return ordered[-limit:] if limit else ordered


def _build_main_5d(history):
    return [
        {
            "date": item.get("date", ""),
            "net": round(float(item.get("main_net_wan", item.get("main_net", 0)) or 0), 2),
            "net_wan": round(float(item.get("main_net_wan", item.get("main_net", 0)) or 0), 2),
            "net_yi": wan_to_yi(item.get("main_net_wan", item.get("main_net", 0))),
        }
        for item in reversed((history or [])[-5:])
    ]


def _apply_watchlist_capital_flow_contract(flow):
    if not flow:
        return flow

    main_net_wan = resolve_amount_wan(
        flow,
        wan_keys=("main_net_wan",),
        yi_keys=("main_net_yi",),
        legacy_keys=("main_net",),
        source_unit=UNIT_WAN_YUAN,
    )
    five_day_total_wan = round(sum(float(item.get("net_wan", item.get("net", 0)) or 0) for item in flow.get("main_5d", [])[:5]), 2)
    flow.update(
        build_capital_flow_payload(
            today_wan=main_net_wan,
            five_day_total_wan=five_day_total_wan,
            trend=flow.get("signal") or "无数据",
        )
    )
    flow["main_net"] = main_net_wan
    flow["main_net_wan"] = main_net_wan
    flow["main_net_yi"] = wan_to_yi(main_net_wan)
    for field in FLOW_AMOUNT_FIELDS[1:]:
        amount_wan = resolve_amount_wan(
            flow,
            wan_keys=(f"{field}_wan",),
            yi_keys=(f"{field}_yi",),
            legacy_keys=(field,),
            source_unit=UNIT_WAN_YUAN,
        )
        flow[field] = amount_wan
        flow[f"{field}_wan"] = amount_wan
        flow[f"{field}_yi"] = wan_to_yi(amount_wan)
    flow["unit"] = UNIT_WAN_YUAN
    return flow


def _apply_capital_flow_signal(flow):
    main_net = flow.get("main_net", 0)
    if main_net > 0:
        flow["signal"] = "主力净流入"
    elif main_net < 0:
        flow["signal"] = "主力净流出"
    else:
        flow["signal"] = "多空平衡"

    if flow["main_5d"]:
        consecutive = 0
        sign = 1 if flow["main_5d"][0]["net"] >= 0 else -1
        for item in flow["main_5d"]:
            item_sign = 1 if item["net"] >= 0 else -1
            if item_sign == sign:
                consecutive += 1
            else:
                break
        if consecutive >= 3:
            direction = "流入" if sign > 0 else "流出"
            flow["signal"] = f"主力连续{consecutive}日{direction}"
    return _apply_watchlist_capital_flow_contract(flow)


def _build_capital_flow_from_history(history):
    if not history:
        return None
    latest = history[-1]
    flow = {
        "as_of_date": latest.get("date"),
        "updated_at": latest.get("date"),
        "main_5d": _build_main_5d(history),
        "main_net": round(float(latest.get("main_net_wan", latest.get("main_net", 0)) or 0), 2),
        "super_net": round(float(latest.get("super_net_wan", latest.get("super_net", 0)) or 0), 2),
        "mid_large_net": round(float(latest.get("mid_large_net_wan", latest.get("mid_large_net", 0)) or 0), 2),
        "retail_net": round(float(latest.get("retail_net_wan", latest.get("retail_net", 0)) or 0), 2),
        "small_net": round(float(latest.get("small_net_wan", latest.get("small_net", 0)) or 0), 2),
    }
    if _is_intraday_session() and latest.get("date") != datetime.now().strftime("%Y-%m-%d"):
        preview = _apply_capital_flow_signal(dict(flow))
        flow["intraday_unconfirmed"] = True
        flow["history_signal"] = preview.get("signal")
        flow["signal"] = f"历史参考（截至{latest.get('date')}）"
        return _apply_watchlist_capital_flow_contract(flow)
    return _apply_capital_flow_signal(flow)


def fetch_capital_flow(code, market):
    """获取主力资金流向（东方财富），失败时回退到历史缓存。"""
    secid = f"0.{code}" if market == "sz" else f"1.{code}"
    cache_path = _fund_flow_cache_path(code, market)

    try:
        # 1. 从 /stock/get 接口的 f178 获取最近5日主力流向
        url_get = (
            f"https://push2.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}&fields=f178"
        )
        resp_get = eastmoney_get(url_get, timeout=10)
        data_get = resp_get.json()
        fdata = data_get.get("data", {})
        flow_5d_raw = fdata.get("f178", "[]")
        if isinstance(flow_5d_raw, str):
            flow_5d_raw = json.loads(flow_5d_raw)

        # 2. 从 /fflow/kline/get 获取今日详细资金流向
        url_kline = (
            f"https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
            f"?secid={secid}&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
            f"&klt=101&fqt=1&lmt=1"
        )
        resp_kline = eastmoney_get(url_kline, timeout=10)
        kdata = resp_kline.json().get("data", {})
    except Exception as e:
        print(f"[WARN] 实时资金流获取失败，回退历史缓存: {code} ({e})", file=sys.stderr)
        history = fetch_fund_flow_history(code, market, days=5)
        return _build_capital_flow_from_history(history)

    flow = {"main_5d": []}

    # 解析5日历史（f178字段）
    for item in flow_5d_raw[:5]:
        flow["main_5d"].append({
            "date": item.get("date", ""),
            "net": yuan_to_wan(item.get("mainNetAmt", 0)),
            "net_wan": yuan_to_wan(item.get("mainNetAmt", 0)),
            "net_yi": wan_to_yi(yuan_to_wan(item.get("mainNetAmt", 0))),
        })

    # 解析今日详细数据（kline接口）
    # kline格式: date, 主力净流入, 超大单净流入, 中大单净流入, 散户大单净流入, 小单净流入
    klines = kdata.get("klines", [])
    if klines:
        parts = klines[0].split(",")
        if len(parts) >= 6:
            main_net = float(parts[1])
            flow["main_net"] = yuan_to_wan(main_net)
            flow["super_net"] = yuan_to_wan(float(parts[2]))   # 超大单
            flow["mid_large_net"] = yuan_to_wan(float(parts[3]))  # 中大单
            flow["retail_net"] = yuan_to_wan(float(parts[4]))    # 散户大单
            flow["small_net"] = yuan_to_wan(float(parts[5]))     # 小单
        else:
            history = fetch_fund_flow_history(code, market, days=5)
            return _build_capital_flow_from_history(history)
    else:
        history = fetch_fund_flow_history(code, market, days=5)
        return _build_capital_flow_from_history(history)

    today = datetime.now().strftime("%Y-%m-%d")
    flow["as_of_date"] = today
    flow["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today_row = {
        "date": today,
        "main_net": flow.get("main_net", 0),
        "super_net": flow.get("super_net", 0),
        "mid_large_net": flow.get("mid_large_net", 0),
        "retail_net": flow.get("retail_net", 0),
        "small_net": flow.get("small_net", 0),
    }
    cached_history = _load_fund_flow_cache(cache_path)
    merged_history = _merge_fund_flow_rows(cached_history, [today_row], limit=120)
    if merged_history:
        _save_cache(cache_path, merged_history)
        flow["main_5d"] = _build_main_5d(merged_history)

    return _apply_capital_flow_signal(flow)


def fetch_fund_flow_history(code, market, days=120):
    """获取历史日频资金流向（四层降级：本地缓存 → push2 → datacenter-web → 空）

    Args:
        code: 6位股票代码
        market: 'sz' 或 'sh'
        days: 需要的交易日天数

    Returns:
        List[dict], 每项: {date: 'YYYY-MM-DD', main_net: 万, super_net: 万, retail_net: 万}
    """
    cache_path = _fund_flow_cache_path(code, market)
    cached = _load_fund_flow_cache(cache_path)

    # === 第零层：本地缓存 ===
    if _is_fund_flow_history_fresh(cached):
        return cached

    secid = f"0.{code}" if market == "sz" else f"1.{code}"
    result = []

    # === 第一层：push2.eastmoney.com (有历史日频数据) ===
    try:
        url = (
            f"https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
            f"?secid={secid}&fields1=f1,f2,f3"
            f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
            f"&klt=101&fqt=1&lmt={days}"
        )
        resp = eastmoney_get(url, timeout=10)
        if resp.text and resp.text.strip():
            d = resp.json()
            klines = d.get("data", {}).get("klines", [])
            if klines:
                for k in klines:
                    parts = k.split(",")
                    if len(parts) >= 6:
                        result.append({
                            "date": parts[0],
                            "main_net": round(float(parts[1]) / 10000, 2),
                            "super_net": round(float(parts[2]) / 10000, 2),
                            "mid_large_net": round(float(parts[3]) / 10000, 2),
                            "retail_net": round(float(parts[4]) / 10000, 2),
                            "small_net": round(float(parts[5]) / 10000, 2),
                        })
                if result:
                    result = _merge_fund_flow_rows(result, limit=max(days, len(result)))
                    _save_cache(cache_path, result)
                    return result
    except Exception:
        pass

    # === 第二层：datacenter-web.eastmoney.com (仅当天数据) ===
    try:
        url = (
            f"https://datacenter-web.eastmoney.com/api/data/v1/get"
            f"?reportName=RPT_DMSK_TS_STOCKNEW"
            f"&columns=TRADE_DATE,SUPERDEAL_INFLOW,SUPERDEAL_OUTFLOW,"
            f"BIGDEAL_INFLOW,BIGDEAL_OUTFLOW,CLOSE_PRICE,CHANGE_RATE"
            f"&filter=(SECURITY_CODE=%22{code}%22)"
            f"&pageSize=1&sortColumns=TRADE_DATE&sortTypes=-1"
        )
        resp = eastmoney_get(url, timeout=10)
        d = resp.json()
        data = d.get("result", {}).get("data", [])
        if data:
            item = data[0]
            si = float(item.get("SUPERDEAL_INFLOW", 0)) / 10000
            so = float(item.get("SUPERDEAL_OUTFLOW", 0)) / 10000
            bi = float(item.get("BIGDEAL_INFLOW", 0)) / 10000
            bo = float(item.get("BIGDEAL_OUTFLOW", 0)) / 10000
            result.append({
                "date": item["TRADE_DATE"][:10],
                "main_net": round((si + bi) - (so + bo), 2),
                "super_net": round(si - so, 2),
                "mid_large_net": round(bi - bo, 2),
                "retail_net": 0,
                "small_net": 0,
            })
    except Exception:
        pass

    # === 第三层：浏览器降级（由 cron agent 手动触发） ===
    # 通过 browser(profile=openclaw) 打开东方财富资金流向页面，
    # 从 DOM table 中提取历史数据，保存到缓存文件
    # 详情见 fetch_fund_flow_browser.py
    if result and cached:
        result = _merge_fund_flow_rows(cached, result, limit=max(days, len(cached)))

    if result and not _is_fund_flow_history_fresh(result):
        result = None

    if not result and cached and _is_fund_flow_history_fresh(cached):
        return cached

    if result:
        _save_cache(cache_path, result)
    return result


def _save_cache(path, data):
    """保存资金流向缓存"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def _fundamentals_cache_path(code, market):
    return os.path.join(FUNDAMENTALS_CACHE_DIR, f"{market}{code}.json")


def _normalize_fundamentals_snapshot(data):
    if not isinstance(data, dict):
        return None

    def safe_num(value):
        if value in (None, "", "-"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    price = safe_num(data.get("price"))
    pe = safe_num(data.get("pe"))
    pb = safe_num(data.get("pb"))
    total_mv_yi = safe_num(data.get("total_mv_yi"))
    circ_mv_yi = safe_num(data.get("circ_mv_yi"))
    roe = safe_num(data.get("roe"))
    gross_margin = safe_num(data.get("gross_margin"))

    if price is not None and price <= 0:
        price = None
    if pe is not None and (pe <= 0 or pe > 300):
        pe = None
    if pb is not None and (pb <= 0 or pb > 30):
        pb = None
    if total_mv_yi is not None and total_mv_yi <= 0:
        total_mv_yi = None
    if circ_mv_yi is not None and circ_mv_yi <= 0:
        circ_mv_yi = None
    if roe is not None and (roe < -50 or roe > 60):
        roe = None
    if gross_margin is not None and (gross_margin < 0 or gross_margin > 95):
        gross_margin = None

    normalized = {
        "price": round(price, 2) if price is not None else None,
        "pe": round(pe, 2) if pe is not None else None,
        "pb": round(pb, 2) if pb is not None else None,
        "total_mv_yi": round(total_mv_yi, 2) if total_mv_yi is not None else None,
        "circ_mv_yi": round(circ_mv_yi, 2) if circ_mv_yi is not None else None,
        "roe": round(roe, 2) if roe is not None else None,
        "gross_margin": round(gross_margin, 2) if gross_margin is not None else None,
    }
    return normalized if any(v is not None for v in normalized.values()) else None


def _merge_fundamentals_snapshots(*items):
    merged = {
        "price": None,
        "pe": None,
        "pb": None,
        "total_mv_yi": None,
        "circ_mv_yi": None,
        "roe": None,
        "gross_margin": None,
    }
    has_value = False
    for item in items:
        normalized = _normalize_fundamentals_snapshot(item)
        if not normalized:
            continue
        for key, value in normalized.items():
            if value is not None:
                merged[key] = value
                has_value = True
    return merged if has_value else None


def _load_fundamentals_cache_entry(code, market):
    path = _fundamentals_cache_path(code, market)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            cached = json.load(f)
        normalized = _normalize_fundamentals_snapshot(cached)
        if not normalized:
            return None
        return {
            "fundamentals": normalized,
            "age_seconds": max(0, time.time() - os.path.getmtime(path)),
        }
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def _save_fundamentals_cache_entry(code, market, data):
    normalized = _normalize_fundamentals_snapshot(data)
    if not normalized:
        return
    path = _fundamentals_cache_path(code, market)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(normalized, f, ensure_ascii=False)
    except Exception:
        pass


def _fetch_fundamentals_ulist_snapshot(code, market):
    secid = f"0.{code}" if market == "sz" else f"1.{code}"
    try:
        url = (
            "https://push2.eastmoney.com/api/qt/ulist.np/get"
            f"?fltt=2&secids={secid}&fields=f2,f9,f12,f20"
        )
        resp = eastmoney_get(url, timeout=10)
        data = resp.json()
        diff = data.get("data", {}).get("diff", [])
        if not diff:
            return None
        item = diff[0]
        pe_raw = item.get("f9")
        mv_raw = item.get("f20")
        return _normalize_fundamentals_snapshot({
            "price": item.get("f2"),
            "pe": float(pe_raw) if pe_raw not in (None, "", "-") else None,
            "pb": None,
            "total_mv_yi": float(mv_raw) / 1e8 if mv_raw not in (None, "", "-") else None,
            "circ_mv_yi": None,
            "roe": None,
            "gross_margin": None,
        })
    except Exception:
        return None


def fetch_fundamentals(code, market):
    """获取基本面数据（东方财富），失败时回退批量快照/本地缓存。"""
    cache_entry = _load_fundamentals_cache_entry(code, market)
    cached = cache_entry["fundamentals"] if cache_entry else None
    snapshot = _fetch_fundamentals_ulist_snapshot(code, market)
    if snapshot and cached:
        merged = _merge_fundamentals_snapshots(cached, snapshot)
        _save_fundamentals_cache_entry(code, market, merged)
        return merged

    secid = f"0.{code}" if market == "sz" else f"1.{code}"
    try:
        url = (
            "https://push2.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}&fields=f43,f167,f168,f116,f117,f173,f186"
        )
        resp = eastmoney_get(url, timeout=10)
        data = resp.json()
        fdata = data.get("data", {})
        if fdata:
            live = _normalize_fundamentals_snapshot({
                "price": float(fdata.get("f43")) / 100 if fdata.get("f43") not in (None, "", "-") else None,
                "pe": float(fdata.get("f167")) / 10 if fdata.get("f167") not in (None, "", "-") else None,
                "pb": float(fdata.get("f168")) / 10 if fdata.get("f168") not in (None, "", "-") else None,
                "total_mv_yi": float(fdata.get("f116")) / 1e8 if fdata.get("f116") not in (None, "", "-") else None,
                "circ_mv_yi": float(fdata.get("f117")) / 1e8 if fdata.get("f117") not in (None, "", "-") else None,
                "roe": fdata.get("f173"),
                "gross_margin": fdata.get("f186"),
            })
            merged = _merge_fundamentals_snapshots(cached, snapshot, live)
            if merged:
                _save_fundamentals_cache_entry(code, market, merged)
                return merged
    except Exception as e:
        print(f"[WARN] 基本面实时接口失败，尝试快照/缓存回退: {code} ({e})", file=sys.stderr)

    merged = _merge_fundamentals_snapshots(cached, snapshot)
    if merged:
        _save_fundamentals_cache_entry(code, market, merged)
        return merged
    return None


def format_technical_indicators(tech):
    """格式化技术指标输出"""
    lines = ["### 技术指标", "| 指标 | 数值 | 信号 |", "|------|------|------|"]
    bias_label = {
        "bull": "看多",
        "bear": "看空",
        "neutral": "中性",
    }

    # 回测评分
    score = tech.get("backtest_score")
    signal = tech.get("backtest_signal")
    if score is not None:
        lines.append(f"| **回测评分** | **{score}** | **{signal}** |")
        thresholds = tech.get("backtest_thresholds")
        bias = tech.get("backtest_bias", "neutral")
        if thresholds:
            lines.append(
                f"| 判定阈值 | >={thresholds['bull']} 看多 / <={thresholds['bear']} 看空 | 当前{bias_label.get(bias, '中性')} |"
            )

    # MACD
    macd = tech.get("macd")
    if macd:
        lines.append(f"| MACD(DIF) | {macd['dif']} | |")
        lines.append(f"| MACD(DEA) | {macd['dea']} | |")
        bar_str = f"{macd['macd']:+.4f}"
        lines.append(f"| MACD柱 | {bar_str} | {tech.get('macd_signal', '-')} |")

    # KDJ
    kdj = tech.get("kdj")
    if kdj:
        lines.append(f"| KDJ-K | {kdj['k']} | |")
        lines.append(f"| KDJ-D | {kdj['d']} | |")
        lines.append(f"| KDJ-J | {kdj['j']} | {tech.get('kdj_signal', '-')} |")

    # 布林带
    boll = tech.get("boll")
    if boll:
        lines.append(f"| 布林上轨 | {boll['upper']} | |")
        lines.append(f"| 布林中轨 | {boll['mid']} | |")
        lines.append(f"| 布林下轨 | {boll['lower']} | {tech.get('boll_signal', '-')} |")

    # 均线
    ma = tech.get("ma", {})
    for key, val in sorted(ma.items(), key=lambda x: int(x[0][2:])):
        lines.append(f"| {key} | {val} | |")

    # 价格位置
    pp = tech.get("price_position")
    if pp:
        lines.append(f"| 20日最高 | {pp['high_20d']} | |")
        lines.append(f"| 20日最低 | {pp['low_20d']} | |")
        lines.append(f"| 距20日高 | {pp['pct_from_high']:+.2f}% | |")
        lines.append(f"| 距20日低 | {pp['pct_from_low']:+.2f}% | |")

    components = tech.get("backtest_components", [])
    if components:
        lines.append("")
        comp_text = "；".join(
            f"{'+' if item['points'] > 0 else ''}{item['points']} {item['reason']}"
            for item in components
        )
        lines.append(f"> 评分构成：{comp_text}")

        if tech.get("backtest_bias") == "neutral":
            lines.append("> 技术提示：当前仍处于中性区间，单一 MACD/KDJ 信号不足以单独把早盘结论翻多或翻空。")

    lines.append("")
    return "\n".join(lines)


def format_capital_flow(flow):
    """格式化资金流向输出"""
    if not flow:
        return ""
    main_net = resolve_amount_wan(flow, wan_keys=("main_net_wan",), yi_keys=("main_net_yi",), legacy_keys=("main_net",), source_unit=UNIT_WAN_YUAN)
    super_net = resolve_amount_wan(flow, wan_keys=("super_net_wan",), yi_keys=("super_net_yi",), legacy_keys=("super_net",), source_unit=UNIT_WAN_YUAN)
    mid_large_net = resolve_amount_wan(flow, wan_keys=("mid_large_net_wan",), yi_keys=("mid_large_net_yi",), legacy_keys=("mid_large_net",), source_unit=UNIT_WAN_YUAN)
    retail_net = resolve_amount_wan(flow, wan_keys=("retail_net_wan",), yi_keys=("retail_net_yi",), legacy_keys=("retail_net",), source_unit=UNIT_WAN_YUAN)
    small_net = resolve_amount_wan(flow, wan_keys=("small_net_wan",), yi_keys=("small_net_yi",), legacy_keys=("small_net",), source_unit=UNIT_WAN_YUAN)
    lines = ["### 资金流向", "| 类型 | 净流入(万元) |", "|------|-------------|"]
    lines.append(f"| 主力净流入 | {main_net:+,.2f} |")
    lines.append(f"| 超大单 | {super_net:+,.2f} |")
    lines.append(f"| 中大单 | {mid_large_net:+,.2f} |")
    lines.append(f"| 散户大单 | {retail_net:+,.2f} |")
    lines.append(f"| 小单 | {small_net:+,.2f} |")

    # 近5日主力
    d5 = flow.get("main_5d", [])
    if d5:
        lines.append("")
        lines.append("| 日期 | 主力净流入(万元) |")
        lines.append("|------|----------------|")
        for item in d5[:5]:
            lines.append(f"| {item['date']} | {item['net']:+,.2f} |")

    if flow.get("intraday_unconfirmed"):
        lines.append(
            f"\n> 数据截至: {flow.get('as_of_date', '-')}（盘中实时资金流未拿到，当前仅作历史参考）"
        )
    lines.append(f"\n> 信号: {flow.get('signal', '-')}\n")
    return "\n".join(lines)


def format_fundamentals(fund):
    """格式化基本面数据输出"""
    if not fund:
        return ""
    lines = ["### 基本面数据", "| 指标 | 数值 |", "|------|------|"]
    lines.append(f"| 最新价 | {fund['price']} 元 |" if fund["price"] else "| 最新价 | - |")
    lines.append(f"| PE(市盈率) | {fund['pe']}" if fund["pe"] is not None else "| PE | - |")
    lines.append(f"| PB(市净率) | {fund['pb']}" if fund["pb"] is not None else "| PB | - |")
    lines.append(f"| 总市值 | {fund['total_mv_yi']} 亿" if fund["total_mv_yi"] is not None else "| 总市值 | - |")
    lines.append(f"| 流通市值 | {fund['circ_mv_yi']} 亿" if fund["circ_mv_yi"] is not None else "| 流通市值 | - |")
    lines.append(f"| ROE | {fund['roe']}%" if fund["roe"] is not None else "| ROE | - |")
    lines.append(f"| 毛利率 | {fund['gross_margin']}%" if fund["gross_margin"] is not None else "| 毛利率 | - |")
    lines.append("")
    return "\n".join(lines)


# 模块级缓存：板块涨跌幅（每次脚本运行只拉一次）
_sector_cache = {}


def fetch_sector(sector_code):
    """获取板块涨跌幅（东方财富 push2his kline 接口）"""
    if sector_code in _sector_cache:
        return _sector_cache[sector_code]

    try:
        # 用 push2his 的 kline 接口获取板块最新K线，从中提取今日涨跌幅
        url = (
            f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid=90.{sector_code}&fields1=f1,f2,f3,f4,f5,f6"
            f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
            f"&klt=101&fqt=1&end=20990101&lmt=1"
        )
        resp = eastmoney_get(url, timeout=10)
        data = resp.json()
        kdata = data.get("data", {})
        klines = kdata.get("klines", [])

        if not klines:
            _sector_cache[sector_code] = None
            return None

        # kline格式: date, open, close, high, low, volume, amount, change%, amplitude, turnover%, ...
        parts = klines[0].split(",")
        if len(parts) < 8:
            _sector_cache[sector_code] = None
            return None

        change_pct = round(float(parts[7]), 2)
        sector_name = kdata.get("name", "")

        result = {
            "change_pct": change_pct,
            "name": sector_name,
        }
        _sector_cache[sector_code] = result
        return result
    except Exception as e:
        print(f"[WARN] 板块数据获取失败: {e}", file=sys.stderr)
        return None


def format_sector(stock, sector_data, stock_change_pct):
    """格式化板块对比输出"""
    if not sector_data:
        return ""
    industry = stock.get("industry", "未知")
    sector_change = sector_data.get("change_pct", 0)

    if sector_change is not None and stock_change_pct is not None:
        diff = stock_change_pct - sector_change
        if diff > 0.5:
            strength = "强于行业"
        elif diff < -0.5:
            strength = "弱于行业"
        else:
            strength = "与行业持平"
    else:
        diff = None
        strength = "-"

    lines = [
        "### 板块对比",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| 所属行业 | {industry} |",
        f"| 行业涨幅 | {sector_change:+.2f}% |" if sector_change is not None else "| 行业涨幅 | - |",
        f"| 个股涨幅 | {stock_change_pct:+.2f}% |" if stock_change_pct is not None else "| 个股涨幅 | - |",
        f"| 相对强弱 | {strength} |",
        "",
    ]
    return "\n".join(lines)


def _dedupe_keep_order(items):
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def summarize_event_bias(news, announcements):
    """从新闻和公告里提取事件偏向与风险标签。"""
    negative_patterns = [
        (r"董事长.*辞职|董事.*辞职|高管.*辞职|法定代表人变更", "治理风险"),
        (r"减持|质押|冻结|立案|处罚|问询|诉讼|仲裁|退市", "重大利空"),
        (r"亏损|预亏|下降|下滑|暴跌|终止|取消|风险提示", "业绩/经营风险"),
    ]
    positive_patterns = [
        (r"回购|增持", "股东回报"),
        (r"分红|派息", "分红催化"),
        (r"中标|签约|订单|合作|牌照|获批", "业务催化"),
        (r"增长|扭亏|投产|扩产", "经营改善"),
    ]

    negative = []
    positive = []

    for item in (announcements or []) + (news or []):
        text = " ".join(
            part for part in [item.get("title", ""), item.get("content", "")]
            if part
        )
        for pattern, label in negative_patterns:
            if re.search(pattern, text):
                negative.append(label)
        for pattern, label in positive_patterns:
            if re.search(pattern, text):
                positive.append(label)

    negative = _dedupe_keep_order(negative)
    positive = _dedupe_keep_order(positive)
    return positive, negative


def build_rule_snapshot(stock, realtime, news, announcements, tech_indicators,
                        capital_flow, fundamentals, sector_data):
    """构建规则化快照，给 AI 报告提供更稳定的护栏。"""
    snapshot = {
        "tech_base": "中性",
        "flow_base": "中性",
        "event_base": "中性",
        "action": "观望",
        "position": "0-0.5成",
        "hard_flags": [],
        "positives": [],
        "watch_points": [],
        "flow_confidence": {
            "label": "未知",
            "penalty": 0,
        },
    }

    tech = tech_indicators or {}
    flow = capital_flow or {}
    fund = fundamentals or {}
    rt = realtime or {}
    pp = tech.get("price_position") or {}

    bias_map = {"bull": "看多", "bear": "看空", "neutral": "中性"}
    tech_bias = tech.get("backtest_bias", "neutral")
    snapshot["tech_base"] = bias_map.get(tech_bias, "中性")

    positive_events, negative_events = summarize_event_bias(news, announcements)
    snapshot["positives"].extend(positive_events)
    snapshot["hard_flags"].extend(negative_events)

    flow_signal = flow.get("signal", "中性")
    flow_confidence = assess_flow_confidence(flow)
    snapshot["flow_confidence"] = {
        "label": flow_confidence["label"],
        "penalty": flow_confidence["penalty"],
        "as_of_date": flow_confidence.get("as_of_date"),
    }
    flow_reference_only = flow_confidence["reference_only"]
    if flow_reference_only:
        as_of_date = flow.get("as_of_date")
        if as_of_date:
            snapshot["watch_points"].append(f"资金流仅更新到 {as_of_date}，先别把它当盘中确认")
    else:
        if "连续" in flow_signal and "流入" in flow_signal:
            snapshot["flow_base"] = "偏多"
            snapshot["positives"].append(flow_signal)
        elif "连续" in flow_signal and "流出" in flow_signal:
            snapshot["flow_base"] = "偏空"
            snapshot["hard_flags"].append(flow_signal)
        elif flow.get("main_net", 0) > 0:
            snapshot["flow_base"] = "偏多"
        elif flow.get("main_net", 0) < 0:
            snapshot["flow_base"] = "偏空"

    if negative_events:
        snapshot["event_base"] = "偏空"
    elif positive_events:
        snapshot["event_base"] = "偏多"

    severe_negatives = 0
    positive_points = 0
    roe_rules = WATCHLIST_RULE_THRESHOLDS["roe"]
    pe_rules = WATCHLIST_RULE_THRESHOLDS["pe"]
    pb_rules = WATCHLIST_RULE_THRESHOLDS["pb"]
    relative_strength_rules = WATCHLIST_RULE_THRESHOLDS["relative_strength"]
    price_position_rules = WATCHLIST_RULE_THRESHOLDS["price_position"]
    action_rules = WATCHLIST_RULE_THRESHOLDS["action"]

    if tech_bias == "bull":
        positive_points += 2
    elif tech_bias == "bear":
        severe_negatives += 2

    if snapshot["flow_base"] == "偏多":
        positive_points += 1
    elif snapshot["flow_base"] == "偏空":
        severe_negatives += 2 if "连续" in flow_signal else 1

    if negative_events:
        severe_negatives += len(negative_events)
    if positive_events:
        positive_points += len(positive_events)
    if flow_confidence["penalty"] > 0:
        severe_negatives += flow_confidence["penalty"]

    pe = fund.get("pe")
    pb = fund.get("pb")
    roe = fund.get("roe")
    if roe is not None and roe < roe_rules["negative_below"]:
        snapshot["hard_flags"].append("ROE为负")
        severe_negatives += 3
    elif roe is not None and roe < roe_rules["weak_below"]:
        snapshot["hard_flags"].append("ROE偏弱")
        severe_negatives += 1
    elif roe is not None and roe >= roe_rules["strong_at_or_above"]:
        positive_points += 1

    if pe is not None and pe > pe_rules["extreme_above"]:
        snapshot["hard_flags"].append("PE极高")
        severe_negatives += 3
    elif pe is not None and pe > pe_rules["high_above"]:
        snapshot["hard_flags"].append("PE偏高")
        severe_negatives += 2
    elif pe is not None and pe < pe_rules["value_below"] and roe is not None and roe >= roe_rules["strong_at_or_above"]:
        positive_points += 1

    if pb is not None and pb > pb_rules["mismatch_above"] and roe is not None and roe < pb_rules["weak_roe_below"]:
        snapshot["hard_flags"].append("PB与ROE不匹配")
        severe_negatives += 2

    sector_change = sector_data.get("change_pct") if sector_data else None
    stock_change = rt.get("change_pct")
    if sector_change is not None and stock_change is not None:
        diff = stock_change - sector_change
        if diff < relative_strength_rules["weak_vs_sector_below"]:
            snapshot["hard_flags"].append("弱于行业")
            severe_negatives += 1
        elif diff > relative_strength_rules["strong_vs_sector_above"]:
            positive_points += 1

    if pp:
        pct_from_high = pp.get("pct_from_high")
        pct_from_low = pp.get("pct_from_low")
        if pct_from_high is not None and pct_from_low is not None:
            if (
                pct_from_high > price_position_rules["chase_risk_from_high_above"]
                and pct_from_low > price_position_rules["chase_risk_from_low_above"]
            ):
                snapshot["hard_flags"].append("追高风险")
                severe_negatives += 1

    snapshot["hard_flags"] = _dedupe_keep_order(snapshot["hard_flags"])
    snapshot["positives"] = _dedupe_keep_order(snapshot["positives"])

    if severe_negatives >= action_rules["avoid_severe_negatives_at"]:
        snapshot["action"] = "回避/逢高减仓"
        snapshot["position"] = "0成或只留观察仓"
    elif tech_bias == "bear" or severe_negatives >= action_rules["reduce_severe_negatives_at"]:
        snapshot["action"] = "减仓观望"
        snapshot["position"] = "0-0.5成"
    elif (
        tech_bias == "bull"
        and positive_points >= action_rules["track_positive_points_at"]
        and severe_negatives == 0
    ):
        snapshot["action"] = "轻仓跟踪"
        snapshot["position"] = "0.5-1成"
    else:
        snapshot["action"] = "观望"
        snapshot["position"] = "0-0.5成"

    ma = tech.get("ma", {})
    if rt.get("price") is not None:
        price = rt["price"]
        ma20 = ma.get("MA20")
        ma60 = ma.get("MA60")
        boll = tech.get("boll") or {}
        if tech_bias == "neutral":
            if ma20 is not None and price < ma20:
                snapshot["watch_points"].append(f"先观察能否站回 MA20（{ma20}）")
            elif ma60 is not None and price < ma60:
                snapshot["watch_points"].append(f"中期仍受 MA60（{ma60}）压制")
        if (not flow_reference_only) and "连续" in flow_signal and "流出" in flow_signal:
            snapshot["watch_points"].append("等待主力连续流出先止住")
        if boll.get("lower") is not None and tech_bias == "bear":
            snapshot["watch_points"].append(f"留意布林下轨支撑（{boll['lower']}）")
        if tech_bias == "bull" and sector_change is not None and stock_change is not None and stock_change <= sector_change:
            snapshot["watch_points"].append("技术偏多但尚未明显强于行业，别追高")

    snapshot["watch_points"] = _dedupe_keep_order(snapshot["watch_points"])[:3]
    return snapshot


def format_rule_snapshot(snapshot):
    """格式化规则化快照。"""
    lines = [
        "### 规则化快照",
        "| 项目 | 结论 |",
        "|------|------|",
        f"| 技术基线 | {snapshot.get('tech_base', '中性')} |",
        f"| 资金确认 | {snapshot.get('flow_base', '中性')} |",
        f"| 资金时效 | {(snapshot.get('flow_confidence') or {}).get('label', '未知')} |",
        f"| 事件偏向 | {snapshot.get('event_base', '中性')} |",
        f"| 建议动作 | {snapshot.get('action', '观望')} |",
        f"| 建议仓位 | {snapshot.get('position', '0-0.5成')} |",
    ]

    hard_flags = snapshot.get("hard_flags") or []
    positives = snapshot.get("positives") or []
    watch_points = snapshot.get("watch_points") or []

    if hard_flags:
        lines.append("")
        lines.append("> 硬风险：{}".format("；".join(hard_flags)))
    if positives:
        lines.append("> 正向因素：{}".format("；".join(positives)))
    if watch_points:
        lines.append("> 观察点：{}".format("；".join(watch_points)))
    lines.append("")
    return "\n".join(lines)


def price_tick(value):
    """按价格区间返回 snapping 步长。"""
    if value < 10:
        return 0.05
    if value < 50:
        return 0.1
    return 0.5


def round_price(value):
    tick = price_tick(value)
    decimals = 2 if tick == 0.05 else 1
    return round(round(value / tick) * tick, decimals)


def snap_stop_loss(anchor):
    """将止损位下移一个缓冲并按价格区间对齐。"""
    raw = max(anchor - 0.05, 0.01)
    tick = price_tick(raw)
    decimals = 2 if tick == 0.05 else 1
    snapped = math.floor(raw / tick) * tick
    return round(snapped, decimals)


def select_support_resistance(tech_indicators, realtime, snapshot):
    """根据技术指标自动生成支撑/压力/止损位。"""
    tech = tech_indicators or {}
    rt = realtime or {}
    price = rt.get("price")
    if price is None:
        return None

    ma = tech.get("ma", {})
    boll = tech.get("boll") or {}
    pp = tech.get("price_position") or {}

    support_candidates = []
    resistance_candidates = []

    def add_candidate(target, label, value):
        if value is None or value <= 0:
            return
        target.append((label, float(value)))

    add_candidate(support_candidates, "布林下轨", boll.get("lower"))
    add_candidate(support_candidates, "MA20", ma.get("MA20"))
    add_candidate(support_candidates, "MA10", ma.get("MA10"))
    add_candidate(support_candidates, "20日低点", pp.get("low_20d"))
    add_candidate(support_candidates, "MA5", ma.get("MA5"))

    add_candidate(resistance_candidates, "布林上轨", boll.get("upper"))
    add_candidate(resistance_candidates, "MA60", ma.get("MA60"))
    add_candidate(resistance_candidates, "20日高点", pp.get("high_20d"))
    add_candidate(resistance_candidates, "MA20", ma.get("MA20"))
    add_candidate(resistance_candidates, "MA10", ma.get("MA10"))

    below = [(label, value) for label, value in support_candidates if value <= price]
    above = [(label, value) for label, value in resistance_candidates if value >= price]

    if below:
        support_label, support_value = max(below, key=lambda item: item[1])
    elif support_candidates:
        support_label, support_value = min(support_candidates, key=lambda item: abs(item[1] - price))
    else:
        support_label, support_value = "近端支撑", price * 0.95

    if above:
        resistance_label, resistance_value = min(above, key=lambda item: item[1])
    elif resistance_candidates:
        resistance_label, resistance_value = max(resistance_candidates, key=lambda item: item[1])
    else:
        resistance_label, resistance_value = "近端压力", price * 1.05

    tech_bias = tech.get("backtest_bias", "neutral")
    stop_anchor_label = support_label
    stop_anchor_value = support_value

    if tech_bias == "bull":
        for label, value in [("MA20", ma.get("MA20")), ("布林下轨", boll.get("lower")), ("20日低点", pp.get("low_20d"))]:
            if value is not None and value <= price * 1.03:
                stop_anchor_label, stop_anchor_value = label, value
                break
    elif tech_bias == "bear":
        for label, value in [("布林下轨", boll.get("lower")), ("20日低点", pp.get("low_20d")), ("MA20", ma.get("MA20"))]:
            if value is not None:
                stop_anchor_label, stop_anchor_value = label, value
                break

    stop_loss = snap_stop_loss(stop_anchor_value)
    support_value = round_price(support_value)
    resistance_value = round_price(resistance_value)

    status = "未触发"
    if price <= stop_loss:
        status = "已触发"
    elif price <= support_value:
        status = "接近止损"

    return {
        "support": {"label": support_label, "value": support_value},
        "resistance": {"label": resistance_label, "value": resistance_value},
        "stop_loss": {"label": stop_anchor_label, "value": stop_loss, "status": status},
    }


def format_trade_levels(levels):
    """格式化支撑/压力/止损位。"""
    if not levels:
        return ""
    lines = [
        "### 关键位",
        "| 项目 | 数值 | 依据 |",
        "|------|------|------|",
        f"| 支撑位 | {levels['support']['value']} 元 | {levels['support']['label']} |",
        f"| 压力位 | {levels['resistance']['value']} 元 | {levels['resistance']['label']} |",
        f"| 止损位 | {levels['stop_loss']['value']} 元 | {levels['stop_loss']['label']} |",
        "",
        f"> 止损状态：{levels['stop_loss']['status']}",
        "",
    ]
    return "\n".join(lines)


def build_intraday_triggers(snapshot, trade_levels, realtime, tech_indicators,
                            capital_flow, sector_data):
    """生成盘中触发器。"""
    if not trade_levels or not realtime:
        return []

    snapshot = snapshot or {}
    tech = tech_indicators or {}
    flow = capital_flow or {}
    sector = sector_data or {}

    price = realtime.get("price")
    support = trade_levels["support"]["value"]
    resistance = trade_levels["resistance"]["value"]
    stop_loss = trade_levels["stop_loss"]["value"]
    flow_signal = "多空平衡" if flow.get("intraday_unconfirmed") else flow.get("signal", "多空平衡")
    tech_base = snapshot.get("tech_base", "中性")
    action = snapshot.get("action", "观望")
    hard_flags = snapshot.get("hard_flags", [])
    sector_strength = "与行业持平"
    stock_change = realtime.get("change_pct")
    sector_change = sector.get("change_pct")
    if stock_change is not None and sector_change is not None:
        diff = stock_change - sector_change
        if diff > 0.5:
            sector_strength = "强于行业"
        elif diff < -0.5:
            sector_strength = "弱于行业"

    triggers = []

    defensive_action = "先减仓或离场"
    if "回避" in action or "逢高减仓" in action or tech_base == "看空":
        defensive_action = "直接按纪律离场，不做低吸"

    triggers.append({
        "name": "防守线",
        "condition": f"盘中跌破止损位 {stop_loss} 元",
        "action": defensive_action,
    })

    breakout_action = "可把结论上调一档，考虑 0.5 成以内试错"
    if tech_base == "看空":
        breakout_action = "只视为弱修复，先别翻多，等收盘确认"
    elif tech_base == "中性":
        breakout_action = "可从观望升级为轻仓跟踪，但别追高"

    breakout_condition = f"放量站上压力位 {resistance} 元"
    if sector_strength == "弱于行业":
        breakout_condition += " 且相对行业不再落后"
    triggers.append({
        "name": "突破线",
        "condition": breakout_condition,
        "action": breakout_action,
    })

    confirm_condition = f"回踩不破支撑位 {support} 元"
    confirm_action = "继续观察，不急着加仓"
    if flow_signal.startswith("主力净流入") or ("流入" in flow_signal and "连续" in flow_signal):
        confirm_condition += "，且主力净流入维持为正"
        confirm_action = "可继续持有/观察，等待二次确认"
    elif "流出" in flow_signal:
        confirm_condition += "，但若主力继续流出则不成立"
        confirm_action = "没有资金确认前，不把反弹当反转"
    triggers.append({
        "name": "确认线",
        "condition": confirm_condition,
        "action": confirm_action,
    })

    if any(flag in hard_flags for flag in ["PE极高", "ROE为负", "治理风险", "主力连续5日流出"]):
        triggers.append({
            "name": "风控备注",
            "condition": "即使盘中反弹",
            "action": "也只按反抽看，除非硬风险先消失，否则不升级到重仓",
        })

    return triggers


def format_intraday_triggers(triggers):
    """格式化盘中触发器。"""
    if not triggers:
        return ""
    lines = [
        "### 盘中触发器",
        "| 场景 | 触发条件 | 对应动作 |",
        "|------|----------|----------|",
    ]
    for item in triggers:
        lines.append(f"| {item['name']} | {item['condition']} | {item['action']} |")
    lines.append("")
    return "\n".join(lines)


def _combine_market_timestamp(date_text, time_text):
    if date_text and time_text:
        return f"{date_text} {time_text}"
    return date_text or time_text or None


def build_snapshot_record(stock, snapshot, tech_indicators, trade_levels, intraday_triggers, today,
                          realtime=None, capital_flow=None):
    """构建每日快照记录。"""
    tech = tech_indicators or {}
    rt = realtime or {}
    flow = capital_flow or {}
    flow_confidence = snapshot.get("flow_confidence") or assess_flow_confidence(flow)
    flow_summary = {
        "signal": flow.get("signal"),
        "main_net_wan": flow.get("main_net_wan", flow.get("main_net")),
        "main_net_yi": flow.get("main_net_yi"),
        "today_wan": flow.get("today_wan"),
        "today_yi": flow.get("today_yi"),
        "five_day_total_wan": flow.get("five_day_total_wan"),
        "five_day_total_yi": flow.get("five_day_total_yi"),
        "unit": flow.get("unit"),
    }
    return {
        "date": today,
        "code": stock["code"],
        "name": stock["name"],
        "action": snapshot.get("action"),
        "position": snapshot.get("position"),
        "tech_base": snapshot.get("tech_base"),
        "flow_base": snapshot.get("flow_base"),
        "event_base": snapshot.get("event_base"),
        "score": tech.get("backtest_score"),
        "score_kind": "技术分",
        "signal": tech.get("backtest_signal"),
        "hard_flags": snapshot.get("hard_flags", []),
        "watch_points": snapshot.get("watch_points", []),
        "positives": snapshot.get("positives", []),
        "support": trade_levels["support"]["value"] if trade_levels else None,
        "resistance": trade_levels["resistance"]["value"] if trade_levels else None,
        "stop_loss": trade_levels["stop_loss"]["value"] if trade_levels else None,
        "intraday_triggers": intraday_triggers or [],
        "price_as_of": _combine_market_timestamp(rt.get("date"), rt.get("time")),
        "flow_as_of": flow.get("updated_at") or flow.get("as_of_date"),
        "flow_unconfirmed": bool(flow.get("intraday_unconfirmed")),
        "flow_confidence": flow_confidence,
        "capital_flow": flow_summary,
        "tech_basis": "240分钟K线",
    }


def save_daily_snapshots(today, records, replace_existing=False):
    """保存今日快照。"""
    if not records:
        return
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    path = os.path.join(SNAPSHOT_DIR, f"{today}.json")
    existing = {}
    if os.path.exists(path) and not replace_existing:
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f).get("stocks", {})
            if not isinstance(existing, dict):
                existing = {}
        except (OSError, json.JSONDecodeError):
            existing = {}

    payload = {
        "date": today,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "price_basis": "新浪实时行情",
        "flow_basis": "东方财富资金流",
        "tech_basis": "240分钟K线",
        "stocks": {**existing, **records},
    }
    with open(path, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def parse_report_snapshots(path):
    """从旧版 markdown 报告里提取关键字段，作为快照回退源。"""
    try:
        text = open(path).read()
    except OSError:
        return {}

    pattern = re.compile(r"^##\s+(.+?)（(\d{6})）(?:[^\n]*)\n(.*?)(?=^##\s+|\Z)", re.M | re.S)
    result = {}
    for match in pattern.finditer(text):
        name, code, body = match.groups()
        score = None
        action = None
        position = None
        stop_loss = None

        tech_score_match = re.search(r"技术面[^\n]*评分\s*(-?\d+)", body)
        if tech_score_match:
            score = int(tech_score_match.group(1))

        score_match = re.search(r"综合评分[:：]\s*\**(\d+)", body)
        if score_match:
            overall_score = int(score_match.group(1))
        else:
            overall_score = None

        label_match = re.search(r"综合评分[:：][^\n]*[（(]([^）)\n]+)[）)]", body)
        if label_match:
            action = label_match.group(1).strip()
        else:
            dash_match = re.search(r"综合评分[:：][^\n]*[—-]\s*([^\n]+)", body)
            if dash_match:
                action = dash_match.group(1).strip()

        position_match = re.search(r"\*{0,2}(?:仓位建议|建议仓位)\s*[:：]\s*([^\n*]+)", body)
        if position_match:
            position = position_match.group(1).strip()

        stop_match = re.search(r"\*{0,2}止损位\s*[:：]\s*([^\n*]+)", body)
        if stop_match:
            stop_loss = stop_match.group(1).strip()

        result[code] = {
            "date": os.path.splitext(os.path.basename(path))[0],
            "name": name,
            "score": score,
            "overall_score": overall_score,
            "score_kind": "技术分" if score is not None else "综合评分",
            "action": action,
            "position": position,
            "stop_loss": stop_loss,
        }
    return result


def _load_snapshot_stocks(path):
    try:
        with open(path) as f:
            stocks = json.load(f).get("stocks", {})
        return stocks if isinstance(stocks, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _merge_previous_snapshot_candidates(result, snapshot_map, target_codes=None):
    if not isinstance(snapshot_map, dict):
        return
    for code, payload in snapshot_map.items():
        if target_codes and code not in target_codes:
            continue
        if code not in result and isinstance(payload, dict):
            result[code] = payload


def load_previous_snapshots(today, target_codes=None):
    """按股票代码回溯最近一个可用的历史快照，优先 JSON，其次旧版 markdown 报告。"""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    target_codes = set(target_codes or [])
    result = {}
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_path = os.path.join(SNAPSHOT_DIR, f"{yesterday}.json")
    if os.path.exists(yesterday_path):
        _merge_previous_snapshot_candidates(result, _load_snapshot_stocks(yesterday_path), target_codes)
        if target_codes and target_codes.issubset(result.keys()):
            return result

    snapshot_files = sorted(glob(os.path.join(SNAPSHOT_DIR, "*.json")))
    earlier = [
        path for path in snapshot_files
        if os.path.basename(path)[:10] < today and path != yesterday_path
    ]
    for path in reversed(earlier):
        _merge_previous_snapshot_candidates(result, _load_snapshot_stocks(path), target_codes)
        if target_codes and target_codes.issubset(result.keys()):
            return result

    report_files = sorted(glob(os.path.join(REPORTS_DIR, "analysis-report-*.md")))
    earlier_reports = [path for path in report_files if re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path)).group(1) < today]
    for path in reversed(earlier_reports):
        parsed = parse_report_snapshots(path)
        _merge_previous_snapshot_candidates(result, parsed, target_codes)
        if target_codes and target_codes.issubset(result.keys()):
            return result

    return result


def action_rank(action):
    text = action or ""
    if any(keyword in text for keyword in ["回避", "清仓", "逢高减仓"]):
        return 0
    if "减仓" in text or "偏空" in text:
        return 1
    if "观望" in text:
        return 2
    if any(keyword in text for keyword in ["轻仓跟踪", "偏多", "买入"]):
        return 3
    return 2


def format_snapshot_change(previous_snapshot, current_snapshot):
    """格式化今日 vs 昨日变化。"""
    if not previous_snapshot:
        return "\n".join([
            "### 今日 vs 昨日",
            "> 暂无可用的昨日快照，今天开始已自动记录，明天起会显示变化原因。",
            "",
        ])

    prev_action = previous_snapshot.get("action") or "未知"
    curr_action = current_snapshot.get("action") or "未知"
    prev_position = previous_snapshot.get("position") or "未知"
    curr_position = current_snapshot.get("position") or "未知"

    prev_score = previous_snapshot.get("score")
    curr_score = current_snapshot.get("score")
    score_change = "-"
    if prev_score is not None and curr_score is not None:
        score_change = f"{prev_score} -> {curr_score}"

    prev_rank = action_rank(prev_action)
    curr_rank = action_rank(curr_action)
    if curr_rank > prev_rank:
        direction = "上调"
    elif curr_rank < prev_rank:
        direction = "下调"
    else:
        direction = "持平"

    reasons = []
    if score_change != "-" and prev_score != curr_score:
        reasons.append(f"技术分 {score_change}")

    for key, label in [("tech_base", "技术基线"), ("flow_base", "资金确认"), ("event_base", "事件偏向")]:
        prev_val = previous_snapshot.get(key)
        curr_val = current_snapshot.get(key)
        if prev_val and curr_val and prev_val != curr_val:
            reasons.append(f"{label} {prev_val} -> {curr_val}")

    prev_flags = set(previous_snapshot.get("hard_flags", []))
    curr_flags = set(current_snapshot.get("hard_flags", []))
    new_flags = [flag for flag in current_snapshot.get("hard_flags", []) if flag not in prev_flags]
    removed_flags = [flag for flag in previous_snapshot.get("hard_flags", []) if flag not in curr_flags]

    if new_flags:
        reasons.append(f"新增风险：{'；'.join(new_flags)}")
    if removed_flags:
        reasons.append(f"缓解风险：{'；'.join(removed_flags)}")

    if not reasons and prev_action != curr_action:
        reasons.append(f"建议动作 {prev_action} -> {curr_action}")

    lines = [
        "### 今日 vs 昨日",
        "| 项目 | 变化 |",
        "|------|------|",
        f"| 动作变化 | {prev_action} -> {curr_action} |",
        f"| 仓位变化 | {prev_position} -> {curr_position} |",
        f"| 技术分变化 | {score_change} |",
        f"| 变化方向 | {direction} |",
    ]
    if reasons:
        lines.extend(["", f"> 主要原因：{'；'.join(reasons)}"])
    lines.append("")
    return "\n".join(lines)


def format_stock_report(stock, realtime, news, announcements, xueqiu_discussions,
                        tech_indicators=None, capital_flow=None, fundamentals=None,
                        sector_data=None, current_snapshot=None,
                        trade_levels=None, intraday_triggers=None,
                        previous_snapshot=None):
    """格式化单只股票的Markdown报告"""
    rt = realtime

    lines = [
        f"## {stock['name']}（{stock['code']}）",
        "",
        "### 实时行情",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 现价 | {rt['price']:.2f} 元 |",
        f"| 涨跌幅 | {rt['change_pct']:+.2f}% |",
        f"| 今开 | {rt['open']:.2f} |",
        f"| 最高 | {rt['high']:.2f} |",
        f"| 最低 | {rt['low']:.2f} |",
        f"| 昨收 | {rt['prev_close']:.2f} |",
        f"| 成交量 | {rt['volume']:,} 手 |",
        f"| 成交额 | {rt['amount']/1e8:.2f} 亿元 |",
        "",
    ]

    if announcements:
        lines.append("### 最新公告")
        for a in announcements:
            lines.append(f"- [{a['date']}] {a['title']}")
        lines.append("")

    if news:
        lines.append("### 近期新闻")
        for n in news:
            lines.append(f"- [{n['date']}] {n['title']}")
            if n.get("content"):
                lines.append(f"  > {n['content']}")
        lines.append("")

    if xueqiu_discussions:
        lines.append("### 社区讨论（雪球）")
        for d in xueqiu_discussions:
            tags = ""
            if d.get("likes", 0) > 0:
                tags += f" ❤️{d['likes']}"
            if d.get("replies", 0) > 0:
                tags += f" 💬{d['replies']}"
            lines.append(f"- [{d['date']}] @{d['user']}{tags}")
            lines.append(f"  > {d['text']}")
        lines.append("")

    snapshot = current_snapshot or build_rule_snapshot(
        stock, rt, news, announcements, tech_indicators, capital_flow, fundamentals, sector_data
    )
    lines.append(format_rule_snapshot(snapshot))
    lines.append(format_snapshot_change(previous_snapshot, {
        **snapshot,
        "score": (tech_indicators or {}).get("backtest_score"),
    }))

    # 新增数据源
    if sector_data:
        lines.append(format_sector(stock, sector_data, rt["change_pct"]))

    if tech_indicators:
        lines.append(format_technical_indicators(tech_indicators))

    if trade_levels:
        lines.append(format_trade_levels(trade_levels))

    if intraday_triggers:
        lines.append(format_intraday_triggers(intraday_triggers))

    if capital_flow:
        lines.append(format_capital_flow(capital_flow))

    if fundamentals:
        lines.append(format_fundamentals(fundamentals))

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="stock-analyzer 数据采集")
    parser.add_argument("--codes", nargs="+", help="仅分析指定股票代码，例如 600030 000977")
    parser.add_argument("--skip-snapshot-save", action="store_true", help="只打印报告，不写入 daily_snapshots")
    args = parser.parse_args()

    selected_codes = set(args.codes or [])
    config = load_config(selected_codes=selected_codes if selected_codes else None)
    today = datetime.now().strftime("%Y-%m-%d")
    previous_snapshots = load_previous_snapshots(
        today,
        target_codes={stock["code"] for stock in config["stocks"]},
    )
    current_snapshot_records = {}

    print(f"# 股票分析数据 - {today}\n")

    for stock in config["stocks"]:
        code = stock["code"]
        name = stock["name"]
        sina = stock.get("sina", f"{'sh' if stock.get('market')=='sh' else 'sz'}{code}")
        print(f"[INFO] 正在获取 {name}({code})...", file=sys.stderr)

        try:
            rt = fetch_realtime(sina)
            news = fetch_news(name, code, config.get("news_count", 5))
            anns = fetch_announcements(code, config.get("news_count", 5))

            # 技术指标
            tech = None
            try:
                kline_days = config.get("kline_days", 60)
                tech = fetch_technical_indicators(sina, kline_days)
            except Exception as e:
                print(f"[WARN] 技术指标获取失败: {e}", file=sys.stderr)

            # 资金流向
            flow = None
            try:
                flow = fetch_capital_flow(code, stock.get("market", "sz"))
            except Exception as e:
                print(f"[WARN] 资金流向获取失败: {e}", file=sys.stderr)

            # 基本面数据
            fund = None
            try:
                fund = fetch_fundamentals(code, stock.get("market", "sz"))
            except Exception as e:
                print(f"[WARN] 基本面数据获取失败: {e}", file=sys.stderr)

            # 板块对比数据
            sector = None
            sector_code = stock.get("sector_code")
            if sector_code:
                try:
                    sector = fetch_sector(sector_code)
                except Exception as e:
                    print(f"[WARN] 板块数据获取失败: {e}", file=sys.stderr)

            snapshot = build_rule_snapshot(stock, rt, news, anns, tech, flow, fund, sector)
            trade_levels = select_support_resistance(tech, rt, snapshot)
            intraday_triggers = build_intraday_triggers(snapshot, trade_levels, rt, tech, flow, sector)
            current_snapshot_records[code] = build_snapshot_record(
                stock, snapshot, tech, trade_levels, intraday_triggers, today,
                realtime=rt,
                capital_flow=flow,
            )

            report = format_stock_report(
                stock, rt, news, anns, [], tech, flow, fund, sector,
                current_snapshot=snapshot,
                trade_levels=trade_levels,
                intraday_triggers=intraday_triggers,
                previous_snapshot=previous_snapshots.get(code),
            )
            print(report)
            print("---\n")
        except Exception as e:
            print(f"[ERROR] {name}({code}) 获取失败: {e}", file=sys.stderr)
            print(f"## {name}（{code}）\n\n⚠️ 数据获取失败: {e}\n\n---\n")

    if not args.skip_snapshot_save:
        save_daily_snapshots(today, current_snapshot_records, replace_existing=not selected_codes)


if __name__ == "__main__":
    main()
