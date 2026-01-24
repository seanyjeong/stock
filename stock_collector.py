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

        CREATE TABLE IF NOT EXISTS ticker_info (
            ticker VARCHAR(10) PRIMARY KEY,
            company_name TEXT,
            sector TEXT,
            industry TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS squeeze_data (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            borrow_rate DECIMAL(10,2),
            short_interest DECIMAL(10,2),
            days_to_cover DECIMAL(8,2),
            short_volume BIGINT,
            squeeze_score DECIMAL(8,2),
            available_shares BIGINT,
            float_shares BIGINT,
            dilution_protected BOOLEAN DEFAULT FALSE,
            has_positive_news BOOLEAN DEFAULT FALSE,
            has_negative_news BOOLEAN DEFAULT FALSE,
            source VARCHAR(50),
            collected_at TIMESTAMP DEFAULT NOW()
        );

        -- v2 컬럼 추가 (이미 테이블 있으면)
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='squeeze_data' AND column_name='available_shares') THEN
                ALTER TABLE squeeze_data ADD COLUMN available_shares BIGINT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='squeeze_data' AND column_name='float_shares') THEN
                ALTER TABLE squeeze_data ADD COLUMN float_shares BIGINT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='squeeze_data' AND column_name='dilution_protected') THEN
                ALTER TABLE squeeze_data ADD COLUMN dilution_protected BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='squeeze_data' AND column_name='has_positive_news') THEN
                ALTER TABLE squeeze_data ADD COLUMN has_positive_news BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='squeeze_data' AND column_name='has_negative_news') THEN
                ALTER TABLE squeeze_data ADD COLUMN has_negative_news BOOLEAN DEFAULT FALSE;
            END IF;
        END $$;

        CREATE INDEX IF NOT EXISTS idx_stock_prices_ticker ON stock_prices(ticker, collected_at DESC);
        CREATE INDEX IF NOT EXISTS idx_blog_posts_new ON blog_posts(is_new, collected_at DESC);
        CREATE INDEX IF NOT EXISTS idx_squeeze_data_ticker ON squeeze_data(ticker, collected_at DESC);
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


def update_ticker_info(tickers):
    """티커 정보(회사명) 업데이트 - yfinance 사용"""
    import yfinance as yf

    conn = get_db()
    cur = conn.cursor()

    for ticker in tickers:
        try:
            # 이미 있는지 확인
            cur.execute("SELECT ticker FROM ticker_info WHERE ticker = %s", (ticker,))
            if cur.fetchone():
                continue  # 이미 있으면 스킵

            stock = yf.Ticker(ticker)
            info = stock.info

            company_name = info.get("shortName") or info.get("longName") or ticker
            sector = info.get("sector")
            industry = info.get("industry")

            cur.execute("""
                INSERT INTO ticker_info (ticker, company_name, sector, industry, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (ticker) DO UPDATE SET
                    company_name = EXCLUDED.company_name,
                    sector = EXCLUDED.sector,
                    industry = EXCLUDED.industry,
                    updated_at = NOW()
            """, (ticker, company_name, sector, industry))

            print(f"  ✅ {ticker}: {company_name}")
        except Exception as e:
            print(f"  ❌ {ticker}: {e}")

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
# Borrow Rate 수집 (shortablestocks.com - 무료)
# ============================================================

async def collect_borrow_rates(page, tickers):
    """shortablestocks.com에서 Borrow 정보 수집"""
    from playwright_stealth import Stealth

    borrow_data = {}

    # Stealth 적용 (봇 감지 우회)
    stealth = Stealth()
    await stealth.apply_stealth_async(page.context)

    for ticker in tickers:
        try:
            url = f"https://www.shortablestocks.com/?{ticker}"
            await page.goto(url, timeout=20000)
            await page.wait_for_timeout(3000)

            text = await page.inner_text("body")

            # "Zero Borrow" = 빌릴 주식 없음 (극도로 높은 borrow rate)
            is_zero_borrow = "zero borrow" in text.lower()

            # Short Interest 데이터 추출
            # 패턴: "12/31/2025	1,230,242	14,571,178	1"
            si_match = re.search(r'\d{1,2}/\d{1,2}/\d{4}\s+([\d,]+)\s+([\d,]+)\s+(\d+)', text)

            short_interest_shares = None
            avg_volume = None
            days_to_cover_official = None

            if si_match:
                short_interest_shares = int(si_match.group(1).replace(',', ''))
                avg_volume = int(si_match.group(2).replace(',', ''))
                days_to_cover_official = int(si_match.group(3))

            # Zero Borrow = 999% (극도로 높음), 아니면 None
            borrow_rate = 999.0 if is_zero_borrow else None

            available = 0 if is_zero_borrow else None
            borrow_data[ticker] = {
                "borrow_rate": borrow_rate,
                "available_shares": available,
                "short_interest_shares": short_interest_shares,
                "is_zero_borrow": is_zero_borrow,
            }

            if is_zero_borrow:
                print(f"  🔥 {ticker}: ZERO BORROW! (빌릴 주식 없음)")
            elif short_interest_shares:
                print(f"  {ticker}: SI {short_interest_shares:,}주")
            else:
                print(f"  {ticker}: 데이터 없음")

        except Exception as e:
            print(f"  ❌ {ticker}: {e}")
            borrow_data[ticker] = {
                "borrow_rate": None,
                "available_shares": None,
                "short_interest_shares": None,
                "is_zero_borrow": False,
            }

    return borrow_data


# ============================================================
# SEC EDGAR 워런트/희석 정보 (Full-Text Search API)
# ============================================================

async def collect_sec_dilution_info(tickers):
    """SEC EDGAR Full-Text Search로 워런트/희석 관련 정보 수집"""
    import httpx

    dilution_data = {}
    headers = {"User-Agent": "DailyStockStory/1.0 (contact@example.com)"}

    async with httpx.AsyncClient(timeout=30) as client:
        for ticker in tickers:
            try:
                found_info = {
                    "warrant_mentions": 0,
                    "dilution_mentions": 0,
                    "covenant_mentions": 0,
                    "positive_news": 0,  # 호재 뉴스
                    "negative_news": 0,  # 악재 뉴스
                }

                # SEC Full-Text Search: 티커 + 키워드로 직접 검색
                keywords_to_search = [
                    ("warrant", "warrant_mentions"),
                    ("dilution", "dilution_mentions"),
                    ("covenant", "covenant_mentions"),
                ]

                # 호재 키워드 (2025년 이후만)
                positive_keywords = ["deal", "partnership", "contract", "agreement"]

                for keyword, field in keywords_to_search:
                    search_url = f'https://efts.sec.gov/LATEST/search-index?q="{keyword}" AND "{ticker}"&dateRange=custom&startdt=2024-01-01'
                    resp = await client.get(search_url, headers=headers)

                    if resp.status_code == 200:
                        data = resp.json()
                        count = data.get("hits", {}).get("total", {}).get("value", 0)
                        found_info[field] = count

                # 호재 공시 검색 (2025년)
                for pk in positive_keywords:
                    search_url = f'https://efts.sec.gov/LATEST/search-index?q="{pk}" AND "{ticker}"&dateRange=custom&startdt=2025-01-01'
                    resp = await client.get(search_url, headers=headers)
                    if resp.status_code == 200:
                        count = resp.json().get("hits", {}).get("total", {}).get("value", 0)
                        found_info["positive_news"] += count

                # 악재 키워드 검색 (2025년)
                negative_keywords = ["lawsuit", "bankruptcy", "default", "fraud", "investigation", "delisting"]
                for nk in negative_keywords:
                    search_url = f'https://efts.sec.gov/LATEST/search-index?q="{nk}" AND "{ticker}"&dateRange=custom&startdt=2025-01-01'
                    resp = await client.get(search_url, headers=headers)
                    if resp.status_code == 200:
                        count = resp.json().get("hits", {}).get("total", {}).get("value", 0)
                        found_info["negative_news"] += count

                # 결과 해석
                has_warrant = found_info["warrant_mentions"] > 10
                has_dilution = found_info["dilution_mentions"] > 5
                has_covenant = found_info["covenant_mentions"] > 3
                has_positive_news = found_info["positive_news"] > 50  # 50건 이상 = 호재
                has_negative_news = found_info["negative_news"] > 20  # 20건 이상 = 악재

                dilution_data[ticker] = {
                    "has_warrant_info": has_warrant,
                    "has_debt_covenant": has_covenant,
                    "dilution_risk": has_dilution,
                    "has_positive_news": has_positive_news,
                    "has_negative_news": has_negative_news,
                    "positive_news_count": found_info["positive_news"],
                    "negative_news_count": found_info["negative_news"],
                    "warrant_mentions": found_info["warrant_mentions"],
                    "dilution_mentions": found_info["dilution_mentions"],
                    "covenant_mentions": found_info["covenant_mentions"],
                }

                # 출력
                details = []
                if has_warrant:
                    details.append(f"워런트({found_info['warrant_mentions']}건)")
                if has_dilution:
                    details.append(f"희석({found_info['dilution_mentions']}건)")
                if has_covenant:
                    details.append(f"covenant({found_info['covenant_mentions']}건)")
                if has_positive_news:
                    details.append(f"호재({found_info['positive_news']}건)🔥")
                if has_negative_news:
                    details.append(f"악재({found_info['negative_news']}건)⚠️")

                if details:
                    print(f"  🔍 {ticker}: {', '.join(details)}")
                else:
                    print(f"  {ticker}: SEC 특이사항 없음")

            except Exception as e:
                print(f"  ❌ {ticker} SEC: {e}")
                dilution_data[ticker] = {
                    "has_warrant_info": False,
                    "has_debt_covenant": False,
                    "dilution_risk": False,
                    "has_positive_news": False,
                    "has_negative_news": False,
                    "positive_news_count": 0,
                    "negative_news_count": 0,
                    "warrant_mentions": 0,
                    "dilution_mentions": 0,
                    "covenant_mentions": 0,
                }

    return dilution_data


# ============================================================
# 숏스퀴즈 데이터 수집 (yfinance + Chartexchange)
# ============================================================

async def collect_squeeze_data(page, tickers):
    """숏스퀴즈 관련 데이터 수집 (v2: yfinance + Borrow Rate + SEC)"""
    import yfinance as yf

    # RegSHO + 보유종목 전체 수집 (cron이니까 시간 OK)
    print(f"  📊 Borrow Rate 수집 ({len(tickers)}개 종목)...")
    borrow_data = await collect_borrow_rates(page, tickers)

    # SEC 희석 정보는 보유 종목만 (API 요청 제한)
    priority_tickers = [h["ticker"] for h in HOLDINGS] + [w["ticker"] for w in WATCHLIST]
    print(f"  📋 SEC 희석 정보 수집 ({len(priority_tickers)}개 보유/워치 종목)...")
    dilution_data = await collect_sec_dilution_info(priority_tickers)

    # 3. yfinance 데이터 + 통합
    print("  📈 yfinance 데이터 수집...")
    squeeze_data = {}

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Short Interest (유동주식 대비 공매도 비율, %)
            short_pct = info.get("shortPercentOfFloat")
            short_interest = round(short_pct * 100, 2) if short_pct else None

            # Days to Cover (Short Ratio)
            days_to_cover = info.get("shortRatio")

            # Shares Short
            short_volume = info.get("sharesShort")

            # Float shares for context
            float_shares = info.get("floatShares")

            # Borrow Rate & SEC 정보 통합
            borrow_info = borrow_data.get(ticker, {})
            dilution_info = dilution_data.get(ticker, {})
            borrow_rate = borrow_info.get("borrow_rate")
            available_shares = borrow_info.get("available_shares")

            # 스퀴즈 점수 v2 계산 (0-100)
            squeeze_score = calculate_squeeze_score_v2(
                borrow_rate=borrow_rate,
                short_interest=short_interest,
                days_to_cover=days_to_cover,
                available_shares=available_shares,
                has_warrant_info=dilution_info.get("has_warrant_info", False),
                has_debt_covenant=dilution_info.get("has_debt_covenant", False),
                float_shares=float_shares,
                has_positive_news=dilution_info.get("has_positive_news", False),
                has_negative_news=dilution_info.get("has_negative_news", False),
            )

            squeeze_data[ticker] = {
                "borrow_rate": borrow_rate,
                "short_interest": short_interest,
                "days_to_cover": round(days_to_cover, 2) if days_to_cover else None,
                "short_volume": short_volume,
                "squeeze_score": squeeze_score,
                "available_shares": available_shares,
                "float_shares": float_shares,
                "dilution_protected": dilution_info.get("has_warrant_info") or dilution_info.get("has_debt_covenant"),
                "has_positive_news": dilution_info.get("has_positive_news", False),
                "has_negative_news": dilution_info.get("has_negative_news", False),
            }

            print(f"  {ticker}: SI {short_interest}% | BR {borrow_rate}% | Score {squeeze_score}")

        except Exception as e:
            print(f"  ❌ {ticker}: {e}")
            squeeze_data[ticker] = {
                "borrow_rate": None,
                "short_interest": None,
                "days_to_cover": None,
                "short_volume": None,
                "squeeze_score": None,
                "available_shares": None,
                "float_shares": None,
                "dilution_protected": False,
                "has_positive_news": False,
                "has_negative_news": False,
            }

    return squeeze_data


def calculate_squeeze_score_v2(borrow_rate, short_interest, days_to_cover,
                               available_shares=None, has_warrant_info=False,
                               has_debt_covenant=False, float_shares=None,
                               has_positive_news=False, has_negative_news=False):
    """
    숏스퀴즈 확률 점수 v2 (0-100)

    Base Score (0-60):
      - Short Interest: 0-25점 (50%+ = 만점)
      - Borrow Rate: 0-20점 (200%+ = 만점)
      - Days to Cover: 0-15점 (10일+ = 만점)

    Squeeze Pressure Bonus (0-25):
      - No shares available: +10점
      - Low float (<10M): +5점
      - Warrant/debt protection: +10점

    Catalyst Bonus (0-10):
      - Positive news/filings: +10점

    Risk Penalty (-15):
      - Negative news (lawsuit/bankruptcy/fraud): -15점

    Urgency Bonus (0-15):
      - Very high borrow rate (>300%): +10점
      - Extreme short interest (>40%): +5점
    """
    if not any([borrow_rate, short_interest, days_to_cover]):
        return None

    score = 0

    # === Base Score (0-60) ===

    # Short Interest 점수 (0-25): 50%+ = 만점
    if short_interest:
        si_score = min(short_interest / 50 * 25, 25)
        score += si_score

    # Borrow Rate 점수 (0-20): 200%+ = 만점
    if borrow_rate:
        br_score = min(borrow_rate / 200 * 20, 20)
        score += br_score

    # Days to Cover 점수 (0-15): 10일+ = 만점
    if days_to_cover:
        dtc_score = min(days_to_cover / 10 * 15, 15)
        score += dtc_score

    # === Squeeze Pressure Bonus (0-25) ===

    # No shares available = 쇼티 빌릴 주식 없음
    if available_shares is not None and available_shares == 0:
        score += 10

    # Low float = 작은 유동주식수
    if float_shares and float_shares < 10_000_000:
        score += 5

    # Warrant/Debt protection = 희석 방어
    if has_warrant_info or has_debt_covenant:
        score += 10

    # === Catalyst Bonus (0-10) ===

    # Positive news/filings = 호재 공시
    if has_positive_news:
        score += 10

    # === Risk Penalty (-15) ===

    # Negative news = 악재 (소송, 파산, 사기 등)
    if has_negative_news:
        score -= 15

    # === Urgency Bonus (0-15) ===

    # Very high borrow rate
    if borrow_rate and borrow_rate > 300:
        score += 10

    # Extreme short interest
    if short_interest and short_interest > 40:
        score += 5

    return round(min(score, 100), 1)


# v1 호환용 (deprecated)
def calculate_squeeze_score(borrow_rate, short_interest, days_to_cover):
    """Legacy v1 score - use calculate_squeeze_score_v2 instead"""
    return calculate_squeeze_score_v2(borrow_rate, short_interest, days_to_cover)


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

def save_to_db(prices, regSHO, exchange_rate, blog_posts, blogger_tickers, squeeze_data=None):
    """수집된 데이터를 DB에 저장"""
    conn = get_db()
    cur = conn.cursor()

    # 주가 저장
    for ticker, data in prices.items():
        cur.execute("""
            INSERT INTO stock_prices (ticker, regular_price, afterhours_price, premarket_price, change_percent, source)
            VALUES (%s, %s, %s, %s, %s, 'benzinga')
        """, (ticker, data.get("regular"), data.get("afterhours"), data.get("premarket"), data.get("change_pct")))

    # RegSHO 저장 (연속 등재일 추적)
    # 어제 등재된 티커와 first_seen_date 가져오기
    cur.execute("""
        SELECT ticker, first_seen_date FROM regsho_list
        WHERE collected_date = (SELECT MAX(collected_date) FROM regsho_list WHERE collected_date < CURRENT_DATE)
    """)
    prev_tickers = {row[0]: row[1] for row in cur.fetchall()}

    # 오늘 데이터 삭제 후 새로 저장
    cur.execute("DELETE FROM regsho_list WHERE collected_date = CURRENT_DATE")
    for item in regSHO:
        ticker = item["ticker"]
        # 어제도 있었으면 first_seen_date 유지, 아니면 오늘 날짜
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

    # 숏스퀴즈 데이터 저장 (v2)
    if squeeze_data:
        for ticker, data in squeeze_data.items():
            if data.get("squeeze_score") is not None:
                cur.execute("""
                    INSERT INTO squeeze_data (ticker, borrow_rate, short_interest, days_to_cover, short_volume, squeeze_score, available_shares, float_shares, dilution_protected, has_positive_news, has_negative_news, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'v2_combined')
                """, (
                    ticker,
                    data.get("borrow_rate"),
                    data.get("short_interest"),
                    data.get("days_to_cover"),
                    data.get("short_volume"),
                    data.get("squeeze_score"),
                    data.get("available_shares"),
                    data.get("float_shares"),
                    data.get("dilution_protected", False),
                    data.get("has_positive_news", False),
                    data.get("has_negative_news", False),
                ))

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

        # 6. 숏스퀴즈 데이터 수집 (포트폴리오 + RegSHO 종목)
        print("\n🔥 숏스퀴즈 데이터 수집...")
        squeeze_tickers = list(set(tickers + [r["ticker"] for r in regSHO]))
        squeeze_data = await collect_squeeze_data(page, squeeze_tickers)

        await browser.close()

    # DB 저장
    print("\n💾 DB 저장...")
    save_to_db(prices, regSHO, exchange_rate, blog_posts, blogger_tickers, squeeze_data)

    # 티커 정보(회사명) 업데이트
    print("\n📛 티커 정보 업데이트...")
    update_ticker_info(tickers)

    # 요약
    print("\n" + "=" * 60)
    print("📊 수집 완료!")
    print(f"  - 주가: {len(prices)}개")
    print(f"  - RegSHO: {len(regSHO)}개")
    print(f"  - 새 블로그 글: {len(blog_posts)}개")
    print(f"  - 블로거 언급 티커: {len(blogger_tickers)}개")
    print(f"  - 숏스퀴즈 데이터: {len(squeeze_data)}개")
    print("=" * 60)

    # 푸시 알림 발송
    print("\n🔔 푸시 알림 발송...")
    try:
        from api.notifications import send_data_update_notification
        result = send_data_update_notification()
        print(f"  - 발송: {result.get('sent', 0)}건, 만료 삭제: {result.get('expired', 0)}건")
    except Exception as e:
        print(f"  - 알림 발송 실패: {e}")


if __name__ == "__main__":
    asyncio.run(main())
