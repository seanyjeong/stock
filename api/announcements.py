"""
공지사항 API
"""
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from db import get_db
from api.auth import require_approved_user, require_admin

router = APIRouter(prefix="/api/announcements", tags=["announcements"])


class AnnouncementCreate(BaseModel):
    title: str
    content: str
    is_important: bool = False


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    is_important: Optional[bool] = None
    is_active: Optional[bool] = None


def create_table():
    """announcements 테이블 생성"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            content TEXT NOT NULL,
            is_important BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


@router.get("/")
async def get_announcements(limit: int = 5):
    """활성 공지사항 조회 (공개)"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 테이블 생성
    cur.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            content TEXT NOT NULL,
            is_important BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    cur.execute("""
        SELECT id, title, content, is_important, created_at
        FROM announcements
        WHERE is_active = TRUE
        ORDER BY is_important DESC, created_at DESC
        LIMIT %s
    """, (limit,))

    announcements = cur.fetchall()
    cur.close()
    conn.close()

    return {
        "announcements": [
            {
                "id": a["id"],
                "title": a["title"],
                "content": a["content"],
                "is_important": a["is_important"],
                "created_at": a["created_at"].isoformat() if a["created_at"] else None,
            }
            for a in announcements
        ],
        "count": len(announcements),
    }


@router.get("/admin")
async def get_all_announcements(admin: dict = Depends(require_admin)):
    """모든 공지사항 조회 (관리자)"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT a.*, u.nickname as author
        FROM announcements a
        LEFT JOIN users u ON a.created_by = u.id
        ORDER BY created_at DESC
    """)

    announcements = cur.fetchall()
    cur.close()
    conn.close()

    return {
        "announcements": [
            {
                "id": a["id"],
                "title": a["title"],
                "content": a["content"],
                "is_important": a["is_important"],
                "is_active": a["is_active"],
                "author": a["author"],
                "created_at": a["created_at"].isoformat() if a["created_at"] else None,
            }
            for a in announcements
        ],
    }


@router.post("/")
async def create_announcement(
    announcement: AnnouncementCreate,
    admin: dict = Depends(require_admin)
):
    """공지사항 작성 (관리자)"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        INSERT INTO announcements (title, content, is_important, created_by)
        VALUES (%s, %s, %s, %s)
        RETURNING *
    """, (announcement.title, announcement.content, announcement.is_important, admin["id"]))

    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return {
        "message": "공지사항 등록됨",
        "announcement": {
            "id": result["id"],
            "title": result["title"],
        }
    }


@router.put("/{announcement_id}")
async def update_announcement(
    announcement_id: int,
    update: AnnouncementUpdate,
    admin: dict = Depends(require_admin)
):
    """공지사항 수정 (관리자)"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id FROM announcements WHERE id = %s", (announcement_id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다")

    updates = []
    values = []
    if update.title is not None:
        updates.append("title = %s")
        values.append(update.title)
    if update.content is not None:
        updates.append("content = %s")
        values.append(update.content)
    if update.is_important is not None:
        updates.append("is_important = %s")
        values.append(update.is_important)
    if update.is_active is not None:
        updates.append("is_active = %s")
        values.append(update.is_active)

    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(announcement_id)
        cur.execute(f"""
            UPDATE announcements SET {', '.join(updates)}
            WHERE id = %s
        """, values)
        conn.commit()

    cur.close()
    conn.close()

    return {"message": "공지사항 수정됨"}


@router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: int,
    admin: dict = Depends(require_admin)
):
    """공지사항 삭제 (관리자)"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM announcements WHERE id = %s", (announcement_id,))
    if cur.rowcount == 0:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다")

    conn.commit()
    cur.close()
    conn.close()

    return {"message": "공지사항 삭제됨"}
