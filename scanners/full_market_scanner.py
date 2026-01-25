"""
전체 시장 스캐너

뉴스 점수 상위 종목에 대해:
1. 기술적 분석 (RSI, MACD, Volume)
2. 성향별 점수 계산 (단타/스윙/장기)
3. 스마트 매수가 계산

실행:
    uv run python scanners/full_market_scanner.py
    uv run python scanners/full_market_scanner.py --test  # 테스트 모드
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf
import pandas as pd
import numpy as np
from google import genai

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_db
from psycopg2.extras import RealDictCursor

# Gemini 설정 (새 SDK)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
else:
    gemini_client = None


def generate_recommendation_reason(data: dict) -> str:
    """Gemini로 한글 추천 이유 생성"""
    if not gemini_client:
        return ""

    prompt = f"""너는 주식 추천 이유를 한글로 작성하는 분석가야.

[규칙]
1. 아래 데이터만 사용해. 추측/예측 금지.
2. "~일 것이다", "~할 것으로 보인다" 금지.
3. 팩트만 서술해. 3줄 이내.

[종목 데이터]
- 티커: {data.get('ticker')}
- 현재가: ${data.get('current_price')}
- RSI: {data.get('rsi')} {'(과매도)' if data.get('rsi', 50) < 30 else '(과매수)' if data.get('rsi', 50) > 70 else ''}
- MACD: {data.get('macd_cross')}
- 거래량: 평균 대비 {data.get('volume_ratio')}배
- 뉴스 점수: {data.get('news_score')} {'(호재)' if data.get('news_score', 0) > 5 else ''}

한글로 3줄 작성:"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={
                "temperature": 0,
                "max_output_tokens": 200,
            }
        )
        return response.text.strip()
    except Exception as e:
        print(f"  Gemini 오류: {e}")
        return ""


def calculate_rating(data: dict) -> tuple:
    """R/R 기반 추천 등급 계산"""
    entry = data.get('entry_balanced', 0)
    target = data.get('target', 0)
    stop = data.get('stop_loss', 0)

    if entry <= 0 or stop <= 0:
        return "★", 0.0

    risk = entry - stop
    reward = target - entry

    if risk <= 0:
        return "★", 0.0

    rr_ratio = reward / risk

    if rr_ratio >= 1.5:
        return "★★★", round(rr_ratio, 2)
    elif rr_ratio >= 1.0:
        return "★★", round(rr_ratio, 2)
    else:
        return "★", round(rr_ratio, 2)


def calculate_split_entry(current: float, support: float, atr: float) -> list:
    """분할매수 3단계 계산"""
    if current <= 0:
        return []

    # 1차: 현재가 (40%)
    entry1 = round(current, 2)
    # 2차: 1차 지지선 (30%)
    entry2 = round(support, 2) if support > 0 else round(current * 0.95, 2)
    # 3차: 강한 지지 (30%)
    entry3 = round(support - atr, 2) if atr > 0 else round(current * 0.90, 2)

    return [
        {"price": entry1, "pct": 40, "label": "현재가"},
        {"price": entry2, "pct": 30, "label": "1차 지지"},
        {"price": entry3, "pct": 30, "label": "강한 지지"}
    ]


def init_tables():
    """스캔 결과 테이블 생성"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_scan_results (
            id SERIAL PRIMARY KEY,
            scan_date DATE NOT NULL,
            results JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scan_date)
        );

        CREATE INDEX IF NOT EXISTS idx_scan_date ON daily_scan_results(scan_date);
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ 테이블 초기화 완료")


def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    """RSI 계산"""
    if len(prices) < period + 1:
        return 50.0

    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0


def calculate_macd(prices: pd.Series) -> tuple:
    """MACD 계산"""
    if len(prices) < 26:
        return 0.0, 0.0, 'neutral'

    exp1 = prices.ewm(span=12, adjust=False).mean()
    exp2 = prices.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()

    macd_val = float(macd.iloc[-1])
    signal_val = float(signal.iloc[-1])

    # 크로스 판단
    if len(macd) >= 2:
        prev_macd = float(macd.iloc[-2])
        prev_signal = float(signal.iloc[-2])

        if prev_macd < prev_signal and macd_val > signal_val:
            cross = 'golden'  # 골든 크로스
        elif prev_macd > prev_signal and macd_val < signal_val:
            cross = 'death'  # 데드 크로스
        else:
            cross = 'neutral'
    else:
        cross = 'neutral'

    return macd_val, signal_val, cross


def calculate_support_resistance(hist: pd.DataFrame) -> tuple:
    """지지선/저항선 계산"""
    if len(hist) < 20:
        close = hist['Close'].iloc[-1]
        return close * 0.95, close * 1.05

    lows = hist['Low'].tail(20)
    highs = hist['High'].tail(20)

    support = float(lows.min())
    resistance = float(highs.max())

    return support, resistance


def calculate_atr(hist: pd.DataFrame, period: int = 14) -> float:
    """ATR (Average True Range) 계산"""
    if len(hist) < period + 1:
        return 0.0

    high = hist['High']
    low = hist['Low']
    close = hist['Close']

    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.0


def score_day_trade(rsi: float, macd_cross: str, volume_ratio: float, news_score: float, info: dict) -> float:
    """단타 점수 계산 (공격형)"""
    score = 0.0

    # 시총 (소형주 선호)
    market_cap = info.get('marketCap', 0) or 0
    if market_cap < 2e9:  # 2B 미만
        score += 20
    elif market_cap < 10e9:
        score += 10

    # RSI (과매도 반등)
    if 30 <= rsi <= 50:
        score += 25
    elif 20 <= rsi < 30:
        score += 15

    # MACD
    if macd_cross == 'golden':
        score += 20
    elif macd_cross == 'neutral':
        score += 5

    # 거래량 급증
    if volume_ratio > 3:
        score += 20
    elif volume_ratio > 2:
        score += 15
    elif volume_ratio > 1.5:
        score += 10

    # 뉴스 점수
    if news_score > 10:
        score += 15
    elif news_score > 5:
        score += 10
    elif news_score > 0:
        score += 5

    return score


def score_swing(rsi: float, macd_cross: str, hist: pd.DataFrame, news_score: float) -> float:
    """스윙 점수 계산 (균형형)"""
    score = 0.0

    # RSI
    if 40 <= rsi <= 60:
        score += 20
    elif 30 <= rsi < 40:
        score += 15

    # MACD
    if macd_cross == 'golden':
        score += 25
    elif macd_cross == 'neutral':
        score += 10

    # 추세 (20일 이동평균)
    if len(hist) >= 20:
        ma20 = hist['Close'].rolling(20).mean().iloc[-1]
        current = hist['Close'].iloc[-1]
        if current > ma20:
            score += 20  # 상승 추세
        elif current > ma20 * 0.98:
            score += 10  # 지지선 근처

    # 거래량 안정성
    if len(hist) >= 5:
        vol_std = hist['Volume'].tail(5).std() / hist['Volume'].tail(5).mean()
        if vol_std < 0.5:
            score += 10

    # 뉴스
    if news_score > 5:
        score += 15
    elif news_score > 0:
        score += 10

    return score


def score_longterm(info: dict, hist: pd.DataFrame, news_score: float) -> float:
    """장기 점수 계산 (안정형)"""
    score = 0.0

    # 시총 (대형주 선호)
    market_cap = info.get('marketCap', 0) or 0
    if market_cap > 100e9:
        score += 25
    elif market_cap > 50e9:
        score += 20
    elif market_cap > 10e9:
        score += 10

    # 배당
    dividend_yield = info.get('dividendYield', 0) or 0
    if dividend_yield > 0.03:
        score += 20
    elif dividend_yield > 0.02:
        score += 15
    elif dividend_yield > 0.01:
        score += 10

    # P/E
    pe = info.get('trailingPE', 0) or 0
    if 10 < pe < 25:
        score += 15
    elif 5 < pe <= 10:
        score += 10

    # 1개월 수익률
    if len(hist) >= 20:
        monthly_return = (hist['Close'].iloc[-1] / hist['Close'].iloc[0] - 1) * 100
        if monthly_return > 5:
            score += 15
        elif monthly_return > 0:
            score += 10

    # 낮은 변동성
    if len(hist) >= 14:
        volatility = hist['Close'].pct_change().std() * 100
        if volatility < 2:
            score += 15
        elif volatility < 3:
            score += 10

    return score


def calculate_entry_prices(hist: pd.DataFrame, current_price: float, atr: float) -> dict:
    """성향별 매수가 계산"""
    support, resistance = calculate_support_resistance(hist)

    return {
        'aggressive': round(current_price * 1.02, 2),  # 현재가 +2%
        'balanced': round((current_price + support) / 2, 2),  # 중간
        'conservative': round(support * 0.99, 2),  # 지지선 -1%
        'stop_loss': round(current_price - (atr * 2), 2),  # ATR 2배
        'target': round(current_price + (atr * 3), 2),  # ATR 3배
        'support': round(support, 2),
        'resistance': round(resistance, 2)
    }


def analyze_ticker(ticker: str, news_score: float) -> Optional[dict]:
    """개별 종목 분석"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='3mo')

        if hist.empty or len(hist) < 20:
            return None

        info = stock.info or {}
        current_price = float(hist['Close'].iloc[-1])

        # 기술적 지표
        rsi = calculate_rsi(hist['Close'])
        macd_val, signal_val, macd_cross = calculate_macd(hist['Close'])
        atr = calculate_atr(hist)

        # 거래량 비율
        vol_avg = hist['Volume'].mean()
        vol_today = hist['Volume'].iloc[-1]
        volume_ratio = float(vol_today / vol_avg) if vol_avg > 0 else 1.0

        # 성향별 점수
        day_score = score_day_trade(rsi, macd_cross, volume_ratio, news_score, info)
        swing_score = score_swing(rsi, macd_cross, hist, news_score)
        long_score = score_longterm(info, hist, news_score)

        # 매수가 계산
        entries = calculate_entry_prices(hist, current_price, atr)

        # 기본 데이터 구성
        result = {
            'ticker': ticker,
            'current_price': round(current_price, 2),
            'rsi': round(rsi, 1),
            'macd': round(macd_val, 4),
            'macd_cross': macd_cross,
            'volume_ratio': round(volume_ratio, 2),
            'atr': round(atr, 2),
            'news_score': news_score,

            # 성향별 점수
            'day_trade_score': round(day_score, 1),
            'swing_score': round(swing_score, 1),
            'longterm_score': round(long_score, 1),

            # 매수가
            'entry_aggressive': entries['aggressive'],
            'entry_balanced': entries['balanced'],
            'entry_conservative': entries['conservative'],
            'stop_loss': entries['stop_loss'],
            'target': entries['target'],
            'support': entries['support'],
            'resistance': entries['resistance'],

            # 추가 정보
            'company_name': info.get('shortName', ticker),
            'market_cap': info.get('marketCap', 0),
            'sector': info.get('sector', 'Unknown')
        }

        # AI 추천 이유 생성 (Gemini)
        reason = generate_recommendation_reason(result)
        result['recommendation_reason'] = reason

        # R/R 기반 등급 계산
        rating, rr_ratio = calculate_rating(result)
        result['rating'] = rating
        result['rr_ratio'] = rr_ratio

        # 분할매수 제안
        split_entries = calculate_split_entry(
            current_price,
            entries['support'],
            atr
        )
        result['split_entries'] = split_entries

        return result

    except Exception as e:
        print(f"  ⚠️ {ticker}: {e}")
        return None


def get_news_top_tickers(limit: int = 50) -> list:
    """뉴스 점수 상위 종목 조회"""
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


def save_scan_results(results: list):
    """스캔 결과 저장"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO daily_scan_results (scan_date, results)
        VALUES (CURRENT_DATE, %s)
        ON CONFLICT (scan_date)
        DO UPDATE SET results = EXCLUDED.results, created_at = CURRENT_TIMESTAMP
    """, (json.dumps(results),))

    conn.commit()
    cur.close()
    conn.close()


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
    parser = argparse.ArgumentParser(description='전체 시장 스캐너')
    parser.add_argument('--test', action='store_true', help='테스트 모드')
    parser.add_argument('--force', action='store_true', help='휴장일 무시하고 실행')
    args = parser.parse_args()

    print("=" * 50)
    print("🔍 전체 시장 스캐너 시작")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 휴장일 체크
    if is_us_market_holiday() and not args.force:
        print("📅 미국 증시 휴장일 - 스캔 건너뜀")
        return

    # 테이블 초기화
    init_tables()

    # 1. 뉴스 점수 상위 종목 조회
    news_tickers = get_news_top_tickers(50)
    print(f"\n📰 뉴스 점수 상위 {len(news_tickers)}개 종목")

    if not news_tickers:
        print("❌ 뉴스 데이터 없음. 먼저 news_collector.py 실행 필요")
        return

    if args.test:
        news_tickers = news_tickers[:5]
        print("  (테스트 모드: 5개만)")

    # 2. 기술적 분석
    print("\n📊 기술적 분석 중...")
    results = []

    for item in news_tickers:
        ticker = item['ticker']
        news_score = item['total_score'] or 0

        print(f"  분석 중: {ticker}", end='\r')
        result = analyze_ticker(ticker, news_score)

        if result:
            results.append(result)

        time.sleep(0.3)  # Rate limit

    print(f"\n  → {len(results)}개 종목 분석 완료")

    # 3. 저장
    save_scan_results(results)
    print("💾 결과 저장 완료")

    # 4. 성향별 TOP 5 출력
    if results:
        print("\n" + "=" * 50)
        print("🔥 단타 추천 TOP 5 (공격형)")
        print("-" * 50)
        day_top = sorted(results, key=lambda x: -x['day_trade_score'])[:5]
        for i, r in enumerate(day_top, 1):
            print(f"  {i}. {r['ticker']} | 점수: {r['day_trade_score']} | "
                  f"RSI: {r['rsi']} | 매수가: ${r['entry_aggressive']}")

        print("\n⚖️ 스윙 추천 TOP 5 (균형형)")
        print("-" * 50)
        swing_top = sorted(results, key=lambda x: -x['swing_score'])[:5]
        for i, r in enumerate(swing_top, 1):
            print(f"  {i}. {r['ticker']} | 점수: {r['swing_score']} | "
                  f"MACD: {r['macd_cross']} | 매수가: ${r['entry_balanced']}")

        print("\n🛡️ 장기 추천 TOP 5 (안정형)")
        print("-" * 50)
        long_top = sorted(results, key=lambda x: -x['longterm_score'])[:5]
        for i, r in enumerate(long_top, 1):
            print(f"  {i}. {r['ticker']} | 점수: {r['longterm_score']} | "
                  f"매수가: ${r['entry_conservative']}")

    print("\n✅ 스캔 완료")


if __name__ == "__main__":
    main()
