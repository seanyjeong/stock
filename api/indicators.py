"""
Technical Indicators API - 기술적 지표 (RSI, MACD)
pandas-ta 없이 직접 계산
"""
import yfinance as yf
import pandas as pd
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/indicators", tags=["indicators"])


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """RSI 계산"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD 계산"""
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


@router.get("/{ticker}")
async def get_indicators(ticker: str, period: str = "3mo"):
    """
    종목의 기술적 지표 조회

    - **RSI (14)**: 과매수(>70) / 과매도(<30) 판단
    - **MACD**: 추세 전환 신호

    Args:
        ticker: 종목 심볼 (예: AAPL, TSLA)
        period: 조회 기간 (1mo, 3mo, 6mo, 1y)
    """
    try:
        # yfinance로 데이터 가져오기
        stock = yf.Ticker(ticker.upper())
        df = stock.history(period=period)

        if df.empty:
            raise HTTPException(status_code=404, detail=f"종목 {ticker}를 찾을 수 없습니다")

        # 기술적 지표 계산
        df['RSI'] = calculate_rsi(df['Close'])
        df['MACD'], df['MACD_Signal'], df['MACD_Hist'] = calculate_macd(df['Close'])

        # 최신 값
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        # RSI 해석
        rsi_value = round(latest['RSI'], 1) if pd.notna(latest['RSI']) else None
        if rsi_value:
            if rsi_value >= 70:
                rsi_signal = "과매수"
                rsi_desc = "매도 고려 구간"
            elif rsi_value <= 30:
                rsi_signal = "과매도"
                rsi_desc = "매수 고려 구간"
            elif rsi_value >= 50:
                rsi_signal = "강세"
                rsi_desc = "상승 추세"
            else:
                rsi_signal = "약세"
                rsi_desc = "하락 추세"
        else:
            rsi_signal = None
            rsi_desc = None

        # MACD 해석
        macd_value = round(latest['MACD'], 3) if pd.notna(latest['MACD']) else None
        macd_signal_value = round(latest['MACD_Signal'], 3) if pd.notna(latest['MACD_Signal']) else None
        macd_hist = round(latest['MACD_Hist'], 3) if pd.notna(latest['MACD_Hist']) else None
        prev_hist = round(prev['MACD_Hist'], 3) if pd.notna(prev['MACD_Hist']) else None

        if macd_value and macd_signal_value:
            if macd_value > macd_signal_value:
                macd_trend = "상승"
                if prev_hist and macd_hist and prev_hist < 0 and macd_hist > 0:
                    macd_desc = "골든크로스 (매수 신호)"
                else:
                    macd_desc = "MACD가 시그널 위"
            else:
                macd_trend = "하락"
                if prev_hist and macd_hist and prev_hist > 0 and macd_hist < 0:
                    macd_desc = "데드크로스 (매도 신호)"
                else:
                    macd_desc = "MACD가 시그널 아래"
        else:
            macd_trend = None
            macd_desc = None

        return {
            "ticker": ticker.upper(),
            "current_price": round(latest['Close'], 2),
            "rsi": {
                "value": rsi_value,
                "signal": rsi_signal,
                "description": rsi_desc,
                "help": "RSI 70↑ 과매수(매도 고려), 30↓ 과매도(매수 고려)"
            },
            "macd": {
                "value": macd_value,
                "signal": macd_signal_value,
                "histogram": macd_hist,
                "trend": macd_trend,
                "description": macd_desc,
                "help": "MACD > Signal = 상승추세, 골든크로스 = 매수신호"
            },
            "period": period
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
