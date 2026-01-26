"""
scanners/day_scanner.py - 단타 스캐너

뉴스 핫 종목 + 소형주 대상, 숏스퀴즈 지표 포함

점수 체계 (0-100):
| 항목          | max | 기준                              |
|--------------|-----|----------------------------------|
| 거래량 급증    | 25  | >5x=25, >3x=20, >2x=15, >1.5x=10 |
| RSI 반등      | 20  | 30-45=20, 25-30=15, 45-60=10      |
| MACD 크로스   | 15  | 골든=15, 양수전환=10, 시그널위=5    |
| ATR 변동성    | 10  | 3-8%=10, 2-3%=7, >8%=3           |
| 뉴스          | 5   | >10점=5, >5점=3, >0점=1           |
| 숏스퀴즈      | 25  | SI+RegSHO+ZB+FTD (cap 25)        |
| 합계          | 100 |                                   |
"""

from typing import Optional

import yfinance as yf
import pandas as pd
import numpy as np

from lib import get_short_history, get_ftd_data, check_regsho, get_borrow_data


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


def _calculate_atr(hist: pd.DataFrame, period: int = 14) -> float:
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


def _calculate_support_resistance(hist: pd.DataFrame) -> tuple:
    if len(hist) < 20:
        close = float(hist['Close'].iloc[-1])
        return close * 0.95, close * 1.05
    lows = hist['Low'].tail(20)
    highs = hist['High'].tail(20)
    return float(lows.min()), float(highs.max())


def analyze(ticker: str, news_score: float) -> Optional[dict]:
    """단타 종목 분석 (숏스퀴즈 지표 포함)

    Returns:
        분석 결과 dict 또는 None (필터 통과 못 하면)
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='1mo')

        if hist.empty or len(hist) < 10:
            return None

        info = stock.info or {}
        current_price = (
            info.get('currentPrice')
            or info.get('regularMarketPrice')
            or float(hist['Close'].iloc[-1])
        )
        current_price = float(current_price)

        # 가격 필터: $0.50 ~ $100 (단타용, 나노캡 포함)
        if current_price < 0.5 or current_price > 100:
            return None

        # 시총 필터: $1M ~ $2B (나노~소형주)
        market_cap = info.get('marketCap', 0) or 0
        if market_cap < 1e6 or market_cap > 2e9:
            return None

        # 기술적 지표
        rsi = _calculate_rsi(hist['Close'])
        macd_val, signal_val, macd_cross = _calculate_macd(hist['Close'])
        atr = _calculate_atr(hist)

        # 거래량 급증 체크
        vol_avg = hist['Volume'].tail(10).mean()
        vol_today = hist['Volume'].iloc[-1]
        volume_ratio = float(vol_today / vol_avg) if vol_avg > 0 else 1.0

        # ========== 숏스퀴즈 지표 (lib/ 연동) ==========
        squeeze_score = 0
        squeeze_signals = []

        # 1. Short Interest
        try:
            short_data = get_short_history(ticker)
            short_float = info.get('shortPercentOfFloat', 0) or 0
            if short_float > 0.20:
                squeeze_score += 10
                squeeze_signals.append(f"SI {short_float*100:.1f}%")
            elif short_float > 0.10:
                squeeze_score += 5
                squeeze_signals.append(f"SI {short_float*100:.1f}%")

            # SI 급증 체크
            if short_data.get('change_30d'):
                change = short_data['change_30d']
                if isinstance(change, str) and '+' in change:
                    pct = float(change.replace('%', '').replace('+', ''))
                    if pct > 50:
                        squeeze_score += 5
                        squeeze_signals.append("SI 급증")
        except Exception:
            pass

        # 2. FTD
        try:
            ftd = get_ftd_data(ticker)
            if ftd.get('total_ftd', 0) > 100000:
                squeeze_score += 5
                squeeze_signals.append(f"FTD {ftd['total_ftd']/1e6:.1f}M")
        except Exception:
            pass

        # 3. RegSHO (대박 신호!)
        try:
            regsho = check_regsho(ticker)
            if regsho.get("listed"):
                squeeze_score += 10
                squeeze_signals.append("RegSHO")
        except Exception:
            pass

        # 4. Borrow Rate
        try:
            borrow = get_borrow_data(ticker)
            if borrow.get('is_zero_borrow'):
                squeeze_score += 10
                squeeze_signals.append("Zero Borrow")
            elif borrow.get('borrow_rate') and borrow['borrow_rate'] > 50:
                squeeze_score += 5
                squeeze_signals.append(f"Borrow {borrow['borrow_rate']:.0f}%")
        except Exception:
            pass

        # cap 25
        squeeze_score = min(squeeze_score, 25)

        # ========== 단타 점수 계산 (0-100) ==========
        score = 0.0

        # 1. 거래량 급증 (max 25)
        if volume_ratio > 5:
            score += 25
        elif volume_ratio > 3:
            score += 20
        elif volume_ratio > 2:
            score += 15
        elif volume_ratio > 1.5:
            score += 10

        # 2. RSI 반등 (max 20)
        if 30 <= rsi <= 45:
            score += 20
        elif 25 <= rsi < 30:
            score += 15
        elif 45 < rsi <= 60:
            score += 10

        # 3. MACD 크로스 (max 15)
        if macd_cross == 'golden':
            score += 15
        elif macd_val > signal_val and macd_val > 0:
            score += 10
        elif macd_val > signal_val:
            score += 5

        # 4. ATR 변동성 (max 10)
        atr_pct = (atr / current_price) * 100 if current_price > 0 else 0
        if 3 <= atr_pct <= 8:
            score += 10
        elif 2 <= atr_pct < 3:
            score += 7
        elif atr_pct > 8:
            score += 3

        # 5. 뉴스 (max 5)
        if news_score > 10:
            score += 5
        elif news_score > 5:
            score += 3
        elif news_score > 0:
            score += 1

        # 6. 숏스퀴즈 (max 25, already capped)
        score += squeeze_score

        if score < 30:
            return None

        support, resistance = _calculate_support_resistance(hist)

        return {
            'ticker': ticker,
            'category': 'day_trade',
            'company_name': info.get('shortName', ticker),
            'sector': info.get('sector', ''),
            'industry': info.get('industry', ''),
            'current_price': round(current_price, 2),
            'market_cap': market_cap,
            'score': round(min(score, 100), 1),
            'rsi': round(rsi, 1),
            'macd_cross': macd_cross,
            'volume_ratio': round(volume_ratio, 2),
            'news_score': news_score,
            'squeeze_score': squeeze_score,
            'squeeze_signals': squeeze_signals,
            'recommended_entry': round(current_price * 0.98, 2),
            'stop_loss': round(current_price - (atr * 1.5), 2),
            'target': round(current_price * 1.08, 2),
            'support': round(support, 2),
            'resistance': round(resistance, 2),
        }

    except Exception as e:
        print(f"  단타 {ticker}: {e}")
        return None
