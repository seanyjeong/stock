"""
Finnhub 실시간 주가 API
- 10초 캐싱으로 API 제한(60콜/분) 회피
- /realtime/prices?tickers=AAPL,TSLA
"""
import os
import time
import logging
import httpx
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/realtime", tags=["realtime"])

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

# 캐시: {ticker: {"price": float, "timestamp": float}}
_price_cache: dict[str, dict] = {}
CACHE_TTL = 10  # 10초 캐싱


async def fetch_finnhub_quote(ticker: str) -> dict | None:
    """Finnhub에서 실시간 시세 조회"""
    if not FINNHUB_API_KEY:
        logger.error("FINNHUB_API_KEY not set")
        return None

    url = f"{FINNHUB_BASE_URL}/quote"
    params = {"symbol": ticker, "token": FINNHUB_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                # c: current, pc: previous close, h: high, l: low, o: open
                return {
                    "current": data.get("c"),
                    "previous_close": data.get("pc"),
                    "high": data.get("h"),
                    "low": data.get("l"),
                    "open": data.get("o"),
                    "change": data.get("d"),
                    "change_pct": data.get("dp"),
                }
            else:
                logger.warning(f"Finnhub error for {ticker}: {resp.status_code}")
                return None
    except Exception as e:
        logger.error(f"Finnhub request failed for {ticker}: {e}")
        return None


@router.get("/prices")
async def get_realtime_prices(tickers: str):
    """
    실시간 가격 조회 (캐싱 적용)

    Query: tickers=AAPL,TSLA,NVDA (쉼표 구분)

    Response:
    {
        "prices": {
            "AAPL": {"current": 185.5, "change_pct": 1.2, ...},
            "TSLA": {"current": 245.0, "change_pct": -0.5, ...}
        },
        "cached": ["AAPL"],  # 캐시에서 반환된 종목
        "fetched": ["TSLA"]  # 새로 조회한 종목
    }
    """
    if not tickers:
        raise HTTPException(status_code=400, detail="tickers parameter required")

    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="No valid tickers provided")

    if len(ticker_list) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 tickers allowed")

    result = {}
    cached = []
    fetched = []
    now = time.time()

    for ticker in ticker_list:
        # 캐시 확인
        if ticker in _price_cache:
            cache_entry = _price_cache[ticker]
            if now - cache_entry["timestamp"] < CACHE_TTL:
                result[ticker] = cache_entry["data"]
                cached.append(ticker)
                continue

        # Finnhub 조회
        quote = await fetch_finnhub_quote(ticker)
        if quote and quote.get("current"):
            _price_cache[ticker] = {
                "data": quote,
                "timestamp": now
            }
            result[ticker] = quote
            fetched.append(ticker)
        else:
            # 조회 실패 시 캐시 데이터 반환 (있으면)
            if ticker in _price_cache:
                result[ticker] = _price_cache[ticker]["data"]
                cached.append(ticker)

    return {
        "prices": result,
        "cached": cached,
        "fetched": fetched,
        "cache_ttl": CACHE_TTL
    }


@router.get("/quote/{ticker}")
async def get_single_quote(ticker: str):
    """단일 종목 실시간 시세"""
    ticker = ticker.upper()
    now = time.time()

    # 캐시 확인
    if ticker in _price_cache:
        cache_entry = _price_cache[ticker]
        if now - cache_entry["timestamp"] < CACHE_TTL:
            return {
                "ticker": ticker,
                **cache_entry["data"],
                "cached": True
            }

    # Finnhub 조회
    quote = await fetch_finnhub_quote(ticker)
    if not quote or not quote.get("current"):
        raise HTTPException(status_code=404, detail=f"Quote not found for {ticker}")

    _price_cache[ticker] = {
        "data": quote,
        "timestamp": now
    }

    return {
        "ticker": ticker,
        **quote,
        "cached": False
    }
