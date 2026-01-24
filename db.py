"""
PostgreSQL 연결 모듈

환경변수:
    DATABASE_URL: PostgreSQL 연결 문자열 (기본값: postgresql://claude:claude_dev@localhost:5432/continuous_claude)
"""

import os

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://claude:claude_dev@localhost:5432/continuous_claude")


def get_db():
    """PostgreSQL 데이터베이스 연결 반환"""
    return psycopg2.connect(DATABASE_URL)


def get_db_cursor(dict_cursor: bool = False):
    """
    컨텍스트 매니저용 DB 커넥션과 커서 반환

    Args:
        dict_cursor: True면 RealDictCursor 사용 (결과를 딕셔너리로 반환)

    Returns:
        tuple: (connection, cursor)

    Example:
        conn, cur = get_db_cursor(dict_cursor=True)
        try:
            cur.execute("SELECT * FROM table")
            rows = cur.fetchall()
        finally:
            cur.close()
            conn.close()
    """
    conn = psycopg2.connect(DATABASE_URL)
    cursor_factory = RealDictCursor if dict_cursor else None
    cur = conn.cursor(cursor_factory=cursor_factory)
    return conn, cur
