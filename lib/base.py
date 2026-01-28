"""
lib/base.py - 공통 유틸리티
모든 모듈이 공유하는 설정과 유틸리티 함수
"""

import psycopg2
from datetime import datetime
from zoneinfo import ZoneInfo

DB_CONFIG = {
    "host": "localhost",
    "database": "continuous_claude",
    "user": "claude",
    "password": "claude_dev",
    "port": 5432
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
}

SEC_HEADERS = {
    "User-Agent": "DailyStockStory/1.0 (contact@example.com)"
}


def get_db():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except:
        return None


def fmt_num(n, prefix="", suffix=""):
    """숫자 포맷팅"""
    if n is None:
        return "N/A"
    if abs(n) >= 1e12:
        return f"{prefix}{n/1e12:.2f}T{suffix}"
    if abs(n) >= 1e9:
        return f"{prefix}{n/1e9:.2f}B{suffix}"
    if abs(n) >= 1e6:
        return f"{prefix}{n/1e6:.2f}M{suffix}"
    if abs(n) >= 1e3:
        return f"{prefix}{n/1e3:.1f}K{suffix}"
    return f"{prefix}{n:,.0f}{suffix}"


def fmt_pct(n, decimals=2):
    """퍼센트 포맷팅"""
    if n is None:
        return "N/A"
    return f"{n*100:.{decimals}f}%" if abs(n) < 1 else f"{n:.{decimals}f}%"


def get_market_status() -> dict:
    """현재 미국 시장 상태 반환 (KST 기준)"""
    kst = ZoneInfo("Asia/Seoul")
    now = datetime.now(kst)
    hour = now.hour
    minute = now.minute
    time_minutes = hour * 60 + minute
    weekday = now.weekday()

    if weekday >= 5:
        return {"status": "closed", "label": "주말"}

    premarket_start = 18 * 60      # 18:00
    regular_start = 23 * 60 + 30   # 23:30
    regular_end = 6 * 60           # 06:00
    afterhours_end = 10 * 60       # 10:00

    if time_minutes >= premarket_start and time_minutes < regular_start:
        return {"status": "premarket", "label": "프리마켓"}
    elif time_minutes >= regular_start or time_minutes < regular_end:
        return {"status": "regular", "label": "정규장"}
    elif time_minutes >= regular_end and time_minutes < afterhours_end:
        return {"status": "afterhours", "label": "애프터"}
    else:
        return {"status": "closed", "label": "장마감"}


def get_extended_price(info: dict, hist_close=None) -> tuple[float | None, str]:
    """시장 상태에 따라 최적 가격 반환 (장외가격 우선)

    Returns:
        (price, source) - source: 'premarket' | 'afterhours' | 'regular' | 'history'
    """
    regular = info.get('currentPrice') or info.get('regularMarketPrice')
    pre = info.get('preMarketPrice')
    post = info.get('postMarketPrice')

    market = get_market_status()
    status = market["status"]

    if status == "premarket" and pre:
        return float(pre), "premarket"
    elif status == "afterhours" and post:
        return float(post), "afterhours"
    elif status == "closed":
        # 장 마감/주말: 애프터 > 정규
        if post:
            return float(post), "afterhours"
        elif regular:
            return float(regular), "regular"
    elif regular:
        return float(regular), "regular"

    # fallback: history
    if regular:
        return float(regular), "regular"
    if hist_close is not None:
        return float(hist_close), "history"
    return None, "none"


# 투자 성향별 손절폭 설정 (%)
STOP_LOSS_CAPS = {
    'conservative': {'day': 0.05, 'swing': 0.10, 'long': 0.15},
    'balanced':     {'day': 0.08, 'swing': 0.15, 'long': 0.20},
    'aggressive':   {'day': 0.12, 'swing': 0.20, 'long': 0.25},
}


def get_profile_type() -> str:
    """DB에서 사용자 프로필 성향 조회 (기본값: balanced)"""
    try:
        conn = get_db()
        if not conn:
            return 'balanced'
        cur = conn.cursor()
        cur.execute("SELECT profile_type FROM user_profiles ORDER BY id LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else 'balanced'
    except Exception:
        return 'balanced'


def get_stop_cap(category: str = 'day') -> float:
    """투자 성향에 맞는 손절폭 cap 반환"""
    profile = get_profile_type()
    caps = STOP_LOSS_CAPS.get(profile, STOP_LOSS_CAPS['balanced'])
    return caps.get(category, 0.08)
