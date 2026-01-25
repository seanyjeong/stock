"""
주식 용어 사전 API
- 시맨틱 검색 (pgvector + Gemini 임베딩)
- AI 질문 답변 (Gemini 2.0 Flash)
"""
import os
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from db import get_db
from api.auth import require_admin
from api.embeddings import get_embedding

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = None

if GEMINI_API_KEY:
    try:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        pass

router = APIRouter(prefix="/api/glossary", tags=["glossary"])


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    related_terms: list[dict]


# ============================================================
# 테이블 생성
# ============================================================

def create_table():
    """glossary_terms 테이블 생성 (pgvector 필요)"""
    conn = get_db()
    cur = conn.cursor()

    # pgvector 확장 생성 (이미 있으면 무시)
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 용어 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS glossary_terms (
            id SERIAL PRIMARY KEY,
            term VARCHAR(100) NOT NULL UNIQUE,
            definition TEXT NOT NULL,
            example TEXT,
            category VARCHAR(50) NOT NULL DEFAULT '기본 용어',
            related_terms TEXT[],
            embedding vector(768),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 임베딩 인덱스 (코사인 유사도용)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_glossary_embedding
        ON glossary_terms USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    conn.commit()
    cur.close()
    conn.close()


# ============================================================
# 공개 API
# ============================================================

@router.get("/categories")
async def get_categories():
    """카테고리 목록 조회"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT category
        FROM glossary_terms
        ORDER BY category
    """)

    categories = [row[0] for row in cur.fetchall()]

    cur.close()
    conn.close()

    return categories


@router.get("/terms/{category}")
async def get_terms_by_category(category: str):
    """카테고리별 용어 목록"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT id, term, definition, example, related_terms
        FROM glossary_terms
        WHERE category = %s
        ORDER BY term
    """, (category,))

    terms = cur.fetchall()

    cur.close()
    conn.close()

    return list(terms)


@router.get("/search")
async def search_terms(q: str = Query(..., min_length=1)):
    """
    시맨틱 검색으로 유사 용어 찾기

    pgvector 코사인 유사도 사용
    """
    # 질문 임베딩 생성
    q_embedding = get_embedding(q)

    if not q_embedding:
        # 임베딩 실패 시 텍스트 검색 fallback
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT term, definition, example, related_terms, 0.5 as similarity
            FROM glossary_terms
            WHERE term ILIKE %s OR definition ILIKE %s
            ORDER BY term
            LIMIT 5
        """, (f"%{q}%", f"%{q}%"))

        results = cur.fetchall()
        cur.close()
        conn.close()

        return list(results)

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # pgvector 코사인 유사도 검색
    cur.execute("""
        SELECT term, definition, example, related_terms,
               1 - (embedding <=> %s::vector) as similarity
        FROM glossary_terms
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT 5
    """, (q_embedding, q_embedding))

    results = cur.fetchall()

    cur.close()
    conn.close()

    return list(results)


@router.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    질문에 AI 답변

    1. 시맨틱 검색으로 관련 용어 찾기
    2. Gemini로 쉬운 설명 생성
    """
    question = request.question

    # 1. 관련 용어 검색
    q_embedding = get_embedding(question)

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if q_embedding:
        cur.execute("""
            SELECT term, definition, example, related_terms,
                   1 - (embedding <=> %s::vector) as similarity
            FROM glossary_terms
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT 5
        """, (q_embedding, q_embedding))
    else:
        # Fallback: 텍스트 검색
        cur.execute("""
            SELECT term, definition, example, related_terms, 0.5 as similarity
            FROM glossary_terms
            WHERE term ILIKE %s OR definition ILIKE %s
            ORDER BY term
            LIMIT 5
        """, (f"%{question}%", f"%{question}%"))

    related = cur.fetchall()
    cur.close()
    conn.close()

    related_terms = list(related)

    # 2. Gemini로 답변 생성
    if not gemini_client:
        # Gemini 없으면 검색 결과로 대체
        if related_terms:
            answer = f"**{related_terms[0]['term']}**: {related_terms[0]['definition']}"
            if related_terms[0].get('example'):
                answer += f"\n\n예시: {related_terms[0]['example']}"
        else:
            answer = "관련 용어를 찾을 수 없습니다."

        return AskResponse(answer=answer, related_terms=related_terms)

    # 컨텍스트 구성
    context = ""
    for term in related_terms:
        context += f"- **{term['term']}**: {term['definition']}\n"
        if term.get('example'):
            context += f"  예시: {term['example']}\n"

    prompt = f"""당신은 미국주식 투자 초보자를 위한 친절한 선생님입니다.

## 관련 용어
{context}

## 사용자 질문
{question}

## 규칙
1. 초보자 눈높이에 맞춰 쉽게 설명
2. 한국 주식 커뮤니티에서 쓰는 은어도 이해 (예: "숏스", "풀매도", "존버" 등)
3. 실제 예시를 들어 설명
4. 마크다운 형식으로 깔끔하게 작성
5. 관련 용어가 있으면 함께 언급
6. 2-3문단 이내로 간결하게
7. 인사말 없이 바로 답변 (안녕하세요, 반갑습니다 등 금지)

답변:"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        answer = response.text.strip()
    except Exception as e:
        answer = f"AI 답변 생성 실패: {str(e)}"

    return AskResponse(answer=answer, related_terms=related_terms)


# ============================================================
# 관리자 API
# ============================================================

@router.post("/embed-all")
async def embed_all_terms(admin: dict = Depends(require_admin)):
    """
    모든 용어에 임베딩 생성 (관리자 전용)

    - 기존 임베딩이 없는 용어만 처리
    - 용어 + 정의를 합쳐서 임베딩
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 임베딩 없는 용어 조회
    cur.execute("""
        SELECT id, term, definition
        FROM glossary_terms
        WHERE embedding IS NULL
    """)

    terms = cur.fetchall()
    updated = 0

    for term in terms:
        text = f"{term['term']}: {term['definition']}"
        embedding = get_embedding(text)

        if embedding:
            cur.execute("""
                UPDATE glossary_terms
                SET embedding = %s::vector, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (embedding, term['id']))
            updated += 1

    conn.commit()
    cur.close()
    conn.close()

    return {
        "message": f"{updated}개 용어 임베딩 완료",
        "total": len(terms),
        "updated": updated
    }


class TermCreate(BaseModel):
    term: str
    definition: str
    example: Optional[str] = None
    category: str = "기본 용어"
    related_terms: Optional[list[str]] = None


@router.post("/terms")
async def create_term(term: TermCreate, admin: dict = Depends(require_admin)):
    """용어 추가 (관리자 전용)"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 임베딩 생성
    text = f"{term.term}: {term.definition}"
    embedding = get_embedding(text)

    try:
        cur.execute("""
            INSERT INTO glossary_terms (term, definition, example, category, related_terms, embedding)
            VALUES (%s, %s, %s, %s, %s, %s::vector)
            RETURNING id, term, definition, example, category, related_terms
        """, (
            term.term,
            term.definition,
            term.example,
            term.category,
            term.related_terms,
            embedding
        ))

        result = cur.fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"용어 추가 실패: {str(e)}")
    finally:
        cur.close()
        conn.close()

    return dict(result)


@router.delete("/terms/{term_id}")
async def delete_term(term_id: int, admin: dict = Depends(require_admin)):
    """용어 삭제 (관리자 전용)"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM glossary_terms WHERE id = %s", (term_id,))

    if cur.rowcount == 0:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="용어를 찾을 수 없습니다")

    conn.commit()
    cur.close()
    conn.close()

    return {"message": "용어 삭제됨"}


# 초기화: 테이블 생성
try:
    create_table()
except Exception:
    pass  # DB 연결 실패 시 무시 (서버 시작 시 재시도)
