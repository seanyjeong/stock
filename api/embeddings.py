"""
Gemini text-embedding-004 임베딩 모듈
- 768차원 벡터 생성
- pgvector와 함께 시맨틱 검색에 사용
"""
import os
import time

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
            contents=text
        )
        return result.embeddings[0].values
    except Exception:
        return None


def get_embeddings_batch(texts: list[str], batch_size: int = 50) -> list[list[float] | None]:
    """
    배치 임베딩 생성 (rate limit 대응)

    Args:
        texts: 임베딩할 텍스트 리스트
        batch_size: 배치 크기 (기본 50)

    Returns:
        각 텍스트에 대한 768차원 벡터 리스트 (실패 시 None)
    """
    if not client:
        return [None] * len(texts)

    results = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            result = client.models.embed_content(
                model="text-embedding-004",
                contents=batch
            )
            for emb in result.embeddings:
                results.append(emb.values)
        except Exception:
            # 배치 실패 시 개별 처리
            for text in batch:
                try:
                    r = client.models.embed_content(
                        model="text-embedding-004",
                        contents=text
                    )
                    results.append(r.embeddings[0].values)
                except Exception:
                    results.append(None)

        # 배치 간 rate limit 대기
        if i + batch_size < len(texts):
            time.sleep(1)

    return results
