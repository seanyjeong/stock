"""
Profile API - 투자성향 프로필 관리
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from db import get_db
from api.auth import require_user

router = APIRouter(prefix="/api/profile", tags=["profile"])


# Pydantic models
class ProfileCreate(BaseModel):
    experience: str  # 'under_1y', '1_3y', 'over_3y'
    risk_tolerance: str  # 'under_5', 'under_10', 'under_20', 'over_20'
    duration_preference: str  # 'day', 'swing', 'long', 'mixed'
    profit_expectation: str  # 'stable', 'moderate', 'aggressive'
    sectors: List[str]  # ['tech', 'bio', 'energy', 'finance', 'all']


class ProfileResponse(BaseModel):
    id: int
    user_id: int
    experience: str
    risk_tolerance: str
    duration_preference: str
    profit_expectation: str
    sectors: List[str]
    profile_type: str  # 'conservative', 'balanced', 'aggressive'
    created_at: str
    updated_at: str


_table_initialized = False


def ensure_profile_table():
    """user_profiles 테이블이 없으면 생성 (lazy initialization)"""
    global _table_initialized
    if _table_initialized:
        return

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                experience VARCHAR(20) NOT NULL,
                risk_tolerance VARCHAR(20) NOT NULL,
                duration_preference VARCHAR(20) NOT NULL,
                profit_expectation VARCHAR(20) NOT NULL,
                sectors TEXT[] NOT NULL,
                profile_type VARCHAR(20) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)
        """)
        conn.commit()
        cur.close()
        conn.close()
        _table_initialized = True
    except Exception:
        # users 테이블이 없으면 나중에 다시 시도
        pass


def calculate_profile_type(data: ProfileCreate) -> str:
    """
    성향 계산 알고리즘
    점수 = 경험(0-2) + 리스크허용(0-3) + 기간선호(0-3) + 수익기대(0-3)
    총점 범위: 0~11
    - 0~3점: conservative (안정형)
    - 4~7점: balanced (균형형)
    - 8~11점: aggressive (공격형)
    """
    score = 0

    # 경험 점수 (0-2)
    experience_scores = {'under_1y': 0, '1_3y': 1, 'over_3y': 2}
    score += experience_scores.get(data.experience, 0)

    # 리스크 허용 점수 (0-3)
    risk_scores = {'under_5': 0, 'under_10': 1, 'under_20': 2, 'over_20': 3}
    score += risk_scores.get(data.risk_tolerance, 0)

    # 기간 선호 점수 (0-3)
    duration_scores = {'long': 0, 'mixed': 1, 'swing': 2, 'day': 3}
    score += duration_scores.get(data.duration_preference, 0)

    # 수익 기대 점수 (0-3)
    profit_scores = {'stable': 0, 'moderate': 2, 'aggressive': 3}
    score += profit_scores.get(data.profit_expectation, 0)

    # 성향 분류
    if score <= 3:
        return 'conservative'
    elif score <= 7:
        return 'balanced'
    else:
        return 'aggressive'


@router.get("/check")
async def check_profile(user: dict = Depends(require_user)):
    """프로필 존재 여부 확인"""
    ensure_profile_table()
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM user_profiles WHERE user_id = %s)",
            (user["id"],)
        )
        exists = cur.fetchone()[0]
        return {"has_profile": exists}
    finally:
        cur.close()
        conn.close()


@router.get("/")
async def get_profile(user: dict = Depends(require_user)):
    """프로필 조회"""
    ensure_profile_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            SELECT id, user_id, experience, risk_tolerance, duration_preference,
                   profit_expectation, sectors, profile_type, created_at, updated_at
            FROM user_profiles
            WHERE user_id = %s
        """, (user["id"],))

        profile = cur.fetchone()

        if not profile:
            raise HTTPException(status_code=404, detail="프로필이 없습니다")

        return {
            "id": profile["id"],
            "user_id": profile["user_id"],
            "experience": profile["experience"],
            "risk_tolerance": profile["risk_tolerance"],
            "duration_preference": profile["duration_preference"],
            "profit_expectation": profile["profit_expectation"],
            "sectors": profile["sectors"],
            "profile_type": profile["profile_type"],
            "created_at": profile["created_at"].isoformat() if profile["created_at"] else None,
            "updated_at": profile["updated_at"].isoformat() if profile["updated_at"] else None
        }
    finally:
        cur.close()
        conn.close()


@router.post("/")
async def create_profile(data: ProfileCreate, user: dict = Depends(require_user)):
    """프로필 생성 (최초)"""
    ensure_profile_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # 이미 프로필이 있는지 확인
        cur.execute(
            "SELECT id FROM user_profiles WHERE user_id = %s",
            (user["id"],)
        )
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="프로필이 이미 존재합니다")

        # 성향 계산
        profile_type = calculate_profile_type(data)

        # 프로필 생성
        cur.execute("""
            INSERT INTO user_profiles
            (user_id, experience, risk_tolerance, duration_preference, profit_expectation, sectors, profile_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, user_id, experience, risk_tolerance, duration_preference,
                      profit_expectation, sectors, profile_type, created_at, updated_at
        """, (
            user["id"],
            data.experience,
            data.risk_tolerance,
            data.duration_preference,
            data.profit_expectation,
            data.sectors,
            profile_type
        ))

        profile = cur.fetchone()
        conn.commit()

        return {
            "id": profile["id"],
            "user_id": profile["user_id"],
            "experience": profile["experience"],
            "risk_tolerance": profile["risk_tolerance"],
            "duration_preference": profile["duration_preference"],
            "profit_expectation": profile["profit_expectation"],
            "sectors": profile["sectors"],
            "profile_type": profile["profile_type"],
            "created_at": profile["created_at"].isoformat() if profile["created_at"] else None,
            "updated_at": profile["updated_at"].isoformat() if profile["updated_at"] else None
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.put("/")
async def update_profile(data: ProfileCreate, user: dict = Depends(require_user)):
    """프로필 수정 (다시하기)"""
    ensure_profile_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # 성향 재계산
        profile_type = calculate_profile_type(data)

        # 프로필 업데이트
        cur.execute("""
            UPDATE user_profiles
            SET experience = %s,
                risk_tolerance = %s,
                duration_preference = %s,
                profit_expectation = %s,
                sectors = %s,
                profile_type = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
            RETURNING id, user_id, experience, risk_tolerance, duration_preference,
                      profit_expectation, sectors, profile_type, created_at, updated_at
        """, (
            data.experience,
            data.risk_tolerance,
            data.duration_preference,
            data.profit_expectation,
            data.sectors,
            profile_type,
            user["id"]
        ))

        profile = cur.fetchone()

        if not profile:
            raise HTTPException(status_code=404, detail="프로필이 없습니다")

        conn.commit()

        return {
            "id": profile["id"],
            "user_id": profile["user_id"],
            "experience": profile["experience"],
            "risk_tolerance": profile["risk_tolerance"],
            "duration_preference": profile["duration_preference"],
            "profit_expectation": profile["profit_expectation"],
            "sectors": profile["sectors"],
            "profile_type": profile["profile_type"],
            "created_at": profile["created_at"].isoformat() if profile["created_at"] else None,
            "updated_at": profile["updated_at"].isoformat() if profile["updated_at"] else None
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
