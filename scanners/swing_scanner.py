"""
scanners/swing_scanner.py - 스윙 스캐너

기술적 과매도 중형주 + 섹터 촉매 + 옵션 분석

점수 체계 (0-100):
| 항목          | max | 기준                              |
|--------------|-----|----------------------------------|
| RSI 과매도    | 25  | 25-40=25, 40-55=15, <25=10       |
| MACD 크로스   | 20  | 골든=20, 시그널위=10              |
| MA 위치       | 20  | MA20 돌파=20, 지지=15, 50일위=10  |
| 촉매          | 25  | 섹터뉴스+FDA+옵션 (cap 25)        |
| Max Pain     | 10  | 현재가<MP=10, 위=-5              |
| 합계          | 100 |                                   |
"""

from typing import Optional

import yfinance as yf
import pandas as pd
import numpy as np

from lib import (
    get_sector_news,
    get_biotech_catalysts,
    get_automotive_catalysts,
    get_financial_catalysts,
    get_options_data,
)


def _calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    result = float(rsi.iloc[-1]) if len(rsi) > 0 else 50.0
    if pd.isna(result) or np.isinf(result):
        return 50.0
    return result


def _calculate_macd(prices: pd.Series) -> tuple:
    if len(prices) < 26:
        return 0.0, 0.0, 'neutral'
    exp1 = prices.ewm(span=12, adjust=False).mean()
    exp2 = prices.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    macd_val = float(macd.iloc[-1])
    signal_val = float(signal.iloc[-1])

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


def _calculate_support_resistance(hist: pd.DataFrame) -> tuple:
    if len(hist) < 20:
        close = float(hist['Close'].iloc[-1])
        return close * 0.95, close * 1.05
    lows = hist['Low'].tail(20)
    highs = hist['High'].tail(20)
    return float(lows.min()), float(highs.max())


def analyze(ticker: str) -> Optional[dict]:
    """스윙 종목 분석 (4-7일 보유) - 섹터 촉매 + 옵션 분석

    Returns:
        분석 결과 dict 또는 None
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='3mo')

        if hist.empty or len(hist) < 30:
            return None

        info = stock.info or {}
        current_price = (
            info.get('currentPrice')
            or info.get('regularMarketPrice')
            or float(hist['Close'].iloc[-1])
        )
        current_price = float(current_price)

        if current_price < 5:
            return None

        # 기술적 지표
        rsi = _calculate_rsi(hist['Close'])
        macd_val, signal_val, macd_cross = _calculate_macd(hist['Close'])

        # 이동평균
        ma20 = float(hist['Close'].rolling(20).mean().iloc[-1])
        ma50 = float(hist['Close'].rolling(50).mean().iloc[-1]) if len(hist) >= 50 else ma20

        # ========== 섹터 촉매 분석 ==========
        catalyst_score = 0
        catalyst_signals = []
        sector = info.get('sector', '')
        industry = info.get('industry', '')
        company_name = info.get('shortName', ticker)

        try:
            sector_news = get_sector_news(ticker, sector, industry)
            if sector_news.get('sector_specific'):
                news_count = len(sector_news['sector_specific'])
                if news_count >= 3:
                    catalyst_score += 15
                    catalyst_signals.append(f"{sector_news.get('source', '')} 뉴스 {news_count}건")

            industry_lower = (industry or "").lower()
            sector_lower = (sector or "").lower()

            if "biotech" in industry_lower or "pharma" in industry_lower:
                catalysts = get_biotech_catalysts(ticker, company_name)
                if catalysts.get('fast_track') or catalysts.get('breakthrough'):
                    catalyst_score += 20
                    catalyst_signals.append("FDA 지정")
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
        except Exception:
            pass

        # cap catalyst at 25
        catalyst_score = min(catalyst_score, 25)

        # ========== 옵션 Max Pain ==========
        max_pain = None
        options_signal = None
        max_pain_score = 0
        try:
            options_data = get_options_data(stock)
            if options_data.get('max_pain'):
                max_pain = options_data['max_pain']
                if current_price < max_pain * 0.95:
                    max_pain_score = 10
                    options_signal = f"Max Pain ${max_pain:.2f} (현재가 아래)"
                elif current_price > max_pain * 1.05:
                    max_pain_score = -5
                    options_signal = f"Max Pain ${max_pain:.2f} (현재가 위)"
        except Exception:
            pass

        # ========== 스윙 점수 계산 (0-100) ==========
        score = 0.0

        # 1. RSI 과매도 (max 25)
        if 25 <= rsi <= 40:
            score += 25
        elif 40 < rsi <= 55:
            score += 15
        elif rsi < 25:
            score += 10

        # 2. MACD 크로스 (max 20)
        if macd_cross == 'golden':
            score += 20
        elif macd_val > signal_val:
            score += 10

        # 3. MA 위치 (max 20)
        if current_price > ma20 and current_price < ma20 * 1.05:
            score += 20  # MA20 돌파 직후
        elif current_price > ma20 * 0.95 and current_price <= ma20:
            score += 15  # MA20 지지 테스트
        elif current_price > ma50:
            score += 10  # 50일선 위

        # 4. 촉매 (max 25, already capped)
        score += catalyst_score

        # 5. Max Pain (max 10)
        score += max_pain_score

        # 하한 클램프
        score = max(score, 0)

        if score < 30:
            return None

        support, resistance = _calculate_support_resistance(hist)

        return {
            'ticker': ticker,
            'category': 'swing',
            'company_name': company_name,
            'sector': sector,
            'industry': industry,
            'current_price': round(current_price, 2),
            'market_cap': info.get('marketCap', 0),
            'score': round(min(score, 100), 1),
            'rsi': round(rsi, 1),
            'macd_cross': macd_cross,
            'ma20': round(ma20, 2),
            'catalyst_score': catalyst_score,
            'catalyst_signals': catalyst_signals,
            'max_pain': round(max_pain, 2) if max_pain else None,
            'options_signal': options_signal,
            'recommended_entry': round(current_price * 0.95, 2),
            'stop_loss': round(support * 0.95, 2),
            'target': round(resistance * 0.95, 2),
            'support': round(support, 2),
            'resistance': round(resistance, 2),
        }

    except Exception as e:
        print(f"  스윙 {ticker}: {e}")
        return None
