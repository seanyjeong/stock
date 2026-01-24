"""
캔들스틱 차트 API
- OHLCV 데이터 + RSI/MACD 시계열
"""
from fastapi import APIRouter, HTTPException
import yfinance as yf
import pandas as pd
from .indicators import calculate_rsi, calculate_macd
from db import get_db
from psycopg2.extras import RealDictCursor

router = APIRouter(prefix="/api/chart", tags=["chart"])


def get_company_name(ticker: str) -> str | None:
    """DB에서 회사명 조회"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT company_name FROM ticker_info WHERE ticker = %s", (ticker.upper(),))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row["company_name"] if row else None
    except:
        return None


@router.get("/{ticker}")
async def get_chart_data(ticker: str, period: str = "3mo", interval: str = "1d"):
    """
    캔들스틱 차트 데이터 + 기술적 지표 시계열

    Args:
        ticker: 종목 심볼
        period: 조회 기간 (1mo, 3mo, 6mo, 1y)
        interval: 봉 간격 (1d, 1h, 15m)

    Returns:
        - candles: OHLCV 데이터 (lightweight-charts 형식)
        - rsi: RSI 시계열
        - macd: MACD/Signal/Histogram 시계열
    """
    try:
        stock = yf.Ticker(ticker.upper())
        df = stock.history(period=period, interval=interval)

        if df.empty:
            raise HTTPException(status_code=404, detail=f"종목 {ticker}를 찾을 수 없습니다")

        # 인덱스를 타임스탬프로 변환
        df = df.reset_index()
        df['time'] = df['Date'].apply(lambda x: int(x.timestamp()) if hasattr(x, 'timestamp') else int(pd.Timestamp(x).timestamp()))

        # 기술적 지표 계산
        df['RSI'] = calculate_rsi(df['Close'])
        df['MACD'], df['MACD_Signal'], df['MACD_Hist'] = calculate_macd(df['Close'])

        # lightweight-charts 형식으로 변환
        candles = []
        rsi_data = []
        macd_data = []

        for _, row in df.iterrows():
            time = row['time']

            # 캔들스틱 데이터
            candles.append({
                "time": time,
                "open": round(row['Open'], 2),
                "high": round(row['High'], 2),
                "low": round(row['Low'], 2),
                "close": round(row['Close'], 2),
                "volume": int(row['Volume']) if pd.notna(row['Volume']) else 0
            })

            # RSI 데이터
            if pd.notna(row['RSI']):
                rsi_data.append({
                    "time": time,
                    "value": round(row['RSI'], 1)
                })

            # MACD 데이터
            if pd.notna(row['MACD']):
                macd_data.append({
                    "time": time,
                    "macd": round(row['MACD'], 3),
                    "signal": round(row['MACD_Signal'], 3) if pd.notna(row['MACD_Signal']) else None,
                    "histogram": round(row['MACD_Hist'], 3) if pd.notna(row['MACD_Hist']) else None
                })

        # 최신 지표 요약
        latest = df.iloc[-1]
        current_price = round(latest['Close'], 2)
        rsi_value = round(latest['RSI'], 1) if pd.notna(latest['RSI']) else None

        return {
            "ticker": ticker.upper(),
            "company_name": get_company_name(ticker),
            "current_price": current_price,
            "period": period,
            "interval": interval,
            "candles": candles,
            "rsi": rsi_data,
            "macd": macd_data,
            "summary": {
                "rsi": rsi_value,
                "rsi_signal": "과매수" if rsi_value and rsi_value >= 70 else ("과매도" if rsi_value and rsi_value <= 30 else "중립"),
                "macd": round(latest['MACD'], 3) if pd.notna(latest['MACD']) else None,
                "macd_signal": round(latest['MACD_Signal'], 3) if pd.notna(latest['MACD_Signal']) else None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
