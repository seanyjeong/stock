"""
scanners/storage.py - 스캔 결과 DB 저장

핵심 변경: 카테고리별 독립 MERGE (덮어쓰기 버그 해결)
- 단타 실행 → day_trade 키만 업데이트
- 스윙 실행 → swing 키만 업데이트
- 장기 실행 → longterm 키만 업데이트
"""

import json

from psycopg2.extras import RealDictCursor

from db import get_db


def init_tables():
    """스캔 결과 테이블 생성"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_scan_results (
            id SERIAL PRIMARY KEY,
            scan_date DATE NOT NULL,
            results JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scan_date)
        );

        CREATE INDEX IF NOT EXISTS idx_scan_date ON daily_scan_results(scan_date);
    """)

    conn.commit()
    cur.close()
    conn.close()


def save_category(category: str, results: list):
    """해당 카테고리만 MERGE 저장 (다른 카테고리 보존)

    Args:
        category: 'day_trade', 'swing', 'longterm'
        results: 분석 결과 리스트 (TOP 5로 자른 후 전달)
    """
    top5 = sorted(results, key=lambda x: -x['score'])[:5]

    conn = get_db()
    cur = conn.cursor()

    # 1. 오늘 row가 없으면 3개 카테고리 빈 배열로 초기화
    #    (API가 "day_trade" 키 존재 여부로 v2 형식 감지)
    cur.execute("""
        INSERT INTO daily_scan_results (scan_date, results)
        VALUES (CURRENT_DATE, '{"day_trade": [], "swing": [], "longterm": []}')
        ON CONFLICT (scan_date) DO NOTHING
    """)

    # 2. 해당 카테고리 키만 업데이트 (jsonb_set)
    cur.execute("""
        UPDATE daily_scan_results
        SET results = jsonb_set(results, %s, %s::jsonb),
            created_at = CURRENT_TIMESTAMP
        WHERE scan_date = CURRENT_DATE
    """, (
        '{' + category + '}',
        json.dumps(top5),
    ))

    conn.commit()
    cur.close()
    conn.close()

    print(f"  {category}: TOP {len(top5)} 저장 완료")


def load_today_results() -> dict:
    """오늘 스캔 결과 전체 조회"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT results
        FROM daily_scan_results
        WHERE scan_date = CURRENT_DATE
    """)

    row = cur.fetchone()
    cur.close()
    conn.close()

    if row and row['results']:
        return row['results']
    return {}
