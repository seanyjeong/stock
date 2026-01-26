"""
lib/borrow.py - 대차 데이터
Zero Borrow 감지, Borrow Rate, 대차가능 주식 수
"""

import re
import requests
from lib.base import HEADERS


def get_borrow_data_playwright(ticker: str) -> dict:
    """Playwright로 Chartexchange에서 Borrow Rate 정확하게 수집"""
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            # Stealth 적용
            stealth = Stealth()
            stealth.apply_stealth_sync(context)
            page = context.new_page()

            result = {
                "is_zero_borrow": None,
                "is_hard_to_borrow": None,
                "borrow_rate": None,
                "available_shares": None,
                "short_interest_shares": None,
                "avg_volume": None,
                "days_to_cover": None,
                "si_date": None,
                "source": None
            }

            # 1. Chartexchange 시도 (Short Interest 페이지)
            try:
                url = f"https://chartexchange.com/symbol/nasdaq-{ticker.lower()}/short-interest/"
                page.goto(url, timeout=20000)
                page.wait_for_load_state("networkidle", timeout=15000)

                content = page.content().lower()

                # Borrow Fee Rate 추출 (다양한 패턴)
                borrow_patterns = [
                    r'borrow\s*fee[:\s]*(\d+\.?\d*)%',
                    r'fee\s*rate[:\s]*(\d+\.?\d*)%',
                    r'cost\s*to\s*borrow[:\s]*(\d+\.?\d*)%',
                    r'ctb[:\s]*(\d+\.?\d*)%',
                    r'(\d+\.?\d*)%\s*(?:borrow|fee|ctb)',
                ]

                for pattern in borrow_patterns:
                    match = re.search(pattern, content)
                    if match:
                        rate = float(match.group(1))
                        if rate > 0:
                            result["borrow_rate"] = rate
                            result["source"] = "Chartexchange"
                            break

                # Short Interest % 추출
                si_patterns = [
                    r'short\s*interest[:\s]*(\d+\.?\d*)%',
                    r'si[:\s]*(\d+\.?\d*)%',
                    r'(\d+\.?\d*)%\s*of\s*float',
                ]
                for pattern in si_patterns:
                    match = re.search(pattern, content)
                    if match:
                        result["short_float_percent"] = float(match.group(1))
                        break

                # Zero/Hard to Borrow 감지
                result["is_zero_borrow"] = "zero borrow" in content or "no shares" in content
                result["is_hard_to_borrow"] = "hard to borrow" in content or "htb" in content

                if result["is_zero_borrow"]:
                    result["borrow_rate"] = 999.0
                    result["available_shares"] = 0

            except Exception:
                pass

            # 2. Shortablestocks 시도 (데이터가 더 정확함)
            if result["borrow_rate"] is None:
                try:
                    url = f"https://www.shortablestocks.com/?{ticker}"
                    page.goto(url, timeout=20000)
                    page.wait_for_selector("#borrowdata", timeout=10000)
                    page.wait_for_timeout(3000)

                    borrow_div = page.query_selector("#borrowdata")
                    if borrow_div:
                        borrow_text = borrow_div.inner_text()

                        lines = borrow_text.split('\n')
                        for line in lines:
                            match = re.match(r'(\d+\.?\d*)%\s+(-?\d+\.?\d*)%\s+(\d+)', line.strip())
                            if match:
                                result["borrow_rate"] = float(match.group(1))
                                result["available_shares"] = int(match.group(3))
                                result["source"] = "shortablestocks.com"
                                break

                    content = page.content().lower()

                    if "zero borrow" in content:
                        result["is_zero_borrow"] = True
                        result["borrow_rate"] = 999.0
                        result["available_shares"] = 0

                    if "hard to borrow" in content:
                        result["is_hard_to_borrow"] = True

                    if result["borrow_rate"] and result["borrow_rate"] >= 100:
                        result["is_hard_to_borrow"] = True

                except Exception:
                    pass

            browser.close()
            return result

    except Exception as e:
        print(f"  ⚠️ Playwright Borrow 수집 실패: {e}")
        return {
            "is_zero_borrow": None,
            "is_hard_to_borrow": None,
            "borrow_rate": None,
            "available_shares": None,
            "short_interest_shares": None,
            "avg_volume": None,
            "days_to_cover": None,
            "si_date": None,
            "source": None
        }


def get_borrow_data(ticker: str) -> dict:
    """Borrow Rate 수집 (Playwright 우선, requests fallback)"""

    # 1. Playwright로 정확한 데이터 시도
    result = get_borrow_data_playwright(ticker)

    # Playwright 성공 시 반환
    if result.get("borrow_rate") is not None or result.get("is_zero_borrow"):
        return result

    # 2. Fallback: requests로 기본 데이터 수집
    url = f"https://www.shortablestocks.com/?{ticker}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        text = resp.text

        is_zero_borrow = "zero borrow" in text.lower()
        is_hard_to_borrow = "hard to borrow" in text.lower()

        si_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})\s+([\d,]+)\s+([\d,]+)\s+(\d+)', text)

        short_interest_shares = None
        avg_volume = None
        days_to_cover = None
        si_date = None

        if si_match:
            si_date = si_match.group(1)
            short_interest_shares = int(si_match.group(2).replace(',', ''))
            avg_volume = int(si_match.group(3).replace(',', ''))
            days_to_cover = int(si_match.group(4))

        borrow_rate = None
        available_shares = None

        if is_zero_borrow:
            borrow_rate = 999.0
            available_shares = 0

        return {
            "is_zero_borrow": is_zero_borrow,
            "is_hard_to_borrow": is_hard_to_borrow,
            "borrow_rate": borrow_rate,
            "available_shares": available_shares,
            "short_interest_shares": short_interest_shares,
            "avg_volume": avg_volume,
            "days_to_cover": days_to_cover,
            "si_date": si_date,
            "source": "shortablestocks.com (limited)"
        }

    except Exception as e:
        print(f"  ⚠️ Borrow 데이터 수집 실패: {e}")
        return {
            "is_zero_borrow": None,
            "is_hard_to_borrow": None,
            "borrow_rate": None,
            "available_shares": None,
            "short_interest_shares": None,
            "avg_volume": None,
            "days_to_cover": None,
            "si_date": None,
            "source": None
        }


def get_fintel_data(ticker: str) -> dict:
    """Fintel에서 추가 데이터 시도"""
    url = f"https://fintel.io/ss/us/{ticker.lower()}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        text = resp.text

        score_match = re.search(r'short\s*squeeze\s*score[:\s]*(\d+\.?\d*)', text.lower())
        squeeze_score = float(score_match.group(1)) if score_match else None

        return {
            "fintel_squeeze_score": squeeze_score,
            "source": "fintel.io"
        }
    except:
        return {"fintel_squeeze_score": None, "source": None}
