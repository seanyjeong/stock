"""
카카오 로그인 인증 모듈
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from db import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

# JWT 설정
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

# 카카오 OAuth 설정
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")
KAKAO_REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI", "")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")

security = HTTPBearer(auto_error=False)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    kakao_id: str
    nickname: str
    email: Optional[str]
    profile_image: Optional[str]
    is_approved: bool


class KakaoCallbackRequest(BaseModel):
    code: str


def create_users_table():
    """users 테이블 생성 (없으면)"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            kakao_id BIGINT UNIQUE NOT NULL,
            nickname VARCHAR(100) NOT NULL,
            email VARCHAR(255),
            profile_image TEXT,
            is_approved BOOLEAN DEFAULT FALSE,
            is_admin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_users_kakao_id ON users(kakao_id);
    """)
    conn.commit()
    cur.close()
    conn.close()


def create_jwt_token(user_id: int, kakao_id: int, nickname: str) -> str:
    """JWT 토큰 생성"""
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "kakao_id": str(kakao_id),
        "nickname": nickname,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt_token(token: str) -> dict:
    """JWT 토큰 검증"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[dict]:
    """현재 로그인한 사용자 정보 (옵셔널)"""
    if not credentials:
        return None

    payload = verify_jwt_token(credentials.credentials)

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE id = %s", (payload["sub"],))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다")

    return dict(user)


async def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """로그인 필수"""
    if not credentials:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    payload = verify_jwt_token(credentials.credentials)

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE id = %s", (payload["sub"],))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다")

    return dict(user)


async def require_approved_user(user: dict = Depends(require_user)) -> dict:
    """승인된 사용자만"""
    if not user.get("is_approved"):
        raise HTTPException(status_code=403, detail="승인되지 않은 사용자입니다")
    return user


@router.get("/kakao/login-url")
async def get_kakao_login_url():
    """카카오 로그인 URL 반환"""
    if not KAKAO_REST_API_KEY:
        raise HTTPException(status_code=500, detail="카카오 API 키가 설정되지 않았습니다")

    login_url = (
        f"https://kauth.kakao.com/oauth/authorize"
        f"?client_id={KAKAO_REST_API_KEY}"
        f"&redirect_uri={KAKAO_REDIRECT_URI}"
        f"&response_type=code"
    )
    return {"login_url": login_url}


@router.post("/kakao/callback")
async def kakao_callback(request: KakaoCallbackRequest):
    """카카오 OAuth 콜백 처리"""
    import httpx

    if not KAKAO_REST_API_KEY:
        raise HTTPException(status_code=500, detail="카카오 API 키가 설정되지 않았습니다")

    # 1. 인가 코드로 토큰 발급
    token_params = {
        "grant_type": "authorization_code",
        "client_id": KAKAO_REST_API_KEY,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "code": request.code,
    }
    if KAKAO_CLIENT_SECRET:
        token_params["client_secret"] = KAKAO_CLIENT_SECRET

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://kauth.kakao.com/oauth/token",
            data=token_params,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if token_response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"카카오 토큰 발급 실패: {token_response.text}"
        )

    token_data = token_response.json()
    kakao_access_token = token_data["access_token"]

    # 2. 사용자 정보 조회
    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {kakao_access_token}"},
        )

    if user_response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"카카오 사용자 정보 조회 실패: {user_response.text}"
        )

    kakao_user = user_response.json()
    kakao_id = kakao_user["id"]

    # 프로필 정보 추출
    kakao_account = kakao_user.get("kakao_account", {})
    profile = kakao_account.get("profile", {})
    properties = kakao_user.get("properties", {})

    nickname = profile.get("nickname") or properties.get("nickname") or "사용자"
    email = kakao_account.get("email")
    profile_image = profile.get("profile_image_url") or properties.get("profile_image")

    # 3. DB에 사용자 저장/업데이트
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # users 테이블이 없으면 생성
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            kakao_id BIGINT UNIQUE NOT NULL,
            nickname VARCHAR(100) NOT NULL,
            email VARCHAR(255),
            profile_image TEXT,
            is_approved BOOLEAN DEFAULT FALSE,
            is_admin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # 기존 사용자 확인
    cur.execute("SELECT * FROM users WHERE kakao_id = %s", (kakao_id,))
    user = cur.fetchone()

    if user:
        # 기존 사용자 업데이트
        cur.execute("""
            UPDATE users SET
                nickname = %s,
                email = %s,
                profile_image = %s,
                last_login = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING *
        """, (nickname, email, profile_image, user["id"]))
        user = cur.fetchone()
    else:
        # 신규 사용자 생성
        cur.execute("""
            INSERT INTO users (kakao_id, nickname, email, profile_image)
            VALUES (%s, %s, %s, %s)
            RETURNING *
        """, (kakao_id, nickname, email, profile_image))
        user = cur.fetchone()

    conn.commit()
    cur.close()
    conn.close()

    # 4. JWT 토큰 생성
    access_token = create_jwt_token(user["id"], user["kakao_id"], user["nickname"])

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "kakao_id": str(user["kakao_id"]),
            "nickname": user["nickname"],
            "email": user["email"],
            "profile_image": user["profile_image"],
            "is_approved": user["is_approved"],
        }
    }


@router.get("/me")
async def get_current_user_info(user: dict = Depends(require_user)):
    """현재 로그인한 사용자 정보"""
    return {
        "id": user["id"],
        "kakao_id": str(user["kakao_id"]),
        "nickname": user["nickname"],
        "email": user["email"],
        "profile_image": user["profile_image"],
        "is_approved": user["is_approved"],
    }


@router.post("/logout")
async def logout():
    """로그아웃 (클라이언트에서 토큰 삭제)"""
    return {"message": "로그아웃 되었습니다"}


# Admin endpoints
async def require_admin(user: dict = Depends(require_user)) -> dict:
    """관리자만 접근 가능"""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다")
    return user


@router.get("/admin/users")
async def list_users(admin: dict = Depends(require_admin)):
    """모든 사용자 목록 (관리자용)"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT id, kakao_id, nickname, email, profile_image,
               is_approved, is_admin, created_at, last_login
        FROM users
        ORDER BY created_at DESC
    """)
    users = cur.fetchall()

    cur.close()
    conn.close()

    return {
        "users": [
            {
                "id": u["id"],
                "kakao_id": str(u["kakao_id"]),
                "nickname": u["nickname"],
                "email": u["email"],
                "profile_image": u["profile_image"],
                "is_approved": u["is_approved"],
                "is_admin": u["is_admin"],
                "created_at": u["created_at"].isoformat() if u["created_at"] else None,
                "last_login": u["last_login"].isoformat() if u["last_login"] else None,
            }
            for u in users
        ],
        "total_count": len(users),
        "pending_count": sum(1 for u in users if not u["is_approved"]),
    }


@router.post("/admin/users/{user_id}/approve")
async def approve_user(user_id: int, admin: dict = Depends(require_admin)):
    """사용자 승인"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id, nickname FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()

    if not user:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    cur.execute("UPDATE users SET is_approved = TRUE WHERE id = %s", (user_id,))
    conn.commit()

    cur.close()
    conn.close()

    return {"message": f"{user['nickname']}님이 승인되었습니다", "user_id": user_id}


@router.post("/admin/users/{user_id}/revoke")
async def revoke_user(user_id: int, admin: dict = Depends(require_admin)):
    """사용자 승인 취소"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id, nickname FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()

    if not user:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    # 자신의 승인은 취소할 수 없음
    if user_id == admin["id"]:
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="자신의 승인은 취소할 수 없습니다")

    cur.execute("UPDATE users SET is_approved = FALSE WHERE id = %s", (user_id,))
    conn.commit()

    cur.close()
    conn.close()

    return {"message": f"{user['nickname']}님의 승인이 취소되었습니다", "user_id": user_id}


@router.delete("/admin/users/{user_id}")
async def delete_user(user_id: int, admin: dict = Depends(require_admin)):
    """사용자 삭제"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id, nickname FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()

    if not user:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    # 자신은 삭제할 수 없음
    if user_id == admin["id"]:
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="자신을 삭제할 수 없습니다")

    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()

    cur.close()
    conn.close()

    return {"message": f"{user['nickname']}님이 삭제되었습니다", "user_id": user_id}
