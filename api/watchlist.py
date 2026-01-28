"""
Watchlist API - 관심 종목 관리
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from db import get_db
from api.auth import require_user

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


# Pydantic models
class WatchlistAdd(BaseModel):
    ticker: str
    note: str | None = None
    target_price: float | None = None
    alert_price: float | None = None
    folder_id: int | None = None


class WatchlistUpdate(BaseModel):
    note: str | None = None
    target_price: float | None = None
    alert_price: float | None = None
    folder_id: int | None = None


class FolderCreate(BaseModel):
    name: str
    color: str = "#3b82f6"


class FolderUpdate(BaseModel):
    name: str | None = None
    color: str | None = None


_table_initialized = False

def ensure_watchlist_table():
    """watchlist 및 folders 테이블 생성 (lazy initialization)"""
    global _table_initialized
    if _table_initialized:
        return

    try:
        conn = get_db()
        cur = conn.cursor()

        # 폴더 테이블 생성
        cur.execute("""
            CREATE TABLE IF NOT EXISTS watchlist_folders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR(50) NOT NULL,
                color VARCHAR(7) DEFAULT '#3b82f6',
                is_default BOOLEAN DEFAULT FALSE,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name)
            )
        """)

        # watchlist 테이블 생성
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_watchlist (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                ticker VARCHAR(20) NOT NULL,
                note TEXT,
                target_price DECIMAL(12, 4),
                alert_price DECIMAL(12, 4),
                folder_id INTEGER REFERENCES watchlist_folders(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, ticker)
            )
        """)

        # folder_id 컬럼이 없으면 추가 (기존 테이블 마이그레이션)
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'user_watchlist' AND column_name = 'folder_id'
                ) THEN
                    ALTER TABLE user_watchlist
                    ADD COLUMN folder_id INTEGER REFERENCES watchlist_folders(id) ON DELETE SET NULL;
                END IF;
            END $$;
        """)

        conn.commit()
        cur.close()
        conn.close()
        _table_initialized = True
    except Exception:
        # users 테이블이 없으면 나중에 다시 시도
        pass


def ensure_default_folder(user_id: int):
    """사용자의 기본 폴더가 없으면 생성"""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO watchlist_folders (user_id, name, is_default)
            VALUES (%s, '관심종목', TRUE)
            ON CONFLICT (user_id, name) DO NOTHING
        """, (user_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()


@router.get("/")
async def get_watchlist(user: dict = Depends(require_user)):
    """사용자의 관심 종목 목록 조회 (현재가 포함)"""
    ensure_watchlist_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # 관심 종목 조회 (폴더 정보 포함)
        cur.execute("""
            SELECT w.id, w.ticker, w.note, w.target_price, w.alert_price, w.folder_id, w.created_at,
                   f.name as folder_name, f.color as folder_color
            FROM user_watchlist w
            LEFT JOIN watchlist_folders f ON w.folder_id = f.id
            WHERE w.user_id = %s
            ORDER BY w.created_at DESC
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
                "folder_id": item.get("folder_id"),
                "folder_name": item.get("folder_name"),
                "folder_color": item.get("folder_color"),
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
async def add_to_watchlist(data: WatchlistAdd, user: dict = Depends(require_user)):
    """관심 종목 추가"""
    ensure_watchlist_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            INSERT INTO user_watchlist (user_id, ticker, note, target_price, alert_price, folder_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, ticker) DO UPDATE SET
                note = EXCLUDED.note,
                target_price = EXCLUDED.target_price,
                alert_price = EXCLUDED.alert_price,
                folder_id = EXCLUDED.folder_id
            RETURNING id, ticker, note, target_price, alert_price, folder_id, created_at
        """, (user["id"], data.ticker.upper(), data.note, data.target_price, data.alert_price, data.folder_id))

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
                "folder_id": result["folder_id"],
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
async def update_watchlist_item(item_id: int, data: WatchlistUpdate, user: dict = Depends(require_user)):
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
async def remove_from_watchlist(item_id: int, user: dict = Depends(require_user)):
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
async def remove_by_ticker(ticker: str, user: dict = Depends(require_user)):
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


# ===== Folder CRUD =====

@router.get("/folders")
async def get_folders(user: dict = Depends(require_user)):
    """폴더 목록 조회"""
    ensure_watchlist_table()
    ensure_default_folder(user["id"])

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            SELECT f.id, f.name, f.color, f.is_default, f.sort_order,
                   COUNT(w.id) as item_count
            FROM watchlist_folders f
            LEFT JOIN user_watchlist w ON w.folder_id = f.id
            WHERE f.user_id = %s
            GROUP BY f.id
            ORDER BY f.is_default DESC, f.sort_order, f.created_at
        """, (user["id"],))

        folders = cur.fetchall()

        # 폴더 없는 종목 수
        cur.execute("""
            SELECT COUNT(*) as count FROM user_watchlist
            WHERE user_id = %s AND folder_id IS NULL
        """, (user["id"],))
        unfiled_count = cur.fetchone()["count"]

        return {
            "folders": [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "color": f["color"],
                    "is_default": f["is_default"],
                    "item_count": f["item_count"]
                }
                for f in folders
            ],
            "unfiled_count": unfiled_count
        }
    finally:
        cur.close()
        conn.close()


@router.post("/folders")
async def create_folder(data: FolderCreate, user: dict = Depends(require_user)):
    """폴더 생성"""
    ensure_watchlist_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            INSERT INTO watchlist_folders (user_id, name, color)
            VALUES (%s, %s, %s)
            RETURNING id, name, color, is_default
        """, (user["id"], data.name, data.color))

        folder = cur.fetchone()
        conn.commit()

        return {
            "success": True,
            "folder": {
                "id": folder["id"],
                "name": folder["name"],
                "color": folder["color"],
                "is_default": folder["is_default"],
                "item_count": 0
            }
        }
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail="같은 이름의 폴더가 이미 존재합니다")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.put("/folders/{folder_id}")
async def update_folder(folder_id: int, data: FolderUpdate, user: dict = Depends(require_user)):
    """폴더 수정"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # 기본 폴더는 이름 변경 불가
        cur.execute("""
            SELECT is_default FROM watchlist_folders
            WHERE id = %s AND user_id = %s
        """, (folder_id, user["id"]))

        folder = cur.fetchone()
        if not folder:
            raise HTTPException(status_code=404, detail="폴더를 찾을 수 없습니다")

        if folder["is_default"] and data.name:
            raise HTTPException(status_code=400, detail="기본 폴더 이름은 변경할 수 없습니다")

        # 업데이트
        updates = []
        values = []
        if data.name:
            updates.append("name = %s")
            values.append(data.name)
        if data.color:
            updates.append("color = %s")
            values.append(data.color)

        if updates:
            values.extend([folder_id, user["id"]])
            cur.execute(f"""
                UPDATE watchlist_folders
                SET {', '.join(updates)}
                WHERE id = %s AND user_id = %s
                RETURNING id, name, color, is_default
            """, values)

            result = cur.fetchone()
            conn.commit()
            return {"success": True, "folder": result}

        return {"success": True, "message": "변경사항 없음"}
    finally:
        cur.close()
        conn.close()


@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: int, user: dict = Depends(require_user)):
    """폴더 삭제 (기본 폴더 제외, 종목은 폴더 없음으로 이동)"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # 기본 폴더 체크
        cur.execute("""
            SELECT is_default FROM watchlist_folders
            WHERE id = %s AND user_id = %s
        """, (folder_id, user["id"]))

        folder = cur.fetchone()
        if not folder:
            raise HTTPException(status_code=404, detail="폴더를 찾을 수 없습니다")

        if folder["is_default"]:
            raise HTTPException(status_code=400, detail="기본 폴더는 삭제할 수 없습니다")

        # 폴더 삭제 (CASCADE로 folder_id는 NULL이 됨)
        cur.execute("""
            DELETE FROM watchlist_folders
            WHERE id = %s AND user_id = %s
        """, (folder_id, user["id"]))

        conn.commit()
        return {"success": True, "deleted_id": folder_id}
    finally:
        cur.close()
        conn.close()


@router.put("/{item_id}/folder")
async def move_to_folder(item_id: int, folder_id: int | None = None, user: dict = Depends(require_user)):
    """종목을 다른 폴더로 이동"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # folder_id가 있으면 해당 폴더가 사용자 것인지 확인
        if folder_id:
            cur.execute("""
                SELECT id FROM watchlist_folders
                WHERE id = %s AND user_id = %s
            """, (folder_id, user["id"]))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="폴더를 찾을 수 없습니다")

        cur.execute("""
            UPDATE user_watchlist
            SET folder_id = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, ticker, folder_id
        """, (folder_id, item_id, user["id"]))

        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="관심 종목을 찾을 수 없습니다")

        conn.commit()
        return {"success": True, "item": result}
    finally:
        cur.close()
        conn.close()
