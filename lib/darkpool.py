"""
lib/darkpool.py - 다크풀/숏볼륨
Chartexchange Playwright(1차) → requests fallback(2차)
"""

import re
import requests
from lib.base import HEADERS


def _parse_short_volume_page(text: str) -> dict:
    """Chartexchange short-volume 페이지 텍스트 파싱"""
    result = {}

    # "Today's Short Volume is 5,675,876, which is 30.59% of today's total reported volume."
    sv_match = re.search(
        r"short volume is ([\d,]+).*?([\d.]+)% of today",
        text.lower()
    )
    if sv_match:
        result["short_volume"] = int(sv_match.group(1).replace(",", ""))
        result["short_volume_percent"] = float(sv_match.group(2))

    # "Over the past 30 days, the average Short Volume has been 29.46%."
    avg_match = re.search(
        r"average short volume has been ([\d.]+)%",
        text.lower()
    )
    if avg_match:
        result["avg_short_volume_30d"] = float(avg_match.group(1))

    return result


def _parse_overview_page(text: str) -> dict:
    """Chartexchange overview 페이지에서 On/Off Exchange 비율 파싱"""
    result = {}

    # "On/Off Exchange\t59%/41%"
    oe_match = re.search(
        r"on/off exchange\s*(\d+)%\s*/\s*(\d+)%",
        text.lower()
    )
    if oe_match:
        result["on_exchange_percent"] = int(oe_match.group(1))
        result["off_exchange_percent"] = int(oe_match.group(2))

    return result


def get_darkpool_data_playwright(ticker: str) -> dict:
    """Chartexchange Playwright 스크래핑 (숏볼륨 + 장외거래)"""
    dp_info = {
        "short_volume": 0,
        "short_volume_percent": 0,
        "avg_short_volume_30d": 0,
        "off_exchange_percent": 0,
        "source": None,
    }

    try:
        import asyncio
        from playwright.async_api import async_playwright

        async def _scrape():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                # 1. Short Volume 페이지
                try:
                    await page.goto(
                        f"https://chartexchange.com/symbol/nasdaq-{ticker.lower()}/short-volume/",
                        timeout=30000,
                        wait_until="networkidle",
                    )
                    await page.wait_for_timeout(3000)
                    body = await page.inner_text("body")

                    sv_data = _parse_short_volume_page(body)
                    if sv_data:
                        dp_info.update(sv_data)
                        dp_info["source"] = "Chartexchange"
                except Exception:
                    pass

                # 2. Overview 페이지 (Off Exchange %)
                try:
                    await page.goto(
                        f"https://chartexchange.com/symbol/nasdaq-{ticker.lower()}/",
                        timeout=30000,
                        wait_until="networkidle",
                    )
                    await page.wait_for_timeout(3000)
                    body = await page.inner_text("body")

                    oe_data = _parse_overview_page(body)
                    if oe_data:
                        dp_info.update(oe_data)
                        if not dp_info["source"]:
                            dp_info["source"] = "Chartexchange"
                except Exception:
                    pass

                await browser.close()

        asyncio.run(_scrape())

    except Exception as e:
        print(f"    ⚠️ 다크풀 Playwright 오류: {e}")

    return dp_info


def get_darkpool_data(ticker: str) -> dict:
    """다크풀/숏볼륨 데이터 (Playwright 우선, requests fallback)"""
    dp_info = {
        "darkpool_volume": 0,
        "darkpool_trades": 0,
        "dp_percent": 0,
        "short_volume_percent": 0,
        "off_exchange_percent": 0,
        "recent_dp_data": [],
        "source": None,
    }

    # 1차: Playwright (Chartexchange)
    try:
        pw_data = get_darkpool_data_playwright(ticker)
        if pw_data.get("source"):
            dp_info["short_volume_percent"] = pw_data.get("short_volume_percent", 0)
            dp_info["off_exchange_percent"] = pw_data.get("off_exchange_percent", 0)
            dp_info["darkpool_volume"] = pw_data.get("short_volume", 0)
            dp_info["avg_short_volume_30d"] = pw_data.get("avg_short_volume_30d", 0)
            dp_info["source"] = pw_data["source"]
    except Exception:
        pass

    # 2차: requests fallback (Chartexchange raw HTML)
    if not dp_info["source"]:
        try:
            ce_url = f"https://chartexchange.com/symbol/nasdaq-{ticker.lower()}/"
            resp = requests.get(ce_url, headers=HEADERS, timeout=10)

            if resp.status_code == 200:
                text = resp.text.lower()

                sv_match = re.search(r'short\s*(?:volume|vol)[:\s]*(\d+\.?\d*)%', text)
                if sv_match:
                    dp_info["short_volume_percent"] = float(sv_match.group(1))
                    dp_info["source"] = "Chartexchange"

                oe_match = re.search(r'off[- ]?exchange[:\s]*(\d+\.?\d*)%', text)
                if oe_match:
                    dp_info["off_exchange_percent"] = float(oe_match.group(1))
        except:
            pass

    # 경고 수준 판단
    if dp_info["short_volume_percent"] > 50:
        dp_info["warning"] = "⚠️ 숏 볼륨 50% 초과 - 숏 압력 높음"
    elif dp_info["short_volume_percent"] > 30:
        dp_info["warning"] = "🟡 숏 볼륨 30%+ - 주의"

    if dp_info["off_exchange_percent"] > 50:
        dp_info["dp_warning"] = "⚠️ 장외거래 50% 초과 - 다크풀 활발"

    return dp_info
