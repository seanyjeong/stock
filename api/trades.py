"""
매매 기록 API
"""
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from db import get_db
from api.auth import require_approved_user
from api.brokerage import get_user_commission_rate

router = APIRouter(prefix="/api/trades", tags=["trades"])


class TradeType(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TradeCreate(BaseModel):
    ticker: str
    trade_type: TradeType
    shares: float
    price: float
    note: Optional[str] = None


@router.get("/")
async def get_trades(
    ticker: Optional[str] = None,
    limit: int = 50,
    user: dict = Depends(require_approved_user)
):
    """매매 기록 조회"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 테이블 생성
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            trade_type VARCHAR(10) NOT NULL,
            shares DECIMAL(15, 4) NOT NULL,
            price DECIMAL(15, 4) NOT NULL,
            total_amount DECIMAL(15, 2) NOT NULL,
            commission DECIMAL(15, 4) DEFAULT 0,
            note TEXT,
            traded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    if ticker:
        cur.execute("""
            SELECT * FROM trades
            WHERE user_id = %s AND ticker = %s
            ORDER BY traded_at DESC
            LIMIT %s
        """, (user["id"], ticker.upper(), limit))
    else:
        cur.execute("""
            SELECT * FROM trades
            WHERE user_id = %s
            ORDER BY traded_at DESC
            LIMIT %s
        """, (user["id"], limit))

    trades = cur.fetchall()
    cur.close()
    conn.close()

    return {
        "trades": [
            {
                "id": t["id"],
                "ticker": t["ticker"],
                "trade_type": t["trade_type"],
                "shares": float(t["shares"]),
                "price": float(t["price"]),
                "total_amount": float(t["total_amount"]),
                "commission": float(t["commission"]) if t.get("commission") else 0,
                "note": t["note"],
                "traded_at": t["traded_at"].isoformat() if t["traded_at"] else None,
            }
            for t in trades
        ],
        "count": len(trades),
    }


@router.post("/")
async def create_trade(trade: TradeCreate, user: dict = Depends(require_approved_user)):
    """매매 기록 추가 + 포트폴리오 자동 업데이트"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 테이블 생성
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            trade_type VARCHAR(10) NOT NULL,
            shares DECIMAL(15, 4) NOT NULL,
            price DECIMAL(15, 4) NOT NULL,
            total_amount DECIMAL(15, 2) NOT NULL,
            commission DECIMAL(15, 4) DEFAULT 0,
            note TEXT,
            traded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
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

    ticker = trade.ticker.upper().strip()
    total_amount = trade.shares * trade.price

    # 수수료 계산
    commission_rate = get_user_commission_rate(user["id"])
    commission = round(total_amount * commission_rate, 4)

    # 현재 보유 현황 확인
    cur.execute(
        "SELECT id, shares, avg_cost FROM user_holdings WHERE user_id = %s AND ticker = %s",
        (user["id"], ticker)
    )
    holding = cur.fetchone()

    if trade.trade_type == TradeType.BUY:
        # 매수: 평단 재계산
        if holding:
            old_shares = float(holding["shares"])
            old_avg = float(holding["avg_cost"])
            new_shares = old_shares + trade.shares
            new_avg = (old_shares * old_avg + trade.shares * trade.price) / new_shares
            cur.execute("""
                UPDATE user_holdings SET shares = %s, avg_cost = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (new_shares, round(new_avg, 4), holding["id"]))
        else:
            cur.execute("""
                INSERT INTO user_holdings (user_id, ticker, shares, avg_cost)
                VALUES (%s, %s, %s, %s)
            """, (user["id"], ticker, trade.shares, trade.price))

    elif trade.trade_type == TradeType.SELL:
        # 매도: 보유 수량 확인
        if not holding:
            cur.close()
            conn.close()
            raise HTTPException(status_code=400, detail=f"{ticker}을(를) 보유하고 있지 않습니다")

        old_shares = float(holding["shares"])
        if trade.shares > old_shares:
            cur.close()
            conn.close()
            raise HTTPException(status_code=400, detail=f"보유 수량({old_shares}주)보다 많이 매도할 수 없습니다")

        new_shares = old_shares - trade.shares
        if new_shares <= 0:
            # 전량 매도: 삭제
            cur.execute("DELETE FROM user_holdings WHERE id = %s", (holding["id"],))
        else:
            # 일부 매도: 수량만 감소 (평단 유지)
            cur.execute("""
                UPDATE user_holdings SET shares = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (new_shares, holding["id"]))

    # 매매 기록 저장
    cur.execute("""
        INSERT INTO trades (user_id, ticker, trade_type, shares, price, total_amount, commission, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
    """, (user["id"], ticker, trade.trade_type.value, trade.shares, trade.price, total_amount, commission, trade.note))

    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    action = "매수" if trade.trade_type == TradeType.BUY else "매도"
    return {
        "message": f"{ticker} {trade.shares}주 {action} 완료 (수수료: ${commission:.2f})",
        "trade": {
            "id": result["id"],
            "ticker": result["ticker"],
            "trade_type": result["trade_type"],
            "shares": float(result["shares"]),
            "price": float(result["price"]),
            "total_amount": float(result["total_amount"]),
            "commission": float(result["commission"]) if result.get("commission") else 0,
        }
    }


@router.delete("/{trade_id}")
async def delete_trade(trade_id: int, user: dict = Depends(require_approved_user)):
    """매매 기록 삭제"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        "SELECT id, ticker FROM trades WHERE id = %s AND user_id = %s",
        (trade_id, user["id"])
    )
    trade = cur.fetchone()

    if not trade:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")

    cur.execute("DELETE FROM trades WHERE id = %s", (trade_id,))
    conn.commit()
    cur.close()
    conn.close()

    return {"message": "기록 삭제됨", "trade_id": trade_id}


@router.get("/summary")
async def get_trade_summary(user: dict = Depends(require_approved_user)):
    """매매 요약 (종목별 실현손익)"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            trade_type VARCHAR(10) NOT NULL,
            shares DECIMAL(15, 4) NOT NULL,
            price DECIMAL(15, 4) NOT NULL,
            total_amount DECIMAL(15, 2) NOT NULL,
            commission DECIMAL(15, 4) DEFAULT 0,
            note TEXT,
            traded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # 종목별 매수/매도 합계
    cur.execute("""
        SELECT
            ticker,
            SUM(CASE WHEN trade_type = 'buy' THEN shares ELSE 0 END) as bought_shares,
            SUM(CASE WHEN trade_type = 'buy' THEN total_amount ELSE 0 END) as bought_amount,
            SUM(CASE WHEN trade_type = 'sell' THEN shares ELSE 0 END) as sold_shares,
            SUM(CASE WHEN trade_type = 'sell' THEN total_amount ELSE 0 END) as sold_amount,
            SUM(COALESCE(commission, 0)) as total_commission
        FROM trades
        WHERE user_id = %s
        GROUP BY ticker
        ORDER BY ticker
    """, (user["id"],))

    summaries = cur.fetchall()
    cur.close()
    conn.close()

    results = []
    total_realized = 0.0
    total_commission = 0.0

    for s in summaries:
        bought = float(s["bought_amount"]) if s["bought_amount"] else 0
        sold = float(s["sold_amount"]) if s["sold_amount"] else 0
        bought_shares = float(s["bought_shares"]) if s["bought_shares"] else 0
        sold_shares = float(s["sold_shares"]) if s["sold_shares"] else 0
        commission = float(s["total_commission"]) if s["total_commission"] else 0

        # 실현 손익 계산 (매도금액 - 매도비율만큼의 매수금액 - 수수료)
        if sold_shares > 0 and bought_shares > 0:
            avg_buy_price = bought / bought_shares
            realized = sold - (sold_shares * avg_buy_price) - commission
        else:
            realized = 0

        total_realized += realized
        total_commission += commission

        results.append({
            "ticker": s["ticker"],
            "bought_shares": bought_shares,
            "bought_amount": round(bought, 2),
            "sold_shares": sold_shares,
            "sold_amount": round(sold, 2),
            "commission": round(commission, 2),
            "realized_gain": round(realized, 2),
        })

    return {
        "summaries": results,
        "total_realized_gain": round(total_realized, 2),
        "total_commission": round(total_commission, 2),
    }
