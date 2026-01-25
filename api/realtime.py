"""
하이브리드 실시간 주가 API
- 정규장(KST 23:30~06:00): Finnhub 실시간 (10초 캐싱)
- 장외(프리/애프터/마감): yfinance 장외가격 (10분 캐싱)
- /realtime/prices?tickers=AAPL,TSLA (Finnhub only)
- /realtime/hybrid?tickers=AAPL,TSLA (자동 선택)
"""
import os
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx
import yfinance as yf
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/realtime", tags=["realtime"])

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

# 캐시: {ticker: {"price": float, "timestamp": float}}
_price_cache: dict[str, dict] = {}
_yfinance_cache: dict[str, dict] = {}
CACHE_TTL = 10  # Finnhub 10초 캐싱
YFINANCE_CACHE_TTL = 600  # yfinance 10분 캐싱


def get_market_status() -> dict:
    """
    현재 미국 시장 상태 반환 (KST 기준)
    - premarket: 18:00~23:30 KST (04:00~09:30 ET)
    - regular: 23:30~06:00 KST (09:30~16:00 ET)
    - afterhours: 06:00~10:00 KST (16:00~20:00 ET)
    - closed: 10:00~18:00 KST (20:00~04:00 ET)
    """
    kst = ZoneInfo("Asia/Seoul")
    now = datetime.now(kst)
    hour = now.hour
    minute = now.minute
    time_minutes = hour * 60 + minute
    weekday = now.weekday()  # 0=월, 6=일

    # 주말은 closed
    if weekday >= 5:
        return {"status": "closed", "is_regular": False, "label": "주말"}

    # KST 시간 구간 (분 단위)
    premarket_start = 18 * 60  # 18:00
    regular_start = 23 * 60 + 30  # 23:30
    regular_end = 6 * 60  # 06:00 (다음날)
    afterhours_end = 10 * 60  # 10:00

    if time_minutes >= premarket_start and time_minutes < regular_start:
        return {"status": "premarket", "is_regular": False, "label": "프리마켓"}
    elif time_minutes >= regular_start or time_minutes < regular_end:
        return {"status": "regular", "is_regular": True, "label": "정규장"}
    elif time_minutes >= regular_end and time_minutes < afterhours_end:
        return {"status": "afterhours", "is_regular": False, "label": "애프터"}
    else:
        return {"status": "closed", "is_regular": False, "label": "장마감"}


def fetch_yfinance_extended(ticker: str) -> dict | None:
    """yfinance에서 장외가격 포함 시세 조회"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # 현재가 (정규장 종가)
        regular_price = info.get("regularMarketPrice") or info.get("currentPrice")

        # 장외가격
        pre_price = info.get("preMarketPrice")
        post_price = info.get("postMarketPrice")

        # 시장 상태에 따라 현재가 선택
        market = get_market_status()
        if market["status"] == "premarket" and pre_price:
            current = pre_price
            source = "premarket"
        elif market["status"] == "afterhours" and post_price:
            current = post_price
            source = "afterhours"
        elif market["status"] == "closed":
            # 장 마감/주말: 가장 최근 가격 사용 (애프터 > 정규)
            if post_price:
                current = post_price
                source = "afterhours"
            else:
                current = regular_price
                source = "regular"
        else:
            current = regular_price
            source = "regular"

        if not current:
            return None

        prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
        change = current - prev_close if prev_close else None
        change_pct = (change / prev_close * 100) if prev_close and change else None

        return {
            "current": current,
            "regular_price": regular_price,
            "pre_price": pre_price,
            "post_price": post_price,
            "previous_close": prev_close,
            "change": round(change, 2) if change else None,
            "change_pct": round(change_pct, 2) if change_pct else None,
            "source": source,
        }
    except Exception as e:
        logger.error(f"yfinance request failed for {ticker}: {e}")
        return None


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


@router.get("/hybrid")
async def get_hybrid_prices(tickers: str):
    """
    하이브리드 가격 조회 (정규장: Finnhub, 장외: yfinance)

    Query: tickers=AAPL,TSLA,NVDA (쉼표 구분)

    Response:
    {
        "prices": {
            "AAPL": {"current": 185.5, "source": "afterhours", ...},
        },
        "market_status": {"status": "afterhours", "is_regular": false, "label": "애프터"},
        "price_source": "yfinance"
    }
    """
    if not tickers:
        raise HTTPException(status_code=400, detail="tickers parameter required")

    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="No valid tickers provided")

    if len(ticker_list) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 tickers allowed")

    market = get_market_status()
    result = {}
    now = time.time()

    if market["is_regular"]:
        # 정규장: Finnhub 사용
        for ticker in ticker_list:
            # 캐시 확인
            if ticker in _price_cache:
                cache_entry = _price_cache[ticker]
                if now - cache_entry["timestamp"] < CACHE_TTL:
                    result[ticker] = {**cache_entry["data"], "source": "regular"}
                    continue

            quote = await fetch_finnhub_quote(ticker)
            if quote and quote.get("current"):
                quote["source"] = "regular"
                _price_cache[ticker] = {"data": quote, "timestamp": now}
                result[ticker] = quote

        return {
            "prices": result,
            "market_status": market,
            "price_source": "finnhub",
            "cache_ttl": CACHE_TTL,
            "is_realtime": True,
        }
    else:
        # 장외: yfinance 사용
        for ticker in ticker_list:
            # 캐시 확인
            if ticker in _yfinance_cache:
                cache_entry = _yfinance_cache[ticker]
                if now - cache_entry["timestamp"] < YFINANCE_CACHE_TTL:
                    result[ticker] = cache_entry["data"]
                    continue

            quote = fetch_yfinance_extended(ticker)
            if quote and quote.get("current"):
                _yfinance_cache[ticker] = {"data": quote, "timestamp": now}
                result[ticker] = quote

        return {
            "prices": result,
            "market_status": market,
            "price_source": "yfinance",
            "cache_ttl": YFINANCE_CACHE_TTL,
            "is_realtime": False,
        }


@router.get("/market-status")
async def get_current_market_status():
    """현재 미국 시장 상태 조회"""
    return get_market_status()


def is_us_dst() -> bool:
    """미국 섬머타임(DST) 여부 확인"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    now_et = datetime.now(et)

    # DST 적용 중이면 utcoffset이 -4시간, 아니면 -5시간
    offset_hours = now_et.utcoffset().total_seconds() / 3600
    return offset_hours == -4


def get_dst_transition_warning() -> dict | None:
    """섬머타임 전환 임박 경고 (7일 전부터)"""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    year = now.year

    # 섬머타임 시작: 3월 두 번째 일요일
    march_1 = datetime(year, 3, 1, tzinfo=et)
    days_until_sunday = (6 - march_1.weekday()) % 7
    dst_start = march_1 + timedelta(days=days_until_sunday + 7)  # 두 번째 일요일

    # 섬머타임 종료: 11월 첫 번째 일요일
    nov_1 = datetime(year, 11, 1, tzinfo=et)
    days_until_sunday = (6 - nov_1.weekday()) % 7
    dst_end = nov_1 + timedelta(days=days_until_sunday)

    # 7일 이내 전환 체크
    for transition, label, action in [
        (dst_start, "섬머타임 시작", "cron 시간을 1시간 앞당기세요 (22:30→21:30)"),
        (dst_end, "섬머타임 종료", "cron 시간을 1시간 늦추세요 (21:30→22:30)")
    ]:
        days_left = (transition - now).days
        if 0 <= days_left <= 7:
            return {
                "warning": True,
                "event": label,
                "date": transition.strftime("%Y-%m-%d"),
                "days_left": days_left,
                "action": action,
            }

    return None


@router.get("/dst-status")
async def get_dst_status():
    """섬머타임 상태 및 전환 경고"""
    is_dst = is_us_dst()
    warning = get_dst_transition_warning()

    return {
        "is_dst": is_dst,
        "timezone_offset": "-04:00 (EDT)" if is_dst else "-05:00 (EST)",
        "kst_market_open": "22:30" if is_dst else "23:30",
        "kst_market_close": "05:00" if is_dst else "06:00",
        "transition_warning": warning,
    }
