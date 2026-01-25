"""
공지사항 API
- Gemini AI로 공지사항 초안 작성 가능
"""
import os
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from db import get_db
from api.auth import require_approved_user, require_admin

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        pass

router = APIRouter(prefix="/api/announcements", tags=["announcements"])


class AnnouncementCreate(BaseModel):
    title: str
    content: str
    is_important: bool = False


class AnnouncementDraft(BaseModel):
    prompt: str  # 대략적인 내용
    tone: str = "friendly"  # friendly, formal, urgent


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


@router.post("/draft")
async def generate_announcement_draft(
    draft: AnnouncementDraft,
    admin: dict = Depends(require_admin)
):
    """
    AI로 공지사항 초안 작성 (관리자)

    - prompt: 대략적인 내용 (예: "내일 서버 점검 있음", "새 기능 추가됨")
    - tone: friendly(친근), formal(공식), urgent(긴급)
    """
    if not gemini_client:
        raise HTTPException(status_code=503, detail="Gemini API 사용 불가")

    tone_guide = {
        "friendly": "친근하고 이모지를 적절히 사용하는 톤",
        "formal": "격식있고 전문적인 톤",
        "urgent": "긴급하고 중요한 느낌의 톤"
    }

    system_prompt = f"""당신은 '달러농장' 미국주식 포트폴리오 웹앱의 공지사항 작성자입니다.

규칙:
1. {tone_guide.get(draft.tone, tone_guide['friendly'])}으로 작성
2. 제목은 20자 이내, 핵심 내용 요약
3. 본문은 2~4문장으로 간결하게
4. 사용자에게 필요한 액션이 있으면 명확히 안내
5. 한국어로 작성

중요:
- 이 서비스는 웹앱(SaaS)입니다. 새로고침만 하면 자동 반영됩니다.
- 절대 "앱스토어", "플레이스토어", "업데이트", "앱 업데이트" 언급 금지
- "새로고침하면 적용됩니다" 또는 언급 없이 작성

JSON 형식으로만 응답:
{{"title": "제목", "content": "본문 내용", "is_important": true/false}}
"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"{system_prompt}\n\n사용자 요청: {draft.prompt}"
        )

        import json
        result_text = response.text.strip()
        # JSON 추출 (```json ... ``` 형식 처리)
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()

        result = json.loads(result_text)

        return {
            "draft": {
                "title": result.get("title", ""),
                "content": result.get("content", ""),
                "is_important": result.get("is_important", False),
            },
            "message": "AI 초안 생성 완료. 수정 후 /api/announcements POST로 등록하세요."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 생성 실패: {str(e)}")
