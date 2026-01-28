"""
lib/news_vectors.py - 뉴스 벡터 DB 시스템

Gemini 임베딩 → pgvector 저장 → 중복감지/유사뉴스연결/시간가중치/시장반영체크/자동정리

Usage:
    from lib.news_vectors import embed_and_dedup, init_vector_tables
    init_vector_tables()
    embed_and_dedup()
"""

import sys
import os
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor

# 프로젝트 루트 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_db
from api.embeddings import get_embedding, get_embeddings_batch


# ──────────────────────────────────────────────
# 테이블 생성
# ──────────────────────────────────────────────

def init_vector_tables():
    """news_vectors, news_links 테이블 생성"""
    conn = get_db()
    cur = conn.cursor()

    try:
        # pgvector 확장 활성화
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

        # news_vectors 테이블
        cur.execute("""
            CREATE TABLE IF NOT EXISTS news_vectors (
                id SERIAL PRIMARY KEY,
                news_mention_id INTEGER NOT NULL REFERENCES news_mentions(id) ON DELETE CASCADE,
                ticker VARCHAR(10) NOT NULL,
                headline_text TEXT NOT NULL,
                embedding vector(768) NOT NULL,
                is_duplicate BOOLEAN DEFAULT FALSE,
                duplicate_of_id INTEGER REFERENCES news_vectors(id) ON DELETE SET NULL,
                is_reflected BOOLEAN DEFAULT FALSE,
                reflected_price_change FLOAT,
                reflected_at TIMESTAMPTZ,
                is_active BOOLEAN DEFAULT TRUE,
                time_weight FLOAT DEFAULT 1.0,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(news_mention_id)
            )
        """)

        # news_links 테이블 (유사 뉴스 연결)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS news_links (
                id SERIAL PRIMARY KEY,
                source_id INTEGER NOT NULL REFERENCES news_vectors(id) ON DELETE CASCADE,
                target_id INTEGER NOT NULL REFERENCES news_vectors(id) ON DELETE CASCADE,
                similarity FLOAT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_id, target_id),
                CHECK(source_id < target_id)
            )
        """)

        # 인덱스 생성 (IF NOT EXISTS 지원 안 하므로 try/except)
        for idx_sql in [
            "CREATE INDEX idx_nv_ticker ON news_vectors(ticker)",
            "CREATE INDEX idx_nv_active ON news_vectors(is_active, is_duplicate)",
            "CREATE INDEX idx_nv_created ON news_vectors(created_at)",
        ]:
            try:
                cur.execute(idx_sql)
            except psycopg2.errors.DuplicateTable:
                conn.rollback()
                # 재연결 필요 없이 다음 인덱스 시도
                cur = conn.cursor()

        conn.commit()
        print("  ✅ news_vectors, news_links 테이블 준비 완료")
    except Exception as e:
        conn.rollback()
        print(f"  ❌ 테이블 생성 오류: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def _ensure_ivfflat_index(conn):
    """IVFFlat 인덱스 생성 (행이 충분할 때만)"""
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM news_vectors")
        count = cur.fetchone()[0]

        # IVFFlat은 최소 lists * 10 행 필요 (lists=100 → 1000행)
        if count >= 1000:
            cur.execute("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'news_vectors' AND indexname = 'idx_nv_embedding'
            """)
            if not cur.fetchone():
                cur.execute("""
                    CREATE INDEX idx_nv_embedding ON news_vectors
                    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
                """)
                conn.commit()
                print(f"  📐 IVFFlat 인덱스 생성 ({count}행)")
    except Exception:
        conn.rollback()
    finally:
        cur.close()


# ──────────────────────────────────────────────
# 메인 진입점: embed_and_dedup
# ──────────────────────────────────────────────

def embed_and_dedup(ticker_filter: str | None = None):
    """
    미임베딩 뉴스 → 벡터화 → 중복/유사 검사

    Args:
        ticker_filter: 특정 티커만 처리 (None이면 전체)
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # 1. news_mentions에서 news_vectors에 없는 행 조회
        query = """
            SELECT nm.id, nm.ticker, nm.headline
            FROM news_mentions nm
            LEFT JOIN news_vectors nv ON nm.id = nv.news_mention_id
            WHERE nv.id IS NULL
        """
        params = []
        if ticker_filter:
            query += " AND nm.ticker = %s"
            params.append(ticker_filter)

        query += " ORDER BY nm.id"
        cur.execute(query, params)
        rows = cur.fetchall()

        if not rows:
            print("  📭 새로운 뉴스 없음 (벡터화 스킵)")
            return

        print(f"\n🔮 뉴스 벡터화 시작: {len(rows)}건")

        # 2. 배치 임베딩 생성
        headlines = [row['headline'] for row in rows]
        embeddings = get_embeddings_batch(headlines)

        embedded = 0
        duplicates = 0
        linked = 0

        # 3. 각 뉴스에 대해 중복/유사 검사 후 저장
        insert_cur = conn.cursor()

        for row, embedding in zip(rows, embeddings):
            if embedding is None:
                continue

            ticker = row['ticker']
            embedding_str = _vec_to_str(embedding)

            # 중복 체크
            dup_id = check_duplicate(conn, ticker, embedding_str)

            if dup_id:
                # 중복 → is_duplicate=TRUE
                insert_cur.execute("""
                    INSERT INTO news_vectors
                    (news_mention_id, ticker, headline_text, embedding, is_duplicate, duplicate_of_id)
                    VALUES (%s, %s, %s, %s::vector, TRUE, %s)
                    ON CONFLICT (news_mention_id) DO NOTHING
                """, (row['id'], ticker, row['headline'], embedding_str, dup_id))
                duplicates += 1
            else:
                # 새 뉴스 삽입
                insert_cur.execute("""
                    INSERT INTO news_vectors
                    (news_mention_id, ticker, headline_text, embedding)
                    VALUES (%s, %s, %s, %s::vector)
                    ON CONFLICT (news_mention_id) DO NOTHING
                    RETURNING id
                """, (row['id'], ticker, row['headline'], embedding_str))

                result = insert_cur.fetchone()
                if result:
                    new_id = result[0]
                    # 유사 뉴스 검색 & 연결
                    similar = find_similar_news(conn, ticker, embedding_str, exclude_id=new_id)
                    for sim_id, sim_score in similar:
                        link_similar_news(conn, new_id, sim_id, sim_score)
                        linked += 1

            embedded += 1

        conn.commit()
        insert_cur.close()

        # IVFFlat 인덱스 체크
        _ensure_ivfflat_index(conn)

        print(f"  ✅ 벡터화 완료: {embedded}건 처리, {duplicates}건 중복, {linked}건 유사연결")

    except Exception as e:
        conn.rollback()
        print(f"  ❌ 벡터화 오류: {e}")
    finally:
        cur.close()
        conn.close()


# ──────────────────────────────────────────────
# 중복/유사 감지
# ──────────────────────────────────────────────

def check_duplicate(conn, ticker: str, embedding_str: str, days: int = 7) -> int | None:
    """
    cosine similarity > 0.95 = 중복

    Returns:
        중복인 경우 기존 news_vectors.id, 아니면 None
    """
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, 1 - (embedding <=> %s::vector) AS similarity
            FROM news_vectors
            WHERE ticker = %s
              AND is_duplicate = FALSE
              AND created_at > NOW() - INTERVAL '%s days'
            ORDER BY embedding <=> %s::vector
            LIMIT 1
        """, (embedding_str, ticker, days, embedding_str))

        row = cur.fetchone()
        if row and row[1] > 0.95:
            return row[0]
        return None
    finally:
        cur.close()


def find_similar_news(conn, ticker: str, embedding_str: str,
                      threshold: float = 0.7, exclude_id: int | None = None,
                      days: int = 7) -> list[tuple[int, float]]:
    """
    0.7 ~ 0.95 사이 = 유사 뉴스

    Returns:
        [(news_vectors_id, similarity_score), ...]
    """
    cur = conn.cursor()
    try:
        query = """
            SELECT id, 1 - (embedding <=> %s::vector) AS similarity
            FROM news_vectors
            WHERE ticker = %s
              AND is_duplicate = FALSE
              AND created_at > NOW() - INTERVAL '%s days'
        """
        params = [embedding_str, ticker, days]

        if exclude_id:
            query += " AND id != %s"
            params.append(exclude_id)

        query += """
            HAVING 1 - (embedding <=> %s::vector) BETWEEN %s AND 0.95
            ORDER BY similarity DESC
            LIMIT 10
        """
        # Can't use HAVING without GROUP BY, use subquery instead
        full_query = f"""
            SELECT id, similarity FROM (
                {query.replace('HAVING 1 - (embedding <=> %s::vector) BETWEEN %s AND 0.95', '')}
                ORDER BY embedding <=> %s::vector
                LIMIT 20
            ) sub
            WHERE similarity BETWEEN %s AND 0.95
            ORDER BY similarity DESC
            LIMIT 10
        """
        # Simpler approach: just filter in application
        cur.execute("""
            SELECT id, 1 - (embedding <=> %s::vector) AS similarity
            FROM news_vectors
            WHERE ticker = %s
              AND is_duplicate = FALSE
              AND created_at > NOW() - INTERVAL '%s days'
              {}
            ORDER BY embedding <=> %s::vector
            LIMIT 20
        """.format("AND id != %s" if exclude_id else ""),
            (embedding_str, ticker, days) +
            ((exclude_id,) if exclude_id else ()) +
            (embedding_str,))

        results = []
        for row in cur.fetchall():
            sim = row[1]
            if threshold <= sim <= 0.95:
                results.append((row[0], sim))
        return results
    finally:
        cur.close()


def link_similar_news(conn, source_id: int, target_id: int, similarity: float):
    """news_links에 유사 관계 삽입 (source_id < target_id 보장)"""
    cur = conn.cursor()
    try:
        # CHECK(source_id < target_id) 제약 준수
        lo, hi = min(source_id, target_id), max(source_id, target_id)
        cur.execute("""
            INSERT INTO news_links (source_id, target_id, similarity)
            VALUES (%s, %s, %s)
            ON CONFLICT (source_id, target_id) DO NOTHING
        """, (lo, hi, similarity))
    finally:
        cur.close()


# ──────────────────────────────────────────────
# 시간 가중치
# ──────────────────────────────────────────────

def calculate_time_weights():
    """
    시간 가중치 일괄 업데이트
    time_weight = max(0.1, 1.0 - (나이_시간 / 168))
    is_reflected=TRUE → weight = 0.0
    """
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE news_vectors
            SET time_weight = CASE
                WHEN is_reflected = TRUE THEN 0.0
                ELSE GREATEST(0.1,
                    1.0 - EXTRACT(EPOCH FROM (NOW() - created_at)) / 3600.0 / 168.0
                )
            END
            WHERE is_active = TRUE
        """)
        updated = cur.rowcount
        conn.commit()
        print(f"  ⏱️ 시간 가중치 업데이트: {updated}건")
    except Exception as e:
        conn.rollback()
        print(f"  ❌ 시간 가중치 오류: {e}")
    finally:
        cur.close()
        conn.close()


def get_time_weighted_score(ticker: str, days: int = 1) -> dict:
    """
    특정 티커의 시간가중 뉴스 점수 조회

    Returns:
        {
            'ticker': str,
            'weighted_count': float,  # 시간가중 뉴스 수
            'total_count': int,       # 전체 뉴스 수
            'unique_count': int,      # 비중복 뉴스 수
            'duplicate_count': int,   # 중복 뉴스 수
        }
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            SELECT
                COUNT(*) AS total_count,
                COUNT(*) FILTER (WHERE is_duplicate = FALSE) AS unique_count,
                COUNT(*) FILTER (WHERE is_duplicate = TRUE) AS duplicate_count,
                COALESCE(SUM(time_weight) FILTER (WHERE is_duplicate = FALSE), 0) AS weighted_count
            FROM news_vectors
            WHERE ticker = %s
              AND is_active = TRUE
              AND created_at > NOW() - INTERVAL '%s days'
        """, (ticker, days))

        row = cur.fetchone()
        return {
            'ticker': ticker,
            'weighted_count': float(row['weighted_count']),
            'total_count': row['total_count'],
            'unique_count': row['unique_count'],
            'duplicate_count': row['duplicate_count'],
        }
    finally:
        cur.close()
        conn.close()


# ──────────────────────────────────────────────
# 시장 반영 체크
# ──────────────────────────────────────────────

def check_market_reflection(tickers: list[str] | None = None):
    """
    뉴스 발행 후 +10% 이상 상승 → is_reflected=TRUE

    yfinance로 뉴스 시점 vs 현재 가격 비교
    """
    import yfinance as yf

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        query = """
            SELECT nv.id, nv.ticker, nv.created_at
            FROM news_vectors nv
            WHERE nv.is_active = TRUE
              AND nv.is_duplicate = FALSE
              AND nv.is_reflected = FALSE
              AND nv.created_at < NOW() - INTERVAL '1 day'
        """
        params = []
        if tickers:
            query += " AND nv.ticker = ANY(%s)"
            params.append(tickers)

        cur.execute(query, params)
        rows = cur.fetchall()

        if not rows:
            print("  📊 시장 반영 체크: 대상 없음")
            return

        # 티커별 그룹핑
        ticker_groups: dict[str, list] = {}
        for row in rows:
            ticker_groups.setdefault(row['ticker'], []).append(row)

        reflected = 0
        update_cur = conn.cursor()

        for ticker, group in ticker_groups.items():
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="1mo")

                if hist.empty:
                    continue

                current_price = hist['Close'].iloc[-1]

                for row in group:
                    news_date = row['created_at'].date()
                    # 뉴스 날짜 이후의 가격 찾기
                    mask = hist.index.date >= news_date
                    if not mask.any():
                        continue

                    news_price = hist.loc[mask, 'Close'].iloc[0]
                    if news_price <= 0:
                        continue

                    price_change = (current_price - news_price) / news_price

                    if price_change >= 0.10:  # +10% 이상
                        update_cur.execute("""
                            UPDATE news_vectors
                            SET is_reflected = TRUE,
                                reflected_price_change = %s,
                                reflected_at = NOW(),
                                time_weight = 0.0
                            WHERE id = %s
                        """, (price_change, row['id']))
                        reflected += 1

            except Exception:
                continue

        conn.commit()
        update_cur.close()
        print(f"  📈 시장 반영 체크: {reflected}건 반영됨")

    except Exception as e:
        conn.rollback()
        print(f"  ❌ 시장 반영 체크 오류: {e}")
    finally:
        cur.close()
        conn.close()


# ──────────────────────────────────────────────
# 클린업
# ──────────────────────────────────────────────

def cleanup_old_news(reflected_days: int = 30, hard_delete_days: int = 90):
    """
    뉴스 정리:
    - 반영됨 + 30일+ → is_active=FALSE (소프트 삭제)
    - 비활성 + 90일+ → DELETE (하드 삭제)
    """
    conn = get_db()
    cur = conn.cursor()

    try:
        # 소프트 삭제: 반영된 뉴스 30일 후 비활성화
        cur.execute("""
            UPDATE news_vectors
            SET is_active = FALSE
            WHERE is_reflected = TRUE
              AND is_active = TRUE
              AND reflected_at < NOW() - INTERVAL '%s days'
        """, (reflected_days,))
        soft = cur.rowcount

        # 하드 삭제: 비활성 90일 후 삭제
        cur.execute("""
            DELETE FROM news_vectors
            WHERE is_active = FALSE
              AND created_at < NOW() - INTERVAL '%s days'
        """, (hard_delete_days,))
        hard = cur.rowcount

        conn.commit()
        print(f"  🧹 뉴스 정리: {soft}건 비활성화, {hard}건 삭제")

    except Exception as e:
        conn.rollback()
        print(f"  ❌ 뉴스 정리 오류: {e}")
    finally:
        cur.close()
        conn.close()


# ──────────────────────────────────────────────
# 시맨틱 검색
# ──────────────────────────────────────────────

def search_similar_news(query_text: str, ticker: str | None = None,
                        limit: int = 5) -> list[dict]:
    """
    시맨틱 검색 - 쿼리 텍스트와 유사한 뉴스 조회

    Args:
        query_text: 검색 텍스트
        ticker: 특정 티커 필터 (옵션)
        limit: 결과 수

    Returns:
        [{'id', 'ticker', 'headline', 'similarity', 'created_at'}, ...]
    """
    embedding = get_embedding(query_text)
    if embedding is None:
        return []

    embedding_str = _vec_to_str(embedding)

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        query = """
            SELECT
                nv.id,
                nv.ticker,
                nv.headline_text AS headline,
                1 - (nv.embedding <=> %s::vector) AS similarity,
                nv.created_at,
                nv.is_duplicate,
                nv.time_weight
            FROM news_vectors nv
            WHERE nv.is_active = TRUE
              AND nv.is_duplicate = FALSE
        """
        params = [embedding_str]

        if ticker:
            query += " AND nv.ticker = %s"
            params.append(ticker)

        query += """
            ORDER BY nv.embedding <=> %s::vector
            LIMIT %s
        """
        params.extend([embedding_str, limit])

        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]

    finally:
        cur.close()
        conn.close()


# ──────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────

def _vec_to_str(vec: list[float]) -> str:
    """벡터를 pgvector 문자열로 변환"""
    return "[" + ",".join(str(v) for v in vec) + "]"
