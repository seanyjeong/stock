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
    recommendation_alerts: bool = True  # 추천 종목 알림
    version_alerts: bool = True  # 버전 업데이트 알림


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
                recommendation_alerts BOOLEAN DEFAULT TRUE,
                version_alerts BOOLEAN DEFAULT TRUE,
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
            SELECT price_alerts, regsho_alerts, blog_alerts,
                   COALESCE(recommendation_alerts, TRUE) as recommendation_alerts,
                   COALESCE(version_alerts, TRUE) as version_alerts
            FROM notification_settings
            WHERE user_id = %s
        """, (user["id"],))

        result = cur.fetchone()

        if not result:
            # 기본 설정 반환
            return {
                "price_alerts": True,
                "regsho_alerts": True,
                "blog_alerts": True,
                "recommendation_alerts": True,
                "version_alerts": True
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
            INSERT INTO notification_settings (user_id, price_alerts, regsho_alerts, blog_alerts, recommendation_alerts, version_alerts)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                price_alerts = EXCLUDED.price_alerts,
                regsho_alerts = EXCLUDED.regsho_alerts,
                blog_alerts = EXCLUDED.blog_alerts,
                recommendation_alerts = EXCLUDED.recommendation_alerts,
                version_alerts = EXCLUDED.version_alerts,
                updated_at = CURRENT_TIMESTAMP
            RETURNING price_alerts, regsho_alerts, blog_alerts, recommendation_alerts, version_alerts
        """, (user["id"], settings.price_alerts, settings.regsho_alerts, settings.blog_alerts, settings.recommendation_alerts, settings.version_alerts))

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


def send_push_notification(subscription: dict, title: str, body: str, url: str = "/"):
    """단일 구독에 푸시 알림 발송"""
    from pywebpush import webpush, WebPushException

    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        return False

    try:
        webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {
                    "p256dh": subscription["p256dh"],
                    "auth": subscription["auth"]
                }
            },
            data=json.dumps({
                "title": title,
                "body": body,
                "url": url,
                "icon": "/icon-192.png"
            }),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_EMAIL}
        )
        return True
    except WebPushException as e:
        print(f"Push failed: {e}")
        # 410 Gone = subscription expired, should delete
        if e.response and e.response.status_code == 410:
            return "expired"
        return False


def send_recommendation_notification(rec_type: str, count: int):
    """추천 종목 알림 발송 (스캐너에서 호출)

    Args:
        rec_type: 'day_trade', 'swing', 'longterm'
        count: 추천 종목 수
    """
    ensure_notifications_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    type_labels = {
        'day_trade': '단타',
        'swing': '스윙',
        'longterm': '장기'
    }
    label = type_labels.get(rec_type, rec_type)

    try:
        # recommendation_alerts가 켜진 사용자의 구독 정보 조회
        cur.execute("""
            SELECT ps.id, ps.user_id, ps.endpoint, ps.p256dh, ps.auth
            FROM push_subscriptions ps
            JOIN notification_settings ns ON ps.user_id = ns.user_id
            WHERE ns.recommendation_alerts = TRUE
        """)
        subscriptions = cur.fetchall()

        # 설정이 없는 사용자도 기본값(TRUE)으로 알림 발송
        cur.execute("""
            SELECT ps.id, ps.user_id, ps.endpoint, ps.p256dh, ps.auth
            FROM push_subscriptions ps
            WHERE NOT EXISTS (
                SELECT 1 FROM notification_settings ns WHERE ns.user_id = ps.user_id
            )
        """)
        subscriptions.extend(cur.fetchall())

        sent = 0
        expired = []

        for sub in subscriptions:
            result = send_push_notification(
                sub,
                "달러농장",
                f"새로운 {label} 추천 종목 {count}개가 등록되었습니다!",
                f"/?type={rec_type}"
            )
            if result is True:
                sent += 1
            elif result == "expired":
                expired.append(sub["id"])

        # 만료된 구독 삭제
        if expired:
            cur.execute("DELETE FROM push_subscriptions WHERE id = ANY(%s)", (expired,))
            conn.commit()

        return {"sent": sent, "expired": len(expired)}
    finally:
        cur.close()
        conn.close()


@router.post("/send-recommendation")
async def trigger_recommendation_notification(rec_type: str = "day_trade", count: int = 5):
    """추천 종목 알림 트리거 (내부용)"""
    # TODO: 내부 호출 인증 추가 필요
    result = send_recommendation_notification(rec_type, count)
    return result


def send_version_notification(new_version: str):
    """버전 업데이트 알림 발송

    Args:
        new_version: 새 버전 문자열 (예: "2.11.0")
    """
    ensure_notifications_table()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # version_alerts가 켜진 사용자의 구독 정보 조회
        cur.execute("""
            SELECT ps.id, ps.user_id, ps.endpoint, ps.p256dh, ps.auth
            FROM push_subscriptions ps
            JOIN notification_settings ns ON ps.user_id = ns.user_id
            WHERE COALESCE(ns.version_alerts, TRUE) = TRUE
        """)
        subscriptions = cur.fetchall()

        # 설정이 없는 사용자도 기본값(TRUE)으로 알림 발송
        cur.execute("""
            SELECT ps.id, ps.user_id, ps.endpoint, ps.p256dh, ps.auth
            FROM push_subscriptions ps
            WHERE NOT EXISTS (
                SELECT 1 FROM notification_settings ns WHERE ns.user_id = ps.user_id
            )
        """)
        subscriptions.extend(cur.fetchall())

        sent = 0
        expired = []

        for sub in subscriptions:
            result = send_push_notification(
                sub,
                "달러농장 업데이트",
                f"v{new_version}으로 업데이트되었습니다!",
                "/settings"
            )
            if result is True:
                sent += 1
            elif result == "expired":
                expired.append(sub["id"])

        # 만료된 구독 삭제
        if expired:
            cur.execute("DELETE FROM push_subscriptions WHERE id = ANY(%s)", (expired,))
            conn.commit()

        return {"sent": sent, "expired": len(expired)}
    finally:
        cur.close()
        conn.close()
