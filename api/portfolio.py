"""
포트폴리오 CRUD API
"""
import os
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from db import get_db
from api.auth import require_approved_user

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class HoldingCreate(BaseModel):
    ticker: str
    shares: float
    avg_cost: float


class HoldingUpdate(BaseModel):
    shares: Optional[float] = None
    avg_cost: Optional[float] = None


class TickerSearchResult(BaseModel):
    symbol: str
    name: str
    exchange: str


def create_portfolio_table():
    """user_holdings 테이블 생성"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_holdings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ticker VARCHAR(10) NOT NULL,
            shares DECIMAL(15, 4) NOT NULL,
            avg_cost DECIMAL(15, 4) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, ticker)
        );
        CREATE INDEX IF NOT EXISTS idx_user_holdings_user ON user_holdings(user_id);
    """)
    conn.commit()
    cur.close()
    conn.close()


@router.get("/search")
async def search_ticker(q: str):
    """티커 검색 (Yahoo Finance API)"""
    if not q or len(q) < 1:
        return {"results": []}

    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://query1.finance.yahoo.com/v1/finance/search",
                params={
                    "q": q.upper(),
                    "quotesCount": 10,
                    "newsCount": 0,
                    "enableFuzzyQuery": False,
                    "quotesQueryId": "tss_match_phrase_query",
                },
                headers={
                    "User-Agent": "Mozilla/5.0",
                },
                timeout=5.0,
            )

        if response.status_code != 200:
            return {"results": []}

        data = response.json()
        quotes = data.get("quotes", [])

        results = []
        for quote in quotes:
            # 주식만 필터링 (ETF, 펀드 제외 옵션)
            if quote.get("quoteType") in ["EQUITY", "ETF"]:
                results.append({
                    "symbol": quote.get("symbol", ""),
                    "name": quote.get("shortname") or quote.get("longname", ""),
                    "exchange": quote.get("exchange", ""),
                    "type": quote.get("quoteType", ""),
                })

        return {"results": results}
    except Exception as e:
        return {"results": [], "error": str(e)}


@router.get("/my")
async def get_my_portfolio(user: dict = Depends(require_approved_user)):
    """내 포트폴리오 조회"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 테이블이 없으면 생성
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_holdings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            shares DECIMAL(15, 4) NOT NULL,
            avg_cost DECIMAL(15, 4) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, ticker)
        )
    """)
    conn.commit()

    cur.execute("""
        SELECT id, ticker, shares, avg_cost, created_at, updated_at
        FROM user_holdings
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (user["id"],))
    holdings = cur.fetchall()

    # 현재가 조회
    if holdings:
        tickers = [h["ticker"] for h in holdings]
        cur.execute("""
            SELECT DISTINCT ON (ticker)
                ticker, regular_price, afterhours_price, premarket_price
            FROM stock_prices
            WHERE ticker = ANY(%s)
            ORDER BY ticker, collected_at DESC
        """, (tickers,))
        prices = {row["ticker"]: row for row in cur.fetchall()}
    else:
        prices = {}

    # 환율 조회
    cur.execute("SELECT rate FROM exchange_rates ORDER BY collected_at DESC LIMIT 1")
    rate_row = cur.fetchone()
    exchange_rate = float(rate_row["rate"]) if rate_row else 1450.0

    cur.close()
    conn.close()

    # 결과 계산
    total_value = 0.0
    total_cost = 0.0
    result = []

    for h in holdings:
        ticker = h["ticker"]
        shares = float(h["shares"])
        avg_cost = float(h["avg_cost"])

        # 현재가
        regular_price = None
        afterhours_price = None
        premarket_price = None

        if ticker in prices:
            p = prices[ticker]
            regular_price = float(p["regular_price"]) if p["regular_price"] else None
            afterhours_price = float(p["afterhours_price"]) if p["afterhours_price"] else None
            premarket_price = float(p["premarket_price"]) if p["premarket_price"] else None
            current_price = afterhours_price or premarket_price or regular_price or 0
        else:
            current_price = 0

        value = shares * current_price
        cost = shares * avg_cost
        gain = value - cost
        gain_pct = (gain / cost * 100) if cost > 0 else 0

        total_value += value
        total_cost += cost

        result.append({
            "id": h["id"],
            "ticker": ticker,
            "shares": shares,
            "avg_cost": avg_cost,
            "current_price": current_price,
            "regular_price": regular_price,
            "afterhours_price": afterhours_price,
            "premarket_price": premarket_price,
            "value": round(value, 2),
            "gain": round(gain, 2),
            "gain_pct": round(gain_pct, 1),
        })

    total_gain = total_value - total_cost
    total_gain_pct = (total_gain / total_cost * 100) if total_cost > 0 else 0

    return {
        "holdings": result,
        "total": {
            "value_usd": round(total_value, 2),
            "value_krw": round(total_value * exchange_rate, 0),
            "cost_usd": round(total_cost, 2),
            "gain_usd": round(total_gain, 2),
            "gain_pct": round(total_gain_pct, 1),
        },
        "exchange_rate": exchange_rate,
    }


@router.post("/holdings")
async def add_holding(holding: HoldingCreate, user: dict = Depends(require_approved_user)):
    """보유 종목 추가"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 테이블 확인
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_holdings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            shares DECIMAL(15, 4) NOT NULL,
            avg_cost DECIMAL(15, 4) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, ticker)
        )
    """)
    conn.commit()

    ticker = holding.ticker.upper().strip()

    # 중복 확인
    cur.execute(
        "SELECT id FROM user_holdings WHERE user_id = %s AND ticker = %s",
        (user["id"], ticker)
    )
    if cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail=f"{ticker}는 이미 포트폴리오에 있습니다")

    # 추가
    cur.execute("""
        INSERT INTO user_holdings (user_id, ticker, shares, avg_cost)
        VALUES (%s, %s, %s, %s)
        RETURNING id, ticker, shares, avg_cost
    """, (user["id"], ticker, holding.shares, holding.avg_cost))

    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return {
        "message": f"{ticker} 추가됨",
        "holding": {
            "id": result["id"],
            "ticker": result["ticker"],
            "shares": float(result["shares"]),
            "avg_cost": float(result["avg_cost"]),
        }
    }


@router.put("/holdings/{holding_id}")
async def update_holding(
    holding_id: int,
    update: HoldingUpdate,
    user: dict = Depends(require_approved_user)
):
    """보유 종목 수정"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 소유권 확인
    cur.execute(
        "SELECT id, ticker FROM user_holdings WHERE id = %s AND user_id = %s",
        (holding_id, user["id"])
    )
    holding = cur.fetchone()

    if not holding:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    # 업데이트
    updates = []
    values = []
    if update.shares is not None:
        updates.append("shares = %s")
        values.append(update.shares)
    if update.avg_cost is not None:
        updates.append("avg_cost = %s")
        values.append(update.avg_cost)

    if not updates:
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="수정할 내용이 없습니다")

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(holding_id)

    cur.execute(
        f"UPDATE user_holdings SET {', '.join(updates)} WHERE id = %s RETURNING *",
        values
    )
    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return {
        "message": f"{holding['ticker']} 수정됨",
        "holding": {
            "id": result["id"],
            "ticker": result["ticker"],
            "shares": float(result["shares"]),
            "avg_cost": float(result["avg_cost"]),
        }
    }


@router.delete("/holdings/{holding_id}")
async def delete_holding(holding_id: int, user: dict = Depends(require_approved_user)):
    """보유 종목 삭제"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 소유권 확인
    cur.execute(
        "SELECT id, ticker FROM user_holdings WHERE id = %s AND user_id = %s",
        (holding_id, user["id"])
    )
    holding = cur.fetchone()

    if not holding:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    cur.execute("DELETE FROM user_holdings WHERE id = %s", (holding_id,))
    conn.commit()
    cur.close()
    conn.close()

    return {"message": f"{holding['ticker']} 삭제됨", "holding_id": holding_id}
