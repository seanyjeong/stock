"""
lib/regsho.py - RegSHO Threshold List
NASDAQ RegSHO 등재 확인 + 과거 데이터 기반 연속등재일 계산
"""

import requests
from datetime import datetime, timedelta
from lib.base import get_db, HEADERS


def fetch_historical_regsho(ticker: str, days: int = 20) -> dict:
    """
    NASDAQ RegSHO 과거 20거래일 파일에서 연속등재일 계산

    URL: https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth{YYYYMMDD}.txt
    포맷: Symbol|Security Name|Market Category|Reg SHO Threshold Flag|Rule 3210|Filler

    Returns: {
        "listed": bool,        # 현재 등재 여부
        "days": int,           # 연속 등재일수
        "first_seen": str,     # 최초 등재일 (YYYY-MM-DD)
        "history": [str],      # 등재된 날짜 목록
        "total_checked": int,  # 체크한 총 거래일 수
    }
    """
    result = {
        "listed": False,
        "days": 0,
        "first_seen": None,
        "history": [],
        "total_checked": 0,
    }

    ticker_upper = ticker.upper()
    consecutive_days = 0
    listed_dates = []
    found_gap = False  # 연속 끊김 감지

    # 오늘부터 거꾸로 거래일(월-금) 탐색
    current_date = datetime.now()
    checked = 0
    skipped = 0  # 404 등 실패 카운트

    while checked < days and skipped < 10:
        # 주말 건너뛰기
        if current_date.weekday() >= 5:  # 토(5), 일(6)
            current_date -= timedelta(days=1)
            continue

        date_str = current_date.strftime("%Y%m%d")
        url = f"https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth{date_str}.txt"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                text = resp.text
                # HTML 응답 감지 (공휴일 등 NASDAQ이 에러페이지 반환)
                if text.strip().startswith('<!') or text.strip().startswith('<html'):
                    skipped += 1
                    current_date -= timedelta(days=1)
                    continue

                text_upper = text.upper()
                # 파일에서 ticker 존재 여부 체크
                # 포맷: Symbol|Security Name|...
                found = False
                for line in text_upper.split('\n'):
                    parts = line.split('|')
                    if parts and parts[0].strip() == ticker_upper:
                        found = True
                        break

                if found:
                    if not found_gap:
                        consecutive_days += 1
                    listed_dates.append(current_date.strftime("%Y-%m-%d"))
                else:
                    if consecutive_days > 0:
                        found_gap = True  # 연속 끊김

                checked += 1
                skipped = 0  # 성공하면 리셋
            elif resp.status_code == 404:
                # 공휴일 등 파일 없음 - 스킵
                skipped += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1

        current_date -= timedelta(days=1)

    if listed_dates:
        result["listed"] = consecutive_days > 0
        result["days"] = consecutive_days
        result["first_seen"] = listed_dates[-1] if listed_dates else None
        result["history"] = listed_dates
    result["total_checked"] = checked

    return result


def check_regsho(ticker: str) -> dict:
    """RegSHO 확인 - NASDAQ 과거 데이터 우선, DB fallback"""

    # 1차: fetch_historical_regsho() 호출 (정확한 연속일)
    try:
        hist = fetch_historical_regsho(ticker)
        if hist.get("listed"):
            return {
                "listed": True,
                "days": hist["days"],
                "first_seen": hist.get("first_seen"),
                "history": hist.get("history", []),
                "source": "nasdaq_historical",
            }
        # 과거 데이터에서 미등재 확인된 경우
        if hist.get("total_checked", 0) >= 3:
            return {"listed": False, "days": 0, "source": "nasdaq_historical"}
    except Exception:
        pass

    # 2차: DB fallback (NASDAQ 접근 불가시)
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT (CURRENT_DATE - first_seen_date) as days_on_list
                FROM regsho_list
                WHERE ticker = %s AND collected_at > NOW() - INTERVAL '7 days'
                LIMIT 1
            """, (ticker,))
            result = cur.fetchone()
            conn.close()
            if result:
                return {"listed": True, "days": result[0] or 1, "source": "db"}
    except:
        pass

    # 3차: NASDAQ 당일 파일 fallback
    try:
        url = "https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth.txt"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if ticker.upper() in resp.text.upper():
            return {"listed": True, "days": 0, "source": "nasdaq_today"}
    except:
        pass

    return {"listed": False, "days": 0}
