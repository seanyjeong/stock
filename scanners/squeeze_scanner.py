"""
숏스퀴즈 데이터 수집기

프론트엔드 /squeeze 페이지용 데이터 수집
- Borrow Rate (Playwright)
- Short Interest
- Days to Cover
- Zero Borrow 감지
- 희석 보호 여부

실행:
    uv run python scanners/squeeze_scanner.py
    uv run python scanners/squeeze_scanner.py --test  # 테스트 (5개만)
"""

import os
import sys
import argparse
from datetime import datetime
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_db
from psycopg2.extras import RealDictCursor

# deep_analyzer에서 함수 import
from deep_analyzer import (
    get_borrow_data,
    get_sec_info,
)

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 호재/악재 키워드
POSITIVE_KEYWORDS = [
    # 실적/계약
    "beat", "beats", "exceed", "exceeds", "surpass", "record", "strong",
    "growth", "profit", "revenue up", "sales up", "contract", "partnership",
    "agreement", "deal", "acquisition", "merger", "buyout", "wins",
    # FDA/바이오
    "fda approval", "fda approves", "approved", "breakthrough", "fast track",
    "positive", "successful", "trial success", "phase 3", "pdufa",
    "fda update", "fda clears", "fda grants",
    # 숏스퀴즈
    "short squeeze", "squeeze", "gamma", "covering", "rally", "surge",
    "soar", "spike", "breakout", "momentum", "explodes", "jumps", "soars",
    # 기관/투자
    "upgrade", "buy rating", "price target raise", "institutional buying",
    "insider buying", "13d", "activist", "bought", "buying",
]

NEGATIVE_KEYWORDS = [
    # 실적/재무
    "miss", "misses", "below", "weak", "loss", "decline", "drop",
    "revenue down", "sales down", "layoff", "restructur", "bankruptcy",
    "default", "debt", "dilution", "offering", "shelf registration",
    # FDA/바이오
    "fda reject", "crl", "fail", "negative", "halt", "suspend",
    "trial fail", "discontinue", "adverse",
    # 주가
    "downgrade", "sell rating", "price target cut", "delisting",
    "compliance", "nasdaq notice",
    # 소송/리스크
    "lawsuit", "sec investigation", "fraud", "scandal",
]


def get_news_sentiment(ticker: str) -> dict:
    """
    Finviz 뉴스에서 호재/악재 감지

    Returns:
        {
            "has_positive": bool,
            "has_negative": bool,
            "positive_count": int,
            "negative_count": int,
            "recent_headlines": list
        }
    """
    result = {
        "has_positive": False,
        "has_negative": False,
        "positive_count": 0,
        "negative_count": 0,
        "recent_headlines": []
    }

    try:
        url = f"https://finviz.com/quote.ashx?t={ticker}"
        resp = requests.get(url, headers=HEADERS, timeout=10)

        if resp.status_code != 200:
            return result

        soup = BeautifulSoup(resp.text, "html.parser")
        news_table = soup.find("table", {"id": "news-table"})

        if not news_table:
            return result

        rows = news_table.find_all("tr")[:10]  # 최근 10개

        for row in rows:
            link = row.find("a")
            if not link:
                continue

            title = link.text.strip().lower()
            result["recent_headlines"].append(link.text.strip())

            # 호재 체크
            for kw in POSITIVE_KEYWORDS:
                if kw in title:
                    result["positive_count"] += 1
                    result["has_positive"] = True
                    break

            # 악재 체크
            for kw in NEGATIVE_KEYWORDS:
                if kw in title:
                    result["negative_count"] += 1
                    result["has_negative"] = True
                    break

    except Exception as e:
        pass

    return result


# ============================================================
# 스퀴즈 후보 종목 스캔 (Finviz 스크리너)
# ============================================================

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def get_squeeze_candidates_from_finviz() -> list[str]:
    """
    Finviz 스크리너로 숏스퀴즈 후보 스캔 (finvizfinance 라이브러리)

    조건:
    - Short Float > 10%
    - Market Cap < $2B (소형주)
    - Average Volume > 100K (유동성)
    """
    tickers = []

    try:
        from finvizfinance.screener.overview import Overview

        screener = Overview()

        # 필터: Float Short > 10%, Small Cap 이하
        filters_dict = {
            'Market Cap.': '-Small (under $2bln)',
            'Float Short': 'Over 10%',
            'Average Volume': 'Over 100K',
        }

        screener.set_filter(filters_dict=filters_dict)
        df = screener.screener_view()

        if df is not None and not df.empty:
            tickers = df['Ticker'].tolist()

        print(f"  📊 Finviz 스크리너: {len(tickers)}개 후보 발견")

    except Exception as e:
        print(f"  ⚠️ Finviz 스크리너 실패: {e}")

    return tickers[:100]  # 최대 100개


def get_regsho_tickers() -> list[str]:
    """RegSHO Threshold List에서 티커 가져오기"""
    tickers = []

    try:
        conn = get_db()
        cur = conn.cursor()
        # 최근 7일 RegSHO 목록
        cur.execute("""
            SELECT DISTINCT ticker FROM regsho_threshold
            WHERE collected_at > NOW() - INTERVAL '7 days'
        """)
        tickers = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        print(f"  📋 RegSHO: {len(tickers)}개")
    except:
        pass

    return tickers


def get_watchlist_tickers() -> list[str]:
    """관심종목에서 티커 가져오기"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT ticker FROM watchlist")
        tickers = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        print(f"  ⭐ 관심종목: {len(tickers)}개")
        return tickers
    except:
        return []


def get_high_si_from_yfinance(tickers_pool: list[str], min_si: float = 10.0) -> list[str]:
    """yfinance로 SI 높은 종목 필터링 (빠른 1차 필터)"""
    high_si = []

    for ticker in tickers_pool:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            si = info.get('shortPercentOfFloat', 0) or 0
            si_pct = si * 100 if si < 1 else si

            if si_pct >= min_si:
                high_si.append(ticker)
        except:
            pass

    return high_si


def get_market_cap_multiplier(market_cap: int) -> tuple[float, str]:
    """시가총액 기반 스퀴즈 가능성 가중치"""
    if market_cap <= 0:
        return 1.0, "Unknown"
    elif market_cap < 100_000_000:       # < $100M
        return 1.0, "Nano"
    elif market_cap < 500_000_000:       # $100M-$500M
        return 0.85, "Micro"
    elif market_cap < 2_000_000_000:     # $500M-$2B
        return 0.6, "Small"
    else:                                 # > $2B
        return 0.3, "Mid/Large"


def calculate_squeeze_score_v4(data: dict) -> tuple[float, float]:
    """
    v4 스퀴즈 점수 계산 (0-100)

    Returns: (raw_score, final_score)
    """
    raw = 0

    # === A. 공급 압박 (Supply Constraint) — cap 35 ===
    supply = 0
    zero_borrow = data.get("zero_borrow", False)
    borrow_rate = data.get("borrow_rate") or 0
    available_shares = data.get("available_shares")

    if zero_borrow:
        supply += 25
    elif borrow_rate >= 100:
        supply += 12  # Hard to Borrow

    # Borrow Rate 가산 (ZB와 별개)
    if borrow_rate >= 100:
        supply += 8
    elif borrow_rate >= 50:
        supply += 5
    elif borrow_rate >= 20:
        supply += 2

    # Available Shares
    if available_shares is not None:
        if available_shares == 0:
            supply += 5
        elif available_shares < 50_000:
            supply += 3

    raw += min(supply, 35)

    # === B. 숏 포지션 압력 (Short Pressure) — cap 25 ===
    short_pressure = 0
    si_pct = data.get("short_interest") or 0
    dtc = data.get("days_to_cover") or 0

    if si_pct >= 40:
        short_pressure += 20
    elif si_pct >= 30:
        short_pressure += 15
    elif si_pct >= 20:
        short_pressure += 10
    elif si_pct >= 10:
        short_pressure += 5

    if dtc >= 7:
        short_pressure += 5
    elif dtc >= 3:
        short_pressure += 3

    raw += min(short_pressure, 25)

    # === C. 촉매 & 모멘텀 (Catalyst & Momentum) — cap 25 ===
    catalyst = 0
    has_positive = data.get("has_positive_news", False)
    has_negative = data.get("has_negative_news", False)
    price_change_5d = data.get("price_change_5d") or 0
    vol_ratio = data.get("vol_ratio") or 1

    if has_positive:
        catalyst += 10
    if has_negative:
        catalyst -= 10
    if not has_positive and not has_negative:
        catalyst -= 5  # 촉매 부재

    if price_change_5d > 50:
        catalyst += 10
    elif price_change_5d > 20:
        catalyst += 7
    elif price_change_5d > 10:
        catalyst += 4
    elif price_change_5d > 5:
        catalyst += 2

    if vol_ratio > 5:
        catalyst += 5
    elif vol_ratio > 3:
        catalyst += 3
    elif vol_ratio > 1.5:
        catalyst += 1

    raw += max(min(catalyst, 25), -15)  # 최소 -15까지 허용

    # === D. 구조적 보호 (Structural) — cap 15 ===
    structural = 0
    float_shares = data.get("float_shares") or 0

    if 0 < float_shares < 5_000_000:
        structural += 7
    elif 0 < float_shares < 10_000_000:
        structural += 4
    elif 0 < float_shares < 20_000_000:
        structural += 2

    if data.get("dilution_protected", False):
        structural += 3

    if data.get("is_regsho", False):
        structural += 5

    raw += min(structural, 15)

    # === 최종 점수 ===
    raw = max(raw, 0)  # 음수 방지
    market_cap = data.get("market_cap") or 0
    multiplier, _ = get_market_cap_multiplier(market_cap)
    final = min(raw * multiplier, 100)

    return round(raw, 2), round(final, 2)


def collect_squeeze_data(ticker: str) -> dict | None:
    """단일 종목 스퀴즈 데이터 수집"""
    try:
        # 1. yfinance 기본 정보
        stock = yf.Ticker(ticker)
        info = stock.info

        short_interest = info.get('shortPercentOfFloat', 0) or 0
        days_to_cover = info.get('shortRatio', 0) or 0
        float_shares = info.get('floatShares', 0) or 0
        market_cap = info.get('marketCap', 0) or 0
        avg_volume = info.get('averageVolume', 0) or 0
        current_volume = info.get('volume', 0) or 0

        # 5일 가격 모멘텀
        price_change_5d = 0.0
        try:
            hist = stock.history(period="5d")
            if len(hist) >= 2:
                price_change_5d = float(((hist['Close'].iloc[-1] / hist['Close'].iloc[0]) - 1) * 100)
        except Exception:
            pass

        vol_ratio = float(current_volume / avg_volume) if avg_volume > 0 else 1.0

        # 2. Borrow Rate (Playwright)
        borrow = get_borrow_data(ticker)
        borrow_rate = borrow.get('borrow_rate')
        zero_borrow = borrow.get('is_zero_borrow', False) or False
        available_shares = borrow.get('available_shares')

        # 3. SEC 희석 리스크 체크
        sec_info = get_sec_info(ticker)
        warrant_count = sec_info.get('warrant_count', 0) or 0
        s3_count = sec_info.get('s3_filing_count', 0) or 0
        dilution_protected = (warrant_count == 0 and s3_count == 0)

        # 4. 뉴스/촉매 체크
        news = get_news_sentiment(ticker)
        has_positive_news = news["has_positive"]
        has_negative_news = news["has_negative"]

        # SI 정규화
        si_pct = short_interest * 100 if short_interest and short_interest < 1 else short_interest

        # RegSHO 등재 여부 확인
        is_regsho = False
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                SELECT 1 FROM regsho_list
                WHERE ticker = %s AND collected_date = (SELECT MAX(collected_date) FROM regsho_list)
            """, (ticker,))
            is_regsho = cur.fetchone() is not None
            cur.close()
            conn.close()
        except Exception:
            pass

        # 5. v4 스퀴즈 점수 계산
        score_data = {
            "zero_borrow": zero_borrow,
            "borrow_rate": borrow_rate,
            "available_shares": available_shares,
            "short_interest": si_pct,
            "days_to_cover": days_to_cover,
            "has_positive_news": has_positive_news,
            "has_negative_news": has_negative_news,
            "price_change_5d": price_change_5d,
            "vol_ratio": vol_ratio,
            "float_shares": float_shares,
            "dilution_protected": dilution_protected,
            "is_regsho": is_regsho,
            "market_cap": market_cap,
        }
        raw_score, final_score = calculate_squeeze_score_v4(score_data)

        return {
            "ticker": ticker,
            "borrow_rate": borrow_rate,
            "short_interest": si_pct,
            "days_to_cover": days_to_cover,
            "available_shares": available_shares,
            "float_shares": float_shares,
            "zero_borrow": zero_borrow,
            "dilution_protected": dilution_protected,
            "has_positive_news": has_positive_news,
            "has_negative_news": has_negative_news,
            "squeeze_score": final_score,
            "source": borrow.get('source', 'yfinance'),
            "market_cap": market_cap,
            "price_change_5d": round(price_change_5d, 2),
            "vol_ratio": round(vol_ratio, 2),
        }

    except Exception as e:
        print(f"  ⚠️ {ticker} 수집 실패: {e}")
        return None


def save_to_db(data_list: list[dict]):
    """DB에 저장 (UPSERT)"""
    conn = get_db()
    cur = conn.cursor()

    for data in data_list:
        cur.execute("""
            INSERT INTO squeeze_data (
                ticker, borrow_rate, short_interest, days_to_cover,
                available_shares, float_shares, dilution_protected,
                squeeze_score, source, collected_at,
                has_positive_news, has_negative_news, short_volume,
                market_cap, price_change_5d, vol_ratio
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, 0,
                %s, %s, %s
            )
            ON CONFLICT (ticker) DO UPDATE SET
                borrow_rate = EXCLUDED.borrow_rate,
                short_interest = EXCLUDED.short_interest,
                days_to_cover = EXCLUDED.days_to_cover,
                available_shares = EXCLUDED.available_shares,
                float_shares = EXCLUDED.float_shares,
                dilution_protected = EXCLUDED.dilution_protected,
                squeeze_score = EXCLUDED.squeeze_score,
                source = EXCLUDED.source,
                has_positive_news = EXCLUDED.has_positive_news,
                has_negative_news = EXCLUDED.has_negative_news,
                market_cap = EXCLUDED.market_cap,
                price_change_5d = EXCLUDED.price_change_5d,
                vol_ratio = EXCLUDED.vol_ratio,
                collected_at = NOW()
        """, (
            data["ticker"],
            data["borrow_rate"],
            data["short_interest"],
            data["days_to_cover"],
            data["available_shares"],
            data["float_shares"],
            data["dilution_protected"],
            data["squeeze_score"],
            data["source"],
            data["has_positive_news"],
            data["has_negative_news"],
            data.get("market_cap"),
            data.get("price_change_5d"),
            data.get("vol_ratio"),
        ))

    conn.commit()
    cur.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="숏스퀴즈 데이터 수집기")
    parser.add_argument("--test", action="store_true", help="테스트 모드 (5개만)")
    parser.add_argument("--quick", action="store_true", help="빠른 모드 (RegSHO + 관심종목만)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"🔥 숏스퀴즈 데이터 수집기 v4 (시가총액 가중치)")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 티커 수집 (다중 소스)
    print("\n📡 스퀴즈 후보 스캔 중...")

    all_tickers = []

    # 1. Finviz 스크리너 (SI > 10%, 소형주)
    if not args.quick:
        finviz_tickers = get_squeeze_candidates_from_finviz()
        all_tickers.extend(finviz_tickers)

    # 2. RegSHO Threshold (결제 실패 종목)
    regsho_tickers = get_regsho_tickers()
    all_tickers.extend(regsho_tickers)

    # 3. 관심종목
    watchlist_tickers = get_watchlist_tickers()
    all_tickers.extend(watchlist_tickers)

    # 중복 제거
    tickers = list(set(all_tickers))

    if args.test:
        tickers = tickers[:5] if tickers else ["GLSI", "BNAI", "GME", "AMC", "TSLA"]
        print(f"🧪 테스트 모드: {tickers}")

    print(f"\n📊 수집 대상: {len(tickers)}개 종목\n")

    # 병렬 수집
    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:  # Playwright 때문에 3개로 제한
        futures = {executor.submit(collect_squeeze_data, t): t for t in tickers}

        for future in as_completed(futures):
            ticker = futures[future]
            try:
                data = future.result()
                if data:
                    results.append(data)
                    br = data.get('borrow_rate')
                    br_str = f"{br:.1f}%" if br else "N/A"
                    zb = "ZB" if data.get('zero_borrow') else ""
                    news = ""
                    if data.get('has_positive_news'):
                        news = "📈"
                    elif data.get('has_negative_news'):
                        news = "📉"
                    _, tier = get_market_cap_multiplier(data.get('market_cap', 0))
                    print(f"  ✅ {ticker}: Score={data.get('squeeze_score', 0)} [{tier}] BR={br_str} SI={data.get('short_interest', 0):.1f}% 5d={data.get('price_change_5d', 0):+.1f}% {zb} {news}")
            except Exception as e:
                print(f"  ❌ {ticker}: {e}")

    # DB 저장
    if results:
        print(f"\n💾 DB 저장 중... ({len(results)}개)")
        save_to_db(results)
        print("✅ 저장 완료!")

    # 결과 요약
    print("\n" + "=" * 60)
    print("📊 결과 요약")
    print("=" * 60)

    # Top 10 by score
    sorted_results = sorted(results, key=lambda x: x.get('squeeze_score', 0), reverse=True)[:10]
    print("\n🔥 Top 10 스퀴즈 후보:")
    for i, r in enumerate(sorted_results, 1):
        zb = "ZB" if r.get('zero_borrow') else ""
        br = r.get('borrow_rate')
        br_str = f"{br:.0f}%" if br else "-"
        news = ""
        if r.get('has_positive_news'):
            news = "📈"
        elif r.get('has_negative_news'):
            news = "📉"
        _, tier = get_market_cap_multiplier(r.get('market_cap', 0))
        score = r['squeeze_score']
        rating = "SQUEEZE" if score >= 75 else "HOT" if score >= 55 else "WATCH" if score >= 35 else "COLD"
        print(f"  {i}. {r['ticker']}: {score}점 {rating} [{tier}] (BR={br_str}, SI={r.get('short_interest', 0):.1f}%, 5d={r.get('price_change_5d', 0):+.1f}%) {zb} {news}")

    print(f"\n✅ 완료! {len(results)}개 종목 업데이트됨")


if __name__ == "__main__":
    main()
