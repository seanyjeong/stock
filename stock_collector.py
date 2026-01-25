#!/usr/bin/env python3
"""
Data Collector v3 (Lite)
- 주가 수집 제거 (yfinance 실시간 사용)
- 숏스퀴즈 수집 제거 (deep_analyzer가 실시간 분석)
- RegSHO, 환율, 블로그만 수집
"""

import asyncio
import json
import re
import os
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.async_api import async_playwright

# ============================================================
# 설정
# ============================================================

DB_URL = os.getenv("DATABASE_URL", "postgresql://claude:claude_dev@localhost:5432/continuous_claude")
BLOG_ID = "stock_moonrabbit"

# 포트폴리오 (RegSHO 체크용)
HOLDINGS = [
    {"ticker": "BNAI", "shares": 464, "avg_cost": 9.55},
    {"ticker": "GLSI", "shares": 67, "avg_cost": 25.22},
]

# 워치리스트
WATCHLIST = [
    {"ticker": "HIMS", "reason": "Short 31%, GLP-1 테마"},
    {"ticker": "SOUN", "reason": "Short 28%, AI 테마"},
]


# ============================================================
# DB 함수
# ============================================================

def get_db():
    return psycopg2.connect(DB_URL)


def init_db():
    """테이블 생성"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS regSHO_list (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            security_name TEXT,
            market_category VARCHAR(10),
            first_seen_date DATE DEFAULT CURRENT_DATE,
            collected_date DATE DEFAULT CURRENT_DATE,
            collected_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS blog_posts (
            id SERIAL PRIMARY KEY,
            post_id VARCHAR(30) UNIQUE,
            title TEXT,
            content TEXT,
            tickers TEXT[],
            keywords TEXT[],
            post_date VARCHAR(50),
            url TEXT,
            is_new BOOLEAN DEFAULT TRUE,
            collected_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS exchange_rates (
            id SERIAL PRIMARY KEY,
            from_currency VARCHAR(3),
            to_currency VARCHAR(3),
            rate DECIMAL(10,4),
            collected_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS blogger_tickers (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            mentioned_in_post VARCHAR(30),
            ticker_info JSONB,
            collected_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_blog_posts_new ON blog_posts(is_new, collected_at DESC);
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ DB 초기화 완료")


def get_existing_post_ids():
    """이미 저장된 포스트 ID 목록"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT post_id FROM blog_posts")
    ids = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return ids


# ============================================================
# RegSHO 수집
# ============================================================

async def collect_regSHO(page):
    """RegSHO Threshold List 수집"""
    url = "https://www.nasdaqtrader.com/trader.aspx?id=regshothreshold"
    await page.goto(url)
    await page.wait_for_timeout(2000)

    content = await page.content()

    tickers = []
    rows = re.findall(r'>([A-Z]{2,5})</td>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>([QGS])</td>', content)

    for ticker, name, market in rows:
        tickers.append({
            "ticker": ticker,
            "name": name.strip(),
            "market": market
        })

    print(f"  RegSHO: {len(tickers)}개 종목")
    return tickers


# ============================================================
# 환율 수집
# ============================================================

async def collect_exchange_rate(page):
    """USD/KRW 환율 수집"""
    url = "https://www.google.com/finance/quote/USD-KRW"
    await page.goto(url)
    await page.wait_for_timeout(2000)

    text = await page.inner_text("body")

    match = re.search(r'(\d{1,3}(?:,\d{3})*\.?\d*)\s*(?:KRW|원)', text)
    if match:
        rate = float(match.group(1).replace(',', ''))
    else:
        rate = 1450.0

    print(f"  환율: $1 = ₩{rate:,.2f}")
    return rate


# ============================================================
# 블로그 수집
# ============================================================

async def collect_blog_posts(page, limit=10):
    """새 블로그 포스트만 수집"""
    existing_ids = get_existing_post_ids()
    print(f"  기존 포스트: {len(existing_ids)}개")

    list_url = f"https://m.blog.naver.com/PostList.naver?blogId={BLOG_ID}&categoryNo=0"
    await page.goto(list_url)
    await page.wait_for_timeout(2000)

    for _ in range(5):
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await page.wait_for_timeout(500)

    links = await page.query_selector_all('a[href*="logNo"]')

    new_posts = []
    seen = set()

    for link in links:
        try:
            href = await link.get_attribute("href")
            if not href or "logNo=" not in href:
                continue

            post_id = href.split("logNo=")[-1].split("&")[0]

            if post_id in seen or post_id in existing_ids:
                continue
            seen.add(post_id)

            if not href.startswith("http"):
                href = f"https://m.blog.naver.com{href}"

            new_posts.append({"post_id": post_id, "url": href})

            if len(new_posts) >= limit:
                break

        except Exception:
            continue

    print(f"  새 포스트: {len(new_posts)}개 발견")

    for post in new_posts:
        try:
            await page.goto(post["url"])
            await page.wait_for_timeout(2000)

            post["title"] = ""
            for sel in ["h3.se_title", "[class*='title']", "h3"]:
                elem = await page.query_selector(sel)
                if elem:
                    post["title"] = (await elem.inner_text()).strip()[:200]
                    if post["title"]:
                        break

            post["date"] = ""
            for sel in ["[class*='date']", "time"]:
                elem = await page.query_selector(sel)
                if elem:
                    post["date"] = (await elem.inner_text()).strip()
                    break

            post["content"] = ""
            for sel in ["div.se-main-container", "div#postViewArea"]:
                elem = await page.query_selector(sel)
                if elem:
                    post["content"] = (await elem.inner_text()).strip()[:10000]
                    break

            content = post.get("content", "")
            raw_tickers = set(re.findall(r'\b([A-Z]{2,5})\b', content))
            common = {'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'SEC', 'ETF', 'CEO', 'IPO', 'FDA', 'NYSE', 'USD', 'KRW', 'SPAC', 'PIPE'}
            post["tickers"] = list(raw_tickers - common)

            keywords = []
            kw_map = {
                "숏스퀴즈": ["숏스퀴즈", "short squeeze", "숏커버"],
                "강제청산": ["강제청산", "forced buy", "close out"],
                "RegSHO": ["regsho", "reg sho", "threshold"],
                "FTD": ["ftd", "fail to deliver"],
                "급등": ["급등", "폭등", "상승"],
                "급락": ["급락", "폭락", "하락"],
            }
            content_lower = content.lower()
            for kw, patterns in kw_map.items():
                if any(p.lower() in content_lower for p in patterns):
                    keywords.append(kw)
            post["keywords"] = keywords

            print(f"    → {post['title'][:40]}... | 티커: {post['tickers'][:5]}")

        except Exception as e:
            print(f"    → 수집 실패: {e}")

    return new_posts


async def collect_blogger_ticker_info(page, tickers):
    """블로거가 언급한 티커들의 추가 정보 수집 (yfinance)"""
    import yfinance as yf

    ticker_info = {}

    for ticker in tickers[:10]:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            ticker_info[ticker] = {
                "name": info.get("shortName") or info.get("longName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "price": info.get("regularMarketPrice"),
            }
            print(f"    {ticker}: {ticker_info[ticker].get('name', 'N/A')}")

        except Exception as e:
            print(f"    {ticker}: 실패 - {e}")
            ticker_info[ticker] = {"name": None, "error": str(e)}

    return ticker_info


# ============================================================
# DB 저장
# ============================================================

def save_to_db(regSHO, exchange_rate, blog_posts, blogger_tickers):
    """수집된 데이터를 DB에 저장"""
    conn = get_db()
    cur = conn.cursor()

    # RegSHO 저장 (연속 등재일 추적)
    cur.execute("""
        SELECT ticker, first_seen_date FROM regsho_list
        WHERE collected_date = (SELECT MAX(collected_date) FROM regsho_list WHERE collected_date < CURRENT_DATE)
    """)
    prev_tickers = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("DELETE FROM regsho_list WHERE collected_date = CURRENT_DATE")
    for item in regSHO:
        ticker = item["ticker"]
        first_seen = prev_tickers.get(ticker, None)
        if first_seen:
            cur.execute("""
                INSERT INTO regsho_list (ticker, security_name, market_category, first_seen_date)
                VALUES (%s, %s, %s, %s)
            """, (ticker, item["name"], item["market"], first_seen))
        else:
            cur.execute("""
                INSERT INTO regsho_list (ticker, security_name, market_category, first_seen_date)
                VALUES (%s, %s, %s, CURRENT_DATE)
            """, (ticker, item["name"], item["market"]))

    # 환율 저장
    cur.execute("""
        INSERT INTO exchange_rates (from_currency, to_currency, rate)
        VALUES ('USD', 'KRW', %s)
    """, (exchange_rate,))

    # 블로그 포스트 저장
    for post in blog_posts:
        cur.execute("""
            INSERT INTO blog_posts (post_id, title, content, tickers, keywords, post_date, url, is_new)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
            ON CONFLICT (post_id) DO NOTHING
        """, (
            post["post_id"],
            post.get("title"),
            post.get("content"),
            post.get("tickers", []),
            post.get("keywords", []),
            post.get("date"),
            post.get("url")
        ))

    # 블로거 언급 티커 정보 저장
    for ticker, info in blogger_tickers.items():
        cur.execute("""
            INSERT INTO blogger_tickers (ticker, ticker_info)
            VALUES (%s, %s)
        """, (ticker, json.dumps(info)))

    conn.commit()
    cur.close()
    conn.close()
    print("✅ DB 저장 완료")


# ============================================================
# 메인
# ============================================================

async def main():
    """
    간소화된 수집기 v3
    - 주가: yfinance 실시간 사용 (수집 불필요)
    - 숏스퀴즈: deep_analyzer가 실시간 분석 (수집 불필요)
    - RegSHO: NASDAQ에서 수집 필요
    - 환율: 하루 1번 수집
    - 블로그: 새 글 스크래핑 필요
    """
    print("=" * 60)
    print(f"📊 Data Collector v3 (Lite) - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    init_db()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 1. RegSHO 수집
        print("\n📋 RegSHO 수집...")
        regSHO = await collect_regSHO(page)

        # 2. 환율 수집
        print("\n💱 환율 수집...")
        exchange_rate = await collect_exchange_rate(page)

        # 3. 블로그 수집 (새 글만)
        print("\n📝 블로그 수집 (새 글만)...")
        blog_posts = await collect_blog_posts(page, limit=10)

        # 4. 블로거 언급 티커 정보 수집
        all_mentioned = set()
        for post in blog_posts:
            all_mentioned.update(post.get("tickers", []))

        blogger_tickers = {}
        if all_mentioned:
            print("\n🔍 블로거 언급 티커 정보 수집...")
            blogger_tickers = await collect_blogger_ticker_info(page, list(all_mentioned))

        await browser.close()

    # DB 저장
    print("\n💾 DB 저장...")
    save_to_db(regSHO, exchange_rate, blog_posts, blogger_tickers)

    # 요약
    print("\n" + "=" * 60)
    print("📊 수집 완료!")
    print(f"  - RegSHO: {len(regSHO)}개")
    print(f"  - 새 블로그 글: {len(blog_posts)}개")
    print(f"  - 블로거 언급 티커: {len(blogger_tickers)}개")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
