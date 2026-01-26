"""
lib/base.py - 공통 유틸리티
모든 모듈이 공유하는 설정과 유틸리티 함수
"""

import psycopg2

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
