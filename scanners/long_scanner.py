"""
scanners/long_scanner.py - 장기 스캐너

S&P 500 대형 배당주 대상, 연속 점수 체계

점수 체계 (0-100):
| 항목          | max | 기준                              |
|--------------|-----|----------------------------------|
| 배당 수익률    | 25  | 5%→25점 (연속)                    |
| P/E 비율      | 20  | 10-20=20, 5-10=15, 20-30=10      |
| 52주 위치     | 20  | 0.2-0.5=20 (저점 반등중)           |
| 1년 수익률    | 15  | 30%→15점                         |
| 변동성         | 10  | 낮을수록 좋음                      |
| 배당 건전성    | 10  | payout 0.2-0.8=10                |
| 합계          | 100 |                                   |

+ 기관/동종업체 보너스 (최대 +20)
"""

from typing import Optional

import yfinance as yf
import pandas as pd

from lib import get_institutional_changes, get_peer_comparison
from lib.base import get_stop_cap


def _calculate_atr(hist: pd.DataFrame, period: int = 14) -> float:
    """ATR (Average True Range) 계산"""
    if len(hist) < period + 1:
        return float(hist['High'].iloc[-1] - hist['Low'].iloc[-1])
    high = hist['High']
    low = hist['Low']
    close = hist['Close'].shift(1)
    tr = pd.concat([high - low, abs(high - close), abs(low - close)], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean().iloc[-1]
    return float(atr) if not pd.isna(atr) else float(hist['High'].iloc[-1] - hist['Low'].iloc[-1])


def _calculate_smart_entry(current_price: float, support: float, atr: float, style: str = 'long') -> float:
    """지지선 + ATR 기반 매수가 계산"""
    support_distance_pct = (current_price - support) / current_price * 100
    atr_factors = {'day': 0.3, 'swing': 0.5, 'long': 0.7}
    atr_factor = atr_factors.get(style, 0.7)
    atr_entry = current_price - (atr * atr_factor)
    buffer_pct = {'day': 0.01, 'swing': 0.02, 'long': 0.03}
    support_entry = support * (1 + buffer_pct.get(style, 0.03))

    if support_distance_pct <= 7:  # 장기는 지지선 7% 이내
        entry = support_entry
    else:
        entry = atr_entry

    min_entry = current_price * 0.90  # 장기는 10% 눌림까지 허용
    entry = max(entry, min_entry)
    entry = min(entry, current_price * 0.98)
    return round(entry, 2)


def analyze(ticker: str) -> Optional[dict]:
    """장기 종목 분석 (3개월+ 보유) - 연속 점수 체계

    Returns:
        분석 결과 dict 또는 None
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='1y')

        if hist.empty or len(hist) < 100:
            return None

        info = stock.info or {}
        from lib.base import get_extended_price
        current_price, price_source = get_extended_price(
            info, float(hist['Close'].iloc[-1])
        )
        if not current_price:
            return None

        # 시총 필터: $10B+
        market_cap = info.get('marketCap', 0) or 0
        if market_cap < 10e9:
            return None

        # 52주 고/저가
        high_52w = float(hist['High'].max())
        low_52w = float(hist['Low'].min())

        # ATR 계산 (매수가 계산용)
        atr = _calculate_atr(hist)
        # 장기는 52주 저점을 지지선으로 사용
        support = low_52w

        # === 연속 점수 체계 (0~100) ===
        score = 0.0
        score_breakdown = {}

        # 1. 배당 수익률 (0~25점) — yfinance dividendYield는 이미 % (0.42 = 0.42%)
        div_yield = info.get('dividendYield', 0) or 0
        div_score = min(25, div_yield * 5) if div_yield > 0 else 0
        score += div_score
        score_breakdown['dividend'] = round(div_score, 1)

        # 2. P/E 비율 (0~20점)
        pe = info.get('trailingPE', 0) or 0
        if 10 <= pe <= 20:
            pe_score = 20
        elif 5 < pe < 10:
            pe_score = 15 - (10 - pe)
        elif 20 < pe <= 30:
            pe_score = 20 - (pe - 20)
        elif pe > 30:
            pe_score = max(0, 10 - (pe - 30) * 0.5)
        else:
            pe_score = 0
        score += pe_score
        score_breakdown['pe'] = round(pe_score, 1)

        # 3. 52주 고점 대비 위치 (0~20점)
        range_52w = high_52w - low_52w
        if range_52w > 0:
            position = (current_price - low_52w) / range_52w
            if 0.2 <= position <= 0.5:
                position_score = 20
            elif position < 0.2:
                position_score = 15
            elif 0.5 < position <= 0.7:
                position_score = 15
            else:
                position_score = max(0, 10 - (position - 0.7) * 20)
        else:
            position_score = 10
        score += position_score
        score_breakdown['position'] = round(position_score, 1)

        # 4. 1년 수익률 (0~15점)
        yearly_return = (hist['Close'].iloc[-1] / hist['Close'].iloc[0] - 1) * 100
        if yearly_return >= 0:
            return_score = min(15, yearly_return * 0.5)
        else:
            return_score = max(0, 10 + yearly_return * 0.3)
        score += return_score
        score_breakdown['return'] = round(return_score, 1)

        # 5. 변동성 (0~10점) - 낮을수록 좋음
        volatility = hist['Close'].pct_change().std() * 100
        vol_score = max(0, 10 - volatility * 3)
        score += vol_score
        score_breakdown['volatility'] = round(vol_score, 1)

        # 6. 배당 건전성 (0~10점)
        div_rate = info.get('dividendRate', 0) or 0
        payout = info.get('payoutRatio', 0) or 0
        if div_rate > 0 and 0.2 < payout < 0.8:
            payout_score = 10
        elif div_rate > 0:
            payout_score = 5
        else:
            payout_score = 0
        score += payout_score
        score_breakdown['payout'] = round(payout_score, 1)

        # ========== 기관 분석 보너스 ==========
        institutional_pct = None
        institutional_signal = None
        try:
            inst_data = get_institutional_changes(stock)
            if inst_data.get('institutional_percent'):
                pct_str = inst_data['institutional_percent']
                institutional_pct = float(str(pct_str).replace('%', ''))

                if institutional_pct > 60:
                    score += 10
                    institutional_signal = f"기관 {institutional_pct:.0f}% 보유 (신뢰도 높음)"
                elif institutional_pct > 40:
                    score += 5
                    institutional_signal = f"기관 {institutional_pct:.0f}% 보유"
        except Exception:
            pass

        # ========== 동종업체 비교 보너스 ==========
        relative_value = None
        try:
            peer_data = get_peer_comparison(stock, ticker)
            if peer_data.get('relative_valuation'):
                relative_value = peer_data['relative_valuation']
                if '저평가' in relative_value:
                    score += 10
                elif '고평가' in relative_value:
                    score -= 5
        except Exception:
            pass

        score_breakdown['institutional'] = (
            10 if institutional_pct and institutional_pct > 60
            else 5 if institutional_pct and institutional_pct > 40
            else 0
        )

        score = max(score, 0)

        if score < 35:
            return None

        return {
            'ticker': ticker,
            'category': 'longterm',
            'company_name': info.get('shortName', ticker),
            'current_price': round(current_price, 2),
            'price_source': price_source,
            'market_cap': market_cap,
            'score': round(min(score, 100), 1),
            'score_breakdown': score_breakdown,
            'dividend_yield': round(div_yield, 2) if div_yield else 0,
            'pe_ratio': round(pe, 1) if pe else None,
            'yearly_return': round(float(yearly_return), 1),
            'position_52w': round((current_price - low_52w) / range_52w * 100, 0) if range_52w > 0 else 50,
            'sector': info.get('sector', 'N/A'),
            'institutional_pct': institutional_pct,
            'institutional_signal': institutional_signal,
            'relative_valuation': relative_value,
            'recommended_entry': _calculate_smart_entry(current_price, support, atr, 'long'),
            'split_entry_2': round(current_price * 0.85, 2),
            'stop_loss': round(max(low_52w * 0.90, current_price * (1 - get_stop_cap('long'))), 2),
            'target': round(high_52w * 0.90, 2),
            'high_52w': round(high_52w, 2),
            'low_52w': round(low_52w, 2),
        }

    except Exception as e:
        print(f"  장기 {ticker}: {e}")
        return None
