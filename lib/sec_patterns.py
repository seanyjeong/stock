"""
lib/sec_patterns.py - SEC 공시 패턴 분석 모듈

블로거의 주식 발굴 기법 자동화:
1. SC 13D 매집 감지 (고래 대량보유 신고)
2. 8-K 이벤트 시퀀스 (CEO 변경 + 인수 = 테마전환)
3. S-8 스톡옵션 보상 + 현금소진
→ SEC 패턴 점수 0-20점 → 스캐너 통합

Usage:
    from lib.sec_patterns import analyze_sec_patterns, get_cached_patterns
    result = analyze_sec_patterns('NCPL')
    cached = get_cached_patterns('NCPL')
"""

import sys
import os
import re
import time
from datetime import datetime, timedelta, date
from typing import Optional

import requests
import pandas as pd
import yfinance as yf
import feedparser

# 프로젝트 루트 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_db
from psycopg2.extras import RealDictCursor, Json

SEC_HEADERS = {
    "User-Agent": "DailyStockStory/1.0 (sean8320@gmail.com)",
    "Accept-Encoding": "gzip, deflate",
}

# 테마 키워드
THEME_KEYWORDS = [
    'ai', 'artificial intelligence', 'machine learning',
    'blockchain', 'crypto', 'bitcoin',
    'ev', 'electric vehicle',
    'quantum', 'space',
    'cannabis', 'psychedelic',
    'weight loss', 'glp-1', 'obesity',
]

# ── 메모리 캐시 ──
_cik_cache: dict[str, str] = {}       # ticker → cik
_reverse_cik: dict[str, str] = {}     # cik → ticker
_tickers_loaded = False


# ──────────────────────────────────────────────
# CIK 변환
# ──────────────────────────────────────────────

def _load_company_tickers():
    """SEC company_tickers.json → 메모리 캐시"""
    global _cik_cache, _reverse_cik, _tickers_loaded
    if _tickers_loaded:
        return
    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for entry in data.values():
                t = entry.get('ticker', '').upper()
                c = str(entry.get('cik_str', ''))
                if t and c:
                    _cik_cache[t] = c
                    _reverse_cik[c] = t
            _tickers_loaded = True
            print(f"    SEC company_tickers: {len(_cik_cache)}개 로드")
    except Exception as e:
        print(f"    SEC company_tickers 로드 실패: {e}")


def resolve_cik(ticker: str) -> Optional[str]:
    """ticker → CIK 변환 (메모리 캐시)"""
    _load_company_tickers()
    return _cik_cache.get(ticker.upper())


def _cik_to_ticker(cik: str) -> Optional[str]:
    """CIK → ticker 역변환"""
    _load_company_tickers()
    return _reverse_cik.get(cik.lstrip('0'))


# ──────────────────────────────────────────────
# SEC API 헬퍼
# ──────────────────────────────────────────────

def _get_submissions(cik: str) -> dict:
    """SEC EDGAR submissions API → 기업 공시 목록"""
    padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded}.json"
    try:
        resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
        time.sleep(0.11)  # SEC rate limit (10 req/sec)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


def _efts_search(query: str, forms: str = "", days: int = 60) -> dict:
    """SEC EFTS 전문 검색"""
    start_dt = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    params = {
        'q': query,
        'dateRange': 'custom',
        'startdt': start_dt,
    }
    if forms:
        params['forms'] = forms

    try:
        resp = requests.get(
            "https://efts.sec.gov/LATEST/search-index",
            params=params,
            headers=SEC_HEADERS,
            timeout=15,
        )
        time.sleep(0.11)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


# ──────────────────────────────────────────────
# 1. SC 13D/13G 대량보유 신고
# ──────────────────────────────────────────────

def get_13d_filings(ticker: str, cik: str) -> dict:
    """SC 13D/13G 대량보유 신고 분석

    EFTS 전문 검색으로 최근 60일 13D 탐색.

    Returns:
        has_13d, whale_name, whale_pct, is_accumulating, is_exiting
    """
    result = {
        'has_13d': False,
        'whale_name': None,
        'whale_pct': 0.0,
        'is_accumulating': False,
        'is_exiting': False,
    }

    try:
        data = _efts_search(
            query=f'"{ticker}"',
            forms="SC 13D,SC 13D/A,SC 13G,SC 13G/A",
            days=60,
        )

        hits = data.get('hits', {})
        total = hits.get('total', {}).get('value', 0) if isinstance(hits.get('total'), dict) else hits.get('total', 0)

        if total and int(total) > 0:
            result['has_13d'] = True
            result['whale_pct'] = 5.0  # SC 13D 최소 기준

            filing_list = hits.get('hits', [])
            if filing_list:
                latest = filing_list[0].get('_source', {})
                form_type = latest.get('file_type', latest.get('form_type', ''))
                # entity name 다양한 필드 시도
                entity = (
                    latest.get('entity_name', '')
                    or (latest.get('display_names', [''])[0] if latest.get('display_names') else '')
                )
                result['whale_name'] = entity[:100] if entity else None

                # 13D/A = 수정 신고 (매도 가능)
                if '/A' in str(form_type):
                    result['is_exiting'] = True
                else:
                    result['is_accumulating'] = True

    except Exception as e:
        print(f"    13D 분석 오류 ({ticker}): {e}")

    return result


# ──────────────────────────────────────────────
# 2. 8-K 이벤트 시퀀스
# ──────────────────────────────────────────────

def detect_8k_sequence(ticker: str, cik: str) -> dict:
    """8-K 시퀀스 분석 - CEO 변경 + 인수 + 테마전환 감지"""
    subs = _get_submissions(cik)
    return _detect_8k_from_subs(subs)


def _detect_8k_from_subs(subs: dict) -> dict:
    """submissions 데이터에서 8-K 시퀀스 분석 (API 호출 절약용)"""
    result = {
        'has_ceo_change': False,
        'has_acquisition': False,
        'has_theme_pivot': False,
        'theme_keywords': [],
        'event_density': 0,
    }

    try:
        recent = subs.get('filings', {}).get('recent', {})
        forms = recent.get('form', [])
        dates = recent.get('filingDate', [])
        items_list = recent.get('items', [])
        descs = recent.get('primaryDocDescription', [])

        cutoff_30d = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        cutoff_90d = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

        count_30d = 0

        for i, form in enumerate(forms):
            if form != '8-K':
                continue

            filing_date = dates[i] if i < len(dates) else ''
            items = items_list[i] if i < len(items_list) else ''
            desc = (descs[i] if i < len(descs) else '').lower()

            if filing_date >= cutoff_30d:
                count_30d += 1

            if filing_date < cutoff_90d:
                continue

            # 8-K Item 분석
            # 1.01/2.01 = 인수/합병/계약
            if any(item in items for item in ['1.01', '2.01']):
                result['has_acquisition'] = True

            # 5.02 = 임원 변경
            if '5.02' in items:
                result['has_ceo_change'] = True

            # 테마 키워드 검색
            search_text = f"{items} {desc}".lower()
            for theme in THEME_KEYWORDS:
                if theme in search_text and theme not in result['theme_keywords']:
                    result['has_theme_pivot'] = True
                    result['theme_keywords'].append(theme)

        result['event_density'] = count_30d

    except Exception:
        pass

    return result


# ──────────────────────────────────────────────
# 3. S-8 스톡옵션 보상
# ──────────────────────────────────────────────

def detect_s8_pattern(ticker: str, cik: str) -> dict:
    """S-8 스톡옵션 보상 등록 감지 (90일)"""
    subs = _get_submissions(cik)
    return _detect_s8_from_subs(subs)


def _detect_s8_from_subs(subs: dict) -> dict:
    """submissions 데이터에서 S-8 분석 (API 호출 절약용)"""
    result = {'s8_count_90d': 0}

    try:
        recent = subs.get('filings', {}).get('recent', {})
        forms = recent.get('form', [])
        dates = recent.get('filingDate', [])

        cutoff = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

        for i, form in enumerate(forms):
            if form == 'S-8' and i < len(dates) and dates[i] >= cutoff:
                result['s8_count_90d'] += 1

    except Exception:
        pass

    return result


# ──────────────────────────────────────────────
# 4. 현금 소진율
# ──────────────────────────────────────────────

def detect_cash_burn(ticker: str) -> dict:
    """현금 포지션 + 소진률 분석 (yfinance)"""
    result = {
        'cash_position': None,
        'runway_quarters': None,
        'is_critical_burn': False,
    }

    try:
        stock = yf.Ticker(ticker)
        bs = stock.quarterly_balance_sheet
        cf = stock.quarterly_cashflow

        # 현금 포지션
        if bs is not None and not bs.empty:
            for label in ['Cash And Cash Equivalents', 'Cash',
                          'CashAndCashEquivalentsAtCarryingValue']:
                if label in bs.index:
                    val = bs.loc[label].iloc[0]
                    if pd.notna(val):
                        result['cash_position'] = float(val)
                    break

        # 소진률 계산
        if cf is not None and not cf.empty and result['cash_position']:
            for label in ['Free Cash Flow', 'FreeCashFlow',
                          'Operating Cash Flow', 'OperatingCashFlow']:
                if label in cf.index:
                    val = cf.loc[label].iloc[0]
                    if pd.notna(val) and float(val) < 0:
                        burn_rate = abs(float(val))
                        runway = result['cash_position'] / burn_rate if burn_rate > 0 else 999
                        result['runway_quarters'] = round(runway, 1)
                        result['is_critical_burn'] = runway < 2
                    break

    except Exception as e:
        print(f"    현금소진 분석 오류 ({ticker}): {e}")

    return result


# ──────────────────────────────────────────────
# 5. 종합 SEC 패턴 분석 (0-20점)
# ──────────────────────────────────────────────

def analyze_sec_patterns(ticker: str) -> dict:
    """SEC 공시 패턴 종합 분석

    점수 체계 (0-20):
    - 13D 매집: max 7 (신규+5, 5%확인+2, 매도-3)
    - 8-K 테마전환: max ~7 (콤보+5 or 단독+2, 테마+3, 밀도+2)
    - S-8 + 현금소진: max 6 (콤보+4, S-8단독+2, 현금단독+2)
    """
    cik = resolve_cik(ticker)

    result = {
        'ticker': ticker,
        'scan_date': date.today().isoformat(),
        'sec_pattern_score': 0.0,
        'pump_probability': 'NONE',
        'signals': [],
        # 13D
        'has_13d': False,
        'whale_name': None,
        'whale_pct': 0.0,
        'is_accumulating': False,
        'is_exiting': False,
        # 8-K
        'has_ceo_change': False,
        'has_acquisition': False,
        'has_theme_pivot': False,
        'theme_keywords': [],
        'event_density': 0,
        # S-8
        's8_count_90d': 0,
        # Cash
        'cash_position': None,
        'runway_quarters': None,
        'is_critical_burn': False,
    }

    if not cik:
        return result

    # ── 데이터 수집 (submissions 1회로 8-K+S-8 동시) ──
    subs = _get_submissions(cik)

    d13 = get_13d_filings(ticker, cik)
    result.update(d13)

    d8k = _detect_8k_from_subs(subs)
    result.update(d8k)

    ds8 = _detect_s8_from_subs(subs)
    result.update(ds8)

    cash = detect_cash_burn(ticker)
    result.update(cash)

    # ── 점수 계산 ──
    score = 0.0
    signals = []

    # 1. 13D 매집 (max 7)
    if result['has_13d'] and result['is_accumulating']:
        score += 5
        signals.append("13D 매집")
        if result['whale_pct'] >= 5:
            score += 2
            name = result['whale_name'] or '불명'
            signals.append(f"보유 {result['whale_pct']:.0f}%+ ({name[:20]})")
    elif result['has_13d'] and result['is_exiting']:
        score -= 3
        signals.append("13D/A 매도 가능")

    # 2. 8-K 테마전환 (max ~7)
    if result['has_ceo_change'] and result['has_acquisition']:
        score += 5
        signals.append("CEO+인수 콤보")
    elif result['has_ceo_change'] or result['has_acquisition']:
        score += 2
        if result['has_ceo_change']:
            signals.append("임원 변경")
        if result['has_acquisition']:
            signals.append("인수/계약")

    if result['has_theme_pivot']:
        score += 3
        themes = ','.join(result['theme_keywords'][:3])
        signals.append(f"테마전환: {themes}")

    if result['event_density'] >= 3:
        score += 2
        signals.append(f"8-K {result['event_density']}건/30일")

    # 3. S-8 + 현금소진 (max 6)
    has_s8 = result['s8_count_90d'] > 0
    has_burn = result['is_critical_burn']

    if has_s8 and has_burn:
        score += 4
        signals.append("S-8+현금소진")
    elif has_s8:
        score += 2
        signals.append(f"S-8 {result['s8_count_90d']}건")
    elif has_burn:
        score += 2
        runway = result['runway_quarters'] or 0
        signals.append(f"현금 {runway:.1f}분기")

    # 클램프 0-20
    score = max(min(score, 20), 0)

    # 펌프 확률
    if score >= 15:
        pump = 'HIGH'
    elif score >= 8:
        pump = 'MEDIUM'
    elif score >= 3:
        pump = 'LOW'
    else:
        pump = 'NONE'

    result['sec_pattern_score'] = round(score, 1)
    result['pump_probability'] = pump
    result['signals'] = signals

    return result


# ──────────────────────────────────────────────
# DB 캐시
# ──────────────────────────────────────────────

def init_sec_patterns_table():
    """sec_filing_patterns 테이블 생성"""
    try:
        conn = get_db()
    except Exception:
        print("    SEC 패턴 테이블: DB 연결 실패")
        return

    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sec_filing_patterns (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            scan_date DATE NOT NULL,
            has_13d BOOLEAN DEFAULT FALSE,
            whale_name TEXT,
            whale_pct FLOAT,
            is_accumulating BOOLEAN DEFAULT FALSE,
            is_exiting BOOLEAN DEFAULT FALSE,
            has_ceo_change BOOLEAN DEFAULT FALSE,
            has_acquisition BOOLEAN DEFAULT FALSE,
            has_theme_pivot BOOLEAN DEFAULT FALSE,
            theme_keywords TEXT[],
            event_density INTEGER DEFAULT 0,
            s8_count_90d INTEGER DEFAULT 0,
            cash_position FLOAT,
            runway_quarters FLOAT,
            is_critical_burn BOOLEAN DEFAULT FALSE,
            sec_pattern_score FLOAT DEFAULT 0,
            pump_probability VARCHAR(10) DEFAULT 'NONE',
            signals TEXT[],
            raw_data JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(ticker, scan_date)
        );

        CREATE INDEX IF NOT EXISTS idx_sec_patterns_ticker
            ON sec_filing_patterns(ticker);
        CREATE INDEX IF NOT EXISTS idx_sec_patterns_date
            ON sec_filing_patterns(scan_date);
        CREATE INDEX IF NOT EXISTS idx_sec_patterns_score
            ON sec_filing_patterns(sec_pattern_score DESC);
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("    SEC 패턴 테이블 초기화 완료")


def get_cached_patterns(ticker: str) -> Optional[dict]:
    """오늘자 SEC 패턴 캐시 조회"""
    try:
        conn = get_db()
    except Exception:
        return None

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT * FROM sec_filing_patterns
            WHERE ticker = %s AND scan_date = CURRENT_DATE
        """, (ticker,))

        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row) if row else None
    except Exception:
        conn.close()
        return None


def collect_sec_patterns(tickers: list[str]):
    """배치: 여러 종목 SEC 패턴 분석 → DB 저장"""
    if not tickers:
        return

    print(f"\n  SEC 패턴 배치 분석: {len(tickers)}개 종목")
    init_sec_patterns_table()

    try:
        conn = get_db()
    except Exception:
        print("    DB 연결 실패")
        return

    cur = conn.cursor()
    analyzed = 0

    for ticker in tickers:
        try:
            # 오늘자 캐시 있으면 스킵
            cur.execute("""
                SELECT 1 FROM sec_filing_patterns
                WHERE ticker = %s AND scan_date = CURRENT_DATE
            """, (ticker,))
            if cur.fetchone():
                continue

            print(f"    {ticker}...", end=" ", flush=True)
            result = analyze_sec_patterns(ticker)

            cur.execute("""
                INSERT INTO sec_filing_patterns
                (ticker, scan_date, has_13d, whale_name, whale_pct,
                 is_accumulating, is_exiting, has_ceo_change, has_acquisition,
                 has_theme_pivot, theme_keywords, event_density, s8_count_90d,
                 cash_position, runway_quarters, is_critical_burn,
                 sec_pattern_score, pump_probability, signals, raw_data)
                VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, scan_date) DO UPDATE SET
                    has_13d = EXCLUDED.has_13d,
                    whale_name = EXCLUDED.whale_name,
                    whale_pct = EXCLUDED.whale_pct,
                    is_accumulating = EXCLUDED.is_accumulating,
                    is_exiting = EXCLUDED.is_exiting,
                    has_ceo_change = EXCLUDED.has_ceo_change,
                    has_acquisition = EXCLUDED.has_acquisition,
                    has_theme_pivot = EXCLUDED.has_theme_pivot,
                    theme_keywords = EXCLUDED.theme_keywords,
                    event_density = EXCLUDED.event_density,
                    s8_count_90d = EXCLUDED.s8_count_90d,
                    cash_position = EXCLUDED.cash_position,
                    runway_quarters = EXCLUDED.runway_quarters,
                    is_critical_burn = EXCLUDED.is_critical_burn,
                    sec_pattern_score = EXCLUDED.sec_pattern_score,
                    pump_probability = EXCLUDED.pump_probability,
                    signals = EXCLUDED.signals,
                    raw_data = EXCLUDED.raw_data
            """, (
                ticker, result['has_13d'], result['whale_name'], result['whale_pct'],
                result['is_accumulating'], result['is_exiting'],
                result['has_ceo_change'], result['has_acquisition'],
                result['has_theme_pivot'], result.get('theme_keywords', []),
                result['event_density'], result['s8_count_90d'],
                result.get('cash_position'), result.get('runway_quarters'),
                result['is_critical_burn'],
                result['sec_pattern_score'], result['pump_probability'],
                result.get('signals', []),
                Json(result),
            ))

            conn.commit()
            analyzed += 1

            score = result['sec_pattern_score']
            if score > 0:
                print(f"점수={score} {result['signals']}")
            else:
                print("0")

        except Exception as e:
            print(f"오류: {e}")
            conn.rollback()

    cur.close()
    conn.close()
    print(f"    SEC 패턴 분석 완료: {analyzed}/{len(tickers)}")


# ──────────────────────────────────────────────
# 13D 디스커버리 (RSS)
# ──────────────────────────────────────────────

def discover_new_13d_filings() -> list[str]:
    """SEC RSS에서 최근 SC 13D 신고 종목 수집

    Returns:
        새 13D 발견된 티커 리스트 (소형주 필터 적용)
    """
    tickers = []

    try:
        rss_url = (
            "https://www.sec.gov/cgi-bin/browse-edgar"
            "?action=getcurrent&type=SC+13D&company=&dateb="
            "&owner=include&count=40&output=atom"
        )

        feed = feedparser.parse(rss_url)
        _load_company_tickers()

        for entry in feed.entries:
            title = entry.get('title', '')
            link = entry.get('link', '')
            summary = entry.get('summary', '')

            # CIK 추출 시도
            cik_match = re.search(r'CIK[=:]?\s*(\d+)', link + summary)
            if cik_match:
                cik = cik_match.group(1).lstrip('0')
                ticker = _cik_to_ticker(cik)
                if ticker and ticker not in tickers:
                    tickers.append(ticker)

            # Title에서 대문자 티커 매칭
            common_words = {
                'THE', 'AND', 'FOR', 'INC', 'LLC', 'CEO', 'SEC', 'CORP',
                'LTD', 'GROUP', 'FILED', 'FORM', 'NEW', 'ALL', 'ONE',
            }
            potential = re.findall(r'\b([A-Z]{2,5})\b', title)
            for t in potential:
                if t not in common_words and t in _cik_cache and t not in tickers:
                    tickers.append(t)

        # 소형주 필터 (시총 < $2B)
        filtered = []
        for ticker in tickers[:20]:
            try:
                info = yf.Ticker(ticker).info or {}
                mcap = info.get('marketCap', 0) or 0
                if 0 < mcap < 2e9:
                    filtered.append(ticker)
            except Exception:
                filtered.append(ticker)
            time.sleep(0.1)

        tickers = filtered

    except Exception as e:
        print(f"    13D 디스커버리 오류: {e}")

    return tickers
