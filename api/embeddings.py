"""
Gemini text-embedding-004 임베딩 모듈
- 768차원 벡터 생성
- pgvector와 함께 시맨틱 검색에 사용
"""
import os

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = None

if GEMINI_API_KEY:
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        pass


def get_embedding(text: str) -> list[float] | None:
    """
    Gemini text-embedding-004로 768차원 벡터 생성

    Args:
        text: 임베딩할 텍스트

    Returns:
        768차원 float 리스트 또는 None (클라이언트 없을 때)
    """
    if not client:
        return None

    try:
        result = client.models.embed_content(
            model="text-embedding-004",
            content=text
        )
        return result.embedding
    except Exception:
        return None
