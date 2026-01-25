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


# ============================================================
# 스퀴즈 후보 종목 리스트
# ============================================================

# RegSHO + 관심종목 + 핫 종목
SQUEEZE_TICKERS = [
    # 현재 핫한 종목
    "GLSI", "BNAI", "GRRR", "DRUG", "KOSS",
    # 바이오텍
    "SAVA", "IMVT", "SRPT", "SGEN", "MRNA",
    # 나노캡 숏스퀴즈 후보
    "FFIE", "MULN", "NKLA", "GOEV", "WKHS",
    # 밈주식
    "GME", "AMC", "BBBY", "BB", "NOK",
    # 기타
    "SPCE", "CLOV", "WISH", "SOFI", "PLTR",
]


def get_watchlist_tickers() -> list[str]:
    """관심종목에서 티커 가져오기"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT ticker FROM watchlist")
        tickers = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return tickers
    except:
        return []


def collect_squeeze_data(ticker: str) -> dict | None:
    """단일 종목 스퀴즈 데이터 수집"""
    try:
        # 1. yfinance 기본 정보
        stock = yf.Ticker(ticker)
        info = stock.info

        short_interest = info.get('shortPercentOfFloat', 0) or 0
        days_to_cover = info.get('shortRatio', 0) or 0
        float_shares = info.get('floatShares', 0) or 0

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

        # 4. 스퀴즈 점수 계산
        score = 0

        # SI 점수 (0-25)
        if short_interest:
            si_pct = short_interest * 100 if short_interest < 1 else short_interest
            if si_pct >= 50:
                score += 25
            elif si_pct >= 30:
                score += 20
            elif si_pct >= 20:
                score += 15
            elif si_pct >= 10:
                score += 10
            else:
                score += si_pct / 2

        # Borrow Rate 점수 (0-20)
        if borrow_rate:
            if borrow_rate >= 200:
                score += 20
            elif borrow_rate >= 100:
                score += 15
            elif borrow_rate >= 50:
                score += 10
            elif borrow_rate >= 20:
                score += 5

        # Zero Borrow 보너스
        if zero_borrow:
            score += 15

        # DTC 점수 (0-15)
        if days_to_cover:
            if days_to_cover >= 10:
                score += 15
            elif days_to_cover >= 5:
                score += 10
            elif days_to_cover >= 2:
                score += 5

        # Low Float 보너스
        if float_shares and float_shares < 10_000_000:
            score += 5

        # 희석 보호 보너스
        if dilution_protected:
            score += 10

        return {
            "ticker": ticker,
            "borrow_rate": borrow_rate,
            "short_interest": short_interest * 100 if short_interest and short_interest < 1 else short_interest,
            "days_to_cover": days_to_cover,
            "available_shares": available_shares,
            "float_shares": float_shares,
            "zero_borrow": zero_borrow,
            "dilution_protected": dilution_protected,
            "squeeze_score": round(score, 2),
            "source": borrow.get('source', 'yfinance'),
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
                has_positive_news, has_negative_news, short_volume
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), FALSE, FALSE, 0
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
        ))

    conn.commit()
    cur.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="숏스퀴즈 데이터 수집기")
    parser.add_argument("--test", action="store_true", help="테스트 모드 (5개만)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"🔥 숏스퀴즈 데이터 수집기")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 티커 수집
    tickers = list(set(SQUEEZE_TICKERS + get_watchlist_tickers()))

    if args.test:
        tickers = tickers[:5]
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
                    zb = "🔥 ZB" if data.get('zero_borrow') else ""
                    print(f"  ✅ {ticker}: BR={br_str} SI={data.get('short_interest', 0):.1f}% Score={data.get('squeeze_score', 0)} {zb}")
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
        print(f"  {i}. {r['ticker']}: {r['squeeze_score']}점 (BR={br_str}, SI={r.get('short_interest', 0):.1f}%) {zb}")

    print(f"\n✅ 완료! {len(results)}개 종목 업데이트됨")


if __name__ == "__main__":
    main()
