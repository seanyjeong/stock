"""
Watchlist API - 관심 종목 관리
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from db import get_db
from api.auth import get_current_user

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


# Pydantic models
class WatchlistAdd(BaseModel):
    ticker: str
    note: str | None = None
    target_price: float | None = None
    alert_price: float | None = None


class WatchlistUpdate(BaseModel):
    note: str | None = None
    target_price: float | None = None
    alert_price: float | None = None


_table_initialized = False

def ensure_watchlist_table():
    """watchlist 테이블이 없으면 생성 (lazy initialization)"""
    global _table_initialized
    if _table_initialized:
        return

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_watchlist (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                ticker VARCHAR(20) NOT NULL,
                note TEXT,
                target_price DECIMAL(12, 4),
                alert_price DECIMAL(12, 4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, ticker)
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        _table_initialized = True
    except Exception:
        # users 테이블이 없으면 나중에 다시 시도
        pass


@router.get("/")
async def get_watchlist(user: dict = Depends(get_current_user)):
    """사용자의 관심 종목 목록 조회 (현재가 포함)"""
    ensure_watchlist_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # 관심 종목 조회
        cur.execute("""
            SELECT id, ticker, note, target_price, alert_price, created_at
            FROM user_watchlist
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user["id"],))
        watchlist = cur.fetchall()

        if not watchlist:
            return {"watchlist": [], "total_count": 0}

        # 현재가 조회 (DB에서 먼저)
        tickers = [item["ticker"] for item in watchlist]
        cur.execute("""
            SELECT DISTINCT ON (ticker)
                ticker, regular_price, afterhours_price, premarket_price, collected_at
            FROM stock_prices
            WHERE ticker = ANY(%s)
            ORDER BY ticker, collected_at DESC
        """, (tickers,))
        prices = {row["ticker"]: row for row in cur.fetchall()}

        # 회사명 조회
        cur.execute("""
            SELECT ticker, company_name FROM ticker_info WHERE ticker = ANY(%s)
        """, (tickers,))
        company_names = {row["ticker"]: row["company_name"] for row in cur.fetchall()}

        # DB에 없는 종목은 yfinance로 실시간 조회
        missing_tickers = [t for t in tickers if t not in prices]
        if missing_tickers:
            import yfinance as yf
            for ticker in missing_tickers:
                try:
                    stock = yf.Ticker(ticker)
                    info = stock.fast_info
                    prices[ticker] = {
                        "ticker": ticker,
                        "regular_price": getattr(info, 'last_price', None) or getattr(info, 'previous_close', None),
                        "afterhours_price": None,
                        "premarket_price": None,
                        "collected_at": None
                    }
                except Exception:
                    pass

        # 결과 병합
        result = []
        for item in watchlist:
            ticker = item["ticker"]
            price_data = prices.get(ticker, {})

            # 현재가 결정 (afterhours > premarket > regular)
            current_price = None
            if price_data:
                current_price = (
                    float(price_data["afterhours_price"]) if price_data.get("afterhours_price")
                    else float(price_data["premarket_price"]) if price_data.get("premarket_price")
                    else float(price_data["regular_price"]) if price_data.get("regular_price")
                    else None
                )

            # 목표가 대비 계산
            target_diff_pct = None
            if item["target_price"] and current_price:
                target_diff_pct = round((float(item["target_price"]) - current_price) / current_price * 100, 1)

            result.append({
                "id": item["id"],
                "ticker": ticker,
                "company_name": company_names.get(ticker),
                "note": item["note"],
                "target_price": float(item["target_price"]) if item["target_price"] else None,
                "alert_price": float(item["alert_price"]) if item["alert_price"] else None,
                "current_price": current_price,
                "regular_price": float(price_data["regular_price"]) if price_data.get("regular_price") else None,
                "afterhours_price": float(price_data["afterhours_price"]) if price_data.get("afterhours_price") else None,
                "premarket_price": float(price_data["premarket_price"]) if price_data.get("premarket_price") else None,
                "target_diff_pct": target_diff_pct,
                "created_at": item["created_at"].isoformat() if item["created_at"] else None,
            })

        return {"watchlist": result, "total_count": len(result)}
    finally:
        cur.close()
        conn.close()


@router.post("/")
async def add_to_watchlist(data: WatchlistAdd, user: dict = Depends(get_current_user)):
    """관심 종목 추가"""
    ensure_watchlist_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            INSERT INTO user_watchlist (user_id, ticker, note, target_price, alert_price)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, ticker) DO UPDATE SET
                note = EXCLUDED.note,
                target_price = EXCLUDED.target_price,
                alert_price = EXCLUDED.alert_price
            RETURNING id, ticker, note, target_price, alert_price, created_at
        """, (user["id"], data.ticker.upper(), data.note, data.target_price, data.alert_price))

        result = cur.fetchone()
        conn.commit()

        return {
            "success": True,
            "watchlist_item": {
                "id": result["id"],
                "ticker": result["ticker"],
                "note": result["note"],
                "target_price": float(result["target_price"]) if result["target_price"] else None,
                "alert_price": float(result["alert_price"]) if result["alert_price"] else None,
                "created_at": result["created_at"].isoformat() if result["created_at"] else None,
            }
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.put("/{item_id}")
async def update_watchlist_item(item_id: int, data: WatchlistUpdate, user: dict = Depends(get_current_user)):
    """관심 종목 수정"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            UPDATE user_watchlist
            SET note = %s, target_price = %s, alert_price = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, ticker, note, target_price, alert_price
        """, (data.note, data.target_price, data.alert_price, item_id, user["id"]))

        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="관심 종목을 찾을 수 없습니다")

        conn.commit()
        return {"success": True, "watchlist_item": result}
    finally:
        cur.close()
        conn.close()


@router.delete("/{item_id}")
async def remove_from_watchlist(item_id: int, user: dict = Depends(get_current_user)):
    """관심 종목 삭제"""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            DELETE FROM user_watchlist
            WHERE id = %s AND user_id = %s
            RETURNING id
        """, (item_id, user["id"]))

        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="관심 종목을 찾을 수 없습니다")

        conn.commit()
        return {"success": True, "deleted_id": item_id}
    finally:
        cur.close()
        conn.close()


@router.delete("/ticker/{ticker}")
async def remove_by_ticker(ticker: str, user: dict = Depends(get_current_user)):
    """티커로 관심 종목 삭제"""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            DELETE FROM user_watchlist
            WHERE ticker = %s AND user_id = %s
            RETURNING id
        """, (ticker.upper(), user["id"]))

        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="관심 종목을 찾을 수 없습니다")

        conn.commit()
        return {"success": True, "ticker": ticker.upper()}
    finally:
        cur.close()
        conn.close()
