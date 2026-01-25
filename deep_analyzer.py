#!/usr/bin/env python3
"""
🔥 초정밀 주식 분석기 v4 (Deep Stock Analyzer) - 나스닥의 신 에디션
Zero Borrow 감지 + Gemini AI 분석 + 섹터별 특화 분석!

v4 새 기능:
- 섹터별 특화 뉴스 (바이오텍/AI·Tech/에너지/일반)
- 바이오텍 촉매 분석 (FDA Fast Track, ClinicalTrials.gov 연동)
- 8-K 주요 이벤트 파싱 (FDA 승인, 임상결과, 계약 등)
- 구글 뉴스 백업 + 최근 60일 필터
- SPAC/Earnout 조건 자동 추출

v3 기능:
- SPAC/Earnout 조건 자동 추출 (S-4, DEFM14A)
- 락업 가격 추출 개선 (가격 기반 락업)
- google.genai 새 SDK 마이그레이션

Usage:
    uv run python deep_analyzer.py BNAI
    uv run python deep_analyzer.py BNAI --no-ai   # AI 분석 스킵
    uv run python deep_analyzer.py GLSI --normal  # 일반 분석 모드
"""

import sys
import os
import json
import re
from datetime import datetime, timedelta
from typing import Optional
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import psycopg2
import pandas as pd

# Gemini API (새 SDK)
from google import genai

# ============================================================
# 설정
# ============================================================

DB_CONFIG = {
    "host": "localhost",
    "database": "dailystock",
    "user": "dailystock",
    "password": "dailystock123",
    "port": 5432
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
}

# Gemini 설정 (새 SDK) - 환경변수에서만 로드!
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


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


def section(title: str, emoji: str = "📊"):
    """섹션 헤더"""
    print(f"\n{'='*70}")
    print(f"{emoji} {title}")
    print(f"{'='*70}")


def subsection(title: str):
    """서브섹션"""
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


# ============================================================
# 1. 기본 정보 (yfinance)
# ============================================================

def get_basic_info(ticker: str) -> dict:
    """yfinance에서 모든 기본 정보 수집"""
    stock = yf.Ticker(ticker)
    info = stock.info

    return {
        "info": info,
        "stock": stock,
        "name": info.get("shortName") or info.get("longName", ticker),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "website": info.get("website"),
        "description": info.get("longBusinessSummary"),
        "employees": info.get("fullTimeEmployees"),
        "exchange": info.get("exchange"),
        "quote_type": info.get("quoteType"),
        # 가격
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "prev_close": info.get("previousClose"),
        "open": info.get("open"),
        "day_high": info.get("dayHigh"),
        "day_low": info.get("dayLow"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "50d_avg": info.get("fiftyDayAverage"),
        "200d_avg": info.get("twoHundredDayAverage"),
        "pre_market": info.get("preMarketPrice"),
        "post_market": info.get("postMarketPrice"),
        # 거래량
        "volume": info.get("volume"),
        "avg_volume": info.get("averageVolume"),
        "avg_volume_10d": info.get("averageVolume10days"),
        # 시총/주식수
        "market_cap": info.get("marketCap"),
        "enterprise_value": info.get("enterpriseValue"),
        "shares_outstanding": info.get("sharesOutstanding"),
        "float_shares": info.get("floatShares"),
        # 재무
        "revenue": info.get("totalRevenue"),
        "revenue_growth": info.get("revenueGrowth"),
        "ebitda": info.get("ebitda"),
        "net_income": info.get("netIncomeToCommon"),
        "eps": info.get("trailingEps"),
        "pe_ratio": info.get("trailingPE"),
        "total_cash": info.get("totalCash"),
        "total_debt": info.get("totalDebt"),
        "debt_to_equity": info.get("debtToEquity"),
        # 숏
        "short_ratio": info.get("shortRatio"),
        "short_pct_float": info.get("shortPercentOfFloat"),
        "shares_short": info.get("sharesShort"),
        "shares_short_prior": info.get("sharesShortPriorMonth"),
        "short_date": info.get("dateShortInterest"),
        # 내부자/기관
        "insider_pct": info.get("heldPercentInsiders"),
        "institution_pct": info.get("heldPercentInstitutions"),
        # 기타
        "beta": info.get("beta"),
        "target_mean": info.get("targetMeanPrice"),
        "recommendation": info.get("recommendationKey"),
    }


# ============================================================
# 2. Zero Borrow & Borrow Rate (shortablestocks.com)
# ============================================================

def get_borrow_data(ticker: str) -> dict:
    """shortablestocks.com에서 Zero Borrow 및 Borrow Rate 수집"""
    url = f"https://www.shortablestocks.com/?{ticker}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        text = resp.text

        # Zero Borrow 감지 (가장 중요!)
        is_zero_borrow = "zero borrow" in text.lower()

        # Hard to Borrow 감지
        is_hard_to_borrow = "hard to borrow" in text.lower()

        # Short Interest 데이터 추출 (패턴: 날짜 숫자 숫자 숫자)
        si_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})\s+([\d,]+)\s+([\d,]+)\s+(\d+)', text)

        short_interest_shares = None
        avg_volume = None
        days_to_cover = None
        si_date = None

        if si_match:
            si_date = si_match.group(1)
            short_interest_shares = int(si_match.group(2).replace(',', ''))
            avg_volume = int(si_match.group(3).replace(',', ''))
            days_to_cover = int(si_match.group(4))

        # Borrow Rate 추출 시도 (테이블에서)
        borrow_rate = None
        available_shares = None

        # Fee Rate 패턴 찾기
        fee_match = re.search(r'(\d+\.?\d*)%?\s*fee', text.lower())
        if fee_match:
            borrow_rate = float(fee_match.group(1))

        # Available shares 패턴
        avail_match = re.search(r'available[:\s]+([\d,]+)', text.lower())
        if avail_match:
            available_shares = int(avail_match.group(1).replace(',', ''))

        # Zero Borrow면 극단적 설정
        if is_zero_borrow:
            borrow_rate = 999.0  # 사실상 무한대
            available_shares = 0

        return {
            "is_zero_borrow": is_zero_borrow,
            "is_hard_to_borrow": is_hard_to_borrow,
            "borrow_rate": borrow_rate,
            "available_shares": available_shares,
            "short_interest_shares": short_interest_shares,
            "avg_volume": avg_volume,
            "days_to_cover": days_to_cover,
            "si_date": si_date,
            "source": "shortablestocks.com"
        }

    except Exception as e:
        print(f"  ⚠️ Borrow 데이터 수집 실패: {e}")
        return {
            "is_zero_borrow": None,
            "is_hard_to_borrow": None,
            "borrow_rate": None,
            "available_shares": None,
            "short_interest_shares": None,
            "avg_volume": None,
            "days_to_cover": None,
            "si_date": None,
            "source": None
        }


# ============================================================
# 3. Fintel 스퀴즈 스코어 (웹 스크래핑)
# ============================================================

def get_fintel_data(ticker: str) -> dict:
    """Fintel에서 추가 데이터 시도"""
    url = f"https://fintel.io/ss/us/{ticker.lower()}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        text = resp.text

        # Short Squeeze Score 찾기
        score_match = re.search(r'short\s*squeeze\s*score[:\s]*(\d+\.?\d*)', text.lower())
        squeeze_score = float(score_match.group(1)) if score_match else None

        return {
            "fintel_squeeze_score": squeeze_score,
            "source": "fintel.io"
        }
    except:
        return {"fintel_squeeze_score": None, "source": None}


# ============================================================
# 3.5 SEC EDGAR 희석/빚/covenant 정보
# ============================================================

def get_sec_info(ticker: str) -> dict:
    """SEC EDGAR Full-Text Search로 워런트/희석/빚/covenant 정보 수집"""

    sec_info = {
        "warrant_mentions": 0,
        "dilution_mentions": 0,
        "covenant_mentions": 0,
        "debt_mentions": 0,
        "lockup_mentions": 0,
        "offering_mentions": 0,  # S-3, 424B 등
        "positive_news": 0,
        "negative_news": 0,
        # 해석
        "has_warrant_risk": False,
        "has_debt_covenant": False,
        "dilution_risk": False,
        "has_lockup": False,
        "has_offering_risk": False,
        "has_positive_news": False,
        "has_negative_news": False,
    }

    headers = {"User-Agent": "DailyStockStory/1.0 (contact@example.com)"}

    try:
        # 키워드 검색 (2024년 이후)
        keywords = [
            ("warrant", "warrant_mentions"),
            ("dilution", "dilution_mentions"),
            ("covenant", "covenant_mentions"),
            ("debt", "debt_mentions"),
            ("lock-up OR lockup", "lockup_mentions"),
            ("S-3 OR 424B", "offering_mentions"),
        ]

        for keyword, field in keywords:
            search_url = f'https://efts.sec.gov/LATEST/search-index?q="{keyword}" AND "{ticker}"&dateRange=custom&startdt=2024-01-01'
            try:
                resp = requests.get(search_url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    count = data.get("hits", {}).get("total", {}).get("value", 0)
                    sec_info[field] = count
            except:
                pass

        # 호재 키워드 (2025년)
        positive_keywords = ["deal", "partnership", "contract", "agreement", "FDA approval"]
        for pk in positive_keywords:
            search_url = f'https://efts.sec.gov/LATEST/search-index?q="{pk}" AND "{ticker}"&dateRange=custom&startdt=2025-01-01'
            try:
                resp = requests.get(search_url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    count = resp.json().get("hits", {}).get("total", {}).get("value", 0)
                    sec_info["positive_news"] += count
            except:
                pass

        # 악재 키워드 (2025년)
        negative_keywords = ["lawsuit", "bankruptcy", "default", "fraud", "investigation", "delisting"]
        for nk in negative_keywords:
            search_url = f'https://efts.sec.gov/LATEST/search-index?q="{nk}" AND "{ticker}"&dateRange=custom&startdt=2025-01-01'
            try:
                resp = requests.get(search_url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    count = resp.json().get("hits", {}).get("total", {}).get("value", 0)
                    sec_info["negative_news"] += count
            except:
                pass

        # 해석 (임계값)
        sec_info["has_warrant_risk"] = sec_info["warrant_mentions"] > 10
        sec_info["has_debt_covenant"] = sec_info["covenant_mentions"] > 3
        sec_info["dilution_risk"] = sec_info["dilution_mentions"] > 5
        sec_info["has_lockup"] = sec_info["lockup_mentions"] > 2
        sec_info["has_offering_risk"] = sec_info["offering_mentions"] > 3
        sec_info["has_positive_news"] = sec_info["positive_news"] > 50
        sec_info["has_negative_news"] = sec_info["negative_news"] > 20

    except Exception as e:
        print(f"    ⚠️ SEC 검색 오류: {e}")

    return sec_info


# ============================================================
# 3.6 FTD (Failure to Deliver) 데이터 - SEC
# ============================================================

def get_ftd_data(ticker: str) -> dict:
    """SEC에서 FTD 데이터 수집 (최근 2개월)"""
    ftd_info = {
        "total_ftd": 0,
        "recent_ftd": [],
        "avg_ftd": 0,
        "max_ftd": 0,
        "ftd_trend": "unknown",  # increasing, decreasing, stable
        "has_significant_ftd": False,
    }

    try:
        # SEC FTD 파일 (최근 2개월)
        from datetime import datetime
        now = datetime.now()

        # SEC FTD는 2주 delay로 발표됨
        # 최근 파일 2개 시도
        months_to_check = []
        for i in range(3):
            check_date = now - timedelta(days=30 * i)
            months_to_check.append(check_date.strftime("%Y%m"))

        all_ftd = []

        for month in months_to_check[:2]:
            # 첫번째 반 (1-15일)
            url1 = f"https://www.sec.gov/files/data/fails-deliver-data/cnsfails{month}a.zip"
            # 두번째 반 (16-말일)
            url2 = f"https://www.sec.gov/files/data/fails-deliver-data/cnsfails{month}b.zip"

            for url in [url1, url2]:
                try:
                    import io
                    import zipfile

                    resp = requests.get(url, headers={"User-Agent": "DailyStockStory/1.0"}, timeout=15)
                    if resp.status_code == 200:
                        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                            for filename in z.namelist():
                                with z.open(filename) as f:
                                    content = f.read().decode('utf-8', errors='ignore')
                                    for line in content.split('\n'):
                                        if ticker.upper() in line.upper():
                                            parts = line.split('|')
                                            if len(parts) >= 5:
                                                try:
                                                    date = parts[0]
                                                    qty = int(parts[3]) if parts[3].isdigit() else 0
                                                    if qty > 0:
                                                        all_ftd.append({
                                                            "date": date,
                                                            "quantity": qty
                                                        })
                                                except:
                                                    pass
                except:
                    pass

        if all_ftd:
            # 정렬 (최신순)
            all_ftd.sort(key=lambda x: x['date'], reverse=True)
            ftd_info["recent_ftd"] = all_ftd[:10]
            ftd_info["total_ftd"] = sum(f['quantity'] for f in all_ftd)
            ftd_info["avg_ftd"] = ftd_info["total_ftd"] // len(all_ftd) if all_ftd else 0
            ftd_info["max_ftd"] = max(f['quantity'] for f in all_ftd)

            # 트렌드 분석
            if len(all_ftd) >= 4:
                recent_avg = sum(f['quantity'] for f in all_ftd[:2]) / 2
                older_avg = sum(f['quantity'] for f in all_ftd[2:4]) / 2
                if recent_avg > older_avg * 1.5:
                    ftd_info["ftd_trend"] = "increasing 📈"
                elif recent_avg < older_avg * 0.5:
                    ftd_info["ftd_trend"] = "decreasing 📉"
                else:
                    ftd_info["ftd_trend"] = "stable"

            # 유의미한 FTD인지 (10만주 이상)
            ftd_info["has_significant_ftd"] = ftd_info["max_ftd"] > 100000

    except Exception as e:
        print(f"    ⚠️ FTD 수집 오류: {e}")

    return ftd_info


# ============================================================
# 3.7 옵션 체인 분석
# ============================================================

def get_options_data(stock) -> dict:
    """옵션 체인 분석 (감마 스퀴즈 가능성)"""
    options_info = {
        "has_options": False,
        "nearest_expiry": None,
        "total_call_oi": 0,
        "total_put_oi": 0,
        "put_call_ratio": 0,
        "max_pain": 0,
        "gamma_exposure": [],
        "itm_calls": 0,  # In-the-money 콜
        "strikes_analysis": [],
    }

    try:
        # 옵션 만기일 확인
        expirations = stock.options
        if not expirations:
            return options_info

        options_info["has_options"] = True
        options_info["nearest_expiry"] = expirations[0]

        # 현재가
        current_price = stock.info.get('regularMarketPrice', 0) or stock.info.get('currentPrice', 0)

        # 가장 가까운 만기 옵션 분석
        opt = stock.option_chain(expirations[0])
        calls = opt.calls
        puts = opt.puts

        if not calls.empty:
            options_info["total_call_oi"] = int(calls['openInterest'].sum())
            # ITM 콜 (행사가 < 현재가)
            itm_calls = calls[calls['strike'] < current_price]
            options_info["itm_calls"] = int(itm_calls['openInterest'].sum()) if not itm_calls.empty else 0

            # 감마 집중 구간 (OI 많은 행사가)
            top_strikes = calls.nlargest(5, 'openInterest')[['strike', 'openInterest']]
            options_info["gamma_exposure"] = [
                {"strike": row['strike'], "oi": int(row['openInterest'])}
                for _, row in top_strikes.iterrows()
            ]

        if not puts.empty:
            options_info["total_put_oi"] = int(puts['openInterest'].sum())

        # Put/Call 비율
        if options_info["total_call_oi"] > 0:
            options_info["put_call_ratio"] = round(
                options_info["total_put_oi"] / options_info["total_call_oi"], 2
            )

        # Max Pain 계산 (간단 버전)
        if not calls.empty and not puts.empty:
            all_strikes = sorted(set(calls['strike'].tolist() + puts['strike'].tolist()))
            min_pain = float('inf')
            max_pain_strike = 0

            for strike in all_strikes:
                # 이 행사가에서의 총 손실
                call_pain = calls[calls['strike'] < strike]['openInterest'].sum() * (strike - calls[calls['strike'] < strike]['strike']).sum() if not calls[calls['strike'] < strike].empty else 0
                put_pain = puts[puts['strike'] > strike]['openInterest'].sum() * (puts[puts['strike'] > strike]['strike'] - strike).sum() if not puts[puts['strike'] > strike].empty else 0
                total_pain = call_pain + put_pain

                if total_pain < min_pain:
                    min_pain = total_pain
                    max_pain_strike = strike

            options_info["max_pain"] = max_pain_strike

    except Exception as e:
        print(f"    ⚠️ 옵션 분석 오류: {e}")

    return options_info


# ============================================================
# 3.8 소셜 센티먼트 (다중 소스)
# ============================================================

def get_social_sentiment(ticker: str) -> dict:
    """Stocktwits + Reddit + 웹 스크래핑으로 센티먼트 수집"""
    sentiment_info = {
        "stocktwits_sentiment": None,
        "stocktwits_messages": 0,
        "trending": False,
        "watchlist_count": 0,
        "recent_posts": [],
        "reddit_mentions": 0,
        "twitter_sentiment": None,
        "overall_sentiment": None,
    }

    bullish_total = 0
    bearish_total = 0

    # 1. Stocktwits
    try:
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
        resp = requests.get(url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            data = resp.json()

            symbol_data = data.get('symbol', {})
            sentiment_info["watchlist_count"] = symbol_data.get('watchlist_count', 0)
            sentiment_info["trending"] = symbol_data.get('is_following', False)

            messages = data.get('messages', [])
            sentiment_info["stocktwits_messages"] = len(messages)

            bullish = 0
            bearish = 0

            for msg in messages[:20]:
                entities = msg.get('entities', {})
                sent = entities.get('sentiment', {})
                if sent:
                    if sent.get('basic') == 'Bullish':
                        bullish += 1
                    elif sent.get('basic') == 'Bearish':
                        bearish += 1

                if len(sentiment_info["recent_posts"]) < 3:
                    sentiment_info["recent_posts"].append({
                        "body": msg.get('body', '')[:100],
                        "sentiment": sent.get('basic', 'Neutral') if sent else 'Neutral',
                        "source": "Stocktwits"
                    })

            bullish_total += bullish
            bearish_total += bearish

            if bullish > bearish * 1.5:
                sentiment_info["stocktwits_sentiment"] = "Bullish 🟢"
            elif bearish > bullish * 1.5:
                sentiment_info["stocktwits_sentiment"] = "Bearish 🔴"
            else:
                sentiment_info["stocktwits_sentiment"] = "Neutral ⚪"

    except:
        pass

    # 2. Reddit (wallstreetbets, stocks 등) - 웹 스크래핑
    try:
        reddit_url = f"https://www.reddit.com/search.json?q={ticker}&sort=new&limit=10"
        resp = requests.get(reddit_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
        }, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            posts = data.get('data', {}).get('children', [])
            sentiment_info["reddit_mentions"] = len(posts)

            # 제목에서 센티먼트 추정
            for post in posts[:5]:
                title = post.get('data', {}).get('title', '').lower()
                subreddit = post.get('data', {}).get('subreddit', '')

                # 간단한 키워드 기반 센티먼트
                bull_words = ['moon', 'rocket', 'buy', 'calls', 'squeeze', 'bullish', 'long', '🚀', '💎']
                bear_words = ['sell', 'puts', 'short', 'bearish', 'crash', 'dump', 'avoid']

                if any(w in title for w in bull_words):
                    bullish_total += 1
                elif any(w in title for w in bear_words):
                    bearish_total += 1

                if len(sentiment_info["recent_posts"]) < 5:
                    sentiment_info["recent_posts"].append({
                        "body": post.get('data', {}).get('title', '')[:100],
                        "sentiment": "Reddit",
                        "source": f"r/{subreddit}"
                    })

    except:
        pass

    # 3. Finviz 뉴스 센티먼트
    try:
        finviz_url = f"https://finviz.com/quote.ashx?t={ticker}"
        resp = requests.get(finviz_url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            # Analyst Rating 추출
            rating_match = re.search(r'Recom.*?(\d+\.?\d*)', resp.text)
            if rating_match:
                rating = float(rating_match.group(1))
                # 1=Strong Buy, 5=Sell
                if rating <= 2:
                    bullish_total += 2
                elif rating >= 4:
                    bearish_total += 2

    except:
        pass

    # 4. 종합 센티먼트 결정
    if bullish_total > bearish_total * 1.5:
        sentiment_info["overall_sentiment"] = "🟢 강세 (Bullish) - 매수 분위기"
    elif bearish_total > bullish_total * 1.5:
        sentiment_info["overall_sentiment"] = "🔴 약세 (Bearish) - 매도 분위기"
    elif bullish_total > 0 or bearish_total > 0:
        sentiment_info["overall_sentiment"] = "⚪ 혼조 (Mixed) - 의견 갈림"
    else:
        sentiment_info["overall_sentiment"] = "❓ 데이터 부족"

    return sentiment_info


# ============================================================
# 3.9 촉매(Catalyst) 일정
# ============================================================

def get_catalyst_calendar(stock) -> dict:
    """어닝, FDA, 컨퍼런스 등 촉매 일정"""
    catalyst_info = {
        "next_earnings": None,
        "earnings_estimate": None,
        "recent_earnings_surprise": None,
        "ex_dividend_date": None,
        "upcoming_events": [],
    }

    try:
        info = stock.info

        # 어닝 일정
        earnings_date = info.get('earningsDate')
        if earnings_date:
            if isinstance(earnings_date, list) and earnings_date:
                catalyst_info["next_earnings"] = datetime.fromtimestamp(earnings_date[0]).strftime('%Y-%m-%d')
            elif isinstance(earnings_date, (int, float)):
                catalyst_info["next_earnings"] = datetime.fromtimestamp(earnings_date).strftime('%Y-%m-%d')

        # 어닝 서프라이즈
        earnings_hist = stock.earnings_history if hasattr(stock, 'earnings_history') else None
        if earnings_hist is not None and not earnings_hist.empty:
            latest = earnings_hist.iloc[-1] if len(earnings_hist) > 0 else None
            if latest is not None:
                surprise = latest.get('surprisePercent')
                if surprise:
                    catalyst_info["recent_earnings_surprise"] = f"{surprise:.1f}%"

        # 배당일
        ex_div = info.get('exDividendDate')
        if ex_div:
            catalyst_info["ex_dividend_date"] = datetime.fromtimestamp(ex_div).strftime('%Y-%m-%d')

        # EPS 추정치
        catalyst_info["earnings_estimate"] = info.get('targetMeanPrice')

    except Exception as e:
        print(f"    ⚠️ Catalyst 오류: {e}")

    return catalyst_info


# ============================================================
# 3.10 피보나치 & 지지/저항 분석
# ============================================================

def get_fibonacci_levels(stock) -> dict:
    """피보나치 되돌림 레벨 계산"""
    fib_info = {
        "levels": {},
        "current_zone": None,
        "support_levels": [],
        "resistance_levels": [],
        "gaps": [],
    }

    try:
        # 최근 6개월 데이터
        hist = stock.history(period="6mo")
        if hist.empty:
            return fib_info

        high = hist['High'].max()
        low = hist['Low'].min()
        current = hist['Close'].iloc[-1]
        diff = high - low

        # 피보나치 레벨
        fib_levels = {
            "0%": high,
            "23.6%": high - diff * 0.236,
            "38.2%": high - diff * 0.382,
            "50%": high - diff * 0.5,
            "61.8%": high - diff * 0.618,
            "78.6%": high - diff * 0.786,
            "100%": low,
        }
        fib_info["levels"] = {k: round(v, 2) for k, v in fib_levels.items()}

        # 현재 위치 분석
        for level_name, level_price in fib_levels.items():
            if current >= level_price:
                fib_info["current_zone"] = f"{level_name} 위"
                break

        # 지지선/저항선 (현재가 기준)
        for level_name, level_price in fib_levels.items():
            if level_price < current:
                fib_info["support_levels"].append({
                    "level": level_name,
                    "price": round(level_price, 2),
                    "distance": f"{((current - level_price) / current * 100):.1f}%"
                })
            elif level_price > current:
                fib_info["resistance_levels"].append({
                    "level": level_name,
                    "price": round(level_price, 2),
                    "distance": f"{((level_price - current) / current * 100):.1f}%"
                })

        # 갭 분석 (최근 20일)
        recent = hist.tail(20)
        for i in range(1, len(recent)):
            prev_close = recent['Close'].iloc[i-1]
            curr_open = recent['Open'].iloc[i]
            curr_high = recent['High'].iloc[i]
            curr_low = recent['Low'].iloc[i]

            # 갭업
            if curr_open > prev_close * 1.02:
                gap_filled = curr_low <= prev_close
                fib_info["gaps"].append({
                    "type": "갭업",
                    "date": str(recent.index[i].date()),
                    "gap_start": round(prev_close, 2),
                    "gap_end": round(curr_open, 2),
                    "filled": "충전됨" if gap_filled else "미충전"
                })
            # 갭다운
            elif curr_open < prev_close * 0.98:
                gap_filled = curr_high >= prev_close
                fib_info["gaps"].append({
                    "type": "갭다운",
                    "date": str(recent.index[i].date()),
                    "gap_start": round(curr_open, 2),
                    "gap_end": round(prev_close, 2),
                    "filled": "충전됨" if gap_filled else "미충전"
                })

    except Exception as e:
        print(f"    ⚠️ 피보나치 오류: {e}")

    return fib_info


# ============================================================
# 3.11 볼륨 프로파일
# ============================================================

def get_volume_profile(stock) -> dict:
    """가격대별 거래량 분석"""
    vp_info = {
        "high_volume_zones": [],
        "poc": None,  # Point of Control (가장 거래량 많은 가격대)
        "value_area_high": None,
        "value_area_low": None,
    }

    try:
        hist = stock.history(period="3mo")
        if hist.empty or len(hist) < 20:
            return vp_info

        # 가격 구간 생성 (20개 구간)
        price_min = hist['Low'].min()
        price_max = hist['High'].max()
        num_bins = 20
        bin_size = (price_max - price_min) / num_bins

        volume_by_price = {}

        for i in range(len(hist)):
            avg_price = (hist['High'].iloc[i] + hist['Low'].iloc[i]) / 2
            volume = hist['Volume'].iloc[i]

            bin_idx = int((avg_price - price_min) / bin_size)
            bin_idx = min(bin_idx, num_bins - 1)
            bin_price = price_min + bin_idx * bin_size + bin_size / 2

            if bin_price not in volume_by_price:
                volume_by_price[bin_price] = 0
            volume_by_price[bin_price] += volume

        if volume_by_price:
            # POC (Point of Control)
            poc_price = max(volume_by_price, key=volume_by_price.get)
            vp_info["poc"] = round(poc_price, 2)

            # 상위 거래량 구간
            sorted_zones = sorted(volume_by_price.items(), key=lambda x: x[1], reverse=True)
            vp_info["high_volume_zones"] = [
                {"price": round(price, 2), "volume": int(vol)}
                for price, vol in sorted_zones[:5]
            ]

            # Value Area (거래량 70% 구간)
            total_vol = sum(volume_by_price.values())
            target_vol = total_vol * 0.7
            cumulative = 0

            # POC에서 시작해서 확장
            va_prices = [poc_price]
            remaining = {k: v for k, v in volume_by_price.items() if k != poc_price}
            cumulative = volume_by_price[poc_price]

            while cumulative < target_vol and remaining:
                next_price = max(remaining, key=remaining.get)
                va_prices.append(next_price)
                cumulative += remaining[next_price]
                del remaining[next_price]

            vp_info["value_area_high"] = round(max(va_prices), 2)
            vp_info["value_area_low"] = round(min(va_prices), 2)

    except Exception as e:
        print(f"    ⚠️ 볼륨 프로파일 오류: {e}")

    return vp_info


# ============================================================
# 3.12 다크풀 & 장외거래 (다중 소스)
# ============================================================

def get_darkpool_data(ticker: str) -> dict:
    """다크풀/숏볼륨 데이터 (여러 소스)"""
    dp_info = {
        "darkpool_volume": 0,
        "darkpool_trades": 0,
        "dp_percent": 0,
        "short_volume_percent": 0,
        "off_exchange_percent": 0,
        "recent_dp_data": [],
        "source": None,
    }

    # 1. Chartexchange 시도
    try:
        ce_url = f"https://chartexchange.com/symbol/nasdaq-{ticker.lower()}/"
        resp = requests.get(ce_url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            text = resp.text.lower()

            # Short Volume 비율
            sv_match = re.search(r'short\s*(?:volume|vol)[:\s]*(\d+\.?\d*)%', text)
            if sv_match:
                dp_info["short_volume_percent"] = float(sv_match.group(1))
                dp_info["source"] = "Chartexchange"

            # Off-exchange (다크풀) 비율
            oe_match = re.search(r'off[- ]?exchange[:\s]*(\d+\.?\d*)%', text)
            if oe_match:
                dp_info["off_exchange_percent"] = float(oe_match.group(1))

            # Dark Pool Volume
            dp_vol_match = re.search(r'dark\s*pool\s*(?:volume)?[:\s]*([\d,]+)', text)
            if dp_vol_match:
                dp_info["darkpool_volume"] = int(dp_vol_match.group(1).replace(',', ''))

    except:
        pass

    # 2. Fintel 백업 시도
    if not dp_info["short_volume_percent"]:
        try:
            fintel_url = f"https://fintel.io/ss/us/{ticker.lower()}"
            resp = requests.get(fintel_url, headers=HEADERS, timeout=10)

            if resp.status_code == 200:
                text = resp.text.lower()

                # Short Volume Ratio
                sv_match = re.search(r'short\s*volume\s*ratio[:\s]*(\d+\.?\d*)%', text)
                if sv_match:
                    dp_info["short_volume_percent"] = float(sv_match.group(1))
                    dp_info["source"] = "Fintel"

        except:
            pass

    # 3. Stocksera 백업 (무료 API)
    if not dp_info["short_volume_percent"]:
        try:
            stocksera_url = f"https://stocksera.pythonanywhere.com/api/short_volume/{ticker}"
            resp = requests.get(stocksera_url, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    latest = data[0]
                    total = latest.get('total_volume', 0)
                    short = latest.get('short_volume', 0)
                    if total > 0:
                        dp_info["short_volume_percent"] = round((short / total) * 100, 1)
                        dp_info["source"] = "Stocksera"

        except:
            pass

    # 4. 경고 수준 판단
    if dp_info["short_volume_percent"] > 50:
        dp_info["warning"] = "⚠️ 숏 볼륨 50% 초과 - 숏 압력 높음"
    elif dp_info["short_volume_percent"] > 30:
        dp_info["warning"] = "🟡 숏 볼륨 30%+ - 주의"

    if dp_info["off_exchange_percent"] > 50:
        dp_info["dp_warning"] = "⚠️ 장외거래 50% 초과 - 다크풀 활발"

    return dp_info


# ============================================================
# 3.13 SEC Filing 파싱 (S-1, 10-K 등) - 개선판
# ============================================================

def get_sec_filings(ticker: str) -> dict:
    """SEC EDGAR에서 최근 filing 목록 및 주요 내용 (개선판)"""
    filings_info = {
        "recent_filings": [],
        "lockup_info": None,
        "warrant_details": [],
        "debt_details": [],
        "insider_lockup_price": None,
        "offering_info": [],
        "company_name": None,
        "cik": None,
        # SPAC 관련
        "is_spac": False,
        "spac_merger_date": None,
        "earnout_conditions": [],
        "earnout_prices": [],
        "earnout_shares": None,
    }

    headers = {"User-Agent": "DailyStockStory/1.0 (sean@example.com)"}

    try:
        cik = None

        # 1. SEC 공식 티커-CIK 매핑 JSON 사용 (가장 정확!)
        try:
            tickers_url = "https://www.sec.gov/files/company_tickers.json"
            resp = requests.get(tickers_url, headers=headers, timeout=15)
            if resp.status_code == 200:
                tickers_data = resp.json()
                for key, company in tickers_data.items():
                    if company.get('ticker', '').upper() == ticker.upper():
                        cik = str(company.get('cik_str', '')).zfill(10)
                        filings_info["company_name"] = company.get('title')
                        break
        except:
            pass

        # 2. 백업: EDGAR 검색
        if not cik:
            try:
                ticker_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type=&dateb=&owner=include&count=10&output=atom"
                resp = requests.get(ticker_url, headers=headers, timeout=15)
                cik_match = re.search(r'CIK=(\d+)', resp.text)
                if cik_match:
                    cik = cik_match.group(1).zfill(10)
            except:
                pass

        if not cik:
            return filings_info
        filings_info["cik"] = cik

        # 2. 최근 filings 가져오기 (JSON API)
        filings_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        resp = requests.get(filings_url, headers=headers, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            filings_info["company_name"] = data.get('name')

            recent = data.get('filings', {}).get('recent', {})

            forms = recent.get('form', [])
            dates = recent.get('filingDate', [])
            accessions = recent.get('accessionNumber', [])
            descriptions = recent.get('primaryDocument', [])

            # 관심 있는 form 타입 (SPAC 관련 S-4, DEFM14A 추가)
            important_forms = ["S-1", "S-1/A", "S-3", "S-4", "S-4/A", "424B4", "424B5", "10-K", "10-Q", "8-K", "DEF 14A", "DEFM14A"]

            for i in range(min(30, len(forms))):
                form_type = forms[i]
                if form_type in important_forms or len(filings_info["recent_filings"]) < 10:
                    filings_info["recent_filings"].append({
                        "form": form_type,
                        "date": dates[i],
                        "accession": accessions[i].replace('-', ''),
                        "document": descriptions[i] if i < len(descriptions) else ""
                    })

            # 3. 주요 문서에서 정보 추출
            for filing in filings_info["recent_filings"][:5]:
                form_type = filing["form"]

                # S-1, S-4, 424B, DEF 14A, DEFM14A에서 락업/워런트/빚/earnout 정보 찾기
                if form_type in ["S-1", "S-1/A", "S-4", "S-4/A", "424B4", "424B5", "DEF 14A", "DEFM14A", "10-K"]:
                    try:
                        # 문서 URL 생성
                        acc_formatted = filing['accession']
                        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc_formatted}/{filing['document']}"

                        doc_resp = requests.get(doc_url, headers=headers, timeout=20)

                        if doc_resp.status_code == 200:
                            doc_text = doc_resp.text.lower()

                            # Lock-up 가격/기간 찾기 (더 많은 패턴)
                            if not filings_info["insider_lockup_price"]:
                                lockup_patterns = [
                                    # 가격 기반 락업 (SPAC 스타일)
                                    r'lock-?up.*?(?:release[sd]?|terminate[sd]?).*?(?:stock\s*)?price.*?(?:equals?\s*or\s*)?exceeds?\s*\$?([\d,]+\.?\d*)',
                                    r'(?:lock-?up|restriction).*?(?:expire[sd]?|release[sd]?).*?(?:when|if).*?\$([\d,]+\.?\d*)',
                                    # 전통적 락업
                                    r'lock-?up.*?(?:price|until).*?(\$[\d,]+\.?\d*)',
                                    r'may not (?:sell|transfer).*?until.*?(?:closing price|stock price).*?(\$[\d,]+\.?\d*)',
                                    r'(?:180|90|365)\s*days?\s*(?:after|following).*?ipo',
                                    r'insider.*?lock.*?(\$[\d,]+\.?\d*)',
                                    r'(?:founder|insider|officer|sponsor).*?(?:may not sell|restricted|cannot transfer).*?(\$[\d,]+)',
                                    # 주가 조건부 락업
                                    r'(?:shares?|stock).*?(?:released?|unlocked?).*?(?:if|when).*?price.*?(?:reaches?|exceeds?|equals?)\s*\$?([\d,]+\.?\d*)',
                                    r'(?:restriction|lock-?up).*?(?:waived?|removed?).*?(?:stock\s*)?price.*?\$?([\d,]+\.?\d*)',
                                ]

                                for pattern in lockup_patterns:
                                    match = re.search(pattern, doc_text)
                                    if match:
                                        if match.groups() and match.group(1):
                                            price_str = match.group(1).replace(',', '')
                                            try:
                                                price_val = float(price_str)
                                                if 10 <= price_val <= 500:  # 합리적인 가격 범위
                                                    filings_info["insider_lockup_price"] = f"${price_val}"
                                                    break
                                            except:
                                                pass
                                        else:
                                            filings_info["lockup_info"] = "180일 락업 존재"
                                            break

                            # 워런트 정보 (더 많은 패턴)
                            if not filings_info["warrant_details"]:
                                warrant_patterns = [
                                    r'warrant.*?exercise\s*price.*?(\$[\d,]+\.?\d*)',
                                    r'warrants?\s*(?:to purchase|exercisable).*?(\$[\d,]+\.?\d*)',
                                    r'exercise\s*price\s*(?:of|is)\s*(\$[\d,]+\.?\d*)\s*per\s*share',
                                ]

                                for pattern in warrant_patterns:
                                    matches = re.findall(pattern, doc_text)
                                    if matches:
                                        filings_info["warrant_details"] = list(set(matches))[:5]
                                        break

                            # 빚/Debt 정보
                            if not filings_info["debt_details"]:
                                debt_patterns = [
                                    r'(credit facility|term loan|senior note|convertible note).*?(\$[\d,]+\.?\d*\s*(?:million|billion)?)',
                                    r'(indebtedness|borrowing).*?(\$[\d,]+\.?\d*\s*(?:million|billion)?)',
                                    r'outstanding\s*(debt|loan).*?(\$[\d,]+\.?\d*\s*(?:million|billion)?)',
                                ]

                                for pattern in debt_patterns:
                                    matches = re.findall(pattern, doc_text)
                                    if matches:
                                        filings_info["debt_details"] = [
                                            f"{m[0].title()}: {m[1]}" for m in matches[:5]
                                        ]
                                        break

                            # Offering 정보 (S-3, 424B)
                            if form_type in ["S-3", "424B4", "424B5"]:
                                offering_match = re.search(r'(?:offering|issuance).*?(\d[\d,]*)\s*shares.*?(\$[\d,]+\.?\d*)', doc_text)
                                if offering_match:
                                    filings_info["offering_info"].append({
                                        "shares": offering_match.group(1),
                                        "price": offering_match.group(2),
                                        "date": filing["date"],
                                        "form": form_type
                                    })

                            # SPAC / Earnout 정보 (S-4, DEFM14A, 8-K)
                            if form_type in ["S-4", "S-4/A", "DEFM14A", "8-K"]:
                                # SPAC 여부 감지
                                spac_keywords = ['business combination', 'spac', 'blank check', 'de-spac', 'merger agreement']
                                if any(kw in doc_text for kw in spac_keywords):
                                    filings_info["is_spac"] = True

                                # Earnout 조건 찾기
                                earnout_patterns = [
                                    # "closing price equals or exceeds $X for Y trading days"
                                    r'(?:closing|stock)\s*price\s*(?:equals?\s*or\s*)?exceeds?\s*\$?([\d,]+\.?\d*)\s*(?:per\s*share\s*)?(?:for|during)\s*(\d+)\s*(?:trading\s*)?days?',
                                    # "VWAP exceeds $X"
                                    r'vwap\s*(?:equals?\s*or\s*)?exceeds?\s*\$?([\d,]+\.?\d*)',
                                    # "stock price reaches $X"
                                    r'stock\s*price\s*(?:of\s*the\s*company\s*)?reaches?\s*\$?([\d,]+\.?\d*)',
                                    # "earnout shares... $X"
                                    r'earnout\s*shares?.*?\$?([\d,]+\.?\d*)\s*(?:per\s*share)?',
                                    # "if the price... exceeds $X"
                                    r'if\s*(?:the\s*)?(?:closing\s*)?price.*?exceeds?\s*\$?([\d,]+\.?\d*)',
                                ]

                                for pattern in earnout_patterns:
                                    matches = re.findall(pattern, doc_text)
                                    for match in matches:
                                        if isinstance(match, tuple):
                                            price = match[0]
                                        else:
                                            price = match
                                        try:
                                            price_val = float(price.replace(',', ''))
                                            if 10 <= price_val <= 500:  # 합리적인 가격 범위
                                                if f"${price_val}" not in filings_info["earnout_prices"]:
                                                    filings_info["earnout_prices"].append(f"${price_val}")
                                        except:
                                            pass

                                # Earnout 주식 수 찾기
                                earnout_shares_patterns = [
                                    r'(\d[\d,]*)\s*(?:earnout|contingent)\s*shares?',
                                    r'(?:earnout|contingent)\s*shares?\s*(?:of\s*)?(\d[\d,]*)',
                                    r'up\s*to\s*(\d[\d,]*)\s*additional\s*shares?',
                                ]
                                for pattern in earnout_shares_patterns:
                                    match = re.search(pattern, doc_text)
                                    if match:
                                        filings_info["earnout_shares"] = match.group(1)
                                        break

                                # 락업 조건 (SPAC 특화)
                                spac_lockup_patterns = [
                                    r'(?:founder|sponsor|insider)\s*shares?.*?(?:lock-?up|may\s*not\s*(?:sell|transfer)).*?(?:until|unless).*?(?:stock\s*)?price.*?\$?([\d,]+\.?\d*)',
                                    r'(?:lock-?up|restriction).*?(?:released?|terminate[sd]?).*?(?:stock\s*)?price.*?(?:equals?\s*or\s*)?exceeds?\s*\$?([\d,]+\.?\d*)',
                                    r'shares?\s*(?:may\s*)?(?:not\s*)?(?:be\s*)?(?:sold|transferred).*?until.*?(?:\$|price\s*of\s*)([\d,]+\.?\d*)',
                                ]
                                for pattern in spac_lockup_patterns:
                                    match = re.search(pattern, doc_text)
                                    if match and not filings_info["insider_lockup_price"]:
                                        try:
                                            price_val = float(match.group(1).replace(',', ''))
                                            if 10 <= price_val <= 500:
                                                filings_info["insider_lockup_price"] = f"${price_val}"
                                        except:
                                            pass

                    except Exception as e:
                        pass  # 개별 문서 파싱 실패는 무시

    except Exception as e:
        print(f"    ⚠️ SEC Filing 파싱 오류: {e}")

    return filings_info


# ============================================================
# 3.14 기관 보유 변화 (13F)
# ============================================================

def get_institutional_changes(stock) -> dict:
    """기관 보유 변화 분석"""
    inst_info = {
        "total_institutional": 0,
        "top_holders": [],
        "recent_changes": [],
        "net_institutional_change": "unknown",
    }

    try:
        # yfinance 기관 보유
        holders = stock.institutional_holders
        if holders is not None and not holders.empty:
            inst_info["total_institutional"] = len(holders)

            for _, row in holders.head(5).iterrows():
                inst_info["top_holders"].append({
                    "holder": row.get('Holder', 'N/A'),
                    "shares": int(row.get('Shares', 0)),
                    "value": int(row.get('Value', 0)),
                    "pct_out": f"{row.get('pctHeld', 0) * 100:.2f}%" if row.get('pctHeld') else 'N/A'
                })

        # 기관 보유 비율
        info = stock.info
        inst_pct = info.get('heldPercentInstitutions')
        if inst_pct:
            inst_info["institutional_percent"] = f"{inst_pct * 100:.1f}%"

    except Exception as e:
        print(f"    ⚠️ 기관 보유 분석 오류: {e}")

    return inst_info


# ============================================================
# 3.15 동종업체 비교
# ============================================================

def get_peer_comparison(stock, ticker: str) -> dict:
    """동종업체 비교 분석"""
    peer_info = {
        "sector": None,
        "industry": None,
        "peers": [],
        "sector_avg_pe": None,
        "relative_valuation": None,
    }

    try:
        info = stock.info
        peer_info["sector"] = info.get('sector')
        peer_info["industry"] = info.get('industry')

        my_pe = info.get('trailingPE')
        my_pb = info.get('priceToBook')
        my_ps = info.get('priceToSalesTrailing12Months')

        # 섹터 평균 (yfinance는 peers 제공 안함, 대신 sector 평균 추정)
        sector_pe_avg = {
            "Technology": 25,
            "Healthcare": 20,
            "Financial Services": 12,
            "Consumer Cyclical": 18,
            "Communication Services": 20,
            "Industrials": 16,
            "Energy": 10,
            "Basic Materials": 12,
            "Consumer Defensive": 22,
            "Real Estate": 35,
            "Utilities": 18,
        }

        sector = info.get('sector')
        if sector and sector in sector_pe_avg:
            peer_info["sector_avg_pe"] = sector_pe_avg[sector]

            if my_pe and my_pe > 0:
                ratio = my_pe / sector_pe_avg[sector]
                if ratio > 1.5:
                    peer_info["relative_valuation"] = "고평가 ⚠️"
                elif ratio < 0.7:
                    peer_info["relative_valuation"] = "저평가 💰"
                else:
                    peer_info["relative_valuation"] = "적정"
            else:
                peer_info["relative_valuation"] = "적자기업 (PE 없음)"

    except Exception as e:
        print(f"    ⚠️ 동종업체 비교 오류: {e}")

    return peer_info


# ============================================================
# 3.16 Short Interest 히스토리
# ============================================================

def get_short_history(ticker: str) -> dict:
    """Short Interest 변화 추이 (여러 소스 시도)"""
    short_hist = {
        "history": [],
        "trend": "unknown",
        "change_30d": None,
        "current_si": None,
        "prior_si": None,
    }

    try:
        # 1. yfinance에서 기본 Short 데이터
        stock = yf.Ticker(ticker)
        info = stock.info

        current = info.get('sharesShort')
        prior = info.get('sharesShortPriorMonth')

        if current:
            short_hist["current_si"] = current
        if prior:
            short_hist["prior_si"] = prior

        # 변화율 계산
        if current and prior and prior > 0:
            change = ((current - prior) / prior) * 100
            short_hist["change_30d"] = f"{change:+.1f}%"

            if change > 50:
                short_hist["trend"] = "급증 📈🔥"
            elif change > 20:
                short_hist["trend"] = "급증 📈"
            elif change > 5:
                short_hist["trend"] = "증가 ↗️"
            elif change < -30:
                short_hist["trend"] = "급감 📉 (커버링?)"
            elif change < -10:
                short_hist["trend"] = "감소 ↘️"
            else:
                short_hist["trend"] = "안정"

            # 히스토리 추가
            short_hist["history"].append({
                "date": "현재",
                "short_interest": current,
            })
            short_hist["history"].append({
                "date": "전월",
                "short_interest": prior,
            })

        # 2. Finviz에서 추가 데이터 시도
        try:
            finviz_url = f"https://finviz.com/quote.ashx?t={ticker}"
            resp = requests.get(finviz_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }, timeout=10)

            if resp.status_code == 200:
                # Short Float % 추출
                match = re.search(r'Short Float.*?(\d+\.?\d*)%', resp.text)
                if match:
                    short_hist["short_float_pct"] = f"{match.group(1)}%"

                # Short Ratio 추출
                match2 = re.search(r'Short Ratio.*?(\d+\.?\d*)', resp.text)
                if match2:
                    short_hist["short_ratio"] = float(match2.group(1))

        except:
            pass

        # 3. Chartexchange 백업
        try:
            ce_url = f"https://chartexchange.com/symbol/nasdaq-{ticker.lower()}/"
            resp = requests.get(ce_url, headers=HEADERS, timeout=10)

            if resp.status_code == 200:
                # Short Volume 추출
                sv_match = re.search(r'short\s*volume[:\s]*(\d[\d,]*)', resp.text.lower())
                if sv_match:
                    short_hist["short_volume"] = sv_match.group(1).replace(',', '')

        except:
            pass

    except Exception as e:
        print(f"    ⚠️ Short History 오류: {e}")

    return short_hist


# ============================================================
# 4. RegSHO Threshold List
# ============================================================

def check_regsho(ticker: str) -> bool:
    """DB 또는 NASDAQ에서 RegSHO 확인"""
    # DB 체크
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 1 FROM regsho_list
                WHERE ticker = %s AND collected_at > NOW() - INTERVAL '7 days'
                LIMIT 1
            """, (ticker,))
            result = cur.fetchone()
            conn.close()
            if result:
                return True
    except:
        pass

    # NASDAQ 직접 체크
    try:
        url = "https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth.txt"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if ticker.upper() in resp.text.upper():
            return True
    except:
        pass

    return False


# ============================================================
# 5. 기술적 지표
# ============================================================

def get_technicals(stock) -> dict:
    """기술적 지표 계산"""
    try:
        hist = stock.history(period="3mo")

        if hist.empty:
            return {}

        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]
        volume = hist["Volume"]

        # RSI (14일)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - signal

        # 볼린저 밴드
        sma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        bb_upper = sma20 + (std20 * 2)
        bb_lower = sma20 - (std20 * 2)

        current = close.iloc[-1]
        bb_position = ((current - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1])) * 100 if bb_upper.iloc[-1] != bb_lower.iloc[-1] else 50

        # ATR
        tr = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()

        # 거래량 비율
        vol_ratio = volume.iloc[-1] / volume.rolling(window=20).mean().iloc[-1] if volume.rolling(window=20).mean().iloc[-1] > 0 else 1

        return {
            "rsi": rsi.iloc[-1],
            "macd": macd.iloc[-1],
            "macd_signal": signal.iloc[-1],
            "macd_hist": macd_hist.iloc[-1],
            "bb_upper": bb_upper.iloc[-1],
            "bb_middle": sma20.iloc[-1],
            "bb_lower": bb_lower.iloc[-1],
            "bb_position": bb_position,
            "atr": atr.iloc[-1],
            "atr_pct": (atr.iloc[-1] / current) * 100,
            "vol_ratio": vol_ratio,
            "sma_20": sma20.iloc[-1],
            "sma_50": close.rolling(window=50).mean().iloc[-1] if len(close) >= 50 else None,
            # 가격 변화
            "change_1d": ((close.iloc[-1] / close.iloc[-2]) - 1) * 100 if len(close) >= 2 else 0,
            "change_5d": ((close.iloc[-1] / close.iloc[-5]) - 1) * 100 if len(close) >= 5 else 0,
            "change_20d": ((close.iloc[-1] / close.iloc[-20]) - 1) * 100 if len(close) >= 20 else 0,
        }
    except Exception as e:
        print(f"  ⚠️ 기술적 분석 실패: {e}")
        return {}


# ============================================================
# 6. 경영진 & 내부자
# ============================================================

def get_officers(stock) -> list:
    """경영진 정보"""
    try:
        return stock.info.get("companyOfficers", [])
    except:
        return []


def get_insider_transactions(stock) -> list:
    """내부자 거래"""
    try:
        insider = stock.insider_transactions
        if insider is not None and not insider.empty:
            return insider.to_dict('records')
        return []
    except:
        return []


def get_institutional_holders(stock) -> list:
    """기관 보유"""
    try:
        holders = stock.institutional_holders
        if holders is not None and not holders.empty:
            return holders.to_dict('records')
        return []
    except:
        return []


# ============================================================
# 7. 뉴스 수집
# ============================================================

def get_news(stock) -> list:
    """yfinance 뉴스"""
    try:
        news = stock.news
        return news[:10] if news else []
    except:
        return []


def search_recent_news(ticker: str, days: int = 60) -> list:
    """구글 뉴스 검색 (최근 N일 필터)"""
    try:
        from datetime import datetime, timedelta
        cutoff_date = datetime.now() - timedelta(days=days)

        url = f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        news = []
        for item in soup.find_all("item")[:15]:
            title = item.find("title")
            link = item.find("link")
            pub_date = item.find("pubDate")

            if title:
                # 날짜 파싱 및 필터링
                date_str = pub_date.text if pub_date else ""
                try:
                    # "Wed, 22 Jan 2026 10:00:00 GMT" 형식
                    parsed_date = datetime.strptime(date_str[:16], "%a, %d %b %Y")
                    if parsed_date < cutoff_date:
                        continue  # 오래된 뉴스 스킵
                except:
                    pass

                news.append({
                    "title": title.text,
                    "link": link.text if link else "",
                    "date": date_str
                })
        return news[:10]
    except:
        return []


# ============================================================
# 섹터별 특화 뉴스 수집
# ============================================================

def get_sector_news(ticker: str, sector: str, industry: str) -> dict:
    """섹터별 특화 뉴스 수집 (최근 60일)"""
    sector_news = {
        "general_news": [],
        "sector_specific": [],
        "catalysts": [],
        "source": None,
    }

    sector_lower = (sector or "").lower()
    industry_lower = (industry or "").lower()

    # 1. 일반 구글 뉴스 (백업)
    sector_news["general_news"] = search_recent_news(ticker, days=60)

    # 2. 섹터별 특화 뉴스
    if "biotech" in industry_lower or "pharma" in industry_lower or "healthcare" in sector_lower:
        sector_news["sector_specific"] = get_biotech_news(ticker)
        sector_news["source"] = "🧬 Biotech"
    elif "software" in industry_lower or "semiconductor" in industry_lower or "technology" in sector_lower:
        sector_news["sector_specific"] = get_tech_news(ticker)
        sector_news["source"] = "🤖 Tech/AI"
    elif "energy" in sector_lower or "oil" in industry_lower or "gas" in industry_lower:
        sector_news["sector_specific"] = get_energy_news(ticker)
        sector_news["source"] = "⛽ Energy"
    elif "auto" in industry_lower or "vehicle" in industry_lower or "ev" in industry_lower:
        sector_news["sector_specific"] = get_automotive_news(ticker)
        sector_news["source"] = "🚗 Automotive"
    elif "real estate" in sector_lower or "reit" in industry_lower:
        # REIT 체크를 retail 앞에 (REIT - Retail 구분)
        sector_news["sector_specific"] = get_realestate_news(ticker)
        sector_news["source"] = "🏠 Real Estate"
    elif "retail" in industry_lower or "e-commerce" in industry_lower or "store" in industry_lower:
        sector_news["sector_specific"] = get_retail_news(ticker)
        sector_news["source"] = "🛒 Retail"
    elif "food" in industry_lower or "beverage" in industry_lower or "consumer" in sector_lower:
        sector_news["sector_specific"] = get_consumer_news(ticker)
        sector_news["source"] = "🍔 Consumer"
    elif "bank" in industry_lower or "financial" in sector_lower or "insurance" in industry_lower:
        sector_news["sector_specific"] = get_financial_news(ticker)
        sector_news["source"] = "🏦 Financial"
    elif "industrial" in sector_lower or "aerospace" in industry_lower or "defense" in industry_lower:
        sector_news["sector_specific"] = get_industrial_news(ticker)
        sector_news["source"] = "🏭 Industrial"
    else:
        # 기본: Finviz 뉴스
        sector_news["sector_specific"] = get_finviz_news(ticker)
        sector_news["source"] = "📰 General"

    return sector_news


def get_biotech_news(ticker: str) -> list:
    """바이오텍 전용 뉴스 (BioSpace, FiercePharma)"""
    news = []

    # 1. BioSpace 검색
    try:
        url = f"https://www.biospace.com/search?q={ticker}"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            articles = soup.select("article h3 a, .article-title a")[:5]
            for a in articles:
                news.append({
                    "title": a.text.strip(),
                    "link": a.get("href", ""),
                    "source": "BioSpace"
                })
    except:
        pass

    # 2. 구글 뉴스 바이오텍 키워드
    try:
        keywords = f"{ticker} FDA OR clinical OR trial OR Phase OR approval"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:5]:
            title = item.find("title")
            if title:
                news.append({
                    "title": title.text,
                    "link": item.find("link").text if item.find("link") else "",
                    "source": "Google/FDA"
                })
    except:
        pass

    return news


def get_tech_news(ticker: str) -> list:
    """AI/Tech 전용 뉴스"""
    news = []

    # 구글 뉴스 AI/Tech 키워드
    try:
        keywords = f"{ticker} AI OR artificial intelligence OR GPU OR datacenter OR cloud"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:7]:
            title = item.find("title")
            if title:
                news.append({
                    "title": title.text,
                    "link": item.find("link").text if item.find("link") else "",
                    "source": "Google/AI"
                })
    except:
        pass

    return news


def get_energy_news(ticker: str) -> list:
    """에너지 전용 뉴스"""
    news = []

    try:
        keywords = f"{ticker} oil OR gas OR drilling OR OPEC OR energy"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:7]:
            title = item.find("title")
            if title:
                news.append({
                    "title": title.text,
                    "link": item.find("link").text if item.find("link") else "",
                    "source": "Google/Energy"
                })
    except:
        pass

    return news


def get_automotive_news(ticker: str) -> list:
    """자동차/EV 전용 뉴스"""
    news = []

    try:
        keywords = f"{ticker} EV OR electric vehicle OR battery OR autonomous OR Tesla OR charging"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:7]:
            title = item.find("title")
            if title:
                news.append({
                    "title": title.text,
                    "link": item.find("link").text if item.find("link") else "",
                    "source": "Google/Auto"
                })
    except:
        pass

    return news


def get_retail_news(ticker: str) -> list:
    """리테일/이커머스 전용 뉴스"""
    news = []

    try:
        keywords = f"{ticker} retail OR e-commerce OR consumer spending OR sales OR store"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:7]:
            title = item.find("title")
            if title:
                news.append({
                    "title": title.text,
                    "link": item.find("link").text if item.find("link") else "",
                    "source": "Google/Retail"
                })
    except:
        pass

    return news


def get_consumer_news(ticker: str) -> list:
    """소비재/식품 전용 뉴스"""
    news = []

    try:
        keywords = f"{ticker} food OR beverage OR consumer goods OR grocery OR brand"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:7]:
            title = item.find("title")
            if title:
                news.append({
                    "title": title.text,
                    "link": item.find("link").text if item.find("link") else "",
                    "source": "Google/Consumer"
                })
    except:
        pass

    return news


def get_financial_news(ticker: str) -> list:
    """금융/핀테크 전용 뉴스"""
    news = []

    try:
        keywords = f"{ticker} bank OR fintech OR interest rate OR Fed OR lending OR credit"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:7]:
            title = item.find("title")
            if title:
                news.append({
                    "title": title.text,
                    "link": item.find("link").text if item.find("link") else "",
                    "source": "Google/Finance"
                })
    except:
        pass

    return news


def get_industrial_news(ticker: str) -> list:
    """산업재/제조 전용 뉴스"""
    news = []

    try:
        keywords = f"{ticker} manufacturing OR industrial OR defense OR aerospace OR contract"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:7]:
            title = item.find("title")
            if title:
                news.append({
                    "title": title.text,
                    "link": item.find("link").text if item.find("link") else "",
                    "source": "Google/Industrial"
                })
    except:
        pass

    return news


def get_realestate_news(ticker: str) -> list:
    """부동산/리츠 전용 뉴스"""
    news = []

    try:
        keywords = f"{ticker} REIT OR real estate OR property OR mortgage OR housing"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:7]:
            title = item.find("title")
            if title:
                news.append({
                    "title": title.text,
                    "link": item.find("link").text if item.find("link") else "",
                    "source": "Google/RealEstate"
                })
    except:
        pass

    return news


def get_finviz_news(ticker: str) -> list:
    """Finviz 뉴스 스크래핑"""
    news = []

    try:
        url = f"https://finviz.com/quote.ashx?t={ticker}"
        resp = requests.get(url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            news_table = soup.find("table", {"id": "news-table"})

            if news_table:
                rows = news_table.find_all("tr")[:7]
                for row in rows:
                    link = row.find("a")
                    if link:
                        news.append({
                            "title": link.text.strip(),
                            "link": link.get("href", ""),
                            "source": "Finviz"
                        })
    except:
        pass

    return news


# ============================================================
# 바이오텍 특화 분석 (FDA, 임상시험)
# ============================================================

def get_biotech_catalysts(ticker: str, company_name: str) -> dict:
    """바이오텍 촉매 분석 (FDA, 임상시험)"""
    catalysts = {
        "fda_status": [],
        "clinical_trials": [],
        "pdufa_dates": [],
        "fast_track": False,
        "breakthrough": False,
        "orphan_drug": False,
    }

    # 1. FDA 관련 뉴스 검색
    try:
        keywords = f"{ticker} FDA approval OR Fast Track OR PDUFA OR BLA OR NDA"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:5]:
            title = item.find("title")
            if title:
                title_lower = title.text.lower()

                # FDA 상태 감지
                if "fast track" in title_lower:
                    catalysts["fast_track"] = True
                if "breakthrough" in title_lower:
                    catalysts["breakthrough"] = True
                if "orphan" in title_lower:
                    catalysts["orphan_drug"] = True
                if "pdufa" in title_lower:
                    catalysts["pdufa_dates"].append(title.text)

                catalysts["fda_status"].append({
                    "headline": title.text,
                    "date": item.find("pubDate").text if item.find("pubDate") else ""
                })
    except:
        pass

    # 2. ClinicalTrials.gov API
    try:
        # 회사명 전체로 검색 (더 정확)
        # "Greenwich LifeSciences" 처럼 앞 2단어 사용
        if company_name:
            words = company_name.replace(",", "").replace(".", "").split()[:2]
            search_term = " ".join(words)
        else:
            search_term = ticker

        ct_url = f"https://clinicaltrials.gov/api/v2/studies?query.spons={search_term}&pageSize=10"
        resp = requests.get(ct_url, headers={"Accept": "application/json"}, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            studies = data.get("studies", [])

            for study in studies[:5]:
                protocol = study.get("protocolSection", {})
                id_module = protocol.get("identificationModule", {})
                status_module = protocol.get("statusModule", {})
                design_module = protocol.get("designModule", {})
                sponsor_module = protocol.get("sponsorCollaboratorsModule", {})

                # 스폰서 이름 확인 (정확한 매칭)
                lead_sponsor = sponsor_module.get("leadSponsor", {}).get("name", "")
                # 회사명이 스폰서에 포함되지 않으면 스킵
                if company_name and company_name.split()[0].lower() not in lead_sponsor.lower():
                    continue

                phase_list = design_module.get("phases", [])
                phase = phase_list[0] if phase_list else "N/A"

                catalysts["clinical_trials"].append({
                    "nct_id": id_module.get("nctId", ""),
                    "title": id_module.get("briefTitle", "")[:80],
                    "phase": phase,
                    "status": status_module.get("overallStatus", ""),
                    "completion": status_module.get("primaryCompletionDateStruct", {}).get("date", "N/A"),
                    "sponsor": lead_sponsor[:40]
                })
    except Exception as e:
        pass

    return catalysts


def get_automotive_catalysts(ticker: str, company_name: str) -> dict:
    """자동차/EV 촉매 분석"""
    catalysts = {
        "production_numbers": [],
        "new_models": [],
        "ev_credits": False,
        "battery_partnership": False,
        "autonomous_update": False,
    }

    try:
        # EV/자동차 관련 뉴스 검색
        keywords = f"{ticker} production OR delivery OR new model OR EV tax credit OR battery"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:5]:
            title = item.find("title")
            if title:
                title_lower = title.text.lower()

                if "production" in title_lower or "deliver" in title_lower:
                    catalysts["production_numbers"].append(title.text)
                if "new model" in title_lower or "launch" in title_lower:
                    catalysts["new_models"].append(title.text)
                if "ev credit" in title_lower or "tax credit" in title_lower:
                    catalysts["ev_credits"] = True
                if "battery" in title_lower and "partner" in title_lower:
                    catalysts["battery_partnership"] = True
                if "autonomous" in title_lower or "self-driving" in title_lower:
                    catalysts["autonomous_update"] = True
    except:
        pass

    return catalysts


def get_retail_catalysts(ticker: str, company_name: str) -> dict:
    """리테일 촉매 분석"""
    catalysts = {
        "same_store_sales": [],
        "ecommerce_growth": [],
        "holiday_sales": False,
        "store_openings": [],
        "inventory_update": False,
    }

    try:
        keywords = f"{ticker} same-store sales OR e-commerce OR holiday sales OR store opening"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:5]:
            title = item.find("title")
            if title:
                title_lower = title.text.lower()

                if "same-store" in title_lower or "comparable" in title_lower:
                    catalysts["same_store_sales"].append(title.text)
                if "e-commerce" in title_lower or "online sales" in title_lower:
                    catalysts["ecommerce_growth"].append(title.text)
                if "holiday" in title_lower or "black friday" in title_lower:
                    catalysts["holiday_sales"] = True
                if "open" in title_lower and "store" in title_lower:
                    catalysts["store_openings"].append(title.text)
                if "inventory" in title_lower:
                    catalysts["inventory_update"] = True
    except:
        pass

    return catalysts


def get_financial_catalysts(ticker: str, company_name: str) -> dict:
    """금융 촉매 분석"""
    catalysts = {
        "fed_rate_impact": [],
        "loan_growth": [],
        "regulatory_news": [],
        "dividend_update": False,
        "capital_ratio": False,
    }

    try:
        keywords = f"{ticker} Fed rate OR interest rate OR loan growth OR regulation OR dividend"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:5]:
            title = item.find("title")
            if title:
                title_lower = title.text.lower()

                if "fed" in title_lower or "interest rate" in title_lower:
                    catalysts["fed_rate_impact"].append(title.text)
                if "loan" in title_lower and ("growth" in title_lower or "demand" in title_lower):
                    catalysts["loan_growth"].append(title.text)
                if "regulat" in title_lower or "compliance" in title_lower:
                    catalysts["regulatory_news"].append(title.text)
                if "dividend" in title_lower:
                    catalysts["dividend_update"] = True
                if "capital" in title_lower and "ratio" in title_lower:
                    catalysts["capital_ratio"] = True
    except:
        pass

    return catalysts


def get_industrial_catalysts(ticker: str, company_name: str) -> dict:
    """산업재 촉매 분석"""
    catalysts = {
        "contracts": [],
        "gov_spending": [],
        "defense_budget": [],
        "supply_chain": False,
        "pmi_update": False,
    }

    try:
        keywords = f"{ticker} contract OR government OR defense budget OR supply chain OR manufacturing"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:5]:
            title = item.find("title")
            if title:
                title_lower = title.text.lower()

                if "contract" in title_lower and ("win" in title_lower or "award" in title_lower):
                    catalysts["contracts"].append(title.text)
                if "government" in title_lower and "spend" in title_lower:
                    catalysts["gov_spending"].append(title.text)
                if "defense" in title_lower and "budget" in title_lower:
                    catalysts["defense_budget"].append(title.text)
                if "supply chain" in title_lower:
                    catalysts["supply_chain"] = True
                if "pmi" in title_lower or "manufacturing index" in title_lower:
                    catalysts["pmi_update"] = True
    except:
        pass

    return catalysts


def get_realestate_catalysts(ticker: str, company_name: str) -> dict:
    """부동산/리츠 촉매 분석"""
    catalysts = {
        "rate_impact": [],
        "occupancy": [],
        "acquisitions": [],
        "cap_rate": False,
        "noi_growth": False,
    }

    try:
        keywords = f"{ticker} interest rate OR occupancy OR acquisition OR cap rate OR NOI"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:5]:
            title = item.find("title")
            if title:
                title_lower = title.text.lower()

                if "rate" in title_lower and ("cut" in title_lower or "hike" in title_lower):
                    catalysts["rate_impact"].append(title.text)
                if "occupancy" in title_lower:
                    catalysts["occupancy"].append(title.text)
                if "acqui" in title_lower or "purchase" in title_lower:
                    catalysts["acquisitions"].append(title.text)
                if "cap rate" in title_lower:
                    catalysts["cap_rate"] = True
                if "noi" in title_lower or "net operating" in title_lower:
                    catalysts["noi_growth"] = True
    except:
        pass

    return catalysts


# ============================================================
# 8-K 공시 내용 파싱
# ============================================================

def parse_8k_content(ticker: str, cik: str) -> list:
    """최근 8-K 공시에서 주요 이벤트 추출"""
    events = []
    headers = {"User-Agent": "DailyStockStory/1.0 (sean@example.com)"}

    if not cik:
        return events

    try:
        # 최근 filing 목록 가져오기
        filings_url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
        resp = requests.get(filings_url, headers=headers, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            recent = data.get('filings', {}).get('recent', {})

            forms = recent.get('form', [])
            dates = recent.get('filingDate', [])
            accessions = recent.get('accessionNumber', [])
            descriptions = recent.get('primaryDocument', [])

            # 최근 8-K만 필터링 (최대 5개)
            eight_k_count = 0
            for i in range(min(50, len(forms))):
                if forms[i] == "8-K" and eight_k_count < 5:
                    eight_k_count += 1

                    # 8-K 문서 내용 가져오기
                    try:
                        acc = accessions[i].replace('-', '')
                        doc = descriptions[i] if i < len(descriptions) else ""
                        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc}/{doc}"

                        doc_resp = requests.get(doc_url, headers=headers, timeout=15)

                        if doc_resp.status_code == 200:
                            text = doc_resp.text.lower()

                            # 주요 이벤트 키워드 감지
                            event_type = "기타"
                            importance = "보통"

                            if "fda" in text and ("approv" in text or "clear" in text):
                                event_type = "FDA 승인/허가"
                                importance = "🔥 중요"
                            elif "phase" in text and ("result" in text or "data" in text):
                                event_type = "임상 결과 발표"
                                importance = "🔥 중요"
                            elif "agreement" in text or "partnership" in text or "collaborat" in text:
                                event_type = "계약/파트너십"
                                importance = "⚡ 주목"
                            elif "offering" in text or "securities" in text:
                                event_type = "유증/공모"
                                importance = "⚠️ 희석"
                            elif "executive" in text or "officer" in text or "director" in text:
                                event_type = "임원 변동"
                                importance = "보통"
                            elif "earning" in text or "financial" in text or "quarter" in text:
                                event_type = "실적 발표"
                                importance = "📊 실적"

                            events.append({
                                "date": dates[i],
                                "type": event_type,
                                "importance": importance,
                                "accession": accessions[i]
                            })
                    except:
                        pass

    except:
        pass

    return events


# ============================================================
# 8. 숏스퀴즈 점수 계산 (v3 - Zero Borrow 반영)
# ============================================================

def calculate_squeeze_score_v3(data: dict, borrow: dict, in_regsho: bool, tech: dict) -> dict:
    """
    숏스퀴즈 점수 v3 (0-100) - Zero Borrow 반영!

    핵심: Zero Borrow = 새 숏 진입 불가 = 스퀴즈 최적 조건
    """
    score = 0
    details = []
    risks = []
    bullish = []

    # ========== ZERO BORROW (최대 30점) ==========
    if borrow.get("is_zero_borrow"):
        score += 30
        details.append("🔥 ZERO BORROW (빌릴 주식 없음): +30점")
        bullish.append("새 숏 진입 불가능 - 기존 숏만 커버해야 함")
    elif borrow.get("is_hard_to_borrow"):
        score += 15
        details.append("⚠️ Hard to Borrow: +15점")

    # ========== Borrow Rate (0-20점) ==========
    br = borrow.get("borrow_rate")
    if br and br < 999:  # 999는 Zero Borrow
        if br > 100:
            score += 20
            details.append(f"Borrow Rate {br:.1f}% (극단적): +20점")
        elif br > 50:
            score += 15
            details.append(f"Borrow Rate {br:.1f}% (높음): +15점")
        elif br > 20:
            score += 10
            details.append(f"Borrow Rate {br:.1f}%: +10점")

    # ========== Short Interest (0-20점) ==========
    si = data.get("short_pct_float")
    if si:
        si_pct = si * 100 if si < 1 else si
        if si_pct > 30:
            score += 20
            details.append(f"Short % of Float {si_pct:.1f}% (높음): +20점")
        elif si_pct > 20:
            score += 15
            details.append(f"Short % of Float {si_pct:.1f}%: +15점")
        elif si_pct > 10:
            score += 10
            details.append(f"Short % of Float {si_pct:.1f}%: +10점")

    # ========== RegSHO (0-15점) ==========
    if in_regsho:
        score += 15
        details.append("RegSHO Threshold 등재: +15점")
        bullish.append("FTD 다수 발생 - 강제 커버링 압력")

    # ========== Low Float (0-10점) ==========
    float_shares = data.get("float_shares")
    if float_shares:
        if float_shares < 5_000_000:
            score += 10
            details.append(f"극소형 Float ({fmt_num(float_shares)}): +10점")
            bullish.append("작은 Float = 매수 압력에 민감")
        elif float_shares < 10_000_000:
            score += 5
            details.append(f"Low Float ({fmt_num(float_shares)}): +5점")

    # ========== 대차가능 주식 (0-10점) ==========
    avail = borrow.get("available_shares")
    if avail is not None:
        if avail == 0:
            score += 10
            details.append("대차가능 주식 0: +10점")
        elif avail < 50000:
            score += 5
            details.append(f"대차가능 부족 ({fmt_num(avail)}): +5점")

    # ========== 거래량 급증 (0-5점) ==========
    vol_ratio = tech.get("vol_ratio", 1) if tech else 1
    if vol_ratio > 3:
        score += 5
        details.append(f"거래량 급증 {vol_ratio:.1f}x: +5점")
        bullish.append("높은 관심도 & 유동성")

    # ========== 내부자 보유율 (0-5점) ==========
    insider = data.get("insider_pct")
    if insider and insider > 0.3:
        score += 5
        details.append(f"내부자 보유 {insider*100:.1f}%: +5점")
        bullish.append("내부자 락업 = Float 축소 효과")

    # ========== 리스크 분석 ==========

    # RSI 과매수
    rsi = tech.get("rsi") if tech else None
    if rsi:
        if rsi > 85:
            risks.append(f"🔴 RSI {rsi:.1f} - 극단적 과매수, 급락 위험")
        elif rsi > 70:
            risks.append(f"🟡 RSI {rsi:.1f} - 과매수 구간")

    # 볼린저 상단 돌파
    bb_pos = tech.get("bb_position") if tech else None
    if bb_pos and bb_pos > 100:
        risks.append(f"🟡 볼린저 상단 돌파 ({bb_pos:.1f}%) - 과열")

    # ATR 변동성
    atr_pct = tech.get("atr_pct") if tech else None
    if atr_pct and atr_pct > 15:
        risks.append(f"🟡 극단적 변동성 (ATR {atr_pct:.1f}%)")

    # Short 변화 (감소 = 커버링 진행중)
    curr = data.get("shares_short")
    prev = data.get("shares_short_prior")
    if curr and prev and prev > 0:
        change = ((curr - prev) / prev) * 100
        if change < -30:
            risks.append(f"⚠️ Short Interest {change:.1f}% 급감 - 커버링 마무리 단계?")

    return {
        "score": min(round(score, 1), 100),
        "details": details,
        "risks": risks,
        "bullish": bullish
    }


# ============================================================
# 9. Gemini AI 분석
# ============================================================

def analyze_with_gemini(ticker: str, data: dict, borrow: dict, tech: dict,
                        in_regsho: bool, score_info: dict, news: list,
                        force_normal: bool = False, sec_info: dict = None,
                        sec_filings: dict = None) -> str:
    """Gemini AI로 종합 분석"""
    sec_info = sec_info or {}
    sec_filings = sec_filings or {}

    # 데이터 요약 생성
    # 안전한 값 추출
    rsi_val = f"{tech.get('rsi'):.1f}" if tech.get('rsi') else 'N/A'
    bb_val = f"{tech.get('bb_position'):.1f}" if tech.get('bb_position') else 'N/A'
    vol_val = f"{tech.get('vol_ratio'):.2f}" if tech.get('vol_ratio') else 'N/A'

    # 재무 지표 추출
    eps = data.get('eps', 0) or 0
    pe = data.get('pe_ratio')
    debt_equity = data.get('debt_to_equity')
    cash = data.get('total_cash', 0) or 0
    debt = data.get('total_debt', 0) or 0
    revenue = data.get('revenue', 0) or 0
    net_income = data.get('net_income', 0) or 0

    summary = f"""
## {ticker} ({data.get('name', ticker)}) 분석 데이터

### 기본 정보
- 현재가: ${data.get('price', 'N/A')}
- 애프터마켓: ${data.get('post_market', 'N/A')}
- 시가총액: {fmt_num(data.get('market_cap'), '$')}
- Float: {fmt_num(data.get('float_shares'))}
- 섹터: {data.get('sector', 'N/A')}
- 직원수: {data.get('employees', 'N/A')}명

### 재무 상태 (중요!)
- EPS: ${eps:.2f}
- P/E: {pe if pe else 'N/A (적자)'}
- 매출: {fmt_num(revenue, '$')}
- 순이익: {fmt_num(net_income, '$')}
- 총 현금: {fmt_num(cash, '$')}
- 총 부채: {fmt_num(debt, '$')}
- 부채비율(D/E): {debt_equity if debt_equity else 'N/A'}

### 숏 포지션
- Short % of Float: {fmt_pct(data.get('short_pct_float'))}
- Short Shares: {fmt_num(data.get('shares_short'))}
- Days to Cover: {data.get('short_ratio', 'N/A')}
- Zero Borrow: {'✅ YES (빌릴 주식 없음!)' if borrow.get('is_zero_borrow') else '❌ NO'}
- Borrow Rate: {borrow.get('borrow_rate', 'N/A')}%
- RegSHO 등재: {'✅ YES' if in_regsho else '❌ NO'}

### 기술적 지표
- RSI: {rsi_val}
- 볼린저 위치: {bb_val}%
- 거래량 비율: {vol_val}x
- 1일 변화: {tech.get('change_1d', 0):.2f}%
- 5일 변화: {tech.get('change_5d', 0):.2f}%
- 20일 변화: {tech.get('change_20d', 0):.2f}%

### 숏스퀴즈 점수
- 점수: {score_info.get('score', 0)}/100
- 주요 요소: {', '.join(score_info.get('details', [])[:3])}
- 리스크: {', '.join(score_info.get('risks', [])[:3]) if score_info.get('risks') else '없음'}

### 최근 뉴스
{chr(10).join([f"- {n.get('title', 'N/A')}" for n in news[:3]]) if news else '뉴스 없음'}

### SEC 공시 분석 (희석/빚/Covenant)
- Warrant 언급: {sec_info.get('warrant_mentions', 0)}건 {'⚠️ 희석 위험!' if sec_info.get('has_warrant_risk') else '✅ OK'}
- Dilution 언급: {sec_info.get('dilution_mentions', 0)}건 {'⚠️ 희석 위험!' if sec_info.get('dilution_risk') else '✅ OK'}
- Covenant/빚 조항: {sec_info.get('covenant_mentions', 0)}건 {'⚠️ 빚 있음!' if sec_info.get('has_debt_covenant') else '✅ OK'}
- Debt 언급: {sec_info.get('debt_mentions', 0)}건
- Lock-up 언급: {sec_info.get('lockup_mentions', 0)}건 {'🔒 내부자 매도 제한' if sec_info.get('has_lockup') else ''}
- S-3/424B 오퍼링: {sec_info.get('offering_mentions', 0)}건 {'⚠️ 오퍼링 위험!' if sec_info.get('has_offering_risk') else '✅ OK'}
- 호재 공시: {sec_info.get('positive_news', 0)}건 {'🔥' if sec_info.get('has_positive_news') else ''}
- 악재 공시: {sec_info.get('negative_news', 0)}건 {'❌' if sec_info.get('has_negative_news') else ''}

### SPAC/Earnout 정보
- SPAC 여부: {'🚀 SPAC 합병 종목!' if sec_filings and sec_filings.get('is_spac') else '❌ 아님'}
- 내부자 락업 가격: {sec_filings.get('insider_lockup_price', '정보없음') if sec_filings else '정보없음'}
- Earnout 조건 가격: {', '.join(sec_filings.get('earnout_prices', [])) if sec_filings and sec_filings.get('earnout_prices') else '정보없음'}
- Earnout 주식 수: {sec_filings.get('earnout_shares', '정보없음') if sec_filings else '정보없음'}
"""

    # 숏스퀴즈 상황인지 판단 (force_normal이면 무조건 일반 분석)
    is_squeeze_play = False if force_normal else (
        borrow.get('is_zero_borrow') or (data.get('short_pct_float') and data.get('short_pct_float') > 0.2)
    )

    if is_squeeze_play:
        prompt = f"""
너는 숏스퀴즈 전문 트레이더야. 핵심만 분석해줘.

{summary}

⚠️ 중요: 이건 **숏스퀴즈 플레이**야! 펀더멘털 분석은 의미없어.
숏스퀴즈는 수급 싸움이야. 펀더멘털 안좋아도 숏들이 강제로 사야하면 폭등해.

다음을 분석해줘:

## 1. 수급 분석 (가장 중요!)
- Zero Borrow 상태면: 숏들이 **새로 못 들어오고, 나가려면 시장에서 사야함**
- Short % of Float 29%면: Float의 거의 1/3이 숏포지션
- Float 296만주면: 극소형, 매수 압력에 민감
- 이 수급 구조에서 **숏들이 강제청산하면 어떻게 되냐?**

## 2. 모멘텀 분석
- 애프터 +255% 갭업이면: 내일 장시작 때 **FOMO** 폭발
- 해외 투자자들 반응 예상
- RSI 88이라도 숏스퀴즈에선 100 넘게 가기도 함

## 3. 타이밍 분석
- 지금이 **초입**이냐, **중반**이냐, **끝물**이냐?
- Days to Cover 0.16일이면 빨리 청산된다는 뜻
- 근데 Zero Borrow면 빌릴 주식이 없어서 못 빠짐

## 4. 전략 (숏스퀴즈 기준!)
- 신규 진입: 언제 들어가면 좋냐, 위험하냐
- 홀딩 중이면: 언제까지 들고갈만 하냐
- 목표가: 숏커버링 완료 시 예상 가격대
- 손절가: 스퀴즈 실패 시 탈출 라인

## 5. 펀더멘털 (참고용)
- 회사 상태가 어떤지 간단히
- 근데 숏스퀴즈엔 펀더멘털 의미없다는 것도 언급

핵심: 숏스퀴즈는 **수급 게임**이야.
펀더멘털 안좋아도 숏들이 청산해야하면 가격은 폭등해.
GME, AMC 다 그랬잖아.
"""
    else:
        prompt = f"""
너는 주식 분석가야. 이 종목 투자할만한지 분석해줘.

{summary}

다음을 분석해줘:

## 1. 펀더멘털 분석
- 이 회사가 돈을 버는 회사인지
- 매출, 이익, 성장성
- 부채 상태, 현금 보유
- 밸류에이션이 적정한지

## 2. 기술적 분석
- 현재 추세
- RSI, 볼린저밴드 상태
- 지지선/저항선

## 3. 리스크 요인
- 어떤 위험이 있는지
- 급락 가능성

## 4. 투자 의견
- 매수/홀드/매도 중 뭐가 맞는지
- 목표가, 손절가
- 투자 시 주의점

구체적인 숫자와 근거를 들어서 분석해줘.
"""

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents={'text': prompt},
        )
        return response.text
    except Exception as e:
        return f"⚠️ Gemini 분석 실패: {e}"


# ============================================================
# 10. 출력 함수들
# ============================================================

def print_basic_info(data: dict):
    """기본 정보 출력"""
    section("회사 개요", "🏢")

    print(f"  회사명: {data['name']}")
    print(f"  섹터: {data['sector'] or 'N/A'} / {data['industry'] or 'N/A'}")
    print(f"  직원수: {fmt_num(data['employees'])}명")
    print(f"  웹사이트: {data['website'] or 'N/A'}")


def print_price_info(data: dict):
    """가격 정보"""
    section("가격 정보", "💰")

    price = data['price']
    prev = data['prev_close']
    change = ((price / prev) - 1) * 100 if price and prev else 0
    emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"

    print(f"  현재가: ${price:.2f} {emoji} {change:+.2f}%" if price else "  현재가: N/A")

    if data.get('pre_market'):
        pm_change = ((data['pre_market'] / price) - 1) * 100 if price else 0
        print(f"  프리마켓: ${data['pre_market']:.2f} ({pm_change:+.2f}%)")

    if data.get('post_market'):
        am_change = ((data['post_market'] / price) - 1) * 100 if price else 0
        print(f"  애프터마켓: ${data['post_market']:.2f} ({am_change:+.2f}%) 🔥")

    print(f"\n  52주: ${data['52w_low']:.2f} ~ ${data['52w_high']:.2f}" if data['52w_low'] else "")
    print(f"  시가총액: {fmt_num(data['market_cap'], '$')}")
    print(f"  Float: {fmt_num(data['float_shares'])}")


def print_short_data(data: dict, borrow: dict, in_regsho: bool):
    """숏 데이터"""
    section("숏 포지션 분석", "🩳")

    # Zero Borrow 강조!
    if borrow.get("is_zero_borrow"):
        print(f"\n  {'🔥'*10}")
        print(f"  🚨 ZERO BORROW! 빌릴 주식 없음! 🚨")
        print(f"  → 새로운 숏 포지션 진입 불가능")
        print(f"  → 기존 숏은 시장에서 사야만 탈출 가능")
        print(f"  {'🔥'*10}\n")
    elif borrow.get("is_hard_to_borrow"):
        print(f"\n  ⚠️ HARD TO BORROW - 대차 어려움\n")

    si_pct = data['short_pct_float']
    print(f"  Short % of Float: {fmt_pct(si_pct)}")
    print(f"  Short Shares: {fmt_num(data['shares_short'])}")
    print(f"  Days to Cover: {data['short_ratio']:.2f}일" if data['short_ratio'] else "")

    # Short 변화
    curr = data['shares_short']
    prev = data['shares_short_prior']
    if curr and prev:
        change = ((curr - prev) / prev) * 100
        emoji = "📈 증가" if change > 0 else "📉 감소"
        print(f"  Short 변화: {emoji} {change:+.1f}%")

    subsection("Borrow Rate")
    br = borrow.get('borrow_rate')
    if br == 999:
        print(f"  Borrow Rate: ∞ (Zero Borrow)")
    elif br:
        print(f"  Borrow Rate: {br:.1f}%")
    else:
        print(f"  Borrow Rate: N/A")

    print(f"  대차가능 주식: {fmt_num(borrow.get('available_shares'))}")

    subsection("RegSHO Threshold")
    if in_regsho:
        print(f"  ✅ 등재됨 - FTD 다수 발생, 강제 커버링 압력")
    else:
        print(f"  ❌ 미등재")


def print_technicals(tech: dict, price: float):
    """기술적 지표"""
    section("기술적 분석", "📈")

    if not tech:
        print("  데이터 없음")
        return

    rsi = tech.get('rsi')
    if rsi:
        status = "🔴 극단적 과매수" if rsi > 80 else "🟠 과매수" if rsi > 70 else "🟢 과매도" if rsi < 30 else "⚪ 중립"
        print(f"  RSI(14): {rsi:.2f} {status}")

    macd_hist = tech.get('macd_hist')
    if macd_hist is not None:
        trend = "📈 상승" if macd_hist > 0 else "📉 하락"
        print(f"  MACD Histogram: {macd_hist:.4f} {trend}")

    bb_pos = tech.get('bb_position')
    if bb_pos is not None:
        status = "🔴 상단 돌파" if bb_pos > 100 else "🟢 하단 이탈" if bb_pos < 0 else ""
        print(f"  볼린저 위치: {bb_pos:.1f}% {status}")

    vol_ratio = tech.get('vol_ratio', 1)
    vol_status = "🔥🔥🔥" if vol_ratio > 5 else "🔥" if vol_ratio > 2 else ""
    print(f"  거래량 비율: {vol_ratio:.2f}x {vol_status}")

    atr_pct = tech.get('atr_pct')
    if atr_pct:
        print(f"  변동성(ATR%): {atr_pct:.2f}%")

    subsection("가격 변화")
    print(f"  1일: {tech.get('change_1d', 0):+.2f}%")
    print(f"  5일: {tech.get('change_5d', 0):+.2f}%")
    print(f"  20일: {tech.get('change_20d', 0):+.2f}%")


def print_squeeze_score(score_info: dict):
    """스퀴즈 점수"""
    section("숏스퀴즈 종합 점수", "🎰")

    score = score_info['score']

    if score >= 80:
        grade = "🔥🔥🔥🔥 극단적 (숏 지옥)"
    elif score >= 60:
        grade = "🔥🔥🔥 매우 높음"
    elif score >= 40:
        grade = "🔥🔥 높음"
    elif score >= 20:
        grade = "🔥 보통"
    else:
        grade = "❄️ 낮음"

    bar_filled = int(score / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    print(f"\n  [{bar}] {score}/100")
    print(f"  등급: {grade}")

    if score_info.get('details'):
        subsection("점수 구성")
        for detail in score_info['details']:
            print(f"    • {detail}")

    if score_info.get('bullish'):
        subsection("🟢 강세 요인")
        for b in score_info['bullish']:
            print(f"    ✅ {b}")

    if score_info.get('risks'):
        subsection("🔴 리스크 요인")
        for risk in score_info['risks']:
            print(f"    {risk}")


def print_officers(officers: list):
    """경영진"""
    section("경영진", "👔")

    if not officers:
        print("  정보 없음")
        return

    for i, o in enumerate(officers[:5], 1):
        name = o.get("name", "N/A")
        title = o.get("title", "N/A")
        age = o.get("age")
        pay = o.get("totalPay")

        print(f"\n  [{i}] {name}")
        print(f"      {title}")
        if age:
            print(f"      나이: {age}세")
        if pay:
            print(f"      보수: {fmt_num(pay, '$')}")


def print_news(news: list):
    """뉴스"""
    section("최근 뉴스", "📰")

    if not news:
        print("  뉴스 없음")
        return

    for i, n in enumerate(news[:5], 1):
        title = n.get('title', 'N/A')
        publisher = n.get('publisher', '')
        print(f"\n  [{i}] {title}")
        if publisher:
            print(f"      출처: {publisher}")


def print_sector_news(sector_news: dict):
    """섹터별 특화 뉴스 출력"""
    source = sector_news.get("source", "General")
    section(f"섹터별 뉴스 ({source})", "📡")

    # 섹터 특화 뉴스
    specific = sector_news.get("sector_specific", [])
    if specific:
        subsection(f"{source} 전문 뉴스 (최근 60일)")
        for i, n in enumerate(specific[:5], 1):
            title = n.get('title', 'N/A')[:70]
            src = n.get('source', '')
            print(f"  [{i}] {title}...")
            if src:
                print(f"      📌 {src}")
    else:
        print("  섹터 특화 뉴스 없음")

    # 일반 뉴스 (백업)
    general = sector_news.get("general_news", [])
    if general:
        subsection("일반 뉴스 (Google)")
        for i, n in enumerate(general[:3], 1):
            title = n.get('title', 'N/A')[:70]
            print(f"  [{i}] {title}...")


def print_biotech_catalysts(catalysts: dict):
    """바이오텍 촉매 출력"""
    section("바이오텍 촉매 분석", "💊")

    # FDA 상태
    if catalysts.get("fast_track"):
        print("  🚀 FDA Fast Track 지정!")
    if catalysts.get("breakthrough"):
        print("  ⭐ FDA Breakthrough 지정!")
    if catalysts.get("orphan_drug"):
        print("  🏥 Orphan Drug 지정!")

    # FDA 관련 뉴스
    fda_status = catalysts.get("fda_status", [])
    if fda_status:
        subsection("FDA 관련 뉴스")
        for i, news in enumerate(fda_status[:3], 1):
            headline = news.get('headline', '')[:70]
            print(f"  [{i}] {headline}...")

    # 임상시험 정보
    trials = catalysts.get("clinical_trials", [])
    if trials:
        subsection("진행 중인 임상시험 (ClinicalTrials.gov)")
        for trial in trials[:3]:
            nct = trial.get('nct_id', '')
            title = trial.get('title', '')[:60]
            phase = trial.get('phase', 'N/A')
            status = trial.get('status', '')
            completion = trial.get('completion', 'N/A')
            sponsor = trial.get('sponsor', '')

            status_emoji = "🟢" if status == "RECRUITING" else "🟡" if "ACTIVE" in status.upper() else "⚪"
            print(f"  {status_emoji} [{phase}] {title}...")
            print(f"      NCT: {nct} | 완료예정: {completion}")
            if sponsor:
                print(f"      스폰서: {sponsor}")
    else:
        print("  임상시험 정보 없음 (또는 검색 실패)")


def print_automotive_catalysts(catalysts: dict):
    """자동차/EV 촉매 출력"""
    section("자동차/EV 촉매 분석", "🚗")

    if catalysts.get("ev_credits"):
        print("  ⚡ EV 세액공제 관련 뉴스!")
    if catalysts.get("battery_partnership"):
        print("  🔋 배터리 파트너십 뉴스!")
    if catalysts.get("autonomous_update"):
        print("  🤖 자율주행 업데이트!")

    production = catalysts.get("production_numbers", [])
    if production:
        subsection("생산/배송 뉴스")
        for i, news in enumerate(production[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    models = catalysts.get("new_models", [])
    if models:
        subsection("신모델 출시")
        for i, news in enumerate(models[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    if not production and not models:
        print("  최근 자동차 관련 촉매 없음")


def print_retail_catalysts(catalysts: dict):
    """리테일 촉매 출력"""
    section("리테일 촉매 분석", "🛒")

    if catalysts.get("holiday_sales"):
        print("  🎄 연말 쇼핑 시즌 뉴스!")
    if catalysts.get("inventory_update"):
        print("  📦 재고 관련 업데이트!")

    sss = catalysts.get("same_store_sales", [])
    if sss:
        subsection("동일점포 매출")
        for i, news in enumerate(sss[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    ecom = catalysts.get("ecommerce_growth", [])
    if ecom:
        subsection("이커머스 성장")
        for i, news in enumerate(ecom[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    stores = catalysts.get("store_openings", [])
    if stores:
        subsection("매장 오픈/폐쇄")
        for i, news in enumerate(stores[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    if not sss and not ecom and not stores:
        print("  최근 리테일 관련 촉매 없음")


def print_financial_catalysts(catalysts: dict):
    """금융 촉매 출력"""
    section("금융 촉매 분석", "🏦")

    if catalysts.get("dividend_update"):
        print("  💰 배당 관련 뉴스!")
    if catalysts.get("capital_ratio"):
        print("  📊 자본비율 관련 뉴스!")

    fed = catalysts.get("fed_rate_impact", [])
    if fed:
        subsection("금리 영향")
        for i, news in enumerate(fed[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    loan = catalysts.get("loan_growth", [])
    if loan:
        subsection("대출 성장")
        for i, news in enumerate(loan[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    reg = catalysts.get("regulatory_news", [])
    if reg:
        subsection("규제 뉴스")
        for i, news in enumerate(reg[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    if not fed and not loan and not reg:
        print("  최근 금융 관련 촉매 없음")


def print_industrial_catalysts(catalysts: dict):
    """산업재 촉매 출력"""
    section("산업재 촉매 분석", "🏭")

    if catalysts.get("supply_chain"):
        print("  🚚 공급망 관련 뉴스!")
    if catalysts.get("pmi_update"):
        print("  📈 PMI/제조업 지수 뉴스!")

    contracts = catalysts.get("contracts", [])
    if contracts:
        subsection("수주/계약")
        for i, news in enumerate(contracts[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    gov = catalysts.get("gov_spending", [])
    if gov:
        subsection("정부 지출")
        for i, news in enumerate(gov[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    defense = catalysts.get("defense_budget", [])
    if defense:
        subsection("국방 예산")
        for i, news in enumerate(defense[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    if not contracts and not gov and not defense:
        print("  최근 산업재 관련 촉매 없음")


def print_realestate_catalysts(catalysts: dict):
    """부동산/리츠 촉매 출력"""
    section("부동산/리츠 촉매 분석", "🏠")

    if catalysts.get("cap_rate"):
        print("  📉 Cap Rate 관련 뉴스!")
    if catalysts.get("noi_growth"):
        print("  📈 NOI 성장 관련 뉴스!")

    rate = catalysts.get("rate_impact", [])
    if rate:
        subsection("금리 영향")
        for i, news in enumerate(rate[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    occ = catalysts.get("occupancy", [])
    if occ:
        subsection("점유율")
        for i, news in enumerate(occ[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    acq = catalysts.get("acquisitions", [])
    if acq:
        subsection("인수/매각")
        for i, news in enumerate(acq[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    if not rate and not occ and not acq:
        print("  최근 부동산 관련 촉매 없음")


def print_8k_events(events: list):
    """8-K 이벤트 출력"""
    section("8-K 주요 공시", "📢")

    if not events:
        print("  최근 8-K 공시 없음")
        return

    for event in events[:5]:
        date = event.get('date', '')
        event_type = event.get('type', '기타')
        importance = event.get('importance', '')

        print(f"  {importance} {date}: {event_type}")


def print_sec_info(sec_info: dict):
    """SEC 공시 정보"""
    section("SEC 공시 분석", "📋")

    # 숫자 표시
    subsection("SEC 키워드 언급 횟수 (2024년~)")
    print(f"  Warrant 언급: {sec_info.get('warrant_mentions', 0)}건")
    print(f"  Dilution 언급: {sec_info.get('dilution_mentions', 0)}건")
    print(f"  Covenant/빚 조항: {sec_info.get('covenant_mentions', 0)}건")
    print(f"  Debt 언급: {sec_info.get('debt_mentions', 0)}건")
    print(f"  Lock-up 언급: {sec_info.get('lockup_mentions', 0)}건")
    print(f"  S-3/424B (오퍼링): {sec_info.get('offering_mentions', 0)}건")

    subsection("뉴스 분석 (2025년)")
    print(f"  호재 관련: {sec_info.get('positive_news', 0)}건")
    print(f"  악재 관련: {sec_info.get('negative_news', 0)}건")

    # 리스크 해석
    subsection("리스크 해석")
    risks = []
    safe = []

    if sec_info.get("has_warrant_risk"):
        risks.append("⚠️ 워런트 리스크 (희석 가능성)")
    else:
        safe.append("✅ 워런트 리스크 낮음")

    if sec_info.get("dilution_risk"):
        risks.append("⚠️ 희석 리스크 (Dilution 언급 多)")
    else:
        safe.append("✅ 희석 리스크 낮음")

    if sec_info.get("has_debt_covenant"):
        risks.append("⚠️ 빚/Covenant 조항 있음")
    else:
        safe.append("✅ Covenant 리스크 낮음")

    if sec_info.get("has_offering_risk"):
        risks.append("⚠️ 오퍼링 리스크 (S-3/424B 등록)")
    else:
        safe.append("✅ 오퍼링 리스크 낮음")

    if sec_info.get("has_lockup"):
        print("  🔒 Lock-up 조항 존재 (내부자 매도 제한)")

    if sec_info.get("has_positive_news"):
        safe.append("🔥 호재 공시 多")
    if sec_info.get("has_negative_news"):
        risks.append("❌ 악재 공시 多")

    if risks:
        for r in risks:
            print(f"  {r}")
    if safe:
        for s in safe:
            print(f"  {s}")

    if not risks and not safe:
        print("  특이사항 없음")


def print_ftd_data(ftd: dict):
    """FTD 데이터 출력"""
    section("FTD (Failure to Deliver)", "📦")

    if not ftd.get("recent_ftd"):
        print("  FTD 데이터 없음")
        return

    print(f"  총 FTD: {fmt_num(ftd.get('total_ftd'))}주")
    print(f"  평균 FTD: {fmt_num(ftd.get('avg_ftd'))}주")
    print(f"  최대 FTD: {fmt_num(ftd.get('max_ftd'))}주")
    print(f"  추세: {ftd.get('ftd_trend', 'N/A')}")

    if ftd.get("has_significant_ftd"):
        print(f"\n  🔥 유의미한 FTD 감지! (10만주+)")

    subsection("최근 FTD")
    for f in ftd.get("recent_ftd", [])[:5]:
        print(f"    {f['date']}: {fmt_num(f['quantity'])}주")


def print_options_data(opt: dict):
    """옵션 데이터 출력"""
    section("옵션 체인 분석", "📊")

    if not opt.get("has_options"):
        print("  옵션 거래 없음")
        return

    print(f"  가장 가까운 만기: {opt.get('nearest_expiry')}")
    print(f"  콜 OI 총합: {fmt_num(opt.get('total_call_oi'))}")
    print(f"  풋 OI 총합: {fmt_num(opt.get('total_put_oi'))}")
    print(f"  Put/Call 비율: {opt.get('put_call_ratio', 0):.2f}")
    print(f"  Max Pain: ${opt.get('max_pain', 0):.2f}")
    print(f"  ITM 콜 OI: {fmt_num(opt.get('itm_calls'))}")

    if opt.get("gamma_exposure"):
        subsection("감마 집중 구간 (OI Top 5)")
        for g in opt.get("gamma_exposure", []):
            print(f"    ${g['strike']:.2f}: {fmt_num(g['oi'])} OI")


def print_social_sentiment(sent: dict):
    """소셜 센티먼트 출력"""
    section("소셜 센티먼트", "💬")

    print(f"  종합 센티먼트: {sent.get('overall_sentiment', 'N/A')}")

    if sent.get("stocktwits_sentiment"):
        print(f"  Stocktwits: {sent['stocktwits_sentiment']} ({sent.get('stocktwits_messages', 0)}개 메시지)")

    if sent.get("watchlist_count"):
        print(f"  관심목록 등록: {fmt_num(sent.get('watchlist_count'))}명")

    if sent.get("reddit_mentions"):
        print(f"  Reddit 언급: {sent['reddit_mentions']}개")

    if sent.get("recent_posts"):
        subsection("최근 포스트")
        for p in sent.get("recent_posts", [])[:5]:
            source = p.get('source', 'Unknown')
            sentiment = p.get('sentiment', 'N/A')
            emoji = "🟢" if sentiment == 'Bullish' else "🔴" if sentiment == 'Bearish' else "⚪"
            print(f"    [{source}] {emoji} {p['body'][:50]}...")


def print_catalyst(cat: dict):
    """촉매 일정 출력"""
    section("촉매(Catalyst) 일정", "📅")

    if cat.get("next_earnings"):
        print(f"  다음 어닝: {cat['next_earnings']}")

    if cat.get("recent_earnings_surprise"):
        print(f"  최근 어닝 서프라이즈: {cat['recent_earnings_surprise']}")

    if cat.get("ex_dividend_date"):
        print(f"  배당락일: {cat['ex_dividend_date']}")

    if cat.get("earnings_estimate"):
        print(f"  목표가 평균: ${cat['earnings_estimate']:.2f}")

    if not any([cat.get("next_earnings"), cat.get("ex_dividend_date")]):
        print("  예정된 촉매 없음")


def print_fibonacci(fib: dict):
    """피보나치 레벨 출력"""
    section("피보나치 & 지지/저항", "📐")

    if not fib.get("levels"):
        print("  데이터 부족")
        return

    print(f"  현재 위치: {fib.get('current_zone', 'N/A')}")

    subsection("피보나치 레벨")
    for level, price in fib.get("levels", {}).items():
        print(f"    {level}: ${price}")

    if fib.get("support_levels"):
        subsection("지지선 (현재가 아래)")
        for s in fib.get("support_levels", [])[:3]:
            print(f"    {s['level']}: ${s['price']} ({s['distance']} 아래)")

    if fib.get("resistance_levels"):
        subsection("저항선 (현재가 위)")
        for r in fib.get("resistance_levels", [])[:3]:
            print(f"    {r['level']}: ${r['price']} ({r['distance']} 위)")

    if fib.get("gaps"):
        subsection("갭 분석 (최근 20일)")
        for g in fib.get("gaps", [])[:5]:
            print(f"    {g['date']}: {g['type']} ${g['gap_start']}-${g['gap_end']} [{g['filled']}]")


def print_volume_profile(vp: dict):
    """볼륨 프로파일 출력"""
    section("볼륨 프로파일", "📊")

    if not vp.get("poc"):
        print("  데이터 부족")
        return

    print(f"  POC (거래량 집중가): ${vp.get('poc')}")
    print(f"  Value Area High: ${vp.get('value_area_high')}")
    print(f"  Value Area Low: ${vp.get('value_area_low')}")

    if vp.get("high_volume_zones"):
        subsection("고거래량 가격대")
        for z in vp.get("high_volume_zones", [])[:5]:
            print(f"    ${z['price']}: {fmt_num(z['volume'])}주")


def print_darkpool(dp: dict):
    """다크풀 데이터 출력"""
    section("다크풀 & 숏볼륨", "🌑")

    if dp.get("source"):
        print(f"  📡 소스: {dp['source']}")

    if dp.get("short_volume_percent"):
        print(f"  숏 볼륨 비율: {dp['short_volume_percent']}%")

    if dp.get("off_exchange_percent"):
        print(f"  장외거래(다크풀) 비율: {dp['off_exchange_percent']}%")

    if dp.get("darkpool_volume"):
        print(f"  다크풀 거래량: {fmt_num(dp['darkpool_volume'])}주")

    if dp.get("warning"):
        print(f"\n  {dp['warning']}")

    if dp.get("dp_warning"):
        print(f"  {dp['dp_warning']}")

    if not dp.get("short_volume_percent") and not dp.get("off_exchange_percent"):
        print("  데이터 없음")


def print_sec_filings(filings: dict):
    """SEC Filing 출력"""
    section("SEC Filing 상세", "📑")

    if filings.get("company_name"):
        print(f"  SEC 등록명: {filings['company_name']}")

    if filings.get("cik"):
        print(f"  CIK: {filings['cik']}")

    if filings.get("insider_lockup_price"):
        print(f"\n  🔒 내부자 락업 가격: {filings['insider_lockup_price']}")

    if filings.get("lockup_info"):
        print(f"  🔒 락업 정보: {filings['lockup_info']}")

    # SPAC / Earnout 정보
    if filings.get("is_spac"):
        print(f"\n  🚀 SPAC 합병 종목!")

    if filings.get("earnout_prices"):
        subsection("Earnout 조건 (락업 해제 가격)")
        for price in filings["earnout_prices"]:
            print(f"    🎯 주가 {price} 도달 시 → 주식 락업 해제")
        print(f"    💡 이 가격들에서 내부자/스폰서가 매도 가능해짐 (공급 증가)")

    if filings.get("earnout_shares"):
        print(f"  📈 Earnout 대상 주식 수: {filings['earnout_shares']}주")

    if filings.get("warrant_details"):
        subsection("워런트 행사가")
        for w in filings["warrant_details"]:
            print(f"    💰 {w}")

    if filings.get("debt_details"):
        subsection("빚/대출 정보")
        for d in filings["debt_details"]:
            print(f"    💳 {d}")

    if filings.get("offering_info"):
        subsection("오퍼링 이력")
        for o in filings["offering_info"]:
            print(f"    📄 {o['date']}: {o['shares']}주 @ {o['price']} ({o['form']})")

    if filings.get("recent_filings"):
        subsection("최근 SEC 공시")
        for f in filings["recent_filings"][:7]:
            form_emoji = "📋"
            if f['form'] in ['S-1', 'S-3', '424B4', '424B5']:
                form_emoji = "⚠️"
            elif f['form'] in ['S-4', 'S-4/A', 'DEFM14A']:
                form_emoji = "🚀"  # SPAC 관련
            elif f['form'] == '8-K':
                form_emoji = "📢"
            elif f['form'] in ['10-K', '10-Q']:
                form_emoji = "📊"
            print(f"    {form_emoji} {f['date']}: {f['form']}")

    if not filings.get("recent_filings") and not filings.get("insider_lockup_price"):
        print("  SEC 데이터 없음")


def print_institutional(inst: dict):
    """기관 보유 출력"""
    section("기관 보유 현황", "🏛️")

    print(f"  기관 보유 비율: {inst.get('institutional_percent', 'N/A')}")
    print(f"  기관 수: {inst.get('total_institutional', 0)}개")

    if inst.get("top_holders"):
        subsection("Top 5 기관")
        for h in inst["top_holders"]:
            print(f"    {h['holder'][:25]}: {fmt_num(h['shares'])}주 ({h['pct_out']})")


def print_peer_comparison(peer: dict):
    """동종업체 비교 출력"""
    section("동종업체 비교", "🏭")

    print(f"  섹터: {peer.get('sector', 'N/A')}")
    print(f"  산업: {peer.get('industry', 'N/A')}")
    print(f"  섹터 평균 PE: {peer.get('sector_avg_pe', 'N/A')}")
    print(f"  상대 밸류에이션: {peer.get('relative_valuation', 'N/A')}")


def print_short_history(sh: dict):
    """Short Interest 히스토리 출력"""
    section("Short Interest 추이", "📉")

    if sh.get("current_si"):
        print(f"  현재 SI: {fmt_num(sh['current_si'])}주")
    if sh.get("prior_si"):
        print(f"  전월 SI: {fmt_num(sh['prior_si'])}주")

    print(f"  30일 변화: {sh.get('change_30d', 'N/A')}")
    print(f"  추세: {sh.get('trend', 'N/A')}")

    if sh.get("short_float_pct"):
        print(f"  Short Float %: {sh['short_float_pct']}")

    if sh.get("short_ratio"):
        print(f"  Short Ratio: {sh['short_ratio']}일")

    if sh.get("short_volume"):
        print(f"  Short Volume: {fmt_num(int(sh['short_volume']))}주")


# ============================================================
# 메인 분석
# ============================================================

def analyze(ticker: str, use_ai: bool = True, force_normal: bool = False):
    """종합 분석 실행"""

    mode = "일반 투자" if force_normal else "자동 (숏스퀴즈/일반)"
    print(f"\n{'#'*70}")
    print(f"#  🔍 {ticker} 초정밀 분석 리포트 v3 (똥꾸멍 주름 에디션)")
    print(f"#  📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"#  🤖 Gemini AI: {'ON' if use_ai else 'OFF'}")
    print(f"#  📊 분석 모드: {mode}")
    print(f"{'#'*70}")

    try:
        # ========== 데이터 수집 ==========
        print("\n⏳ 데이터 수집 중... (초정밀 분석 v3)")

        # 1. yfinance 기본 정보
        print("  → yfinance 기본 정보...")
        data = get_basic_info(ticker)
        stock = data['stock']

        # 2. Borrow 데이터 (Zero Borrow 포함)
        print("  → Borrow Rate & Zero Borrow...")
        borrow = get_borrow_data(ticker)

        # 3. RegSHO
        print("  → RegSHO Threshold...")
        in_regsho = check_regsho(ticker)

        # 4. 기술적 지표
        print("  → 기술적 분석...")
        tech = get_technicals(stock)

        # 5. 경영진 & 내부자
        print("  → 경영진 & 내부자...")
        officers = get_officers(stock)
        insider_tx = get_insider_transactions(stock)
        inst_holders = get_institutional_holders(stock)

        # 6. 뉴스 (섹터별 특화)
        print("  → 뉴스...")
        news = get_news(stock)
        if not news:
            news = search_recent_news(ticker)

        # 6.5 섹터별 특화 뉴스
        print("  → 섹터별 특화 뉴스...")
        sector = data.get('sector', '')
        industry = data.get('industry', '')
        sector_news = get_sector_news(ticker, sector, industry)

        # 6.6 섹터별 촉매 분석
        sector_catalysts = None
        sector_catalyst_type = None
        company_name = data.get('name', ticker)
        industry_lower = (industry or "").lower()
        sector_lower = (sector or "").lower()

        if "biotech" in industry_lower or "pharma" in industry_lower or "healthcare" in sector_lower:
            print("  → 바이오텍 촉매 분석 (FDA/임상)...")
            sector_catalysts = get_biotech_catalysts(ticker, company_name)
            sector_catalyst_type = "biotech"
        elif "auto" in industry_lower or "vehicle" in industry_lower or "ev" in industry_lower:
            print("  → 자동차/EV 촉매 분석...")
            sector_catalysts = get_automotive_catalysts(ticker, company_name)
            sector_catalyst_type = "automotive"
        elif "real estate" in sector_lower or "reit" in industry_lower:
            # REIT 체크를 retail 앞에 (REIT - Retail 구분)
            print("  → 부동산/리츠 촉매 분석...")
            sector_catalysts = get_realestate_catalysts(ticker, company_name)
            sector_catalyst_type = "realestate"
        elif "retail" in industry_lower or "e-commerce" in industry_lower or "store" in industry_lower:
            print("  → 리테일 촉매 분석...")
            sector_catalysts = get_retail_catalysts(ticker, company_name)
            sector_catalyst_type = "retail"
        elif "food" in industry_lower or "beverage" in industry_lower or "consumer" in sector_lower:
            print("  → 소비재 촉매 분석...")
            sector_catalysts = get_retail_catalysts(ticker, company_name)  # 리테일과 유사
            sector_catalyst_type = "consumer"
        elif "bank" in industry_lower or "financial" in sector_lower or "insurance" in industry_lower:
            print("  → 금융 촉매 분석...")
            sector_catalysts = get_financial_catalysts(ticker, company_name)
            sector_catalyst_type = "financial"
        elif "industrial" in sector_lower or "aerospace" in industry_lower or "defense" in industry_lower:
            print("  → 산업재 촉매 분석...")
            sector_catalysts = get_industrial_catalysts(ticker, company_name)
            sector_catalyst_type = "industrial"

        # 7. SEC 공시 정보 (빚, covenant, 희석 리스크)
        print("  → SEC 공시 키워드 분석...")
        sec_info = get_sec_info(ticker)

        # 8. FTD 데이터
        print("  → FTD (Failure to Deliver)...")
        ftd_data = get_ftd_data(ticker)

        # 9. 옵션 체인
        print("  → 옵션 체인 분석...")
        options_data = get_options_data(stock)

        # 10. 소셜 센티먼트
        print("  → 소셜 센티먼트 (Stocktwits)...")
        sentiment_data = get_social_sentiment(ticker)

        # 11. 촉매 일정
        print("  → 촉매 일정...")
        catalyst_data = get_catalyst_calendar(stock)

        # 12. 피보나치 & 지지/저항
        print("  → 피보나치 레벨...")
        fib_data = get_fibonacci_levels(stock)

        # 13. 볼륨 프로파일
        print("  → 볼륨 프로파일...")
        volume_profile = get_volume_profile(stock)

        # 14. 다크풀
        print("  → 다크풀 데이터...")
        darkpool_data = get_darkpool_data(ticker)

        # 15. SEC Filing 상세 (S-1, 락업, 워런트)
        print("  → SEC Filing 상세 파싱...")
        sec_filings = get_sec_filings(ticker)

        # 15.5 8-K 주요 이벤트 파싱
        print("  → 8-K 주요 이벤트 파싱...")
        cik = sec_filings.get("cik", "")
        eight_k_events = parse_8k_content(ticker, cik)

        # 16. 기관 보유 변화
        print("  → 기관 보유 분석...")
        institutional_data = get_institutional_changes(stock)

        # 17. 동종업체 비교
        print("  → 동종업체 비교...")
        peer_data = get_peer_comparison(stock, ticker)

        # 18. Short Interest 히스토리
        print("  → Short Interest 추이...")
        short_history = get_short_history(ticker)

        # 19. 스퀴즈 점수
        print("  → 스퀴즈 점수 계산...")
        score_info = calculate_squeeze_score_v3(data, borrow, in_regsho, tech)

        print("\n✅ 데이터 수집 완료!")

        # ========== 출력 ==========

        # 기본 정보
        print_basic_info(data)
        print_price_info(data)

        # 숏스퀴즈 관련
        print_short_data(data, borrow, in_regsho)
        print_short_history(short_history)
        print_ftd_data(ftd_data)

        # 기술적 분석
        print_technicals(tech, data.get('price', 0))
        print_fibonacci(fib_data)
        print_volume_profile(volume_profile)

        # 옵션 & 다크풀
        print_options_data(options_data)
        print_darkpool(darkpool_data)

        # 스퀴즈 점수
        print_squeeze_score(score_info)

        # SEC 분석
        print_sec_info(sec_info)
        print_sec_filings(sec_filings)

        # 기관 & 동종업체
        print_institutional(institutional_data)
        print_peer_comparison(peer_data)

        # 촉매 & 센티먼트
        print_catalyst(catalyst_data)
        print_social_sentiment(sentiment_data)

        # 경영진 & 뉴스
        print_officers(officers)
        print_news(news)

        # 섹터별 특화 뉴스
        print_sector_news(sector_news)

        # 8-K 주요 이벤트
        print_8k_events(eight_k_events)

        # 섹터별 촉매 (해당시)
        if sector_catalysts:
            if sector_catalyst_type == "biotech":
                print_biotech_catalysts(sector_catalysts)
            elif sector_catalyst_type == "automotive":
                print_automotive_catalysts(sector_catalysts)
            elif sector_catalyst_type == "retail" or sector_catalyst_type == "consumer":
                print_retail_catalysts(sector_catalysts)
            elif sector_catalyst_type == "financial":
                print_financial_catalysts(sector_catalysts)
            elif sector_catalyst_type == "industrial":
                print_industrial_catalysts(sector_catalysts)
            elif sector_catalyst_type == "realestate":
                print_realestate_catalysts(sector_catalysts)

        # ========== Gemini AI 분석 ==========

        if use_ai:
            section("Gemini AI 종합 분석", "🤖")
            print("\n  ⏳ AI 분석 중...")
            ai_analysis = analyze_with_gemini(
                ticker, data, borrow, tech, in_regsho, score_info, news, force_normal, sec_info, sec_filings
            )
            print(f"\n{ai_analysis}")

        # ========== 최종 요약 ==========

        section("최종 요약", "💡")

        price = data.get('price', 0)
        post = data.get('post_market')
        score = score_info['score']

        print(f"\n  📊 {data['name']} ({ticker})")
        print(f"  💰 현재가: ${price:.2f}")
        if post:
            print(f"  🌙 애프터: ${post:.2f} ({((post/price)-1)*100:+.1f}%)")
        print(f"  🎰 스퀴즈 점수: {score}/100")

        if borrow.get("is_zero_borrow"):
            print(f"\n  🔥 ZERO BORROW 상태!")
            print(f"     → 새 숏 진입 불가")
            print(f"     → 기존 숏 탈출 = 시장 매수 필수")
            print(f"     → 스퀴즈 조건 충족!")

        print(f"\n{'='*70}")
        print(f"⚠️ 투자 결정은 본인 책임입니다.")
        print(f"{'='*70}\n")

        return {
            "data": data,
            "borrow": borrow,
            "tech": tech,
            "in_regsho": in_regsho,
            "score_info": score_info
        }

    except Exception as e:
        print(f"\n❌ 분석 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python deep_analyzer.py <TICKER> [OPTIONS]")
        print("Example: uv run python deep_analyzer.py BNAI")
        print("         uv run python deep_analyzer.py BNAI --no-ai")
        print("         uv run python deep_analyzer.py GLSI --normal  # 일반 투자 분석")
        sys.exit(1)

    ticker = sys.argv[1].upper()
    use_ai = "--no-ai" not in sys.argv
    force_normal = "--normal" in sys.argv

    analyze(ticker, use_ai, force_normal)


if __name__ == "__main__":
    main()
