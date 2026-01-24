#!/usr/bin/env python3
"""
Stock Briefing Data Collector v2
- Benzinga에서 정확한 주가 수집
- 새 블로그 글만 수집 (DB 비교)
- 블로거 언급 티커 추가 정보 수집
"""

import asyncio
import json
import re
import os
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.async_api import async_playwright

# ============================================================
# 설정
# ============================================================

DB_URL = os.getenv("DATABASE_URL", "postgresql://claude:claude_dev@localhost:5432/continuous_claude")
BLOG_ID = "stock_moonrabbit"

# 포트폴리오
HOLDINGS = [
    {"ticker": "BNAI", "shares": 464, "avg_cost": 9.55},
    {"ticker": "GLSI", "shares": 67, "avg_cost": 25.22},
]

# 워치리스트 (숏스퀴즈 후보)
WATCHLIST = [
    {"ticker": "HIMS", "reason": "Short 31%, GLP-1 테마, Novo 협상"},
    {"ticker": "SOUN", "reason": "Short 28%, AI 테마, 2/26 실적"},
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
        CREATE TABLE IF NOT EXISTS stock_prices (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            regular_price DECIMAL(10,4),
            afterhours_price DECIMAL(10,4),
            premarket_price DECIMAL(10,4),
            change_percent DECIMAL(8,4),
            source VARCHAR(50),
            collected_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS regSHO_list (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            security_name TEXT,
            market_category VARCHAR(10),
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

        CREATE TABLE IF NOT EXISTS stock_briefing (
            id SERIAL PRIMARY KEY,
            briefing_date DATE DEFAULT CURRENT_DATE,
            briefing_json JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_stock_prices_ticker ON stock_prices(ticker, collected_at DESC);
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


def mark_posts_as_read():
    """모든 새 글을 읽음 처리"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE blog_posts SET is_new = FALSE WHERE is_new = TRUE")
    conn.commit()
    cur.close()
    conn.close()


# ============================================================
# 주가 수집 (Benzinga)
# ============================================================

async def collect_stock_prices(page, tickers):
    """주가 수집 (yfinance 우선, 더 안정적)"""
    import yfinance as yf

    prices = {}

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            regular = info.get("regularMarketPrice") or info.get("currentPrice")
            premarket = info.get("preMarketPrice")
            afterhours = info.get("postMarketPrice")
            change_pct = info.get("regularMarketChangePercent")

            prices[ticker] = {
                "regular": regular,
                "afterhours": afterhours,
                "premarket": premarket,
                "change_pct": round(change_pct, 2) if change_pct else None,
            }

            current = afterhours or premarket or regular
            print(f"  {ticker}: 종가 ${regular} | AH ${afterhours} | PM ${premarket} | 현재 ${current}")

        except Exception as e:
            print(f"  {ticker}: yfinance 실패 - {e}")
            prices[ticker] = {"regular": None, "afterhours": None, "premarket": None, "change_pct": None}

    return prices


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
    # 테이블에서 티커 추출
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

    # 환율 패턴
    match = re.search(r'(\d{1,3}(?:,\d{3})*\.?\d*)\s*(?:KRW|원)', text)
    if match:
        rate = float(match.group(1).replace(',', ''))
    else:
        rate = 1450.0  # 기본값

    print(f"  환율: $1 = ₩{rate:,.2f}")
    return rate


# ============================================================
# 블로그 수집 (새 글만)
# ============================================================

async def collect_blog_posts(page, limit=10):
    """새 블로그 포스트만 수집"""
    existing_ids = get_existing_post_ids()
    print(f"  기존 포스트: {len(existing_ids)}개")

    # 포스트 목록 페이지
    list_url = f"https://m.blog.naver.com/PostList.naver?blogId={BLOG_ID}&categoryNo=0"
    await page.goto(list_url)
    await page.wait_for_timeout(2000)

    # 스크롤해서 더 많은 포스트 로드
    for _ in range(5):
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await page.wait_for_timeout(500)

    # 포스트 링크 수집
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

            new_posts.append({
                "post_id": post_id,
                "url": href
            })

            if len(new_posts) >= limit:
                break

        except Exception:
            continue

    print(f"  새 포스트: {len(new_posts)}개 발견")

    # 각 새 포스트 내용 수집
    for post in new_posts:
        try:
            await page.goto(post["url"])
            await page.wait_for_timeout(2000)

            # 제목
            post["title"] = ""
            for sel in ["h3.se_title", "[class*='title']", "h3"]:
                elem = await page.query_selector(sel)
                if elem:
                    post["title"] = (await elem.inner_text()).strip()[:200]
                    if post["title"]:
                        break

            # 날짜
            post["date"] = ""
            for sel in ["[class*='date']", "time"]:
                elem = await page.query_selector(sel)
                if elem:
                    post["date"] = (await elem.inner_text()).strip()
                    break

            # 본문
            post["content"] = ""
            for sel in ["div.se-main-container", "div#postViewArea"]:
                elem = await page.query_selector(sel)
                if elem:
                    post["content"] = (await elem.inner_text()).strip()[:10000]
                    break

            # 티커 추출
            content = post.get("content", "")
            raw_tickers = set(re.findall(r'\b([A-Z]{2,5})\b', content))
            # 일반 단어 제외
            common = {'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'SEC', 'ETF', 'CEO', 'IPO', 'FDA', 'NYSE', 'USD', 'KRW', 'SPAC', 'PIPE'}
            post["tickers"] = list(raw_tickers - common)

            # 키워드 추출
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


# ============================================================
# 블로거 언급 티커 추가 정보 수집
# ============================================================

async def collect_blogger_ticker_info(page, tickers):
    """블로거가 언급한 티커들의 추가 정보 수집"""
    ticker_info = {}

    # 보유 종목 제외, 새로 언급된 티커만
    my_tickers = {h["ticker"] for h in HOLDINGS}
    new_tickers = [t for t in tickers if t not in my_tickers][:5]  # 최대 5개

    for ticker in new_tickers:
        try:
            url = f"https://www.benzinga.com/quote/{ticker.lower()}"
            await page.goto(url)
            await page.wait_for_timeout(2000)

            text = await page.inner_text("body")

            # 기본 정보 추출
            price_match = re.search(r'\$(\d+\.?\d*)', text)
            change_match = re.search(r'([+-]?\d+\.?\d*)\s*%', text)

            ticker_info[ticker] = {
                "price": float(price_match.group(1)) if price_match else None,
                "change_pct": float(change_match.group(1)) if change_match else None,
                "collected_at": datetime.now().isoformat()
            }

            print(f"    {ticker}: ${ticker_info[ticker]['price']} ({ticker_info[ticker]['change_pct']}%)")

        except Exception as e:
            print(f"    {ticker}: 수집 실패")

    return ticker_info


# ============================================================
# DB 저장
# ============================================================

def save_to_db(prices, regSHO, exchange_rate, blog_posts, blogger_tickers):
    """수집된 데이터를 DB에 저장"""
    conn = get_db()
    cur = conn.cursor()

    # 주가 저장
    for ticker, data in prices.items():
        cur.execute("""
            INSERT INTO stock_prices (ticker, regular_price, afterhours_price, premarket_price, change_percent, source)
            VALUES (%s, %s, %s, %s, %s, 'benzinga')
        """, (ticker, data.get("regular"), data.get("afterhours"), data.get("premarket"), data.get("change_pct")))

    # RegSHO 저장
    cur.execute("DELETE FROM regSHO_list WHERE collected_date = CURRENT_DATE")
    for item in regSHO:
        cur.execute("""
            INSERT INTO regSHO_list (ticker, security_name, market_category)
            VALUES (%s, %s, %s)
        """, (item["ticker"], item["name"], item["market"]))

    # 환율 저장
    cur.execute("""
        INSERT INTO exchange_rates (from_currency, to_currency, rate)
        VALUES ('USD', 'KRW', %s)
    """, (exchange_rate,))

    # 블로그 포스트 저장 (새 글만)
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

    # 브리핑 JSON 생성 및 저장
    briefing = generate_briefing(prices, regSHO, exchange_rate, blog_posts, blogger_tickers)
    cur.execute("DELETE FROM stock_briefing WHERE briefing_date = CURRENT_DATE")
    cur.execute("""
        INSERT INTO stock_briefing (briefing_date, briefing_json)
        VALUES (CURRENT_DATE, %s)
    """, (json.dumps(briefing, ensure_ascii=False),))

    conn.commit()
    cur.close()
    conn.close()
    print("✅ DB 저장 완료")


def generate_briefing(prices, regSHO, exchange_rate, blog_posts, blogger_tickers):
    """브리핑 JSON 생성"""
    # 포트폴리오 계산
    portfolio = []
    total_value = 0
    total_cost = 0

    for holding in HOLDINGS:
        ticker = holding["ticker"]
        data = prices.get(ticker, {})

        # 우선순위: 애프터 > 프리 > 종가
        current = data.get("afterhours") or data.get("premarket") or data.get("regular") or 0

        value = holding["shares"] * current
        cost = holding["shares"] * holding["avg_cost"]
        gain = value - cost
        gain_pct = (gain / cost * 100) if cost > 0 else 0

        portfolio.append({
            "ticker": ticker,
            "shares": holding["shares"],
            "avg_cost": holding["avg_cost"],
            "regular_price": data.get("regular"),
            "afterhours_price": data.get("afterhours"),
            "premarket_price": data.get("premarket"),
            "current_price": current,
            "value": round(value, 2),
            "gain": round(gain, 2),
            "gain_pct": round(gain_pct, 1)
        })

        total_value += value
        total_cost += cost

    total_gain = total_value - total_cost
    total_gain_krw = total_gain * exchange_rate

    # 세금 계산
    taxable = max(0, total_gain_krw - 2500000)
    tax = taxable * 0.22
    net_profit = total_gain_krw - tax

    # RegSHO 체크
    regSHO_tickers = {item["ticker"] for item in regSHO}
    holdings_in_regSHO = [h["ticker"] for h in HOLDINGS if h["ticker"] in regSHO_tickers]

    # 새 블로그 글 요약
    new_blog_posts = []
    all_blog_tickers = set()
    for post in blog_posts:
        new_blog_posts.append({
            "title": post.get("title", "")[:100],
            "url": post.get("url"),
            "tickers": post.get("tickers", [])[:10],
            "keywords": post.get("keywords", []),
            "date": post.get("date")
        })
        all_blog_tickers.update(post.get("tickers", []))

    return {
        "timestamp": datetime.now().isoformat(),
        "exchange_rate": exchange_rate,
        "portfolio": portfolio,
        "total": {
            "value_usd": round(total_value, 2),
            "value_krw": round(total_value * exchange_rate, 0),
            "gain_usd": round(total_gain, 2),
            "gain_krw": round(total_gain_krw, 0),
            "gain_pct": round((total_gain / total_cost * 100) if total_cost > 0 else 0, 1)
        },
        "tax": {
            "taxable_krw": round(taxable, 0),
            "tax_krw": round(tax, 0),
            "net_profit_krw": round(net_profit, 0)
        },
        "regSHO": {
            "total_count": len(regSHO),
            "holdings_on_list": holdings_in_regSHO,
            "top_tickers": [item["ticker"] for item in regSHO[:15]]
        },
        "new_blog_posts": new_blog_posts,
        "blogger_mentioned_tickers": list(all_blog_tickers),
        "blogger_ticker_info": blogger_tickers
    }


# ============================================================
# 메인
# ============================================================

async def main():
    print("=" * 60)
    print(f"📊 Stock Data Collector v2 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    init_db()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 1. 주가 수집 (포트폴리오 + 워치리스트)
        print("\n📈 주가 수집...")
        tickers = [h["ticker"] for h in HOLDINGS] + [w["ticker"] for w in WATCHLIST]
        prices = await collect_stock_prices(page, tickers)

        # 2. RegSHO 수집
        print("\n📋 RegSHO 수집...")
        regSHO = await collect_regSHO(page)

        # 3. 환율 수집
        print("\n💱 환율 수집...")
        exchange_rate = await collect_exchange_rate(page)

        # 4. 블로그 수집 (새 글만)
        print("\n📝 블로그 수집 (새 글만)...")
        blog_posts = await collect_blog_posts(page, limit=10)

        # 5. 블로거 언급 티커 정보 수집
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
    save_to_db(prices, regSHO, exchange_rate, blog_posts, blogger_tickers)

    # 요약
    print("\n" + "=" * 60)
    print("📊 수집 완료!")
    print(f"  - 주가: {len(prices)}개")
    print(f"  - RegSHO: {len(regSHO)}개")
    print(f"  - 새 블로그 글: {len(blog_posts)}개")
    print(f"  - 블로거 언급 티커: {len(blogger_tickers)}개")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
