"""
전체 시장 스캐너 v2

각 투자 성향별로 완전히 다른 종목 풀에서 스캔:
- 단타: 뉴스 핫 종목 + 거래량 급증 (소형주)
- 스윙: 기술적 과매도 + 반등 신호 (중형주)
- 장기: S&P 500 대형주 (안정적 배당주)

실행:
    uv run python scanners/full_market_scanner.py
    uv run python scanners/full_market_scanner.py --test
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

# Gemini 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
else:
    gemini_client = None

# ============================================================
# 종목 풀 정의
# ============================================================

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

# 스윙 투자용 중형주 (기술적 분석 후보)
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


# ============================================================
# 기술적 지표 계산
# ============================================================

def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    """RSI 계산"""
    if len(prices) < period + 1:
        return 50.0

    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).abs().rolling(window=period).mean()

    # 0으로 나누기 방지
    rs = np.where(loss == 0, 100, gain / loss)
    rsi = 100 - (100 / (1 + rs))

    result = float(rsi[-1]) if len(rsi) > 0 else 50.0

    # NaN, Infinity 처리
    if pd.isna(result) or np.isinf(result):
        return 50.0

    return result


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
            cross = 'golden'
        elif prev_macd > prev_signal and macd_val < signal_val:
            cross = 'death'
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
    """ATR 계산"""
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


# ============================================================
# 단타 스캐너 (뉴스 핫 + 소형주)
# ============================================================

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


def analyze_day_trade(ticker: str, news_score: float) -> Optional[dict]:
    """단타 종목 분석"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='1mo')

        if hist.empty or len(hist) < 10:
            return None

        info = stock.info or {}
        current_price = float(hist['Close'].iloc[-1])

        # 가격 필터: $1 ~ $100 (단타용)
        if current_price < 1 or current_price > 100:
            return None

        # 시총 필터: $50M ~ $5B (소형주)
        market_cap = info.get('marketCap', 0) or 0
        if market_cap < 50e6 or market_cap > 5e9:
            return None

        # 기술적 지표
        rsi = calculate_rsi(hist['Close'])
        macd_val, signal_val, macd_cross = calculate_macd(hist['Close'])
        atr = calculate_atr(hist)

        # 거래량 급증 체크
        vol_avg = hist['Volume'].tail(10).mean()
        vol_today = hist['Volume'].iloc[-1]
        volume_ratio = float(vol_today / vol_avg) if vol_avg > 0 else 1.0

        # 단타 점수 계산
        score = 0.0

        # 거래량 급증 (가장 중요)
        if volume_ratio > 5:
            score += 30
        elif volume_ratio > 3:
            score += 25
        elif volume_ratio > 2:
            score += 20
        elif volume_ratio > 1.5:
            score += 10

        # RSI 반등 구간 (30-50)
        if 30 <= rsi <= 50:
            score += 25
        elif 20 <= rsi < 30:
            score += 15  # 과매도 주의
        elif rsi < 20:
            score += 5   # 너무 과매도

        # MACD 골든크로스
        if macd_cross == 'golden':
            score += 25

        # 뉴스 점수
        if news_score > 10:
            score += 20
        elif news_score > 5:
            score += 15
        elif news_score > 0:
            score += 10

        if score < 40:  # 최소 점수
            return None

        support, resistance = calculate_support_resistance(hist)

        return {
            'ticker': ticker,
            'category': 'day_trade',
            'company_name': info.get('shortName', ticker),
            'current_price': round(current_price, 2),
            'market_cap': market_cap,
            'score': round(score, 1),
            'rsi': round(rsi, 1),
            'macd_cross': macd_cross,
            'volume_ratio': round(volume_ratio, 2),
            'news_score': news_score,
            'recommended_entry': round(current_price * 0.98, 2),  # -2%
            'stop_loss': round(current_price - (atr * 1.5), 2),
            'target': round(current_price * 1.08, 2),  # +8% 목표
            'support': round(support, 2),
            'resistance': round(resistance, 2),
        }

    except Exception as e:
        print(f"  ⚠️ 단타 {ticker}: {e}")
        return None


# ============================================================
# 스윙 스캐너 (기술적 과매도 중형주)
# ============================================================

def analyze_swing(ticker: str) -> Optional[dict]:
    """스윙 종목 분석 (4-7일 보유)"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='3mo')

        if hist.empty or len(hist) < 30:
            return None

        info = stock.info or {}
        current_price = float(hist['Close'].iloc[-1])

        # 가격 필터
        if current_price < 5:
            return None

        # 기술적 지표
        rsi = calculate_rsi(hist['Close'])
        macd_val, signal_val, macd_cross = calculate_macd(hist['Close'])
        atr = calculate_atr(hist)

        # 이동평균
        ma20 = hist['Close'].rolling(20).mean().iloc[-1]
        ma50 = hist['Close'].rolling(50).mean().iloc[-1] if len(hist) >= 50 else ma20

        # 스윙 점수 계산
        score = 0.0

        # RSI 과매도 반등 (핵심)
        if 25 <= rsi <= 40:
            score += 30  # 반등 시작 구간
        elif 40 < rsi <= 55:
            score += 20  # 상승 초기
        elif rsi < 25:
            score += 15  # 바닥 탐색

        # MACD 크로스
        if macd_cross == 'golden':
            score += 30
        elif macd_val > signal_val:
            score += 15

        # 가격 vs 이동평균
        if current_price > ma20 and current_price < ma20 * 1.05:
            score += 20  # MA20 돌파 직후
        elif current_price > ma20 * 0.95 and current_price <= ma20:
            score += 15  # MA20 지지 테스트

        # 50일선 위
        if current_price > ma50:
            score += 10

        if score < 40:
            return None

        support, resistance = calculate_support_resistance(hist)

        return {
            'ticker': ticker,
            'category': 'swing',
            'company_name': info.get('shortName', ticker),
            'current_price': round(current_price, 2),
            'market_cap': info.get('marketCap', 0),
            'score': round(score, 1),
            'rsi': round(rsi, 1),
            'macd_cross': macd_cross,
            'ma20': round(ma20, 2),
            'recommended_entry': round((current_price + support) / 2, 2),
            'stop_loss': round(support * 0.97, 2),
            'target': round(resistance * 0.98, 2),
            'support': round(support, 2),
            'resistance': round(resistance, 2),
        }

    except Exception as e:
        print(f"  ⚠️ 스윙 {ticker}: {e}")
        return None


# ============================================================
# 장기 스캐너 (대형 배당주)
# ============================================================

def analyze_longterm(ticker: str) -> Optional[dict]:
    """장기 종목 분석 (3개월+ 보유)"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='1y')

        if hist.empty or len(hist) < 100:
            return None

        info = stock.info or {}
        current_price = float(hist['Close'].iloc[-1])

        # 시총 필터: $10B+ (대형주만)
        market_cap = info.get('marketCap', 0) or 0
        if market_cap < 10e9:
            return None

        # 장기 점수 계산
        score = 0.0

        # 시총 (대형주 보너스)
        if market_cap > 200e9:
            score += 25  # 메가캡
        elif market_cap > 100e9:
            score += 20
        elif market_cap > 50e9:
            score += 15
        else:
            score += 10

        # 배당 수익률 (핵심)
        div_yield = info.get('dividendYield', 0) or 0
        if div_yield > 0.04:
            score += 25  # 4%+ 고배당
        elif div_yield > 0.03:
            score += 20
        elif div_yield > 0.02:
            score += 15
        elif div_yield > 0.01:
            score += 10

        # P/E 비율 (저평가)
        pe = info.get('trailingPE', 0) or 0
        if 8 < pe < 15:
            score += 20  # 저평가
        elif 15 <= pe < 25:
            score += 15  # 적정
        elif 5 < pe <= 8:
            score += 10  # 너무 낮으면 주의

        # 1년 수익률
        if len(hist) >= 252:
            yearly_return = (hist['Close'].iloc[-1] / hist['Close'].iloc[0] - 1) * 100
            if yearly_return > 20:
                score += 15
            elif yearly_return > 10:
                score += 10
            elif yearly_return > 0:
                score += 5

        # 변동성 (낮을수록 좋음)
        volatility = hist['Close'].pct_change().std() * 100
        if volatility < 1.5:
            score += 15
        elif volatility < 2.5:
            score += 10

        if score < 40:
            return None

        # 52주 고/저가
        high_52w = hist['High'].max()
        low_52w = hist['Low'].min()

        return {
            'ticker': ticker,
            'category': 'longterm',
            'company_name': info.get('shortName', ticker),
            'current_price': round(current_price, 2),
            'market_cap': market_cap,
            'score': round(score, 1),
            'dividend_yield': round(div_yield * 100, 2) if div_yield and div_yield < 1 else round(div_yield, 2) if div_yield else 0,
            'pe_ratio': round(pe, 1) if pe else None,
            'sector': info.get('sector', 'N/A'),
            'recommended_entry': round(current_price * 0.97, 2),  # -3%
            'stop_loss': round(low_52w * 0.95, 2),
            'target': round(high_52w * 0.95, 2),
            'high_52w': round(high_52w, 2),
            'low_52w': round(low_52w, 2),
        }

    except Exception as e:
        print(f"  ⚠️ 장기 {ticker}: {e}")
        return None


# ============================================================
# AI 분석 (Gemini)
# ============================================================

def generate_recommendation_reason(result: dict) -> str:
    """AI 추천 이유 생성"""
    if not gemini_client:
        return f"{result['ticker']} - 점수 {result['score']}"

    category_kr = {
        'day_trade': '단타',
        'swing': '스윙',
        'longterm': '장기'
    }

    prompt = f"""
주식 추천 이유를 한국어로 2문장 이내로 작성해주세요.

종목: {result['ticker']} ({result.get('company_name', '')})
투자 유형: {category_kr.get(result['category'], '단타')}
현재가: ${result['current_price']}
점수: {result['score']}점
"""

    if result['category'] == 'day_trade':
        prompt += f"""
RSI: {result.get('rsi', 'N/A')}
거래량 급증: {result.get('volume_ratio', 1)}배
뉴스 점수: {result.get('news_score', 0)}
"""
    elif result['category'] == 'swing':
        prompt += f"""
RSI: {result.get('rsi', 'N/A')}
MACD: {result.get('macd_cross', 'neutral')}
20일선: ${result.get('ma20', 'N/A')}
"""
    else:  # longterm
        prompt += f"""
배당수익률: {result.get('dividend_yield', 0)}%
P/E: {result.get('pe_ratio', 'N/A')}
섹터: {result.get('sector', 'N/A')}
"""

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"  ⚠️ Gemini 오류: {e}")
        return f"{result['ticker']} 추천"


def calculate_split_entry(current_price: float, support: float, atr: float) -> list:
    """분할매수 제안"""
    if atr == 0:
        atr = current_price * 0.03

    return [
        {'price': round(current_price, 2), 'pct': 40, 'label': '현재가'},
        {'price': round(current_price - atr, 2), 'pct': 30, 'label': '1차 조정'},
        {'price': round(support, 2), 'pct': 30, 'label': '지지선'},
    ]


def calculate_rating(result: dict) -> tuple:
    """등급 계산"""
    score = result['score']

    if score >= 70:
        return '★★★', round(score / 30, 2)
    elif score >= 50:
        return '★★', round(score / 40, 2)
    else:
        return '★', round(score / 50, 2)


# ============================================================
# 결과 저장
# ============================================================

def save_scan_results(day_results: list, swing_results: list, long_results: list):
    """스캔 결과 저장"""
    # 각 카테고리별 TOP 5
    all_results = {
        'day_trade': sorted(day_results, key=lambda x: -x['score'])[:5],
        'swing': sorted(swing_results, key=lambda x: -x['score'])[:5],
        'longterm': sorted(long_results, key=lambda x: -x['score'])[:5],
    }

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO daily_scan_results (scan_date, results)
        VALUES (CURRENT_DATE, %s)
        ON CONFLICT (scan_date)
        DO UPDATE SET results = EXCLUDED.results, created_at = CURRENT_TIMESTAMP
    """, (json.dumps(all_results),))

    conn.commit()
    cur.close()
    conn.close()


def is_us_market_holiday() -> bool:
    """미국 증시 휴장일 체크"""
    from datetime import date
    today = date.today()

    if today.weekday() >= 5:
        return True

    holidays_2026 = [
        date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16),
        date(2026, 4, 3), date(2026, 5, 25), date(2026, 7, 3),
        date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25),
    ]

    return today in holidays_2026


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='전체 시장 스캐너 v2')
    parser.add_argument('--test', action='store_true', help='테스트 모드')
    parser.add_argument('--force', action='store_true', help='휴장일 무시')
    parser.add_argument('--type', choices=['all', 'day', 'swing', 'long'], default='all',
                        help='스캔 유형: all(전체), day(단타만), swing(스윙만), long(장기만)')
    args = parser.parse_args()

    scan_day = args.type in ['all', 'day']
    scan_swing = args.type in ['all', 'swing']
    scan_long = args.type in ['all', 'long']

    print("=" * 60)
    print("🔍 전체 시장 스캐너 v2")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if is_us_market_holiday() and not args.force:
        print("📅 미국 증시 휴장일 - 스캔 건너뜀")
        return

    init_tables()

    # ========== 1. 단타 스캔 (뉴스 핫 종목) ==========
    day_results = []
    if scan_day:
        print("\n🔥 [단타] 뉴스 핫 종목 스캔 중...")
        news_tickers = get_news_top_tickers(30)

        if not news_tickers:
            print("  ❌ 뉴스 데이터 없음")
        else:
            for item in news_tickers[:10] if args.test else news_tickers:
                ticker = item['ticker']
                result = analyze_day_trade(ticker, item['total_score'] or 0)
                if result:
                    # AI 분석 추가
                    result['recommendation_reason'] = generate_recommendation_reason(result)
                    rating, rr = calculate_rating(result)
                    result['rating'] = rating
                    result['rr_ratio'] = rr
                    result['split_entries'] = calculate_split_entry(
                        result['current_price'],
                        result['support'],
                        result['current_price'] * 0.03
                    )
                    day_results.append(result)
                time.sleep(0.3)
            print(f"  ✅ 단타 추천: {len(day_results)}개")
    else:
        print("\n⏭️ [단타] 스킵")

    # ========== 2. 스윙 스캔 (중형 성장주) ==========
    swing_results = []
    if scan_swing:
        print("\n⚖️ [스윙] 중형 성장주 스캔 중...")
        swing_pool = SWING_UNIVERSE[:15] if args.test else SWING_UNIVERSE

        for ticker in swing_pool:
            result = analyze_swing(ticker)
            if result:
                result['recommendation_reason'] = generate_recommendation_reason(result)
                rating, rr = calculate_rating(result)
                result['rating'] = rating
                result['rr_ratio'] = rr
                result['split_entries'] = calculate_split_entry(
                    result['current_price'],
                    result['support'],
                    result['current_price'] * 0.03
                )
                swing_results.append(result)
            time.sleep(0.3)
        print(f"  ✅ 스윙 추천: {len(swing_results)}개")
    else:
        print("\n⏭️ [스윙] 스킵")

    # ========== 3. 장기 스캔 (대형 배당주) ==========
    long_results = []
    if scan_long:
        print("\n🛡️ [장기] 대형 배당주 스캔 중...")
        long_pool = LONGTERM_UNIVERSE[:15] if args.test else LONGTERM_UNIVERSE

        for ticker in long_pool:
            result = analyze_longterm(ticker)
            if result:
                result['recommendation_reason'] = generate_recommendation_reason(result)
                rating, rr = calculate_rating(result)
                result['rating'] = rating
                result['rr_ratio'] = rr
                # 장기는 분할매수 다르게
                result['split_entries'] = [
                    {'price': result['current_price'], 'pct': 30, 'label': '1차 매수'},
                    {'price': round(result['current_price'] * 0.95, 2), 'pct': 40, 'label': '-5% 추가'},
                    {'price': round(result['current_price'] * 0.90, 2), 'pct': 30, 'label': '-10% 적극'},
                ]
                long_results.append(result)
            time.sleep(0.3)
        print(f"  ✅ 장기 추천: {len(long_results)}개")
    else:
        print("\n⏭️ [장기] 스킵")

    # ========== 4. 결과 저장 ==========
    save_scan_results(day_results, swing_results, long_results)
    print("\n💾 결과 저장 완료")

    # ========== 5. 결과 출력 ==========
    print("\n" + "=" * 60)

    print("\n🔥 단타 추천 TOP 5")
    print("-" * 60)
    for i, r in enumerate(sorted(day_results, key=lambda x: -x['score'])[:5], 1):
        print(f"  {i}. {r['ticker']:6} | 점수: {r['score']:5.1f} | "
              f"RSI: {r['rsi']:5.1f} | 거래량: {r['volume_ratio']:.1f}x | ${r['current_price']:.2f}")

    print("\n⚖️ 스윙 추천 TOP 5 (4-7일)")
    print("-" * 60)
    for i, r in enumerate(sorted(swing_results, key=lambda x: -x['score'])[:5], 1):
        print(f"  {i}. {r['ticker']:6} | 점수: {r['score']:5.1f} | "
              f"RSI: {r['rsi']:5.1f} | MACD: {r['macd_cross']:7} | ${r['current_price']:.2f}")

    print("\n🛡️ 장기 추천 TOP 5 (3개월+)")
    print("-" * 60)
    for i, r in enumerate(sorted(long_results, key=lambda x: -x['score'])[:5], 1):
        div = r.get('dividend_yield', 0)
        pe = r.get('pe_ratio', 0) or 0
        print(f"  {i}. {r['ticker']:6} | 점수: {r['score']:5.1f} | "
              f"배당: {div:.1f}% | P/E: {pe:.1f} | ${r['current_price']:.2f}")

    print("\n✅ 스캔 완료!")


if __name__ == '__main__':
    main()
