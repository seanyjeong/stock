"""
증권사 설정 + 달러 잔고 API
"""
from typing import Optional, List
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from db import get_db
from api.auth import require_approved_user

router = APIRouter(prefix="/api/brokerage", tags=["brokerage"])

# 증권사 목록 (앱 레벨 상수)
BROKERAGES = {
    "키움증권": 0.0025,
    "미래에셋증권": 0.0025,
    "삼성증권": 0.0025,
    "NH투자증권": 0.0025,
    "한국투자증권": 0.0025,
    "토스증권": 0.0010,
    "KB증권": 0.0025,
    "기타": 0.0025,
}


class BrokerageSettingsUpdate(BaseModel):
    brokerage_name: str


class CashTransactionCreate(BaseModel):
    transaction_type: str  # 'deposit' or 'withdraw'
    amount: float
    note: Optional[str] = None


def _ensure_tables(cur, conn):
    """테이블 생성 (lazy init)"""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_brokerage_settings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE,
            brokerage_name VARCHAR(50) NOT NULL DEFAULT '키움증권',
            commission_rate DECIMAL(6, 4) NOT NULL DEFAULT 0.0025,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cash_transactions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            transaction_type VARCHAR(20) NOT NULL,
            amount DECIMAL(15, 2) NOT NULL,
            note TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cash_tx_user ON cash_transactions(user_id)
    """)
    # trades 테이블에 commission 컬럼 추가 (없으면)
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'trades' AND column_name = 'commission'
            ) THEN
                ALTER TABLE trades ADD COLUMN commission DECIMAL(15, 4) DEFAULT 0;
            END IF;
        END $$;
    """)
    conn.commit()


@router.get("/brokerages")
async def get_brokerages():
    """증권사 목록 조회"""
    return {
        "brokerages": [
            {"name": name, "commission_rate": rate}
            for name, rate in BROKERAGES.items()
        ]
    }


@router.get("/settings")
async def get_brokerage_settings(user: dict = Depends(require_approved_user)):
    """내 증권사 설정 조회"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    _ensure_tables(cur, conn)

    cur.execute(
        "SELECT * FROM user_brokerage_settings WHERE user_id = %s",
        (user["id"],)
    )
    settings = cur.fetchone()

    cur.close()
    conn.close()

    if not settings:
        # 기본값 반환
        return {
            "brokerage_name": "키움증권",
            "commission_rate": 0.0025,
        }

    return {
        "brokerage_name": settings["brokerage_name"],
        "commission_rate": float(settings["commission_rate"]),
    }


@router.put("/settings")
async def update_brokerage_settings(
    data: BrokerageSettingsUpdate,
    user: dict = Depends(require_approved_user)
):
    """증권사 설정 저장"""
    if data.brokerage_name not in BROKERAGES:
        raise HTTPException(status_code=400, detail="유효하지 않은 증권사입니다")

    commission_rate = BROKERAGES[data.brokerage_name]

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    _ensure_tables(cur, conn)

    cur.execute("""
        INSERT INTO user_brokerage_settings (user_id, brokerage_name, commission_rate)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            brokerage_name = EXCLUDED.brokerage_name,
            commission_rate = EXCLUDED.commission_rate,
            updated_at = NOW()
        RETURNING *
    """, (user["id"], data.brokerage_name, commission_rate))

    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return {
        "message": f"{data.brokerage_name} 설정됨",
        "brokerage_name": result["brokerage_name"],
        "commission_rate": float(result["commission_rate"]),
    }


@router.get("/cash-balance")
async def get_cash_balance(user: dict = Depends(require_approved_user)):
    """달러 잔고 조회

    잔고 = (입금 합계 - 출금 합계) + (매도 수령액 합계) - (매수 지출액 합계)
    매수 지출 = total_amount + commission
    매도 수령 = total_amount - commission
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    _ensure_tables(cur, conn)

    # 입출금 합계
    cur.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN transaction_type = 'deposit' THEN amount ELSE 0 END), 0) as deposits,
            COALESCE(SUM(CASE WHEN transaction_type = 'withdraw' THEN amount ELSE 0 END), 0) as withdrawals
        FROM cash_transactions
        WHERE user_id = %s
    """, (user["id"],))
    cash_row = cur.fetchone()
    deposits = float(cash_row["deposits"])
    withdrawals = float(cash_row["withdrawals"])

    # 매매 합계 (commission 포함)
    cur.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN trade_type = 'buy' THEN total_amount + COALESCE(commission, 0) ELSE 0 END), 0) as buy_total,
            COALESCE(SUM(CASE WHEN trade_type = 'sell' THEN total_amount - COALESCE(commission, 0) ELSE 0 END), 0) as sell_total
        FROM trades
        WHERE user_id = %s
    """, (user["id"],))
    trade_row = cur.fetchone()
    buy_total = float(trade_row["buy_total"])
    sell_total = float(trade_row["sell_total"])

    # 환율 조회
    cur.execute("SELECT rate FROM exchange_rates ORDER BY collected_at DESC LIMIT 1")
    rate_row = cur.fetchone()
    exchange_rate = float(rate_row["rate"]) if rate_row else 1450.0

    cur.close()
    conn.close()

    # 잔고 계산
    balance_usd = (deposits - withdrawals) + sell_total - buy_total
    balance_krw = balance_usd * exchange_rate

    return {
        "balance_usd": round(balance_usd, 2),
        "balance_krw": round(balance_krw, 0),
        "exchange_rate": exchange_rate,
        "breakdown": {
            "deposits": round(deposits, 2),
            "withdrawals": round(withdrawals, 2),
            "buy_total": round(buy_total, 2),
            "sell_total": round(sell_total, 2),
        }
    }


@router.post("/cash-transaction")
async def create_cash_transaction(
    data: CashTransactionCreate,
    user: dict = Depends(require_approved_user)
):
    """입금/출금 기록"""
    if data.transaction_type not in ("deposit", "withdraw"):
        raise HTTPException(status_code=400, detail="transaction_type은 deposit 또는 withdraw여야 합니다")

    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="금액은 0보다 커야 합니다")

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    _ensure_tables(cur, conn)

    cur.execute("""
        INSERT INTO cash_transactions (user_id, transaction_type, amount, note)
        VALUES (%s, %s, %s, %s)
        RETURNING *
    """, (user["id"], data.transaction_type, data.amount, data.note))

    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    action = "입금" if data.transaction_type == "deposit" else "출금"
    return {
        "message": f"${data.amount:.2f} {action} 완료",
        "transaction": {
            "id": result["id"],
            "transaction_type": result["transaction_type"],
            "amount": float(result["amount"]),
            "note": result["note"],
            "created_at": result["created_at"].isoformat() if result["created_at"] else None,
        }
    }


@router.get("/cash-transactions")
async def get_cash_transactions(
    limit: int = 20,
    user: dict = Depends(require_approved_user)
):
    """입출금 내역 조회"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    _ensure_tables(cur, conn)

    cur.execute("""
        SELECT * FROM cash_transactions
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s
    """, (user["id"], limit))

    transactions = cur.fetchall()
    cur.close()
    conn.close()

    return {
        "transactions": [
            {
                "id": t["id"],
                "transaction_type": t["transaction_type"],
                "amount": float(t["amount"]),
                "note": t["note"],
                "created_at": t["created_at"].isoformat() if t["created_at"] else None,
            }
            for t in transactions
        ],
        "count": len(transactions),
    }


@router.delete("/cash-transaction/{transaction_id}")
async def delete_cash_transaction(
    transaction_id: int,
    user: dict = Depends(require_approved_user)
):
    """입출금 삭제"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        "SELECT id FROM cash_transactions WHERE id = %s AND user_id = %s",
        (transaction_id, user["id"])
    )
    if not cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")

    cur.execute("DELETE FROM cash_transactions WHERE id = %s", (transaction_id,))
    conn.commit()
    cur.close()
    conn.close()

    return {"message": "삭제됨", "transaction_id": transaction_id}


def get_user_commission_rate(user_id: int) -> float:
    """유저의 수수료율 조회 (trades.py에서 사용)"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        "SELECT commission_rate FROM user_brokerage_settings WHERE user_id = %s",
        (user_id,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row:
        return float(row["commission_rate"])
    return 0.0025  # 기본값: 키움증권 0.25%
