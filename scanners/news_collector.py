"""
뉴스 수집 스캐너

데이터 소스:
1. SEC EDGAR - 8-K, 10-K 공시
2. Finviz - 뉴스 헤드라인
3. Yahoo Finance - 뉴스

실행:
    uv run python scanners/news_collector.py
    uv run python scanners/news_collector.py --test  # 테스트 모드
"""

import os
import sys
import json
import time
import re
import argparse
from datetime import datetime, timedelta
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
import feedparser

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_db
from psycopg2.extras import RealDictCursor

# SEC EDGAR RSS 피드
SEC_RSS_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&company=&dateb=&owner=include&count=100&output=atom"

# 호재/악재 키워드
POSITIVE_KEYWORDS = [
    'partnership', 'agreement', 'contract', 'deal', 'acquisition',
    'merger', 'fda approval', 'breakthrough', 'patent', 'revenue growth',
    'earnings beat', 'upgrade', 'buy rating', 'strong buy', 'outperform'
]

NEGATIVE_KEYWORDS = [
    'lawsuit', 'litigation', 'bankruptcy', 'default', 'fraud',
    'investigation', 'delisting', 'downgrade', 'sell rating', 'underperform',
    'recall', 'warning', 'loss', 'decline', 'cut'
]


def init_tables():
    """뉴스 테이블 생성"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS news_mentions (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            source VARCHAR(50) NOT NULL,
            headline TEXT NOT NULL,
            url TEXT,
            sentiment VARCHAR(20) DEFAULT 'neutral',
            sentiment_score FLOAT DEFAULT 0,
            keywords TEXT[],
            published_at TIMESTAMP WITH TIME ZONE,
            collected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ticker, headline, source)
        );

        CREATE INDEX IF NOT EXISTS idx_news_ticker ON news_mentions(ticker);
        CREATE INDEX IF NOT EXISTS idx_news_collected ON news_mentions(collected_at);
        CREATE INDEX IF NOT EXISTS idx_news_sentiment ON news_mentions(sentiment);
    """)

    # 일일 뉴스 점수 집계 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_news_scores (
            id SERIAL PRIMARY KEY,
            scan_date DATE NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            positive_count INTEGER DEFAULT 0,
            negative_count INTEGER DEFAULT 0,
            neutral_count INTEGER DEFAULT 0,
            total_score FLOAT DEFAULT 0,
            sources TEXT[],
            top_headlines TEXT[],
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scan_date, ticker)
        );

        CREATE INDEX IF NOT EXISTS idx_daily_news_date ON daily_news_scores(scan_date);
        CREATE INDEX IF NOT EXISTS idx_daily_news_score ON daily_news_scores(total_score DESC);
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ 테이블 초기화 완료")


def extract_ticker_from_text(text: str) -> list:
    """텍스트에서 티커 심볼 추출"""
    # 일반적인 티커 패턴: 1-5글자 대문자
    pattern = r'\b([A-Z]{1,5})\b'
    matches = re.findall(pattern, text)

    # 일반 단어 제외
    common_words = {'THE', 'AND', 'FOR', 'INC', 'LLC', 'CEO', 'CFO', 'SEC', 'FDA', 'IPO', 'NYSE', 'NASDAQ'}
    tickers = [m for m in matches if m not in common_words and len(m) >= 2]

    return list(set(tickers))


def analyze_sentiment(text: str) -> tuple:
    """
    텍스트 감성 분석 (룰 기반)

    Returns:
        tuple: (sentiment, score, keywords)
    """
    text_lower = text.lower()

    pos_found = [kw for kw in POSITIVE_KEYWORDS if kw in text_lower]
    neg_found = [kw for kw in NEGATIVE_KEYWORDS if kw in text_lower]

    pos_score = len(pos_found) * 2
    neg_score = len(neg_found) * 3  # 악재에 더 높은 가중치

    total_score = pos_score - neg_score

    if total_score > 0:
        sentiment = 'positive'
    elif total_score < 0:
        sentiment = 'negative'
    else:
        sentiment = 'neutral'

    keywords = pos_found + neg_found

    return sentiment, total_score, keywords


def fetch_sec_edgar() -> list:
    """SEC EDGAR 8-K 공시 수집"""
    print("📄 SEC EDGAR 수집 중...")

    try:
        headers = {
            'User-Agent': 'DailyStockStory/1.0 (sean8320@gmail.com)'
        }

        feed = feedparser.parse(SEC_RSS_URL)

        results = []
        for entry in feed.entries[:50]:  # 최근 50개
            title = entry.get('title', '')
            link = entry.get('link', '')
            published = entry.get('published', '')

            # 티커 추출
            tickers = extract_ticker_from_text(title)

            # 감성 분석
            sentiment, score, keywords = analyze_sentiment(title)

            for ticker in tickers:
                results.append({
                    'ticker': ticker,
                    'source': 'SEC_EDGAR',
                    'headline': title[:500],
                    'url': link,
                    'sentiment': sentiment,
                    'sentiment_score': score,
                    'keywords': keywords,
                    'published_at': published
                })

        print(f"  → SEC EDGAR: {len(results)}건")
        return results

    except Exception as e:
        print(f"  ❌ SEC EDGAR 오류: {e}")
        return []


def fetch_finviz_news(ticker: str) -> list:
    """Finviz에서 특정 종목 뉴스 수집"""
    try:
        url = f"https://finviz.com/quote.ashx?t={ticker}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        news_table = soup.find('table', {'id': 'news-table'})

        if not news_table:
            return []

        results = []
        rows = news_table.find_all('tr')[:10]  # 최근 10개

        for row in rows:
            link = row.find('a')
            if not link:
                continue

            headline = link.text.strip()
            news_url = link.get('href', '')

            sentiment, score, keywords = analyze_sentiment(headline)

            results.append({
                'ticker': ticker,
                'source': 'Finviz',
                'headline': headline[:500],
                'url': news_url,
                'sentiment': sentiment,
                'sentiment_score': score,
                'keywords': keywords,
                'published_at': None
            })

        return results

    except Exception as e:
        return []


def fetch_yahoo_news(ticker: str) -> list:
    """Yahoo Finance에서 특정 종목 뉴스 수집"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        # Yahoo Finance 뉴스 API
        news_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={ticker}&newsCount=10"
        response = requests.get(news_url, headers=headers, timeout=10)

        if response.status_code != 200:
            return []

        data = response.json()
        news_items = data.get('news', [])

        results = []
        for item in news_items:
            headline = item.get('title', '')
            news_url = item.get('link', '')
            pub_time = item.get('providerPublishTime', 0)

            sentiment, score, keywords = analyze_sentiment(headline)

            published_at = None
            if pub_time:
                published_at = datetime.fromtimestamp(pub_time).isoformat()

            results.append({
                'ticker': ticker,
                'source': 'Yahoo',
                'headline': headline[:500],
                'url': news_url,
                'sentiment': sentiment,
                'sentiment_score': score,
                'keywords': keywords,
                'published_at': published_at
            })

        return results

    except Exception as e:
        return []


def get_trending_tickers() -> list:
    """트렌딩 종목 리스트 (RegSHO + 기존 관심종목)"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    tickers = set()

    # RegSHO 종목
    cur.execute("""
        SELECT DISTINCT ticker FROM regsho_list
        WHERE collected_date >= CURRENT_DATE - INTERVAL '7 days'
    """)
    for row in cur.fetchall():
        tickers.add(row['ticker'])

    # 사용자 관심종목
    cur.execute("SELECT DISTINCT ticker FROM user_watchlist")
    for row in cur.fetchall():
        tickers.add(row['ticker'])

    # 사용자 포트폴리오
    cur.execute("SELECT DISTINCT ticker FROM user_holdings")
    for row in cur.fetchall():
        tickers.add(row['ticker'])

    cur.close()
    conn.close()

    return list(tickers)


def save_news(news_list: list):
    """뉴스 저장"""
    if not news_list:
        return 0

    conn = get_db()
    cur = conn.cursor()

    saved = 0
    for news in news_list:
        try:
            cur.execute("""
                INSERT INTO news_mentions
                (ticker, source, headline, url, sentiment, sentiment_score, keywords, published_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, headline, source) DO NOTHING
            """, (
                news['ticker'],
                news['source'],
                news['headline'],
                news.get('url'),
                news['sentiment'],
                news['sentiment_score'],
                news.get('keywords', []),
                news.get('published_at')
            ))
            saved += cur.rowcount
        except Exception as e:
            print(f"  저장 오류: {e}")

    conn.commit()
    cur.close()
    conn.close()

    return saved


def calculate_daily_scores():
    """일일 뉴스 점수 집계"""
    print("\n📊 일일 점수 집계 중...")

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 오늘 수집된 뉴스 집계
    cur.execute("""
        SELECT
            ticker,
            COUNT(*) FILTER (WHERE sentiment = 'positive') as positive_count,
            COUNT(*) FILTER (WHERE sentiment = 'negative') as negative_count,
            COUNT(*) FILTER (WHERE sentiment = 'neutral') as neutral_count,
            SUM(sentiment_score) as total_score,
            ARRAY_AGG(DISTINCT source) as sources,
            ARRAY_AGG(headline ORDER BY sentiment_score DESC) as headlines
        FROM news_mentions
        WHERE collected_at >= CURRENT_DATE
        GROUP BY ticker
        HAVING COUNT(*) >= 1
    """)

    rows = cur.fetchall()

    for row in rows:
        # 상위 3개 헤드라인만 저장
        top_headlines = row['headlines'][:3] if row['headlines'] else []

        cur.execute("""
            INSERT INTO daily_news_scores
            (scan_date, ticker, positive_count, negative_count, neutral_count,
             total_score, sources, top_headlines)
            VALUES (CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (scan_date, ticker)
            DO UPDATE SET
                positive_count = EXCLUDED.positive_count,
                negative_count = EXCLUDED.negative_count,
                neutral_count = EXCLUDED.neutral_count,
                total_score = EXCLUDED.total_score,
                sources = EXCLUDED.sources,
                top_headlines = EXCLUDED.top_headlines
        """, (
            row['ticker'],
            row['positive_count'],
            row['negative_count'],
            row['neutral_count'],
            row['total_score'] or 0,
            row['sources'],
            top_headlines
        ))

    conn.commit()
    cur.close()
    conn.close()

    print(f"  → {len(rows)}개 종목 점수 집계 완료")


def get_top_buzz(limit: int = 50) -> list:
    """뉴스 점수 상위 종목 조회"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT ticker, positive_count, negative_count, total_score, sources, top_headlines
        FROM daily_news_scores
        WHERE scan_date = CURRENT_DATE
          AND total_score > 0  -- 긍정 > 부정
        ORDER BY total_score DESC
        LIMIT %s
    """, (limit,))

    results = cur.fetchall()
    cur.close()
    conn.close()

    return results


def is_us_market_holiday() -> bool:
    """미국 증시 휴장일 체크"""
    from datetime import date
    today = date.today()

    # 주말
    if today.weekday() >= 5:
        return True

    # 2026년 미국 증시 휴장일
    holidays_2026 = [
        date(2026, 1, 1),   # 새해
        date(2026, 1, 19),  # MLK Day
        date(2026, 2, 16),  # Presidents Day
        date(2026, 4, 3),   # Good Friday
        date(2026, 5, 25),  # Memorial Day
        date(2026, 7, 3),   # Independence Day (observed)
        date(2026, 9, 7),   # Labor Day
        date(2026, 11, 26), # Thanksgiving
        date(2026, 12, 25), # Christmas
    ]

    return today in holidays_2026


def main():
    parser = argparse.ArgumentParser(description='뉴스 수집 스캐너')
    parser.add_argument('--test', action='store_true', help='테스트 모드')
    parser.add_argument('--force', action='store_true', help='휴장일 무시')
    args = parser.parse_args()

    print("=" * 50)
    print("📰 뉴스 수집 스캐너 시작")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 휴장일 체크
    if is_us_market_holiday() and not args.force:
        print("📅 미국 증시 휴장일 - 수집 건너뜀")
        return

    # 테이블 초기화
    init_tables()

    all_news = []

    # 1. SEC EDGAR 수집
    sec_news = fetch_sec_edgar()
    all_news.extend(sec_news)

    # 2. 트렌딩 종목별 뉴스 수집
    tickers = get_trending_tickers()
    print(f"\n🔍 {len(tickers)}개 종목 뉴스 수집 중...")

    if args.test:
        tickers = tickers[:5]  # 테스트 모드: 5개만
        print("  (테스트 모드: 5개 종목만)")

    # 병렬 수집
    with ThreadPoolExecutor(max_workers=5) as executor:
        finviz_futures = {executor.submit(fetch_finviz_news, t): t for t in tickers}
        yahoo_futures = {executor.submit(fetch_yahoo_news, t): t for t in tickers}

        for future in as_completed(finviz_futures):
            news = future.result()
            all_news.extend(news)

        for future in as_completed(yahoo_futures):
            news = future.result()
            all_news.extend(news)

        # Rate limit
        time.sleep(0.5)

    print(f"\n💾 총 {len(all_news)}건 수집됨")

    # 3. 저장
    saved = save_news(all_news)
    print(f"  → {saved}건 신규 저장")

    # 4. 일일 점수 집계
    calculate_daily_scores()

    # 5. 뉴스 벡터화 + 중복 감지 + 시간 가중치
    try:
        from lib.news_vectors import embed_and_dedup as _embed_dedup, init_vector_tables as _init_vt, calculate_time_weights as _calc_tw
        _init_vt()
        _embed_dedup()
        _calc_tw()
    except Exception as e:
        print(f"  ⚠️ 뉴스 벡터화 스킵 (기존 파이프라인 정상): {e}")

    # 6. 상위 종목 출력
    top = get_top_buzz(10)
    if top:
        print("\n🔥 뉴스 점수 TOP 10:")
        for i, item in enumerate(top, 1):
            sentiment_emoji = "📈" if item['total_score'] > 5 else "📊"
            print(f"  {i}. {item['ticker']}: {sentiment_emoji} 점수={item['total_score']:.1f} "
                  f"(+{item['positive_count']}/-{item['negative_count']})")

    print("\n✅ 뉴스 수집 완료")


if __name__ == "__main__":
    main()
