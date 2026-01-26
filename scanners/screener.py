"""
scanners/screener.py - 종목 풀 소싱

각 스캐너 유형별 후보 종목 목록 제공:
- 단타: news_collector DB에서 뉴스 핫 종목
- 스윙: Finviz 스크리너 (중형주+과매도+풀백) + SWING_UNIVERSE fallback
- 장기: LONGTERM_UNIVERSE (고정 대형 배당주)
"""

import requests
from bs4 import BeautifulSoup
from psycopg2.extras import RealDictCursor

from db import get_db

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
}

# 장기 투자용 대형주 (S&P 500 Top 50 + 배당 귀족주)
LONGTERM_UNIVERSE = [
    # 메가캡 (시총 $500B+)
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'BRK-B', 'LLY', 'TSM', 'V',
    # 대형 배당주
    'JNJ', 'PG', 'KO', 'PEP', 'WMT', 'HD', 'MCD', 'ABBV', 'MRK', 'PFE',
    # 금융 대형주
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'AXP', 'C',
    # 산업/에너지 대형주
    'XOM', 'CVX', 'CAT', 'UNP', 'HON', 'GE', 'RTX', 'LMT',
    # 통신/유틸리티
    'T', 'VZ', 'NEE', 'DUK', 'SO',
    # 헬스케어
    'UNH', 'CVS', 'CI', 'ELV', 'HUM',
    # 기술 대형주
    'ORCL', 'IBM', 'CSCO', 'INTC', 'TXN', 'QCOM', 'AVGO',
    # 소비재
    'COST', 'TGT', 'LOW', 'NKE', 'SBUX', 'DIS',
]

# 스윙 투자용 중형주 (Finviz 실패 시 fallback)
SWING_UNIVERSE = [
    # 성장 중형주
    'PLTR', 'SNOW', 'DDOG', 'NET', 'CRWD', 'ZS', 'MDB', 'PANW',
    'SQ', 'SHOP', 'ROKU', 'TTD', 'TWLO', 'OKTA', 'DOCU',
    # 바이오/헬스
    'MRNA', 'BNTX', 'REGN', 'VRTX', 'ILMN', 'DXCM', 'ISRG',
    # 핀테크
    'PYPL', 'COIN', 'SOFI', 'AFRM', 'UPST',
    # EV/클린에너지
    'TSLA', 'RIVN', 'LCID', 'ENPH', 'SEDG', 'FSLR',
    # 반도체
    'AMD', 'MU', 'MRVL', 'ON', 'LRCX', 'KLAC', 'AMAT',
    # 기타 성장주
    'UBER', 'LYFT', 'ABNB', 'DASH', 'RBLX', 'U', 'DUOL',
]


def get_day_candidates(limit: int = 50) -> list:
    """뉴스 점수 상위 종목 조회 (news_collector DB)"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT ticker, total_score, positive_count, negative_count
        FROM daily_news_scores
        WHERE scan_date = CURRENT_DATE
        ORDER BY total_score DESC
        LIMIT %s
    """, (limit,))

    results = cur.fetchall()
    cur.close()
    conn.close()

    return results


def get_swing_candidates() -> list[str]:
    """스윙 후보 종목 (Finviz 스크리너 + SWING_UNIVERSE fallback)

    Finviz 스크리너 조건:
    - 중형주 ($2B~$10B)
    - RSI 과매도 (30~50)
    - 가격 $5 이상
    """
    try:
        url = (
            "https://finviz.com/screener.ashx?v=111"
            "&f=cap_midover,geo_usa,sh_price_o5,ta_rsi_os40"
            "&ft=4&o=-volume"
        )
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        # Finviz screener table
        rows = soup.select('table.screener_table tr.screener-body-table-nw')

        tickers = []
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 2:
                ticker_link = cols[1].find('a')
                if ticker_link:
                    tickers.append(ticker_link.text.strip())

        if len(tickers) >= 10:
            print(f"  Finviz 스크리너: {len(tickers)}개 발견")
            return tickers[:60]

    except Exception as e:
        print(f"  Finviz 스크리너 실패: {e}")

    # fallback
    print(f"  SWING_UNIVERSE fallback: {len(SWING_UNIVERSE)}개")
    return SWING_UNIVERSE


def get_long_candidates() -> list[str]:
    """장기 투자 후보 (고정 대형 배당주)"""
    return LONGTERM_UNIVERSE
