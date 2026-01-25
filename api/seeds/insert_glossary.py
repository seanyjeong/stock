"""
주식 용어 사전 DB 삽입 스크립트

사용법:
    uv run python api/seeds/insert_glossary.py

옵션:
    --reset: 기존 데이터 삭제 후 재삽입
    --dry-run: 실제 삽입 없이 확인만
"""

import sys
import argparse
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from db import get_db_cursor
from api.seeds.glossary_data import GLOSSARY_TERMS, get_category_stats


def create_table():
    """glossary_terms 테이블 생성"""
    conn, cur = get_db_cursor()
    try:
        # SQL 파일 읽기
        sql_path = Path(__file__).parent / "create_glossary_table.sql"
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()

        cur.execute(sql)
        conn.commit()
        print("[OK] 테이블 생성 완료")
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 테이블 생성 실패: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def reset_table():
    """기존 데이터 삭제"""
    conn, cur = get_db_cursor()
    try:
        cur.execute("TRUNCATE TABLE glossary_terms RESTART IDENTITY")
        conn.commit()
        print("[OK] 기존 데이터 삭제 완료")
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 데이터 삭제 실패: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def insert_terms(dry_run=False):
    """용어 데이터 삽입"""
    if dry_run:
        print("\n[DRY RUN] 실제 삽입 없이 확인만 합니다.\n")
        stats = get_category_stats()
        print("=== 삽입 예정 통계 ===")
        for cat, count in sorted(stats.items()):
            print(f"  {cat}: {count}개")
        print(f"  ---\n  총: {len(GLOSSARY_TERMS)}개")
        return

    conn, cur = get_db_cursor()
    try:
        insert_sql = """
            INSERT INTO glossary_terms
                (term, term_en, category, definition, example, related_terms, is_slang, difficulty)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (term, category) DO UPDATE SET
                term_en = EXCLUDED.term_en,
                definition = EXCLUDED.definition,
                example = EXCLUDED.example,
                related_terms = EXCLUDED.related_terms,
                is_slang = EXCLUDED.is_slang,
                difficulty = EXCLUDED.difficulty
        """

        inserted = 0
        for term in GLOSSARY_TERMS:
            cur.execute(insert_sql, (
                term["term"],
                term.get("term_en"),
                term["category"],
                term["definition"],
                term.get("example"),
                term.get("related_terms"),
                term.get("is_slang", False),
                term.get("difficulty", "beginner")
            ))
            inserted += 1

        conn.commit()
        print(f"[OK] {inserted}개 용어 삽입 완료")

        # 통계 출력
        stats = get_category_stats()
        print("\n=== 카테고리별 통계 ===")
        for cat, count in sorted(stats.items()):
            print(f"  {cat}: {count}개")
        print(f"  ---\n  총: {len(GLOSSARY_TERMS)}개")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 데이터 삽입 실패: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def verify_insert():
    """삽입 결과 확인"""
    conn, cur = get_db_cursor(dict_cursor=True)
    try:
        # 총 개수
        cur.execute("SELECT COUNT(*) as cnt FROM glossary_terms")
        total = cur.fetchone()["cnt"]

        # 카테고리별 개수
        cur.execute("""
            SELECT category, COUNT(*) as cnt
            FROM glossary_terms
            GROUP BY category
            ORDER BY category
        """)
        categories = cur.fetchall()

        print("\n=== DB 저장 확인 ===")
        for cat in categories:
            print(f"  {cat['category']}: {cat['cnt']}개")
        print(f"  ---\n  총: {total}개")

        # 샘플 출력
        cur.execute("""
            SELECT term, term_en, category, difficulty
            FROM glossary_terms
            ORDER BY RANDOM()
            LIMIT 5
        """)
        samples = cur.fetchall()

        print("\n=== 샘플 데이터 ===")
        for s in samples:
            print(f"  [{s['category']}] {s['term']} ({s['term_en']}) - {s['difficulty']}")

    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="주식 용어 사전 DB 삽입")
    parser.add_argument("--reset", action="store_true", help="기존 데이터 삭제 후 재삽입")
    parser.add_argument("--dry-run", action="store_true", help="실제 삽입 없이 확인만")
    args = parser.parse_args()

    print("=" * 50)
    print("  주식 용어 사전 DB 삽입 스크립트")
    print("=" * 50)

    if args.dry_run:
        insert_terms(dry_run=True)
        return

    # 1. 테이블 생성
    print("\n[1/3] 테이블 생성 중...")
    create_table()

    # 2. 기존 데이터 삭제 (옵션)
    if args.reset:
        print("\n[2/3] 기존 데이터 삭제 중...")
        reset_table()
    else:
        print("\n[2/3] 기존 데이터 유지 (UPSERT 모드)")

    # 3. 데이터 삽입
    print("\n[3/3] 용어 데이터 삽입 중...")
    insert_terms()

    # 4. 결과 확인
    verify_insert()

    print("\n" + "=" * 50)
    print("  완료!")
    print("=" * 50)


if __name__ == "__main__":
    main()
