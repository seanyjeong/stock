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

# deep_analyzer에서 핵심 함수 import
from deep_analyzer import (
    get_short_history,
    get_ftd_data,
    check_regsho,
    get_borrow_data,
    get_options_data,
    get_sector_news,
    get_biotech_catalysts,
    get_automotive_catalysts,
    get_retail_catalysts,
    get_financial_catalysts,
    get_industrial_catalysts,
    get_realestate_catalysts,
    get_institutional_changes,
    get_peer_comparison,
)
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
    """단타 종목 분석 (숏스퀴즈 지표 포함)"""
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

        # ========== 숏스퀴즈 지표 (deep_analyzer 연동) ==========
        squeeze_score = 0
        squeeze_signals = []

        # 1. Short Interest 체크
        try:
            short_data = get_short_history(ticker)
            short_float = info.get('shortPercentOfFloat', 0) or 0
            if short_float > 0.20:  # 20%+ SI
                squeeze_score += 15
                squeeze_signals.append(f"SI {short_float*100:.1f}%")
            elif short_float > 0.10:  # 10%+ SI
                squeeze_score += 10
                squeeze_signals.append(f"SI {short_float*100:.1f}%")

            # SI 급증 체크
            if short_data.get('change_30d'):
                change = short_data['change_30d']
                if isinstance(change, str) and '+' in change:
                    pct = float(change.replace('%', '').replace('+', ''))
                    if pct > 50:
                        squeeze_score += 10
                        squeeze_signals.append("SI 급증")
        except:
            pass

        # 2. FTD 체크
        try:
            ftd = get_ftd_data(ticker)
            if ftd.get('total_ftd', 0) > 100000:
                squeeze_score += 10
                squeeze_signals.append(f"FTD {ftd['total_ftd']/1e6:.1f}M")
        except:
            pass

        # 3. RegSHO 체크 (대박 신호!)
        try:
            if check_regsho(ticker):
                squeeze_score += 20
                squeeze_signals.append("RegSHO 🔥")
        except:
            pass

        # 4. Borrow Rate 체크
        try:
            borrow = get_borrow_data(ticker)
            if borrow.get('zero_borrow'):
                squeeze_score += 15
                squeeze_signals.append("Zero Borrow 🔥")
            elif borrow.get('rate') and float(borrow['rate'].replace('%', '')) > 50:
                squeeze_score += 10
                squeeze_signals.append(f"Borrow {borrow['rate']}")
        except:
            pass

        # 단타 점수 계산
        score = 0.0

        # ========== 단타 점수 (기술적 요인 80% 이상) ==========

        # 1. 거래량 급증 (35점 - 핵심!)
        if volume_ratio > 5:
            score += 35
        elif volume_ratio > 3:
            score += 30
        elif volume_ratio > 2:
            score += 25
        elif volume_ratio > 1.5:
            score += 15

        # 2. RSI 반등 구간 (30점)
        if 30 <= rsi <= 45:
            score += 30  # 반등 초기 = 최적
        elif 25 <= rsi < 30:
            score += 25  # 과매도 탈출
        elif 45 < rsi <= 60:
            score += 20  # 상승 중
        elif rsi < 25:
            score += 10  # 너무 과매도 (위험)

        # 3. MACD 크로스 (30점)
        if macd_cross == 'golden':
            score += 30  # 골든크로스 = 강력
        elif macd_val > signal_val and macd_val > 0:
            score += 20  # MACD 양수 전환
        elif macd_val > signal_val:
            score += 10  # 상승 시작

        # 4. 볼린저/ATR 변동성 (15점) - 단타에 중요
        atr_pct = (atr / current_price) * 100 if current_price > 0 else 0
        if 3 <= atr_pct <= 8:
            score += 15  # 적절한 변동성
        elif 2 <= atr_pct < 3:
            score += 10  # 조금 낮음
        elif atr_pct > 8:
            score += 5   # 너무 변동적

        # 5. 뉴스 점수 (10점 - 단타는 기술적 요인이 더 중요)
        if news_score > 10:
            score += 10
        elif news_score > 5:
            score += 7
        elif news_score > 0:
            score += 5

        # 6. 숏스퀴즈 보너스 (추가 점수)
        score += squeeze_score

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
            # 숏스퀴즈 데이터 추가
            'squeeze_score': squeeze_score,
            'squeeze_signals': squeeze_signals,
            # 매수/매도 전략
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
    """스윙 종목 분석 (4-7일 보유) - 섹터 촉매 + 옵션 분석"""
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

        # ========== 섹터 촉매 분석 (스윙 핵심) ==========
        catalyst_score = 0
        catalyst_signals = []
        sector = info.get('sector', '')
        industry = info.get('industry', '')
        company_name = info.get('shortName', ticker)

        try:
            # 섹터별 뉴스 체크
            sector_news = get_sector_news(ticker, sector, industry)
            if sector_news.get('sector_specific'):
                news_count = len(sector_news['sector_specific'])
                if news_count >= 3:
                    catalyst_score += 15
                    catalyst_signals.append(f"{sector_news.get('source', '')} 뉴스 {news_count}건")

            # 섹터별 촉매 체크
            industry_lower = (industry or "").lower()
            sector_lower = (sector or "").lower()

            if "biotech" in industry_lower or "pharma" in industry_lower:
                catalysts = get_biotech_catalysts(ticker, company_name)
                if catalysts.get('fast_track') or catalysts.get('breakthrough'):
                    catalyst_score += 20
                    catalyst_signals.append("FDA 지정 🔥")
                if catalysts.get('clinical_trials'):
                    catalyst_score += 10
                    catalyst_signals.append(f"임상 {len(catalysts['clinical_trials'])}건")
            elif "auto" in industry_lower:
                catalysts = get_automotive_catalysts(ticker, company_name)
                if catalysts.get('ev_credits'):
                    catalyst_score += 10
                    catalyst_signals.append("EV 세액공제")
            elif "bank" in industry_lower or "financial" in sector_lower:
                catalysts = get_financial_catalysts(ticker, company_name)
                if catalysts.get('dividend_update'):
                    catalyst_score += 10
                    catalyst_signals.append("배당 뉴스")
        except:
            pass

        # ========== 옵션 Max Pain 분석 ==========
        max_pain = None
        options_signal = None
        try:
            options_data = get_options_data(stock)
            if options_data.get('max_pain'):
                max_pain = options_data['max_pain']
                # 현재가가 Max Pain 아래면 상승 가능성
                if current_price < max_pain * 0.95:
                    catalyst_score += 15
                    options_signal = f"Max Pain ${max_pain:.2f} (현재가 아래)"
                elif current_price > max_pain * 1.05:
                    catalyst_score -= 5  # 하락 압력
                    options_signal = f"Max Pain ${max_pain:.2f} (현재가 위)"
        except:
            pass

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

        # 촉매 보너스
        score += catalyst_score

        if score < 40:
            return None

        support, resistance = calculate_support_resistance(hist)

        # 스윙 매수가는 더 여유있게 (-5% vs 단타 -2%)
        return {
            'ticker': ticker,
            'category': 'swing',
            'company_name': company_name,
            'sector': sector,
            'industry': industry,
            'current_price': round(current_price, 2),
            'market_cap': info.get('marketCap', 0),
            'score': round(score, 1),
            'rsi': round(rsi, 1),
            'macd_cross': macd_cross,
            'ma20': round(ma20, 2),
            # 촉매 데이터
            'catalyst_score': catalyst_score,
            'catalyst_signals': catalyst_signals,
            'max_pain': round(max_pain, 2) if max_pain else None,
            'options_signal': options_signal,
            # 매수가 더 여유있게 (스윙은 -5%)
            'recommended_entry': round(current_price * 0.95, 2),
            'stop_loss': round(support * 0.95, 2),  # 지지선 -5%
            'target': round(resistance * 0.95, 2),  # 저항선 근처
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
    """장기 종목 분석 (3개월+ 보유) - 연속 점수 체계"""
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

        # 52주 고/저가
        high_52w = hist['High'].max()
        low_52w = hist['Low'].min()

        # === 연속 점수 체계 (0~100) ===
        score = 0.0
        score_breakdown = {}

        # 1. 배당 수익률 (0~25점) - 핵심 지표
        div_yield = info.get('dividendYield', 0) or 0
        if div_yield > 0:
            div_score = min(25, div_yield * 100 * 5)  # 5% → 25점
        else:
            div_score = 0
        score += div_score
        score_breakdown['dividend'] = round(div_score, 1)

        # 2. P/E 비율 (0~20점) - 10~20이 최적
        pe = info.get('trailingPE', 0) or 0
        if 10 <= pe <= 20:
            pe_score = 20
        elif 5 < pe < 10:
            pe_score = 15 - (10 - pe)  # 5→10, 10→15
        elif 20 < pe <= 30:
            pe_score = 20 - (pe - 20)  # 20→20, 30→10
        elif pe > 30:
            pe_score = max(0, 10 - (pe - 30) * 0.5)
        else:
            pe_score = 0
        score += pe_score
        score_breakdown['pe'] = round(pe_score, 1)

        # 3. 52주 고점 대비 위치 (0~20점) - 저점 매수 기회
        range_52w = high_52w - low_52w
        if range_52w > 0:
            position = (current_price - low_52w) / range_52w  # 0=저점, 1=고점
            # 0.3~0.5 구간이 최적 (저점 근처지만 반등 중)
            if 0.2 <= position <= 0.5:
                position_score = 20
            elif position < 0.2:
                position_score = 15  # 너무 저점 (위험)
            elif 0.5 < position <= 0.7:
                position_score = 15
            else:
                position_score = 10 - (position - 0.7) * 20  # 고점 근처 감점
            position_score = max(0, position_score)
        else:
            position_score = 10
        score += position_score
        score_breakdown['position'] = round(position_score, 1)

        # 4. 1년 수익률 (0~15점)
        yearly_return = (hist['Close'].iloc[-1] / hist['Close'].iloc[0] - 1) * 100
        if yearly_return >= 0:
            return_score = min(15, yearly_return * 0.5)  # 30% → 15점
        else:
            return_score = max(0, 10 + yearly_return * 0.3)  # -33% → 0점
        score += return_score
        score_breakdown['return'] = round(return_score, 1)

        # 5. 변동성 (0~10점) - 낮을수록 좋음
        volatility = hist['Close'].pct_change().std() * 100
        vol_score = max(0, 10 - volatility * 3)  # 3% → 1점
        score += vol_score
        score_breakdown['volatility'] = round(vol_score, 1)

        # 6. 연속 배당 여부 (0~10점)
        div_rate = info.get('dividendRate', 0) or 0
        payout = info.get('payoutRatio', 0) or 0
        if div_rate > 0 and 0.2 < payout < 0.8:
            payout_score = 10  # 건전한 배당
        elif div_rate > 0:
            payout_score = 5
        else:
            payout_score = 0
        score += payout_score
        score_breakdown['payout'] = round(payout_score, 1)

        # ========== 기관 분석 (장기 핵심) ==========
        institutional_pct = None
        institutional_signal = None
        try:
            inst_data = get_institutional_changes(stock)
            if inst_data.get('institutional_percent'):
                pct_str = inst_data['institutional_percent']
                if isinstance(pct_str, str):
                    institutional_pct = float(pct_str.replace('%', ''))
                else:
                    institutional_pct = float(pct_str)

                # 기관 보유 60%+ = 신뢰도 높음
                if institutional_pct > 60:
                    score += 10
                    institutional_signal = f"기관 {institutional_pct:.0f}% 보유 (신뢰도 높음)"
                elif institutional_pct > 40:
                    score += 5
                    institutional_signal = f"기관 {institutional_pct:.0f}% 보유"
        except:
            pass

        # ========== 동종업체 비교 ==========
        relative_value = None
        try:
            peer_data = get_peer_comparison(stock, ticker)
            if peer_data.get('relative_valuation'):
                relative_value = peer_data['relative_valuation']
                if '저평가' in relative_value:
                    score += 10
                elif '고평가' in relative_value:
                    score -= 5
        except:
            pass

        score_breakdown['institutional'] = 10 if institutional_pct and institutional_pct > 60 else 5 if institutional_pct and institutional_pct > 40 else 0

        if score < 35:
            return None

        return {
            'ticker': ticker,
            'category': 'longterm',
            'company_name': info.get('shortName', ticker),
            'current_price': round(current_price, 2),
            'market_cap': market_cap,
            'score': round(score, 1),
            'score_breakdown': score_breakdown,
            'dividend_yield': round(div_yield * 100, 2) if div_yield and div_yield < 1 else round(div_yield, 2) if div_yield else 0,
            'pe_ratio': round(pe, 1) if pe else None,
            'yearly_return': round(yearly_return, 1),
            'position_52w': round((current_price - low_52w) / range_52w * 100, 0) if range_52w > 0 else 50,
            'sector': info.get('sector', 'N/A'),
            # 기관 데이터
            'institutional_pct': institutional_pct,
            'institutional_signal': institutional_signal,
            'relative_valuation': relative_value,
            # 장기는 매수가 더 여유있게 (-10% 분할매수)
            'recommended_entry': round(current_price * 0.90, 2),  # -10%
            'split_entry_2': round(current_price * 0.85, 2),  # -15%
            'stop_loss': round(low_52w * 0.90, 2),  # 52주 저점 -10%
            'target': round(high_52w * 0.90, 2),
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
