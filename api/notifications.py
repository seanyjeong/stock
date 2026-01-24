"""
Push Notifications API - 푸시 알림 관리
"""
import os
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from db import get_db
from api.auth import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

# VAPID keys should be set in environment variables
# Generate with: npx web-push generate-vapid-keys
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_EMAIL = os.getenv("VAPID_EMAIL", "mailto:admin@example.com")


class PushSubscription(BaseModel):
    endpoint: str
    keys: dict


class NotificationSettings(BaseModel):
    price_alerts: bool = True
    regsho_alerts: bool = True
    blog_alerts: bool = True


_table_initialized = False


def ensure_notifications_table():
    """알림 테이블이 없으면 생성"""
    global _table_initialized
    if _table_initialized:
        return

    try:
        conn = get_db()
        cur = conn.cursor()

        # Push 구독 테이블
        cur.execute("""
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                endpoint TEXT NOT NULL,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, endpoint)
            )
        """)

        # 알림 설정 테이블
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notification_settings (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                price_alerts BOOLEAN DEFAULT TRUE,
                regsho_alerts BOOLEAN DEFAULT TRUE,
                blog_alerts BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id)
            )
        """)

        conn.commit()
        cur.close()
        conn.close()
        _table_initialized = True
    except Exception:
        pass


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    """VAPID public key 반환 (클라이언트 구독용)"""
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return {"publicKey": VAPID_PUBLIC_KEY}


@router.post("/subscribe")
async def subscribe_push(subscription: PushSubscription, user: dict = Depends(get_current_user)):
    """Push 알림 구독 등록"""
    ensure_notifications_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, endpoint) DO UPDATE SET
                p256dh = EXCLUDED.p256dh,
                auth = EXCLUDED.auth,
                created_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (
            user["id"],
            subscription.endpoint,
            subscription.keys.get("p256dh", ""),
            subscription.keys.get("auth", "")
        ))

        result = cur.fetchone()
        conn.commit()

        return {"success": True, "subscription_id": result["id"]}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.delete("/subscribe")
async def unsubscribe_push(subscription: PushSubscription, user: dict = Depends(get_current_user)):
    """Push 알림 구독 해제"""
    ensure_notifications_table()
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            DELETE FROM push_subscriptions
            WHERE user_id = %s AND endpoint = %s
            RETURNING id
        """, (user["id"], subscription.endpoint))

        result = cur.fetchone()
        conn.commit()

        if not result:
            raise HTTPException(status_code=404, detail="구독 정보를 찾을 수 없습니다")

        return {"success": True}
    finally:
        cur.close()
        conn.close()


@router.get("/settings")
async def get_notification_settings(user: dict = Depends(get_current_user)):
    """알림 설정 조회"""
    ensure_notifications_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            SELECT price_alerts, regsho_alerts, blog_alerts
            FROM notification_settings
            WHERE user_id = %s
        """, (user["id"],))

        result = cur.fetchone()

        if not result:
            # 기본 설정 반환
            return {
                "price_alerts": True,
                "regsho_alerts": True,
                "blog_alerts": True
            }

        return result
    finally:
        cur.close()
        conn.close()


@router.put("/settings")
async def update_notification_settings(settings: NotificationSettings, user: dict = Depends(get_current_user)):
    """알림 설정 업데이트"""
    ensure_notifications_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            INSERT INTO notification_settings (user_id, price_alerts, regsho_alerts, blog_alerts)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                price_alerts = EXCLUDED.price_alerts,
                regsho_alerts = EXCLUDED.regsho_alerts,
                blog_alerts = EXCLUDED.blog_alerts,
                updated_at = CURRENT_TIMESTAMP
            RETURNING price_alerts, regsho_alerts, blog_alerts
        """, (user["id"], settings.price_alerts, settings.regsho_alerts, settings.blog_alerts))

        result = cur.fetchone()
        conn.commit()

        return {"success": True, "settings": result}
    finally:
        cur.close()
        conn.close()


@router.get("/subscriptions")
async def get_subscriptions(user: dict = Depends(get_current_user)):
    """사용자의 푸시 구독 목록 조회"""
    ensure_notifications_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            SELECT id, endpoint, created_at
            FROM push_subscriptions
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user["id"],))

        subscriptions = cur.fetchall()

        return {
            "subscriptions": [
                {
                    "id": s["id"],
                    "endpoint": s["endpoint"][:50] + "...",  # 보안상 일부만 표시
                    "created_at": s["created_at"].isoformat() if s["created_at"] else None
                }
                for s in subscriptions
            ],
            "count": len(subscriptions)
        }
    finally:
        cur.close()
        conn.close()
