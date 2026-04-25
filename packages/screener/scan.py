#!/usr/bin/env python3
"""A股多因子选股扫描（两阶段：新浪初筛→东方财富精选）"""

import os, sys, json, time, random, re, argparse
from pathlib import Path

try:
    from screener.capital_flow_contract import (
        AUTO_UNIT,
        UNIT_YUAN,
        build_capital_flow_payload,
        normalize_capital_flow_row,
        wan_to_yi,
    )
    from screener.parameters import (
        ATTACK_PROFILE_RULES,
        CAPITAL_SCORE_THRESHOLDS,
        EMOTION_SCORE_RULES,
        FUNDAMENTAL_SCORE_RULES,
        MISSING_DATA_PENALTIES,
        OVERHEAT_PENALTY_RULES,
        TRADE_NOTE_RULES,
        build_execution_gate,
        clamp_fundamental_score,
        compute_emotion_score,
        compute_final_score,
        compute_missing_cap_penalty,
        compute_overheat_penalty,
    )
except ModuleNotFoundError:
    from capital_flow_contract import (
        AUTO_UNIT,
        UNIT_YUAN,
        build_capital_flow_payload,
        normalize_capital_flow_row,
        wan_to_yi,
    )
    from parameters import (
        ATTACK_PROFILE_RULES,
        CAPITAL_SCORE_THRESHOLDS,
        EMOTION_SCORE_RULES,
        FUNDAMENTAL_SCORE_RULES,
        MISSING_DATA_PENALTIES,
        OVERHEAT_PENALTY_RULES,
        TRADE_NOTE_RULES,
        build_execution_gate,
        clamp_fundamental_score,
        compute_emotion_score,
        compute_final_score,
        compute_missing_cap_penalty,
        compute_overheat_penalty,
    )

# 清除代理环境变量 — 手动按需启用
for k in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'no_proxy', 'NO_PROXY']:
    os.environ.pop(k, None)
import urllib.request as _ureq

# 无代理 opener（新浪等直连）
_NO_PROXY_OPENER = _ureq.build_opener(_ureq.ProxyHandler({}))
# 走 Clash 代理 opener（东方财富等需要代理的接口）
_PROXY = os.environ.get('PRISM_PROXY_URL', '')
_PROXY_OPENER = _ureq.build_opener(_ureq.ProxyHandler({'http': _PROXY, 'https': _PROXY})) if _PROXY else _NO_PROXY_OPENER

# 默认直连
_ureq.install_opener(_NO_PROXY_OPENER)

from urllib.request import Request, urlopen
from urllib.error import URLError
from datetime import datetime

try:
    import akshare as ak
except Exception:
    ak = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = Path(BASE_DIR).parent
DATA_DIR = SKILL_DIR / 'data'
HISTORY_DIR = DATA_DIR / 'history'
INDEX_CONS_CACHE_DIR = DATA_DIR / 'index_cons_cache'
CAPITAL_FLOW_CACHE_DIR = DATA_DIR / 'capital_flow_cache'
CAPITAL_FLOW_CACHE_TTL_SECONDS = 15 * 60
CAPITAL_FLOW_BATCH_SIZE = 40
FUNDAMENTALS_CACHE_DIR = DATA_DIR / 'fundamentals_cache'
FUNDAMENTALS_CACHE_TTL_SECONDS = 12 * 60 * 60
FUNDAMENTALS_BATCH_SIZE = 40
REALTIME_QUOTE_BATCH_SIZE = 40
H_SINA = {'Referer': 'https://finance.sina.com.cn', 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
H_EM = {'Referer': 'https://data.eastmoney.com', 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}


def http_get(url, headers, timeout=10, retries=1, delay=2, use_proxy=False):
    """通用HTTP GET，支持重试。use_proxy=True 走 Clash 代理"""
    opener = _PROXY_OPENER if use_proxy else _NO_PROXY_OPENER
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers=headers)
            with opener.open(req, timeout=timeout) as r:
                return r.read()
        except (URLError, OSError, Exception) as e:
            if attempt < retries:
                print(f'    [retry] {url[:60]}... ({e}), attempt {attempt+1}/{retries}', file=sys.stderr)
                time.sleep(delay * (attempt + 1))
            else:
                print(f'    [fail] {url[:60]}... ({e})', file=sys.stderr)
                return None


def get_sina(url, timeout=10, retries=2):
    """新浪接口返回GBK编码"""
    raw = http_get(url, H_SINA, timeout=timeout, retries=retries, delay=1)
    if raw is None:
        return None
    return raw.decode('gbk', errors='replace')


def get_em(url, timeout=8, retries=1):
    """东方财富接口返回UTF-8编码，走代理避免IP封锁"""
    raw = http_get(url, H_EM, timeout=timeout, retries=retries, delay=1, use_proxy=True)
    if raw is None:
        return None
    return raw.decode('utf-8', errors='replace')


def get_sina_code(code):
    return f'sh{code}' if code.startswith('6') else f'sz{code}'


def get_em_secid(code):
    return f'1.{code}' if code.startswith('6') else f'0.{code}'


def _safe_float(value, default=0.0):
    if value in (None, '', '-'):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_stage0_stock(raw, source_pool):
    code = str(raw.get('code') or '').strip()
    if code.isdigit():
        code = code.zfill(6)
    name = str(raw.get('name') or '').strip()
    amount = _safe_float(raw.get('amount'), 0)
    if 'ST' in name:
        return None
    if code.startswith('68') or code.startswith('30'):
        return None
    if amount <= 0 or not code:
        return None
    return {
        'code': code,
        'name': name,
        'price': _safe_float(raw.get('price')),
        'prev': _safe_float(raw.get('prev')),
        'open': _safe_float(raw.get('open')),
        'high': _safe_float(raw.get('high')),
        'low': _safe_float(raw.get('low')),
        'change_pct': _safe_float(raw.get('change_pct')),
        'volume': _safe_float(raw.get('volume')),
        'amount': amount,
        'pe': _safe_float(raw.get('pe')),
        'pb': _safe_float(raw.get('pb')),
        'mktcap': _safe_float(raw.get('mktcap')),
        'turnover': _safe_float(raw.get('turnover')),
        'source_pool': source_pool,
    }


def _is_intraday_window():
    now_hm = datetime.now().strftime('%H:%M')
    return '09:20' <= now_hm <= '15:10'


def _capital_flow_cache_path(code):
    return CAPITAL_FLOW_CACHE_DIR / f'{code}.json'


def _normalize_capital_flow_rows(rows, limit=5, source_unit=AUTO_UNIT):
    normalized = {}
    for row in rows or []:
        normalized_row = normalize_capital_flow_row(row, source_unit=source_unit)
        if not normalized_row:
            continue
        normalized[normalized_row['date']] = normalized_row
    ordered = [normalized[date] for date in sorted(normalized)]
    return ordered[-limit:] if limit else ordered


def _load_capital_flow_cache(code):
    path = _capital_flow_cache_path(code)
    if not path.exists():
        return None
    try:
        with path.open('r', encoding='utf-8') as f:
            rows = json.load(f)
        flows = _normalize_capital_flow_rows(rows)
        if not flows:
            return None
        return {
            'flows': flows,
            'age_seconds': max(0, time.time() - path.stat().st_mtime),
        }
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _save_capital_flow_cache(code, flows):
    rows = _normalize_capital_flow_rows(flows)
    if not rows:
        return
    CAPITAL_FLOW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _capital_flow_cache_path(code)
    with path.open('w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def _merge_capital_flow_rows(today_row, cached_flows=None, limit=5):
    combined = list(cached_flows or [])
    if today_row:
        combined.append(today_row)
    return _normalize_capital_flow_rows(combined, limit=limit)


def _parse_em_capital_flow_daykline(klines, limit=5):
    rows = []
    for item in klines or []:
        parts = item.split(',')
        if len(parts) < 3 or not parts[0]:
            continue
        rows.append({
            'date': parts[0],
            'main_net': _safe_float(parts[1]),
            'super_large': _safe_float(parts[2]),
        })
    return _normalize_capital_flow_rows(rows, limit=limit, source_unit=UNIT_YUAN)


def fetch_capital_flow_batch_today(codes):
    """批量获取当日主力资金流快照，降低筛选阶段的逐只请求压力。"""
    if not codes:
        return {}

    today = datetime.now().strftime('%Y-%m-%d')
    snapshot = {}
    deduped_codes = []
    seen = set()
    for code in codes:
        if code and code not in seen:
            deduped_codes.append(code)
            seen.add(code)

    for i in range(0, len(deduped_codes), CAPITAL_FLOW_BATCH_SIZE):
        chunk = deduped_codes[i:i + CAPITAL_FLOW_BATCH_SIZE]
        secids = ','.join(get_em_secid(code) for code in chunk)
        url = (f'https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2'
               f'&secids={secids}&fields=f12,f62,f66')
        text = get_em(url, timeout=8, retries=1)
        if not text:
            continue
        try:
            data = json.loads(text)
            diff = (data.get('data') or {}).get('diff', [])
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue

        for item in diff:
            raw_code = item.get('f12')
            if raw_code in (None, ''):
                continue
            code = str(raw_code)
            if code.isdigit():
                code = code.zfill(6)
            main_raw = item.get('f62')
            super_raw = item.get('f66')
            if main_raw in (None, '-') and super_raw in (None, '-'):
                continue
            normalized_row = normalize_capital_flow_row({
                'date': today,
                'main_net': _safe_float(main_raw),
                'super_large': _safe_float(super_raw),
            }, source_unit=UNIT_YUAN)
            if normalized_row:
                snapshot[code] = normalized_row

        if i + CAPITAL_FLOW_BATCH_SIZE < len(deduped_codes):
            time.sleep(random.uniform(0.15, 0.35))

    return snapshot


def _fetch_capital_flow_history_em(code, limit=5, timeout=6, retries=0):
    secid = get_em_secid(code)
    url = (f'https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get?'
           f'secid={secid}&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56&lmt={limit}')
    text = get_em(url, timeout=timeout, retries=retries)
    if not text:
        return None
    try:
        data = json.loads(text)
        klines = (data.get('data') or {}).get('klines', [])
        rows = _parse_em_capital_flow_daykline(klines, limit=limit)
        return rows or None
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None


def _normalize_fundamentals(result):
    if not isinstance(result, dict):
        return None

    pe = _safe_float(result.get('pe_ttm'), None)
    pb = _safe_float(result.get('pb'), None)
    roe = _safe_float(result.get('roe'), None)
    margin = _safe_float(result.get('margin'), None)
    total_mv = _safe_float(result.get('total_mv'), None)
    industry = result.get('industry') or None
    concept = result.get('concept') or None

    if pe is not None and (pe <= 0 or pe < 3 or pe > 300):
        pe = None
    if pb is not None and (pb <= 0 or pb > 30):
        pb = None
    if roe is not None and (roe < -50 or roe > 60):
        roe = None
    if margin is not None and (margin < 0 or margin > 95):
        margin = None
    if total_mv is not None and total_mv <= 0:
        total_mv = None

    normalized = {
        'pe_ttm': pe,
        'pb': pb,
        'roe': roe,
        'margin': margin,
        'total_mv': total_mv,
        'industry': industry,
        'concept': concept,
    }
    return normalized if any(v is not None for v in normalized.values()) else None


def _merge_fundamentals(*items):
    merged = {
        'pe_ttm': None,
        'pb': None,
        'roe': None,
        'margin': None,
        'total_mv': None,
        'industry': None,
        'concept': None,
    }
    has_value = False
    for item in items:
        normalized = _normalize_fundamentals(item)
        if not normalized:
            continue
        for key, value in normalized.items():
            if value is not None:
                merged[key] = value
                has_value = True
    return merged if has_value else None


def _fundamentals_cache_path(code):
    return FUNDAMENTALS_CACHE_DIR / f'{code}.json'


def _load_fundamentals_cache(code):
    path = _fundamentals_cache_path(code)
    if not path.exists():
        return None
    try:
        with path.open('r', encoding='utf-8') as f:
            cached = json.load(f)
        normalized = _normalize_fundamentals(cached)
        if not normalized:
            return None
        return {
            'fundamentals': normalized,
            'age_seconds': max(0, time.time() - path.stat().st_mtime),
        }
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _save_fundamentals_cache(code, fundamentals):
    normalized = _normalize_fundamentals(fundamentals)
    if not normalized:
        return
    FUNDAMENTALS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _fundamentals_cache_path(code)
    with path.open('w', encoding='utf-8') as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)


def fetch_fundamentals_batch(codes):
    """批量获取 PE/总市值 等更稳的基本面快照。"""
    if not codes:
        return {}

    snapshot = {}
    deduped_codes = []
    seen = set()
    for code in codes:
        if code and code not in seen:
            deduped_codes.append(code)
            seen.add(code)

    for i in range(0, len(deduped_codes), FUNDAMENTALS_BATCH_SIZE):
        chunk = deduped_codes[i:i + FUNDAMENTALS_BATCH_SIZE]
        secids = ','.join(get_em_secid(code) for code in chunk)
        url = (f'https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2'
               f'&secids={secids}&fields=f12,f9,f20')
        text = get_em(url, timeout=8, retries=1)
        if not text:
            continue
        try:
            data = json.loads(text)
            diff = (data.get('data') or {}).get('diff', [])
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue

        for item in diff:
            raw_code = item.get('f12')
            if raw_code in (None, ''):
                continue
            code = str(raw_code)
            if code.isdigit():
                code = code.zfill(6)
            pe_raw = item.get('f9')
            mv_raw = item.get('f20')
            normalized = _normalize_fundamentals({
                'pe_ttm': _safe_float(pe_raw, None) if pe_raw not in (None, '', '-') else None,
                'pb': None,
                'roe': None,
                'margin': None,
                'total_mv': _safe_float(mv_raw, None) / 1e8 if mv_raw not in (None, '', '-') else None,
                'industry': None,
                'concept': None,
            })
            if normalized:
                snapshot[code] = normalized

        if i + FUNDAMENTALS_BATCH_SIZE < len(deduped_codes):
            time.sleep(random.uniform(0.12, 0.3))

    return snapshot


def fetch_realtime_quotes_batch(codes):
    """批量获取实时行情快照，用于指数成分兜底源补齐成交额/换手/估值。"""
    if not codes:
        return {}

    snapshot = {}
    deduped_codes = []
    seen = set()
    for code in codes:
        if code and code not in seen:
            deduped_codes.append(code)
            seen.add(code)

    for i in range(0, len(deduped_codes), REALTIME_QUOTE_BATCH_SIZE):
        chunk = deduped_codes[i:i + REALTIME_QUOTE_BATCH_SIZE]
        secids = ','.join(get_em_secid(code) for code in chunk)
        url = (f'https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2'
               f'&secids={secids}&fields=f12,f14,f2,f3,f17,f15,f16,f5,f6,f8,f9,f20,f18')
        text = get_em(url, timeout=8, retries=1)
        if not text:
            continue
        try:
            data = json.loads(text)
            diff = (data.get('data') or {}).get('diff', [])
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue

        for item in diff:
            raw_code = item.get('f12')
            if raw_code in (None, ''):
                continue
            code = str(raw_code)
            if code.isdigit():
                code = code.zfill(6)
            snapshot[code] = {
                'code': code,
                'name': item.get('f14') or '',
                'price': _safe_float(item.get('f2')),
                'change_pct': _safe_float(item.get('f3')),
                'open': _safe_float(item.get('f17')),
                'high': _safe_float(item.get('f15')),
                'low': _safe_float(item.get('f16')),
                'volume': _safe_float(item.get('f5')) * 100,  # 东方财富 f5 为手
                'amount': _safe_float(item.get('f6')),
                'turnover': _safe_float(item.get('f8')),
                'pe': _safe_float(item.get('f9')),
                'mktcap': _safe_float(item.get('f20')),
                'prev': _safe_float(item.get('f18')),
            }

        if i + REALTIME_QUOTE_BATCH_SIZE < len(deduped_codes):
            time.sleep(random.uniform(0.12, 0.3))

    return snapshot


def _index_cons_cache_path(source_pool):
    return INDEX_CONS_CACHE_DIR / f'{source_pool}.json'


def _save_index_cons_cache(source_pool, rows):
    normalized = []
    seen = set()
    for row in rows or []:
        code = str((row or {}).get('code') or '').strip()
        if code.isdigit():
            code = code.zfill(6)
        if not code or code in seen:
            continue
        seen.add(code)
        normalized.append({
            'code': code,
            'name': str((row or {}).get('name') or '').strip(),
        })
    if not normalized:
        return
    INDEX_CONS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _index_cons_cache_path(source_pool)
    with path.open('w', encoding='utf-8') as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)


def _load_index_cons_cache(source_pool):
    path = _index_cons_cache_path(source_pool)
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []
    normalized = []
    seen = set()
    for row in rows or []:
        code = str((row or {}).get('code') or '').strip()
        if code.isdigit():
            code = code.zfill(6)
        if not code or code in seen:
            continue
        seen.add(code)
        normalized.append({
            'code': code,
            'name': str((row or {}).get('name') or '').strip(),
        })
    return normalized


def _load_index_cons_from_cache(source_pool):
    cached = _load_index_cons_cache(source_pool)
    if not cached:
        return []
    realtime = fetch_realtime_quotes_batch([row['code'] for row in cached if row.get('code')])
    all_stocks = []
    for row in cached:
        code = row.get('code')
        if not code:
            continue
        quote = realtime.get(code)
        if not quote:
            continue
        normalized = _normalize_stage0_stock({
            **quote,
            'name': row.get('name') or quote.get('name') or '',
        }, source_pool)
        if normalized:
            all_stocks.append(normalized)
    return all_stocks


def fetch_announcements(code, count=5):
    """抓取东方财富公告标题，用于风险标签识别。"""
    url = (
        "https://np-anotice-stock.eastmoney.com/api/security/ann"
        f"?sr=-1&page_size={count}&page_index=1"
        f"&ann_type=A&client_source=web&stock_list={code}"
    )
    text = get_em(url, timeout=8, retries=1)
    if text is None:
        return []
    try:
        data = json.loads(text)
        items = data.get('data', {}).get('list', [])
        result = []
        for item in items[:count]:
            title = item.get('title', '')
            clean_title = re.sub(r'^[\w\u4e00-\u9fff]+[:：]', '', title).strip()
            result.append({
                'date': item.get('notice_date', '')[:10],
                'title': clean_title or title,
                'source': item.get('source', '东方财富'),
            })
        return result
    except Exception:
        return []


def classify_notice_risk(announcements):
    """公告标题风险标签分类：减持/质押/诉讼/处罚/业绩预警/董监高变动。"""
    risk_map = {
        '减持': ['减持', '拟减持', '持股5%以上股东减持', '股份减持'],
        '质押': ['质押', '补充质押', '解除质押'],
        '诉讼': ['诉讼', '仲裁', '涉诉'],
        '处罚': ['处罚', '监管函', '警示函', '立案', '调查'],
        '业绩预警': ['预亏', '预减', '业绩预告', '亏损', '商誉减值'],
        '董监高变动': ['辞职', '董事会换届', '监事会换届', '高管变动', '董事长变更'],
    }
    hits = []
    for item in announcements or []:
        title = item.get('title', '')
        for label, keywords in risk_map.items():
            if any(k in title for k in keywords):
                hits.append({'label': label, 'title': title, 'date': item.get('date')})
                break
    return hits


# ── Stage 0: 股票池成分股+行情（新浪一条龙） ──

def _load_index_cons_with_em_quotes(symbol, source_pool):
    """官方指数成分 + 东方财富批量实时快照，用于新浪 node 失效时兜底。"""
    if ak is None:
        print(f'  [warn] akshare unavailable, cannot fallback {source_pool} {symbol}', file=sys.stderr)
        return []

    try:
        df = ak.index_stock_cons_csindex(symbol=symbol)
    except Exception as e:
        print(f'  [warn] akshare csindex {symbol} failed: {e}', file=sys.stderr)
        return []

    if df is None or df.empty:
        return []

    rows = df.to_dict(orient='records')
    codes = []
    name_map = {}
    for row in rows:
        code = str(row.get('成分券代码') or '').strip()
        if code.isdigit():
            code = code.zfill(6)
        if not code:
            continue
        codes.append(code)
        name_map[code] = (row.get('成分券名称') or '').strip()

    realtime = fetch_realtime_quotes_batch(codes)
    all_stocks = []
    seen = set()
    for code in codes:
        if code in seen:
            continue
        seen.add(code)
        quote = realtime.get(code)
        if not quote:
            continue
        normalized = _normalize_stage0_stock({
            **quote,
            'name': name_map.get(code) or quote.get('name') or '',
        }, source_pool)
        if normalized:
            all_stocks.append(normalized)
    return all_stocks


def _load_index_cons_with_sina_quotes(symbol, source_pool):
    """AkShare-Sina 指数成分行情兜底，适合 000300/000905 这类少数主流指数。"""
    if ak is None:
        return []

    try:
        df = ak.index_stock_cons_sina(symbol=symbol)
    except Exception as e:
        print(f'  [warn] akshare sina-index {symbol} failed: {e}', file=sys.stderr)
        return []

    if df is None or df.empty:
        return []

    rows = df.to_dict(orient='records')
    realtime = fetch_realtime_quotes_batch([
        str(row.get('code') or '').zfill(6)
        for row in rows
        if row.get('code')
    ])
    all_stocks = []
    seen = set()
    for row in rows:
        code = str(row.get('code') or '').strip()
        if code.isdigit():
            code = code.zfill(6)
        if not code or code in seen:
            continue
        seen.add(code)
        extra = realtime.get(code, {})
        normalized = _normalize_stage0_stock({
            'code': code,
            'name': row.get('name') or extra.get('name') or '',
            'price': _safe_float(row.get('trade')) or extra.get('price'),
            'prev': _safe_float(row.get('settlement')) or extra.get('prev'),
            'open': _safe_float(row.get('open')) or extra.get('open'),
            'high': _safe_float(row.get('high')) or extra.get('high'),
            'low': _safe_float(row.get('low')) or extra.get('low'),
            'change_pct': _safe_float(row.get('changepercent')) or extra.get('change_pct'),
            'volume': _safe_float(row.get('volume')) or extra.get('volume'),
            'amount': _safe_float(row.get('amount')) or extra.get('amount'),
            'turnover': extra.get('turnover'),
            'pe': extra.get('pe'),
            'mktcap': extra.get('mktcap'),
            'pb': extra.get('pb'),
        }, source_pool)
        if normalized:
            all_stocks.append(normalized)
    return all_stocks

def load_node_with_quotes(node, pages=3):
    """从新浪获取指定板块成分股+实时行情（含PE/PB/市值）"""
    all_stocks = []
    seen = set()
    for page in range(1, pages + 1):
        url = (f'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
               f'Market_Center.getHQNodeData?page={page}&num=100&sort=changepercent&asc=0&node={node}&symbol=')
        text = get_sina(url, timeout=15, retries=2)
        if text is None:
            print(f'  [warn] 新浪 {node} page{page}失败，跳过', file=sys.stderr)
            time.sleep(0.5)
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            print(f'  [warn] 新浪 {node} page{page} JSON解析失败', file=sys.stderr)
            continue
        for item in data:
            code = str(item.get('code', '') or '')
            if code in seen:
                continue
            normalized = _normalize_stage0_stock({
                'code': code,
                'name': item.get('name', ''),
                'price': item.get('trade', 0),
                'prev': item.get('settlement', 0),
                'open': item.get('open', 0),
                'high': item.get('high', 0),
                'low': item.get('low', 0),
                'change_pct': item.get('changepercent', 0),
                'volume': item.get('volume', 0),
                'amount': item.get('amount', 0),
                'pe': item.get('per', 0),
                'pb': item.get('pb', 0),
                'mktcap': item.get('mktcap', 0),
                'turnover': item.get('turnoverratio', 0),
            }, node)
            if not normalized:
                continue
            seen.add(code)
            all_stocks.append(normalized)
        time.sleep(0.3)
    return all_stocks


def load_hs300_with_quotes():
    hs300 = load_node_with_quotes('hs300', pages=3)
    if hs300:
        _save_index_cons_cache('hs300', hs300)
        return hs300
    print('  [fallback] 新浪 hs300 节点为空，改用中证成分 + 东方财富快照', file=sys.stderr)
    hs300 = _load_index_cons_with_em_quotes('000300', 'hs300')
    if hs300:
        _save_index_cons_cache('hs300', hs300)
        return hs300
    print('  [fallback] 中证 000300 + EM 失败，改用 AkShare-Sina 000300', file=sys.stderr)
    hs300 = _load_index_cons_with_sina_quotes('000300', 'hs300')
    if hs300:
        _save_index_cons_cache('hs300', hs300)
        return hs300
    print('  [fallback] hs300 实时成分源全部失败，改用本地缓存成分 + 东方财富快照', file=sys.stderr)
    return _load_index_cons_from_cache('hs300')


def load_zz500_with_quotes():
    zz500 = load_node_with_quotes('zz500', pages=6)
    if zz500:
        _save_index_cons_cache('zz500', zz500)
        return zz500
    print('  [fallback] 新浪 zz500 节点为空，改用中证成分 + 东方财富快照', file=sys.stderr)
    zz500 = _load_index_cons_with_em_quotes('000905', 'zz500')
    if zz500:
        _save_index_cons_cache('zz500', zz500)
        return zz500
    print('  [fallback] 中证 000905 + EM 失败，改用 AkShare-Sina 000905', file=sys.stderr)
    zz500 = _load_index_cons_with_sina_quotes('000905', 'zz500')
    if zz500:
        _save_index_cons_cache('zz500', zz500)
        return zz500
    print('  [fallback] zz500 实时成分源全部失败，改用本地缓存成分 + 东方财富快照', file=sys.stderr)
    return _load_index_cons_from_cache('zz500')


def load_aggressive_pool_with_quotes():
    """进攻型股票池：中证500 + 沪深300（主板可交易范围内提高弹性）"""
    hs300 = load_node_with_quotes('hs300', pages=3)
    if not hs300:
        hs300 = load_hs300_with_quotes()
    zz500 = load_zz500_with_quotes()

    merged = {}
    for stock in hs300 + zz500:
        code = stock['code']
        if code not in merged:
            merged[code] = stock
        else:
            merged[code]['source_pool'] = f"{merged[code].get('source_pool', '')}+{stock.get('source_pool', '')}".strip('+')

    def is_too_defensive(s):
        name = s.get('name', '')
        # 进攻型扫描里，主动排除极防守方向
        defensive_keywords = ['银行', '保险', '高速', '港口', '机场', '电力', '燃气', '铁路', '运营']
        return any(k in name for k in defensive_keywords)

    def has_min_attack_profile(s):
        # 基础攻击性门槛：活跃度、换手、振幅至少满足其一，避免“池子进攻，结果防守”
        turnover = s.get('turnover', 0) or 0
        change_pct = abs(s.get('change_pct', 0) or 0)
        intraday_amp = 0
        if s.get('prev'):
            intraday_amp = ((s.get('high', 0) - s.get('low', 0)) / s['prev']) * 100
        return (
            s.get('amount', 0) >= 5e8 and (
                turnover >= 2.0 or
                change_pct >= 1.5 or
                intraday_amp >= 3.0 or
                'zz500' in s.get('source_pool', '')
            )
        )

    aggressive = [
        s for s in merged.values()
        if not is_too_defensive(s) and has_min_attack_profile(s)
    ]
    return aggressive


# ── Stage 1: 新浪K线技术面初筛 ──

def fetch_sina_kline(code, days=20):
    """新浪日K线，带重试"""
    sina_code = get_sina_code(code)
    url = (f'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/'
           f'CN_MarketData.getKLineData?symbol={sina_code}&scale=240&ma=no&datalen={days}')
    text = get_sina(url, timeout=10, retries=2)
    if text is None:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        # 兼容 eval 风格返回
        if text.strip().startswith('['):
            return eval(text)
        return []
    except (json.JSONDecodeError, SyntaxError):
        return []


def stage1_screener(raw_stocks):
    """Stage1: K线技术面初筛，返回候选列表"""
    print('  [Stage1] 新浪数据初筛...', file=sys.stderr)
    print(f'  [Stage1] 活跃: {len(raw_stocks)}只', file=sys.stderr)

    # 进攻型更强调成交活跃、涨跌弹性与换手
    def pre_rank_score(x):
        intraday_amp = 0
        if x.get('prev'):
            intraday_amp = ((x.get('high', 0) - x.get('low', 0)) / x['prev']) * 100
        return (
            x['amount'] * 0.55 +
            abs(x.get('change_pct', 0)) * 1e8 * 8 +
            (x.get('turnover', 0) or 0) * 1e8 * 12 +
            intraday_amp * 1e8 * 6
        )

    sorted_stocks = sorted(raw_stocks, key=pre_rank_score, reverse=True)
    top60 = sorted_stocks[:60]

    print(f'  [Stage1] 拉取K线(top60)...', file=sys.stderr)
    candidates = []
    for i, stock in enumerate(top60):
        klines = fetch_sina_kline(stock['code'], 20)
        time.sleep(random.uniform(0.1, 0.3))

        if len(klines) < 10:
            continue

        closes = [float(k['close']) for k in klines]
        highs = [float(k['high']) for k in klines]
        lows = [float(k['low']) for k in klines]
        volumes = [float(k['volume']) for k in klines]

        tech_score = 0
        signals = []

        # 均线多头排列
        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else 0
        if closes[-1] > ma5 > ma10 > ma20 > 0:
            tech_score += 14
            signals.append('均线强多头')
        elif closes[-1] > ma5 > ma10:
            tech_score += 10
            signals.append('均线多头')
        elif closes[-1] > ma5:
            tech_score += 4
            signals.append('站上MA5')

        chg = stock['change_pct']

        # 放量
        if len(volumes) >= 2 and volumes[-1] > volumes[-2] * 1.8:
            tech_score += 10
            signals.append('强放量')
        elif len(volumes) >= 2 and volumes[-1] > volumes[-2] * 1.5:
            tech_score += 8
            signals.append('放量')
        elif len(volumes) >= 2 and volumes[-1] > volumes[-2] * 1.2:
            tech_score += 4

        # 涨幅信号
        if chg > 7:
            tech_score += 10
            signals.append('强势拉升')
        elif chg > 5:
            tech_score += 8
        elif chg > 2:
            tech_score += 5
        elif chg > 0:
            tech_score += 2

        # 成交活跃 + 换手弹性
        if stock['amount'] > 15e8:
            tech_score += 5
        elif stock['amount'] > 8e8:
            tech_score += 3
        elif stock['amount'] > 5e8:
            tech_score += 2

        turnover = stock.get('turnover', 0) or 0
        if turnover > 8:
            tech_score += 8
            signals.append('高换手')
        elif turnover > 5:
            tech_score += 6
        elif turnover > 3:
            tech_score += 4
        elif turnover > 2:
            tech_score += 2

        # 低位反弹 / 趋势突破
        high20 = max(highs[-20:])
        low20 = min(lows[-20:])
        pos = (closes[-1] - low20) / (high20 - low20) if high20 > low20 else 0.5
        if pos < 0.3 and chg > 1:
            tech_score += 6
            signals.append('低位反弹')
        elif pos > 0.75 and chg > 2:
            tech_score += 6
            signals.append('接近突破')

        if tech_score >= 14:
            candidates.append({
                **stock,
                'tech_score': tech_score,
                'tech_signals': signals,
                'ma5': round(ma5, 2), 'ma10': round(ma10, 2), 'ma20': round(ma20, 2),
                'high20': high20, 'low20': low20,
                'position_20d': round(pos, 3),
                'kline': klines[-5:],
            })

        if (i + 1) % 20 == 0:
            print(f'    K线进度: {i + 1}/60', file=sys.stderr)

    candidates.sort(key=lambda x: x['tech_score'], reverse=True)
    return candidates[:30]


# ── Stage 2: 东方财富资金+基本面精选 ──

def fetch_capital_flow(code, prefetched_today=None):
    """资金流主路：优先批量/缓存拿到今日快照，失败时回退历史或旧快照。"""
    today = datetime.now().strftime('%Y-%m-%d')
    cache_entry = _load_capital_flow_cache(code)
    cached_flows = cache_entry['flows'] if cache_entry else None

    if cache_entry and cached_flows[-1]['date'] == today and cache_entry['age_seconds'] <= CAPITAL_FLOW_CACHE_TTL_SECONDS:
        return cached_flows, 'eastmoney-cache'

    today_row = prefetched_today
    source = 'eastmoney-batch'
    if not today_row:
        single_snapshot = fetch_capital_flow_batch_today([code])
        today_row = single_snapshot.get(code)
        source = 'eastmoney'

    if today_row:
        merged = _merge_capital_flow_rows(today_row, cached_flows)
        if len(merged) < 2 and _is_intraday_window():
            hist = _fetch_capital_flow_history_em(code, limit=5, timeout=6, retries=0)
            if hist:
                merged = hist
                source = 'eastmoney-history'
        if merged:
            _save_capital_flow_cache(code, merged)
            return merged, source

    hist = _fetch_capital_flow_history_em(code, limit=5, timeout=10, retries=1)
    if hist:
        _save_capital_flow_cache(code, hist)
        return hist, 'eastmoney-history'

    if cached_flows:
        return cached_flows, 'eastmoney-stale-cache'

    return None, 'none'


def _ths_get(url, timeout=15):
    """同花顺页面请求（用 urllib，走直连）"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html',
    }
    req = Request(url, headers=headers)
    resp = urlopen(req, timeout=timeout)
    if resp.status != 200:
        return None
    return resp.read().decode('utf-8', errors='ignore')


def fetch_capital_flow_ths(code):
    """同花顺 fallback：从个股页面抓取当日资金流"""
    try:
        text = _ths_get(f'https://stockpage.10jqka.com.cn/{code}/')
        if not text:
            return None

        # 从页面提取总流入、总流出、净额
        import re
        inflow_match = re.search(r'总流入[：:](\s*<[^>]*>)*(\d[\d.]*)', text)
        outflow_match = re.search(r'总流出[：:](\s*<[^>]*>)*(\d[\d.]*)', text)
        net_match = re.search(r'净[\s]*额[：:](\s*<[^>]*>)*(\d[\d.]*)', text)

        net_val = None
        if net_match:
            net_val = float(net_match.group(2)) * 1e4  # 万元 → 元
        elif inflow_match and outflow_match:
            inflow = float(inflow_match.group(2))
            outflow = float(outflow_match.group(2))
            net_val = (inflow - outflow) * 1e4

        if net_val is not None:
            today = datetime.now().strftime('%Y-%m-%d')
            return [normalize_capital_flow_row({'date': today, 'main_net': net_val, 'super_large': 0}, source_unit=UNIT_YUAN)]
    except Exception as e:
        print(f'    [ths-fallback] capital flow failed for {code}: {e}', file=sys.stderr)
    return None


def fetch_fundamentals_ths(code, base_funda=None):
    """同花顺 fallback：从个股页面抓取基本面，结合 EM 市值算 PE/PB"""
    try:
        text = _ths_get(f'https://stockpage.10jqka.com.cn/{code}/')
        if not text:
            return None

        result = {}

        # 每股收益
        eps_match = re.search(r'每股收益[：:]\s*</dt>\s*<dd>([\d.-]+)元', text)
        eps = float(eps_match.group(1)) if eps_match else None

        # 净利润
        profit_match = re.search(r'净利润[：:]\s*</dt>\s*<dd>([\d.-]+)亿元', text)
        if profit_match:
            result['net_profit'] = float(profit_match.group(1))

        # 营业收入
        rev_match = re.search(r'营业收入[：:]\s*</dt>\s*<dd>([\d.-]+)亿元', text)
        if rev_match:
            result['revenue'] = float(rev_match.group(1))

        # 总股本
        shares_match = re.search(r'总股本[：:]\s*</dt>\s*<dd>([\d.]+)亿', text)
        total_shares = float(shares_match.group(1)) if shares_match else None

        # 每股净资产
        bvps_match = re.search(r'每股净资产[：:]\s*</dt>\s*<dd>([\d.]+)元', text)

        # 尝试从东方财富 ulist 获取总市值（这个接口比较稳定）
        total_mv = None
        merged_base = _merge_fundamentals(
            (_load_fundamentals_cache(code) or {}).get('fundamentals'),
            base_funda,
        )
        if merged_base and merged_base.get('total_mv'):
            total_mv = merged_base['total_mv']
        else:
            batch_result = fetch_fundamentals_batch([code]).get(code)
            if batch_result and batch_result.get('total_mv'):
                total_mv = batch_result['total_mv']

        # 用总市值 + EPS 算 PE
        if total_mv and total_shares and eps and eps > 0:
            price = total_mv / total_shares
            pe = price / eps
            if 3 <= pe <= 300:
                result['pe_ttm'] = round(pe, 2)
            result['total_mv'] = total_mv
        elif total_mv:
            result['total_mv'] = total_mv

        # 用总市值 + 每股净资产算 PB
        if total_mv and total_shares and bvps_match:
            bvps = float(bvps_match.group(1))
            price = total_mv / total_shares
            if bvps > 0:
                result['pb'] = round(price / bvps, 2)

        if result:
            return _merge_fundamentals(base_funda, result)
    except Exception as e:
        print(f'    [ths-fallback] fundamentals failed for {code}: {e}', file=sys.stderr)
    return None


def fetch_capital_flow_with_fallback(code, prefetched_today=None):
    """资金流：东方财富单日/历史 → 同花顺页面 fallback。
    优先保证“今天主力是否流入”可用，其次才追求历史完整性。
    """
    result, source = fetch_capital_flow(code, prefetched_today=prefetched_today)
    if result:
        return result, source
    print(f'    [fallback] EM capital failed for {code}, trying THS...', file=sys.stderr)
    result = fetch_capital_flow_ths(code)
    if result:
        cache_entry = _load_capital_flow_cache(code)
        merged = _merge_capital_flow_rows(result[-1], cache_entry['flows'] if cache_entry else None)
        if merged:
            _save_capital_flow_cache(code, merged)
            return merged, 'ths'
        return result, 'ths'
    return None, 'none'


def fetch_fundamentals_with_fallback(code, prefetched=None):
    """基本面：东方财富 → 同花顺 fallback"""
    result, source = fetch_fundamentals(code, prefetched=prefetched)
    # 只有 PE 或 PB 至少有一个有效值才算成功
    if result and (result.get('pe_ttm') or result.get('pb')):
        return result, source
    # EM 失败或关键字段缺失，尝试 THS
    if result:
        print(f'    [fallback] EM funda returned but pe/pb missing for {code}, trying THS...', file=sys.stderr)
    else:
        print(f'    [fallback] EM funda failed for {code}, trying THS...', file=sys.stderr)
    ths_result = fetch_fundamentals_ths(code, base_funda=result)
    if ths_result:
        _save_fundamentals_cache(code, ths_result)
        return ths_result, 'ths'
    return result, source  # 都失败了返回东方财富原始结果


def fetch_fundamentals(code, prefetched=None):
    """基本面数据：优先批量快照+缓存，必要时才打 stock/get。"""
    cache_entry = _load_fundamentals_cache(code)
    cached_funda = cache_entry['fundamentals'] if cache_entry else None

    if prefetched:
        merged = _merge_fundamentals(cached_funda, prefetched)
        if merged:
            _save_fundamentals_cache(code, merged)
            return merged, 'eastmoney-batch-cache' if cached_funda else 'eastmoney-batch'

    if cache_entry and cache_entry['age_seconds'] <= FUNDAMENTALS_CACHE_TTL_SECONDS:
        return cached_funda, 'eastmoney-cache'

    if not prefetched:
        batch_result = fetch_fundamentals_batch([code]).get(code)
        if batch_result:
            merged = _merge_fundamentals(cached_funda, batch_result)
            _save_fundamentals_cache(code, merged)
            return merged, 'eastmoney-batch'

    secid = get_em_secid(code)
    url = (f'https://push2.eastmoney.com/api/qt/stock/get?'
           f'secid={secid}&fields=f43,f57,f58,f116,f127,f128,f163,f167,f168,f169,f170')
    text = get_em(url, timeout=8, retries=1)
    if text:
        try:
            data = json.loads(text)
            d = data.get('data', {})
            normalized = _normalize_fundamentals({
                'pe_ttm': _safe_float(d.get('f163'), None) / 100 if d.get('f163') not in (None, 0, '-') else None,
                'pb': _safe_float(d.get('f168'), None) / 100 if d.get('f168') not in (None, 0, '-') else None,
                'roe': _safe_float(d.get('f169'), None) / 100 if d.get('f169') not in (None, 0, '-') else None,
                'margin': _safe_float(d.get('f170'), None) / 100 if d.get('f170') not in (None, 0, '-') else None,
                'total_mv': _safe_float(d.get('f116'), None) / 1e8 if d.get('f116') not in (None, 0, '-') else None,
                'industry': d.get('f127') or None,
                'concept': d.get('f128') or None,
            })
            merged = _merge_fundamentals(cached_funda, normalized)
            if merged:
                _save_fundamentals_cache(code, merged)
                return merged, 'eastmoney-stock-get'
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass

    if cached_funda:
        return cached_funda, 'eastmoney-stale-cache'
    return None, 'none'



def calc_fund_score(funda):
    """基本面评分 (轻权重)，仅对可信值打分"""
    score = 0
    signals = []
    if not funda:
        return score, signals

    pe = funda.get('pe_ttm')
    roe = funda.get('roe')
    margin = funda.get('margin')

    if pe is not None:
        if 8 <= pe <= 20:
            score += 6
            signals.append(f'PE偏低({pe:.1f})')
        elif 20 < pe <= 35:
            score += 4
            signals.append(f'PE合理({pe:.1f})')
        elif 35 < pe <= 60:
            score += 1
        elif 80 < pe <= 300:
            score -= 5
            signals.append(f'PE偏高({pe:.1f})')

    if roe is not None:
        if roe > 15:
            score += 8
            signals.append(f'ROE优秀({roe:.1f}%)')
        elif roe > 10:
            score += 5
            signals.append(f'ROE良好({roe:.1f}%)')
        elif 0 < roe < 5:
            score -= 3
            signals.append(f'ROE偏弱({roe:.1f}%)')

    if margin is not None:
        if margin > 25:
            score += 6
            signals.append(f'毛利率高({margin:.1f}%)')
        elif margin > 15:
            score += 3

    return score, signals


def calc_cap_score(flows):
    """资金面评分 (0-30)"""
    score = 0
    signals = []
    if not flows:
        return score, signals

    today = _safe_float(flows[-1].get('main_net'))
    for rule in CAPITAL_SCORE_THRESHOLDS['today_flow_wan']:
        if today > rule['above']:
            score += rule['score']
            signal = rule.get('signal')
            if signal:
                signals.append(
                    signal.format(
                        value_wan=today,
                        value_yi=wan_to_yi(today),
                    )
                )
            break

    consecutive = 0
    for f in flows[::-1]:
        if _safe_float(f.get('main_net')) > 0:
            consecutive += 1
        else:
            break
    for rule in CAPITAL_SCORE_THRESHOLDS['consecutive_inflow_days']:
        if consecutive >= rule['at_least']:
            score += rule['score']
            signal = rule.get('signal')
            if signal:
                signals.append(signal.format(days=consecutive))
            break

    reversal_rule = CAPITAL_SCORE_THRESHOLDS['reversal']
    if (
        len(flows) >= 2
        and _safe_float(flows[-2].get('main_net')) < reversal_rule['previous_day_below']
        and today > reversal_rule['today_above']
    ):
        score += reversal_rule['score']
        signals.append(reversal_rule['signal'])

    return score, signals


def build_trade_note(stock):
    flows = stock.get('flows') or []
    today_flow = _safe_float(flows[-1].get('main_net')) if flows else 0
    pos20 = stock.get('position_20d', 0.5)
    chg = stock.get('change_pct', 0) or 0
    turnover = stock.get('turnover', 0) or 0
    amount_yi = (stock.get('amount', 0) or 0) / 1e8
    pe = _get_pe(stock)
    note_rules = TRADE_NOTE_RULES

    reasons = []
    primary_reason_rules = note_rules['reasons']['primary']
    if (
        pos20 >= primary_reason_rules['trend_breakout']['position_20d_at_least']
        and today_flow > primary_reason_rules['trend_breakout']['today_flow_above']
    ):
        reasons.append(primary_reason_rules['trend_breakout']['text'])
    elif (
        pos20 <= primary_reason_rules['low_rebound']['position_20d_at_most']
        and chg > primary_reason_rules['low_rebound']['change_pct_above']
    ):
        reasons.append(primary_reason_rules['low_rebound']['text'])
    elif today_flow > primary_reason_rules['flow_driven']['today_flow_above']:
        reasons.append(primary_reason_rules['flow_driven']['text'])
    else:
        reasons.append(primary_reason_rules['default'])

    secondary_reason_rules = note_rules['reasons']['secondary']
    if turnover >= secondary_reason_rules['turnover']['at_least']:
        reasons.append(secondary_reason_rules['turnover']['text'])
    if amount_yi >= secondary_reason_rules['amount_yi']['at_least']:
        reasons.append(secondary_reason_rules['amount_yi']['text'])

    risks = []
    risk_rules = note_rules['risks']
    if (
        chg >= risk_rules['high_move_breakout']['change_pct_at_least']
        and pos20 >= risk_rules['high_move_breakout']['position_20d_at_least']
    ):
        risks.append(risk_rules['high_move_breakout']['text'])
    if (
        turnover >= risk_rules['blowoff']['turnover_at_least']
        and chg >= risk_rules['blowoff']['change_pct_at_least']
    ):
        risks.append(risk_rules['blowoff']['text'])
    if pe and pe > risk_rules['high_pe']['pe_above']:
        risks.append(risk_rules['high_pe']['text'])
    style_text = _get_style_text(stock)
    if any(k in style_text for k in risk_rules['style_volatility']['keywords']):
        risks.append(risk_rules['style_volatility']['text'])
    if not risks:
        risks.append(risk_rules['default'])

    watch = []
    watch_rules = note_rules['watch']
    if pos20 >= watch_rules['trend_breakout']['position_20d_at_least']:
        watch.extend(watch_rules['trend_breakout']['items'])
    else:
        watch.extend(watch_rules['general']['items'])
    if today_flow > watch_rules['flow_positive']['today_flow_above']:
        watch.append(watch_rules['flow_positive']['text'])
    else:
        watch.append(watch_rules['flow_non_positive']['text'])

    return {
        'entry_reason': ' + '.join(reasons[:2]),
        'main_risk': '；'.join(risks[:2]),
        'watch_condition': '；'.join(watch[:3]),
    }


def stage2_enrich(candidates):
    """Stage2: 对初筛候选拉资金+基本面"""
    print(f'  [Stage2] 东方财富精选({len(candidates)}只)...', file=sys.stderr)
    codes = [stock['code'] for stock in candidates]
    prefetched_flow_map = fetch_capital_flow_batch_today(codes)
    prefetched_funda_map = fetch_fundamentals_batch(codes)
    if prefetched_flow_map:
        print(f'    [capital-flow] 批量预取命中 {len(prefetched_flow_map)}/{len(codes)}', file=sys.stderr)
    if prefetched_funda_map:
        print(f'    [fundamentals] 批量预取命中 {len(prefetched_funda_map)}/{len(codes)}', file=sys.stderr)
    enriched = []
    for i, stock in enumerate(candidates):
        flows, flow_src = fetch_capital_flow_with_fallback(
            stock['code'],
            prefetched_today=prefetched_flow_map.get(stock['code']),
        )
        if 'cache' in flow_src or flow_src.startswith('eastmoney-batch'):
            time.sleep(random.uniform(0.12, 0.25))
        else:
            time.sleep(random.uniform(0.8, 1.2))
        funda, funda_src = fetch_fundamentals_with_fallback(
            stock['code'],
            prefetched=prefetched_funda_map.get(stock['code']),
        )
        if 'cache' in funda_src or funda_src.startswith('eastmoney-batch'):
            time.sleep(random.uniform(0.08, 0.18))
        else:
            time.sleep(random.uniform(0.5, 0.8))

        stock['flows'] = flows
        stock['fundamentals'] = funda
        stock['announcements'] = fetch_announcements(stock['code'], count=5)
        stock['notice_risk_tags'] = classify_notice_risk(stock['announcements'])
        stock['has_capital_flow'] = bool(flows)
        stock['flow_source'] = flow_src
        stock['funda_source'] = funda_src

        cap_score, cap_signals = calc_cap_score(flows)
        fund_score, fund_signals = calc_fund_score(funda)

        # 情绪面评分 (0-20)
        chg = stock['change_pct']
        amt = stock['amount']
        turnover = stock.get('turnover', 0) or 0
        emotion_score = compute_emotion_score(change_pct=chg, amount=amt, turnover=turnover)

        # 进攻型不鼓励“基本面平庸但巨大权重白马”霸榜，因此基本面只保留轻权重
        fund_score = clamp_fundamental_score(fund_score)

        # 资金流缺失时，明确做轻微降权，避免误把“无数据”当中性
        missing_cap_penalty = compute_missing_cap_penalty(has_capital_flow=bool(flows))

        # 过热惩罚：高位+大涨+爆量/高换手，防止纯情绪高潮票霸榜
        # 新增：连续涨停/接近涨停的退潮惩罚，避免把高潮末端当成机会
        pos20 = stock.get('position_20d', 0.5)
        overheat_penalty, overheat_tags = compute_overheat_penalty(
            position_20d=pos20,
            change_pct=chg,
            turnover=turnover,
        )

        stock['cap_score'] = cap_score
        stock['cap_signals'] = cap_signals
        stock['fund_score'] = fund_score
        stock['fund_signals'] = fund_signals
        stock['emotion_score'] = emotion_score
        stock['missing_cap_penalty'] = missing_cap_penalty
        stock['overheat_penalty'] = overheat_penalty
        stock['overheat_tags'] = overheat_tags

        # 进攻型总分：技术优先 + 资金优先 + 情绪增强 + 基本面轻权重
        stock['final_score'] = compute_final_score(
            tech_score=stock['tech_score'],
            capital_score=cap_score,
            emotion_score=stock['emotion_score'],
            fundamental_score=fund_score,
            missing_cap_penalty=missing_cap_penalty,
            overheat_penalty=overheat_penalty,
        )
        stock['trade_note'] = build_trade_note(stock)
        if stock.get('notice_risk_tags'):
            notice_labels = ' / '.join(sorted({x['label'] for x in stock['notice_risk_tags']}))
            base_risk = stock['trade_note'].get('main_risk', '')
            notice_prefix = TRADE_NOTE_RULES['risks']['notice_prefix']
            stock['trade_note']['main_risk'] = f"{notice_prefix}{notice_labels}" + (f"；{base_risk}" if base_risk else '')

        enriched.append(stock)
        if (i + 1) % 10 == 0:
            print(f'    精选进度: {i + 1}/{len(candidates)}', file=sys.stderr)

    enriched.sort(key=lambda x: x['final_score'], reverse=True)
    return enriched


def classify_theme(stock):
    """把个股归类到更高一层的主线主题：行业优先，概念次之，名字只做兜底"""
    f = stock.get('fundamentals') or {}
    industry = f.get('industry') or ''
    concept = f.get('concept') or ''
    name = stock.get('name', '') or ''

    theme_map = [
        ('AI硬件链', {
            'industry': ['元件', '光学光电子', '消费电子', '半导体', '电子化学品', '通信设备'],
            'concept': ['算力', '服务器', 'CPO', 'PCB', 'AI硬件', '铜连接', '光模块'],
            'name': ['工业富联', '鹏鼎', '沪电', '生益', '长电', '中兴通讯', '深南电路']
        }),
        ('AI信息链', {
            'industry': ['通信服务', '软件开发', '计算机设备', '互联网服务', 'IT服务'],
            'concept': ['云计算', '数据中心', '人工智能', '算力', '运营商', '信创'],
            'name': ['浪潮信息', '紫光股份', '中际旭创', '中科曙光']
        }),
        ('消费电子链', {
            'industry': ['消费电子', '电子元件'],
            'concept': ['苹果概念', '消费电子', '无线耳机'],
            'name': ['立讯精密', '歌尔', '蓝思科技']
        }),
        ('光伏链', {
            'industry': ['光伏设备'],
            'concept': ['光伏', 'TOPCon', 'HJT', 'BC电池', '钙钛矿', '逆变器'],
            'name': ['通威股份', '爱旭股份', '德业股份', '隆基绿能', '晶澳科技', 'TCL中环', '福斯特', '大全能源']
        }),
        ('新能源链', {
            'industry': ['能源金属', '电池', '电池化学品', '风电设备', '油气开采', '油气开采Ⅱ'],
            'concept': ['锂电池', '储能', '新能源车', '风电', '油气改革', '盐湖提锂'],
            'name': ['赣锋锂业', '天齐锂业', '华友钴业', '恩捷股份', '宁德时代', '中国海油', '盐湖股份']
        }),
        ('有色资源链', {
            'industry': ['工业金属', '小金属', '贵金属', '钢铁', '普钢'],
            'concept': ['有色金属', '黄金', '稀土永磁', '钢铁'],
            'name': ['中国铝业', '洛阳钼业', '紫金矿业', '中金黄金', '山东黄金', '北方稀土', '包钢股份']
        }),
        ('军工链', {
            'industry': ['军工电子', '军工电子Ⅱ', '航天装备', '航空装备', '地面兵装'],
            'concept': ['军工', '大飞机', '卫星导航'],
            'name': ['中航', '航发', '洪都']
        }),
        ('汽车链', {
            'industry': ['汽车整车', '汽车零部件', '摩托车及其他', '汽车服务'],
            'concept': ['新能源车', '智能驾驶', '无人驾驶', '汽车热管理'],
            'name': ['比亚迪', '长安汽车', '赛力斯', '德赛西威', '拓普集团', '潍柴动力']
        }),
        ('化工材料链', {
            'industry': ['化学原料', '化学制品', '化学纤维', '塑料制品', '玻璃玻纤'],
            'concept': ['磷化工', '氟化工', '化工原料', '玻纤'],
            'name': ['中国巨石', '万华化学', '卫星化学', '新和成']
        }),
        ('建材链', {
            'industry': ['装修建材', '建筑材料', '水泥建材'],
            'concept': ['建材', '防水材料', '装配式建筑'],
            'name': ['东方雨虹', '北新建材', '海螺水泥', '伟星新材', '三棵树']
        }),
        ('农业养殖链', {
            'industry': ['养殖业', '饲料', '农产品加工', '种植业与林业'],
            'concept': ['猪肉', '鸡肉', '养殖', '饲料', '农业'],
            'name': ['牧原股份', '温氏股份', '海大集团', '新希望', '圣农发展']
        }),
        ('工程机械链', {
            'industry': ['工程机械', '专用设备'],
            'concept': ['工程机械', '基建'],
            'name': ['徐工机械', '三一重工']
        }),
        ('电网设备链', {
            'industry': ['电网设备', '其他电源设备', '电机'],
            'concept': ['特高压', '智能电网', '输配电'],
            'name': ['东方电气', '特变电工', '许继电气']
        }),
        ('高端制造链', {
            'industry': ['自动化设备', '通用设备', '专用设备'],
            'concept': ['工业母机', '机器人', '自动化'],
            'name': ['北方华创', '汇川技术', '埃斯顿']
        }),
        ('游戏传媒链', {
            'industry': ['游戏', '文化传媒', '影视院线'],
            'concept': ['网络游戏', '短剧游戏', '传媒', 'AIGC'],
            'name': ['三七互娱', '恺英网络', '分众传媒']
        }),
    ]

    def normalize_text(text):
        return (text or '').replace(' ', '').replace('　', '')

    def hit(text, keys):
        norm = normalize_text(text)
        return any(k and normalize_text(k) in norm for k in keys)

    for theme, rules in theme_map:
        if hit(industry, rules.get('industry', [])):
            return theme
    for theme, rules in theme_map:
        if hit(concept, rules.get('concept', [])):
            return theme
    for theme, rules in theme_map:
        if hit(name, rules.get('name', [])):
            return theme
    return '其他'


def _load_recent_theme_history(limit=3):
    """读取最近历史扫描中的主题结果，用于持续性判断。"""
    results = []
    if not HISTORY_DIR.exists():
        return results

    files = sorted(HISTORY_DIR.glob('aggressive_all_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        try:
            with path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            market_themes = data.get('market_themes') or {}
            themes = market_themes.get('themes') or []
            if not themes:
                continue
            results.append({
                'path': path.name,
                'timestamp': data.get('timestamp'),
                'themes': themes,
            })
            if len(results) >= limit:
                break
        except Exception:
            continue
    return list(reversed(results))


def _build_theme_history_map(history_snapshots):
    history_map = {}
    for snap in history_snapshots:
        for item in snap.get('themes') or []:
            theme = item.get('theme')
            if not theme:
                continue
            history_map.setdefault(theme, []).append(item)
    return history_map


def assess_market_themes(stocks):
    """识别今日主线方向：看候选集中度、龙头强度、资金集中度、结构完整度、风格纯度"""
    if not stocks:
        return {
            'top_theme': None,
            'summary': '无候选，无法判断主线。',
            'themes': []
        }

    history_snapshots = _load_recent_theme_history(limit=3)
    history_map = _build_theme_history_map(history_snapshots)

    groups = {}
    weighted_total = 0
    for s in stocks:
        theme = classify_theme(s)
        s['theme'] = theme
        attack_profile = s.get('attack_profile') or {}
        weight = max(0.6, min(1.8, (s.get('final_score', 0) or 0) / 60))
        if s.get('final_score', 0) >= 85:
            weight += 0.35
        if s.get('final_score', 0) >= 92:
            weight += 0.2
        # 进攻风格纯的票，再给一点权重；降级票减一点
        if attack_profile.get('status') == 'keep':
            weight += 0.12
        elif attack_profile.get('status') == 'downgrade':
            weight -= 0.08
        groups.setdefault(theme, []).append((s, weight))
        weighted_total += weight

    theme_results = []
    for theme, pairs in groups.items():
        pairs = sorted(pairs, key=lambda x: x[0].get('final_score', 0), reverse=True)
        items = [x[0] for x in pairs]
        weights = [x[1] for x in pairs]
        leaders = items[:3]
        weighted_count = sum(weights)
        top1 = leaders[0].get('final_score', 0) if leaders else 0
        top3_avg = sum(x.get('final_score', 0) for x in leaders) / len(leaders) if leaders else 0
        total_flow = sum(((x.get('flows') or [{}])[-1].get('main_net', 0) if x.get('flows') else 0) for x in items)
        avg_flow = total_flow / max(len(items), 1)

        preferred_weight = 0
        keep_weight = 0
        hot_weight = 0
        for x, w in pairs:
            ap = x.get('attack_profile') or {}
            if ap.get('is_preferred'):
                preferred_weight += w
            if ap.get('status') == 'keep':
                keep_weight += w
            if x.get('change_pct', 0) >= 5 and ((x.get('flows') or [{}])[-1].get('main_net', 0) if x.get('flows') else 0) > 0:
                hot_weight += w

        preferred_ratio = preferred_weight / max(weighted_count, 1)
        keep_ratio = keep_weight / max(weighted_count, 1)
        hot_ratio = hot_weight / max(weighted_count, 1)

        # 1) 候选数量分（25）— 按高分权重计
        count_score = min(25, round((weighted_count / max(weighted_total, 1)) * 100 * 0.7, 2))
        # 2) 龙头强度分（25）
        leader_score = min(25, round(top1 * 0.16 + top3_avg * 0.1, 2))
        # 3) 资金集中度分（20）
        capital_score = min(20, round(wan_to_yi(max(total_flow, 0)) * 0.16 + wan_to_yi(max(avg_flow, 0)) * 0.08, 2))
        # 4) 结构完整度分（15）
        structure_score = 0
        if len(items) >= 3:
            structure_score += 8
        elif len(items) >= 2:
            structure_score += 5
        if len(leaders) >= 2 and leaders[1].get('final_score', 0) >= leaders[0].get('final_score', 0) * 0.82:
            structure_score += 4
        if len(leaders) >= 3 and leaders[2].get('final_score', 0) >= leaders[0].get('final_score', 0) * 0.7:
            structure_score += 3
        structure_score = min(15, structure_score)
        # 5) 风格纯度分（15）
        purity_score = round(preferred_ratio * 7 + keep_ratio * 5 + hot_ratio * 3, 2)
        if theme in ['AI硬件链', 'AI信息链', '军工链', '新能源链', '光伏链']:
            purity_score = min(15, purity_score + 1.5)
        elif theme in ['有色资源链']:
            purity_score = min(15, purity_score + 0.5)
        elif theme == '其他':
            purity_score = min(2.5, purity_score)
        purity_score = min(15, purity_score)

        base_score = round(count_score + leader_score + capital_score + structure_score + purity_score, 2)

        # 6) 主题持续性分（20）
        # v2：叠加最近历史快照，观察主题是否延续增强、龙头是否稳定、热度是否衰减
        history_items = history_map.get(theme, [])
        prev_item = history_items[-1] if history_items else None
        prev2_item = history_items[-2] if len(history_items) >= 2 else None

        persistence_score = 0
        if len(items) >= 3:
            persistence_score += 4
        elif len(items) >= 2:
            persistence_score += 2
        if keep_ratio >= 0.75:
            persistence_score += 3
        elif keep_ratio >= 0.55:
            persistence_score += 2
        if preferred_ratio >= 0.5:
            persistence_score += 2
        if avg_flow > 0:
            persistence_score += 2
        if top3_avg >= top1 * 0.82:
            persistence_score += 2
        elif top3_avg >= top1 * 0.72:
            persistence_score += 1
        if hot_ratio >= 0.65:
            persistence_score -= 2
        elif hot_ratio <= 0.25:
            persistence_score += 1

        trend_notes = []
        trend_state = 'neutral'
        leader_stability = 0.0
        if prev_item:
            prev_weighted = float(prev_item.get('weighted_count', 0) or 0)
            prev_score = float(prev_item.get('score', 0) or 0)
            prev_leaders = set(prev_item.get('leader_codes') or [])
            curr_leaders = {f"{x.get('name','')}({x.get('code','')})" for x in leaders}
            overlap = len(prev_leaders & curr_leaders)
            leader_stability = round(overlap / max(len(curr_leaders), 1), 2)

            if weighted_count >= prev_weighted * 1.08:
                persistence_score += 3
                trend_notes.append('主题权重增强')
                trend_state = 'up'
            elif prev_weighted > 0 and weighted_count <= prev_weighted * 0.9:
                persistence_score -= 2
                trend_notes.append('主题权重回落')
                trend_state = 'down'

            if base_score >= prev_score + 4:
                persistence_score += 2
                trend_notes.append('主题分提升')
                trend_state = 'up'
            elif base_score <= prev_score - 4:
                persistence_score -= 2
                trend_notes.append('主题分回落')
                trend_state = 'down'

            if overlap >= 2:
                persistence_score += 3
                trend_notes.append('龙头稳定')
            elif overlap == 1:
                persistence_score += 1
                trend_notes.append('龙头部分延续')
            else:
                persistence_score -= 2
                trend_notes.append('龙头切换较快')

        if prev2_item and prev_item:
            prev2_weighted = float(prev2_item.get('weighted_count', 0) or 0)
            prev_weighted = float(prev_item.get('weighted_count', 0) or 0)
            if prev2_weighted > 0 and prev_weighted > 0:
                if weighted_count >= prev_weighted >= prev2_weighted * 0.95:
                    persistence_score += 2
                    trend_notes.append('连续两段维持')
                elif weighted_count < prev_weighted < prev2_weighted:
                    persistence_score -= 2
                    trend_notes.append('连续两段衰减')
                    trend_state = 'down'

        persistence_score = max(0, min(20, round(persistence_score, 2)))
        if persistence_score >= 16:
            persistence_label = '持续增强'
        elif persistence_score >= 12:
            persistence_label = '强势延续'
        elif persistence_score >= 8:
            persistence_label = '延续但分化'
        elif persistence_score >= 5:
            persistence_label = '热度衰减'
        else:
            persistence_label = '一日游风险'

        persistence_summary = '；'.join(trend_notes[:3]) if trend_notes else '更多依赖当前截面强度，历史延续性一般'

        score = base_score
        # 压制“其他”：除非明显遥遥领先，否则不让它轻易当主线
        if theme == '其他':
            score = round(score * 0.72, 2)

        theme_results.append({
            'theme': theme,
            'score': score,
            'count': len(items),
            'weighted_count': round(weighted_count, 2),
            'leader_codes': [f"{x.get('name','')}({x.get('code','')})" for x in leaders],
            'persistence': {
                'score': persistence_score,
                'label': persistence_label,
                'summary': persistence_summary,
                'trend': trend_state,
                'leader_stability': leader_stability,
            },
            'metrics': {
                'count_score': count_score,
                'leader_score': leader_score,
                'capital_score': capital_score,
                'structure_score': structure_score,
                'purity_score': purity_score,
                'persistence_score': persistence_score,
                'total_flow_yi': wan_to_yi(total_flow),
                'avg_flow_yi': wan_to_yi(avg_flow),
                'preferred_ratio': round(preferred_ratio, 2),
                'keep_ratio': round(keep_ratio, 2),
                'hot_ratio': round(hot_ratio, 2),
            }
        })

    theme_results.sort(key=lambda x: x['score'], reverse=True)

    # “其他”默认不参与主线竞争，除非内部也形成明显强结构
    if theme_results and theme_results[0]['theme'] == '其他':
        other = theme_results[0]
        strong_other = (
            other.get('count', 0) >= 4 and
            other.get('score', 0) >= 72 and
            len(other.get('leader_codes', [])) >= 2
        )
        if not strong_other:
            theme_results = sorted(theme_results, key=lambda x: (x['theme'] == '其他', -x['score']))

    top_theme = theme_results[0]['theme'] if theme_results else None

    if len(theme_results) >= 2 and theme_results[0]['score'] - theme_results[1]['score'] <= 6:
        summary = f"今日偏双主线：主攻 {theme_results[0]['theme']}，次主线 {theme_results[1]['theme']}。"
    elif theme_results and theme_results[0]['score'] >= 58:
        summary = f"今日主线较清晰，主攻方向偏 {theme_results[0]['theme']}。"
    else:
        summary = '今日主线不够集中，更像轮动市，适合精选个股。'

    if theme_results:
        p = theme_results[0].get('persistence', {})
        summary += f" 主线持续性：{p.get('label', '未知')}（{p.get('score', 0)}分）。"

    return {
        'top_theme': top_theme,
        'summary': summary,
        'themes': theme_results[:6],
    }


# ── 策略筛选 ──

def _get_pe(stock):
    """获取PE：优先东方财富，回退新浪"""
    f = stock.get('fundamentals')
    if f and f.get('pe_ttm') is not None:
        return f['pe_ttm']
    return stock.get('pe', 0) or 0


def _consecutive_inflows(flows):
    """计算连续流入天数"""
    if not flows:
        return 0
    c = 0
    for f in flows[::-1]:
        if f['main_net'] > 0:
            c += 1
        else:
            break
    return c


def _detect_volume_divergence(stock, lookback=10):
    """检测量价背离，返回 (type, strength)。

    顶背离定义：近5日价格创新高/走强，但近5日均量较前段明显萎缩。
    strength: 1-3，数值越大表示背离越强。
    """
    klines = stock.get('klines') or []
    if len(klines) < lookback + 5:
        return 'none', 0

    try:
        closes = [float(x.get('close', 0) or 0) for x in klines]
        volumes = [float(x.get('volume', 0) or 0) for x in klines]
    except Exception:
        return 'none', 0

    recent_closes = closes[-5:]
    prev_closes = closes[-lookback:-5]
    recent_volumes = volumes[-5:]
    prev_volumes = volumes[-lookback:-5]
    if not prev_closes or not prev_volumes:
        return 'none', 0

    recent_high = max(recent_closes)
    prev_high = max(prev_closes)
    recent_vol = sum(recent_volumes) / len(recent_volumes)
    prev_vol = sum(prev_volumes) / len(prev_volumes)
    if prev_vol <= 0:
        return 'none', 0

    price_up = recent_high > prev_high * 1.02
    volume_down = recent_vol < prev_vol * 0.7
    if not (price_up and volume_down):
        return 'none', 0

    shrink_ratio = max(0.0, 1 - recent_vol / prev_vol)
    strength = 1
    if shrink_ratio >= 0.45:
        strength = 3
    elif shrink_ratio >= 0.35:
        strength = 2
    return 'top_diverge', strength


def _get_style_text(stock):
    f = stock.get('fundamentals') or {}
    style_parts = [f.get('industry'), f.get('concept')]
    if not any(style_parts):
        name = stock.get('name', '')
        keyword_rules = ATTACK_PROFILE_RULES['style_keywords']
        fallback_keywords = (
            keyword_rules['preferred']
            + keyword_rules['weak']
            + keyword_rules['cyclical_soft']
        )
        hit = [k for k in fallback_keywords if k in name]
        if hit:
            style_parts.append('name:' + '/'.join(hit[:2]))
    style_parts.append(stock.get('name', ''))
    return ' | '.join([x for x in style_parts if x])


def classify_attack_profile(stock):
    """进攻型三档筛选：保留 / 降级 / 淘汰"""
    turnover = stock.get('turnover', 0) or 0
    chg = stock.get('change_pct', 0) or 0
    pos20 = stock.get('position_20d', 0.5)
    flows = stock.get('flows') or []
    today_flow = _safe_float(flows[-1].get('main_net')) if flows else 0
    pe = _get_pe(stock)
    style_text = _get_style_text(stock)

    rules = ATTACK_PROFILE_RULES
    keyword_rules = rules['style_keywords']
    style_rules = rules['style']

    bias = 0
    tags = []
    is_preferred = False
    is_weak = False
    is_cyclical_soft = False

    for k in keyword_rules['preferred']:
        if k in style_text:
            bias += style_rules['preferred']['delta']
            is_preferred = True
            tags.append(f"{style_rules['preferred']['tag_prefix']}{k}")
            break
    for k in keyword_rules['weak']:
        if k in style_text:
            bias += style_rules['weak']['delta']
            is_weak = True
            tags.append(f"{style_rules['weak']['tag_prefix']}{k}")
            break
    for k in keyword_rules['cyclical_soft']:
        if k in style_text:
            bias += style_rules['cyclical_soft']['delta']
            is_cyclical_soft = True
            tags.append(f"{style_rules['cyclical_soft']['tag_prefix']}{k}")
            break

    turnover_rules = rules['turnover']
    if turnover >= turnover_rules['high']['at_least']:
        bias += turnover_rules['high']['delta']
        tags.append(turnover_rules['high']['tag'])
    elif turnover < turnover_rules['too_low']['below']:
        bias += turnover_rules['too_low']['delta']
        tags.append(turnover_rules['too_low']['tag'])
    elif turnover < turnover_rules['low_pulse']['below'] and chg >= turnover_rules['low_pulse']['change_pct_at_least']:
        bias += turnover_rules['low_pulse']['delta']
        tags.append(turnover_rules['low_pulse']['tag'])

    diverge_type, diverge_strength = _detect_volume_divergence(stock)
    if diverge_type == 'top_diverge':
        divergence_rules = rules['divergence']
        bias += divergence_rules['top_diverge_multiplier'] * diverge_strength
        tags.append(divergence_rules['tag_template'].format(strength=diverge_strength))

    if len(flows) >= 2:
        prev_flow = _safe_float(flows[-2].get('main_net'))
        transition_rules = rules['flow_transition']
        if today_flow < transition_rules['negative_with_rise']['today_flow_below'] and chg > transition_rules['negative_with_rise']['change_pct_above']:
            bias += transition_rules['negative_with_rise']['delta']
            tags.append(transition_rules['negative_with_rise']['tag'])
        elif today_flow > transition_rules['repair']['today_flow_above'] and prev_flow < transition_rules['repair']['previous_flow_below']:
            bias += transition_rules['repair']['delta']
            tags.append(transition_rules['repair']['tag'])

    change_rules = rules['change_pct']
    if chg >= change_rules['strong']['at_least']:
        bias += change_rules['strong']['delta']
        tags.append(change_rules['strong']['tag'])
    elif chg < change_rules['weak']['below']:
        bias += change_rules['weak']['delta']
        tags.append(change_rules['weak']['tag'])

    consecutive_in = _consecutive_inflows(flows)
    flow_today_rules = rules['flow_today']
    if today_flow > flow_today_rules['positive']['above']:
        bias += flow_today_rules['positive']['delta']
        tags.append(flow_today_rules['positive']['tag'])
    elif flows:
        bias += flow_today_rules['non_positive']['delta']
        tags.append(flow_today_rules['non_positive']['tag'])
    else:
        bias += flow_today_rules['missing']['delta']
        tags.append(flow_today_rules['missing']['tag'])

    consecutive_rules = rules['consecutive_inflows']
    if consecutive_in >= consecutive_rules['multi_day']['at_least']:
        bias += consecutive_rules['multi_day']['delta']
        tags.append(consecutive_rules['multi_day']['tag'].format(days=consecutive_in))
    elif consecutive_in == consecutive_rules['single_day']['equals']:
        bias += consecutive_rules['single_day']['delta']
        tags.append(consecutive_rules['single_day']['tag'])
    elif flows and today_flow <= 0:
        bias += consecutive_rules['non_positive_penalty']['delta']

    position_rules = rules['position_20d']
    if pos20 >= position_rules['breakout']['at_least']:
        bias += position_rules['breakout']['delta']
        tags.append(position_rules['breakout']['tag'])
    elif pos20 <= position_rules['low']['at_most']:
        bias += position_rules['low']['delta']
        tags.append(position_rules['low']['tag'])
    elif pos20 >= position_rules['mid_high']['at_least']:
        bias += position_rules['mid_high']['delta']
        tags.append(position_rules['mid_high']['tag'])

    valuation_rules = rules['valuation']
    if pe and pe > valuation_rules['high_pe']['above']:
        bias += valuation_rules['high_pe']['delta']
        tags.append(valuation_rules['high_pe']['tag'])

    # 强制负面规则：把“不够纯的进攻票”打下去
    hard_exclude = False
    hard_rules = rules['hard_rules']
    if is_weak:
        hard_exclude = True
        tags.append(hard_rules['weak_style_exclude_tag'])
    if is_cyclical_soft and today_flow <= 0:
        bias += hard_rules['cyclical_negative']['delta']
        tags.append(hard_rules['cyclical_negative']['tag'])
    if is_cyclical_soft and not is_preferred and consecutive_in == 0:
        bias += hard_rules['cyclical_non_resonance']['delta']
        tags.append(hard_rules['cyclical_non_resonance']['tag'])
    if not is_preferred and today_flow <= 0 and chg < 5:
        bias += hard_rules['non_preferred_no_flow']['delta']
        tags.append(hard_rules['non_preferred_no_flow']['tag'])

    status = 'keep'
    status_rules = rules['status']
    reason = status_rules['reasons']['keep']
    if hard_exclude or bias <= status_rules['exclude_at_or_below']:
        status = 'exclude'
        reason = status_rules['reasons']['exclude']
    elif bias <= status_rules['downgrade_at_or_below']:
        status = 'downgrade'
        reason = status_rules['reasons']['downgrade']

    return {
        'status': status,
        'bias_score': bias,
        'tags': tags[:5],
        'reason': reason,
        'is_preferred': is_preferred,
        'is_cyclical_soft': is_cyclical_soft,
        'consecutive_inflows': consecutive_in,
        'style_text': style_text,
    }


def filter_strategy(stocks, strategy):
    results = []
    for s in stocks:
        pool = s.get('source_pool', '')
        pe = _get_pe(s)
        flows = s.get('flows') or []
        f = s.get('fundamentals')
        roe = (f or {}).get('roe')
        turnover = s.get('turnover', 0) or 0
        pos20 = s.get('position_20d', 0.5)
        attack_profile = classify_attack_profile(s)
        s['attack_profile'] = attack_profile

        # 进攻型公共偏好：尽量回避过于防守、低弹性的票
        aggressive_blocklist = ['银行', '保险', '高速', '港口', '机场', '电力', '燃气', '铁路', '运营']
        if any(k in s.get('name', '') for k in aggressive_blocklist):
            continue
        if s.get('change_pct', 0) < 0:
            continue
        if s.get('amount', 0) < 4e8:
            continue
        if turnover < 1.8 and 'zz500' not in pool:
            continue
        if attack_profile['status'] == 'exclude':
            continue

        if strategy == 'conservative':
            if not roe or roe < 12:
                continue
            if not (8 <= pe <= 25):
                continue
            if _consecutive_inflows(flows) < 3:
                continue

        elif strategy == 'growth':
            if s['change_pct'] <= 2:
                continue
            if s['amount'] <= 5e8:
                continue
            if turnover < 2.5:
                continue
            if not (10 <= pe <= 80):
                continue
            if pos20 < 0.45:
                continue
            if attack_profile['status'] != 'keep':
                continue
            if attack_profile.get('consecutive_inflows', 0) < 1 and (flows[-1]['main_net'] if flows else 0) <= 0:
                continue
            if attack_profile.get('is_cyclical_soft') and not attack_profile.get('is_preferred'):
                continue
            if 'zz500' not in pool and turnover < 3.5:
                continue

        elif strategy == 'rebound':
            if len(flows) < 3:
                continue
            prev_out = all(flows[j]['main_net'] < 0 for j in range(max(0, len(flows) - 4), len(flows) - 1))
            today_in = flows[-1]['main_net'] > 0
            if not (prev_out and today_in):
                continue
            if pos20 > 0.55:
                continue

        elif strategy == 'hot':
            if s['change_pct'] < 3:
                continue
            if flows and flows[-1]['main_net'] < 3000:
                continue
            if turnover < 3:
                continue
            if attack_profile['status'] == 'downgrade':
                continue
            if attack_profile.get('is_cyclical_soft') and not attack_profile.get('is_preferred'):
                continue

        if attack_profile['status'] == 'downgrade':
            s = {**s, 'final_score': round(s['final_score'] - 6, 2)}
        results.append(s)
    return results


def _calc_trend(flows, today_flow):
    """计算资金流向趋势文字描述"""
    if not flows:
        return '无数据'
    c = _consecutive_inflows(flows)
    if c >= 2:
        return f'连续{c}日流入'
    if len(flows) >= 2 and flows[-2]['main_net'] < 0 and today_flow > 0:
        return '由负转正'
    if today_flow > 0:
        return '今日流入'
    return 'mixed'


def assess_market_regime(stocks, basis='candidate'):
    """简易市场环境判断：决定今天是否适合进攻。

    basis:
    - pool: 股票池全样本，更接近真实环境口径
    - candidate: 已入围候选，更适合观察候选强度
    """
    if not stocks:
        return {
            'score': 0,
            'label': '数据不足',
            'attack_ok': False,
            'regime': 'defensive',
            'summary': '样本为空，暂不建议进攻。',
            'basis': basis,
            'sample_size': 0,
        }

    positive_ratio = sum(1 for s in stocks if s.get('change_pct', 0) > 0) / len(stocks)
    avg_change = sum(s.get('change_pct', 0) for s in stocks) / len(stocks)
    avg_turnover = sum((s.get('turnover', 0) or 0) for s in stocks) / len(stocks)
    strong_count = sum(1 for s in stocks if s.get('change_pct', 0) >= 3)
    strong_ratio = strong_count / len(stocks)

    score = 0
    if positive_ratio >= 0.65:
        score += 2
    elif positive_ratio >= 0.55:
        score += 1
    if avg_change >= 1.2:
        score += 2
    elif avg_change >= 0.5:
        score += 1
    if avg_turnover >= 3.0:
        score += 2
    elif avg_turnover >= 2.0:
        score += 1
    if strong_ratio >= 0.25:
        score += 2
    elif strong_ratio >= 0.15:
        score += 1

    if score >= 6:
        label = '进攻环境较强'
        regime = 'aggressive'
        attack_ok = True
        summary = '市场活跃度和强势股占比都不错，可正常做进攻型观察。'
    elif score >= 4:
        label = '中性偏进攻'
        regime = 'balanced'
        attack_ok = True
        summary = '可以做进攻型筛选，但别满仓追。'
    else:
        label = '偏谨慎'
        regime = 'defensive'
        attack_ok = False
        summary = '强势扩散不够，今天更适合精选观察，不适合激进追高。'

    return {
        'score': score,
        'label': label,
        'regime': regime,
        'attack_ok': attack_ok,
        'summary': summary,
        'basis': basis,
        'sample_size': len(stocks),
        'metrics': {
            'positive_ratio': round(positive_ratio, 3),
            'avg_change_pct': round(avg_change, 2),
            'avg_turnover': round(avg_turnover, 2),
            'strong_ratio': round(strong_ratio, 3),
        }
    }


def build_market_regime_context(pool_stocks, candidate_stocks):
    """同时保留全池环境口径和候选强度口径。

    下游 ai_screening 默认使用更宽口径的 pool 视角，避免把入围候选的强度
    误当成整个策略池当天的真实环境。
    """
    broad_regime = assess_market_regime(pool_stocks, basis='pool')
    candidate_regime = assess_market_regime(candidate_stocks, basis='candidate')
    score_gap = round(candidate_regime.get('score', 0) - broad_regime.get('score', 0), 2)

    if score_gap >= 2:
        gap_note = '候选口径明显更强，说明入围票强于整体股票池，别把候选强度误读成真实环境。'
    elif score_gap <= -2:
        gap_note = '候选口径弱于整体股票池，说明热点集中度一般，临盘执行要更挑。'
    else:
        gap_note = '候选口径与整体股票池接近，可把候选强度当作环境的辅助参考。'

    execution_gate = build_execution_gate(broad_regime, candidate_regime)
    broad_regime['candidate_view'] = candidate_regime
    broad_regime['candidate_score_gap'] = score_gap
    broad_regime['candidate_gap_note'] = gap_note
    broad_regime['execution_gate'] = execution_gate
    broad_regime['attack_ok'] = execution_gate.get('status') != 'off'
    return broad_regime


def format_output(stocks, strategy_name, top_n):
    out = []
    for s in stocks[:top_n]:
        all_signals = s.get('tech_signals', []) + s.get('cap_signals', []) + s.get('fund_signals', [])
        if s.get('overheat_tags'):
            all_signals += s.get('overheat_tags', [])
        f = s.get('fundamentals') or {}
        # 如果新浪数据里有pe/pb，补充进去
        if not f.get('pe_ttm') and s.get('pe'):
            f['pe_ttm'] = s['pe']
        if not f.get('pb') and s.get('pb'):
            f['pb'] = s['pb']

        flows = s.get('flows') or []
        today_flow = flows[-1]['main_net'] if flows else 0
        trend = _calc_trend(flows, today_flow)

        out.append({
            'code': s['code'],
            'name': s.get('name', ''),
            'price': s['price'],
            'change_pct': round(s['change_pct'], 2),
            'score': s.get('final_score', s.get('tech_score', 0)),
            'scores': {
                'technical': s.get('tech_score', 0),
                'capital': s.get('cap_score', 0),
                'fundamental': s.get('fund_score', 0),
                'emotion': s.get('emotion_score', 0),
            },
            'signals': all_signals[:8],
            'capital_flow': {
                **build_capital_flow_payload(
                    today_wan=today_flow,
                    five_day_total_wan=round(sum(x['main_net'] for x in flows), 2) if flows else 0,
                    trend=trend,
                ),
            },
            'fundamentals': {k: round(v, 2) if isinstance(v, (int, float)) and v is not None else v for k, v in f.items()},
            'style': {
                'industry': f.get('industry'),
                'concept': f.get('concept'),
            },
            'trade_note': s.get('trade_note'),
            'technical_state': {
                'ma5': round(s.get('ma5'), 2) if isinstance(s.get('ma5'), (int, float)) else None,
                'ma10': round(s.get('ma10'), 2) if isinstance(s.get('ma10'), (int, float)) else None,
                'ma20': round(s.get('ma20'), 2) if isinstance(s.get('ma20'), (int, float)) else None,
                'high20': round(s.get('high20'), 2) if isinstance(s.get('high20'), (int, float)) else None,
                'low20': round(s.get('low20'), 2) if isinstance(s.get('low20'), (int, float)) else None,
                'position_20d': round(s.get('position_20d'), 3) if isinstance(s.get('position_20d'), (int, float)) else None,
            },
            'amount_yi': round(s['amount'] / 1e8, 1),
            'source_pool': s.get('source_pool'),
            'has_capital_flow': s.get('has_capital_flow', False),
            'missing_cap_penalty': s.get('missing_cap_penalty', 0),
            'overheat_penalty': s.get('overheat_penalty', 0),
            'attack_profile': s.get('attack_profile'),
            'theme': s.get('theme'),
            'announcements': s.get('announcements', [])[:3],
            'notice_risk_tags': s.get('notice_risk_tags', []),
        })
    return out


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description='A股多因子选股扫描')
    parser.add_argument('--strategy', default='combined',
                        choices=['conservative', 'growth', 'rebound', 'hot', 'combined', 'all'])
    parser.add_argument('--top', type=int, default=5)
    parser.add_argument('--pool', default='hs300', choices=['hs300', 'aggressive'],
                        help='股票池：hs300=沪深300；aggressive=中证500+沪深300（进攻型）')
    parser.add_argument('--output', help='输出到文件')
    args = parser.parse_args()

    pool_label = '沪深300' if args.pool == 'hs300' else '进攻型池(中证500+沪深300)'
    print(f'[{datetime.now().strftime("%H:%M:%S")}] 开始{pool_label}选股扫描', file=sys.stderr)

    # Stage 0+1: 新浪成分股+行情（一条龙）
    if args.pool == 'aggressive':
        stocks = load_aggressive_pool_with_quotes()
    else:
        stocks = load_hs300_with_quotes()
    print(f'  股票池: {args.pool}', file=sys.stderr)
    print(f'  成分股: {len(stocks)}只', file=sys.stderr)

    candidates = stage1_screener(stocks)
    print(f'  [Stage1] 初筛候选: {len(candidates)}只', file=sys.stderr)

    # Stage 2: 东方财富精选
    enriched = stage2_enrich(candidates)
    print(f'  [Stage2] 精选完成: {len(enriched)}只', file=sys.stderr)

    # 先给全量候选打进攻标签与主线标签，供后续主题识别/策略筛选共用
    for s in enriched:
        if not s.get('attack_profile'):
            s['attack_profile'] = classify_attack_profile(s)
        s['theme'] = classify_theme(s)

    # 策略筛选
    strategies = ['conservative', 'growth', 'rebound', 'hot', 'combined']
    market_regime = build_market_regime_context(stocks, enriched)
    market_themes = assess_market_themes(enriched)
    result = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'pool': args.pool,
        'pool_label': pool_label,
        'stage1_count': len(candidates),
        'stage2_count': len(enriched),
        'market_regime': market_regime,
        'market_themes': market_themes,
        'verification_universe': format_output(enriched, 'combined', len(enriched)),
    }


    if args.strategy == 'all':
        result['strategies'] = {}
        for strat in strategies:
            filtered = filter_strategy(enriched, strat)
            result['strategies'][strat] = format_output(filtered, strat, args.top)
            print(f'  {strat}: {len(filtered)}只, top{args.top}输出', file=sys.stderr)
    else:
        filtered = filter_strategy(enriched, args.strategy)
        result['strategy'] = args.strategy
        result['candidates'] = format_output(filtered, args.strategy, args.top)

    output = json.dumps(result, ensure_ascii=False, indent=2)

    # 自动归档：保留每次扫描结果，供后续回看/回测
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
    archive_file = HISTORY_DIR / f'{args.pool}_{args.strategy}_{stamp}.json'
    archive_file.write_text(output)
    latest_file = DATA_DIR / 'scan_result.json'
    latest_file.write_text(output)
    print(f'  自动归档: {archive_file}', file=sys.stderr)
    print(f'  最新结果: {latest_file}', file=sys.stderr)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f'  结果保存: {args.output}', file=sys.stderr)
    else:
        print(output)

    print(f'[{datetime.now().strftime("%H:%M:%S")}] 扫描完成', file=sys.stderr)


if __name__ == '__main__':
    main()
