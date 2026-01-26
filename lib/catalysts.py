"""
lib/catalysts.py - 촉매 이벤트
실적 발표, 섹터별 특화 촉매 (FDA, 임상, EV, 금리 등)
"""

import requests
from datetime import datetime
from bs4 import BeautifulSoup
from lib.base import HEADERS


def get_catalyst_calendar(stock) -> dict:
    """어닝, FDA, 컨퍼런스 등 촉매 일정"""
    catalyst_info = {
        "next_earnings": None,
        "earnings_estimate": None,
        "recent_earnings_surprise": None,
        "ex_dividend_date": None,
        "upcoming_events": [],
    }

    try:
        info = stock.info

        earnings_date = info.get('earningsDate')
        if earnings_date:
            if isinstance(earnings_date, list) and earnings_date:
                catalyst_info["next_earnings"] = datetime.fromtimestamp(earnings_date[0]).strftime('%Y-%m-%d')
            elif isinstance(earnings_date, (int, float)):
                catalyst_info["next_earnings"] = datetime.fromtimestamp(earnings_date).strftime('%Y-%m-%d')

        earnings_hist = stock.earnings_history if hasattr(stock, 'earnings_history') else None
        if earnings_hist is not None and not earnings_hist.empty:
            latest = earnings_hist.iloc[-1] if len(earnings_hist) > 0 else None
            if latest is not None:
                surprise = latest.get('surprisePercent')
                if surprise:
                    catalyst_info["recent_earnings_surprise"] = f"{surprise:.1f}%"

        ex_div = info.get('exDividendDate')
        if ex_div:
            catalyst_info["ex_dividend_date"] = datetime.fromtimestamp(ex_div).strftime('%Y-%m-%d')

        catalyst_info["earnings_estimate"] = info.get('targetMeanPrice')

    except Exception as e:
        print(f"    ⚠️ Catalyst 오류: {e}")

    return catalyst_info


def _google_catalyst_search(ticker: str, keywords_suffix: str, limit: int = 5) -> list:
    """공통 구글 뉴스 촉매 검색 헬퍼"""
    results = []
    try:
        keywords = f"{ticker} {keywords_suffix}"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:limit]:
            title = item.find("title")
            if title:
                results.append({
                    "headline": title.text,
                    "date": item.find("pubDate").text if item.find("pubDate") else ""
                })
    except:
        pass
    return results


def get_biotech_catalysts(ticker: str, company_name: str) -> dict:
    """바이오텍 촉매 분석 (FDA, 임상시험)"""
    catalysts = {
        "fda_status": [],
        "clinical_trials": [],
        "pdufa_dates": [],
        "fast_track": False,
        "breakthrough": False,
        "orphan_drug": False,
    }

    # 1. FDA 관련 뉴스 검색
    try:
        keywords = f"{ticker} FDA approval OR Fast Track OR PDUFA OR BLA OR NDA"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:5]:
            title = item.find("title")
            if title:
                title_lower = title.text.lower()

                if "fast track" in title_lower:
                    catalysts["fast_track"] = True
                if "breakthrough" in title_lower:
                    catalysts["breakthrough"] = True
                if "orphan" in title_lower:
                    catalysts["orphan_drug"] = True
                if "pdufa" in title_lower:
                    catalysts["pdufa_dates"].append(title.text)

                catalysts["fda_status"].append({
                    "headline": title.text,
                    "date": item.find("pubDate").text if item.find("pubDate") else ""
                })
    except:
        pass

    # 2. ClinicalTrials.gov API
    try:
        if company_name:
            words = company_name.replace(",", "").replace(".", "").split()[:2]
            search_term = " ".join(words)
        else:
            search_term = ticker

        ct_url = f"https://clinicaltrials.gov/api/v2/studies?query.spons={search_term}&pageSize=10"
        resp = requests.get(ct_url, headers={"Accept": "application/json"}, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            studies = data.get("studies", [])

            for study in studies[:5]:
                protocol = study.get("protocolSection", {})
                id_module = protocol.get("identificationModule", {})
                status_module = protocol.get("statusModule", {})
                design_module = protocol.get("designModule", {})
                sponsor_module = protocol.get("sponsorCollaboratorsModule", {})

                lead_sponsor = sponsor_module.get("leadSponsor", {}).get("name", "")
                if company_name and company_name.split()[0].lower() not in lead_sponsor.lower():
                    continue

                phase_list = design_module.get("phases", [])
                phase = phase_list[0] if phase_list else "N/A"

                catalysts["clinical_trials"].append({
                    "nct_id": id_module.get("nctId", ""),
                    "title": id_module.get("briefTitle", "")[:80],
                    "phase": phase,
                    "status": status_module.get("overallStatus", ""),
                    "completion": status_module.get("primaryCompletionDateStruct", {}).get("date", "N/A"),
                    "sponsor": lead_sponsor[:40]
                })
    except Exception:
        pass

    return catalysts


def get_automotive_catalysts(ticker: str, company_name: str) -> dict:
    """자동차/EV 촉매 분석"""
    catalysts = {
        "production_numbers": [],
        "new_models": [],
        "ev_credits": False,
        "battery_partnership": False,
        "autonomous_update": False,
    }

    try:
        keywords = f"{ticker} production OR delivery OR new model OR EV tax credit OR battery"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:5]:
            title = item.find("title")
            if title:
                title_lower = title.text.lower()

                if "production" in title_lower or "deliver" in title_lower:
                    catalysts["production_numbers"].append(title.text)
                if "new model" in title_lower or "launch" in title_lower:
                    catalysts["new_models"].append(title.text)
                if "ev credit" in title_lower or "tax credit" in title_lower:
                    catalysts["ev_credits"] = True
                if "battery" in title_lower and "partner" in title_lower:
                    catalysts["battery_partnership"] = True
                if "autonomous" in title_lower or "self-driving" in title_lower:
                    catalysts["autonomous_update"] = True
    except:
        pass

    return catalysts


def get_retail_catalysts(ticker: str, company_name: str) -> dict:
    """리테일 촉매 분석"""
    catalysts = {
        "same_store_sales": [],
        "ecommerce_growth": [],
        "holiday_sales": False,
        "store_openings": [],
        "inventory_update": False,
    }

    try:
        keywords = f"{ticker} same-store sales OR e-commerce OR holiday sales OR store opening"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:5]:
            title = item.find("title")
            if title:
                title_lower = title.text.lower()

                if "same-store" in title_lower or "comparable" in title_lower:
                    catalysts["same_store_sales"].append(title.text)
                if "e-commerce" in title_lower or "online sales" in title_lower:
                    catalysts["ecommerce_growth"].append(title.text)
                if "holiday" in title_lower or "black friday" in title_lower:
                    catalysts["holiday_sales"] = True
                if "open" in title_lower and "store" in title_lower:
                    catalysts["store_openings"].append(title.text)
                if "inventory" in title_lower:
                    catalysts["inventory_update"] = True
    except:
        pass

    return catalysts


def get_financial_catalysts(ticker: str, company_name: str) -> dict:
    """금융 촉매 분석"""
    catalysts = {
        "fed_rate_impact": [],
        "loan_growth": [],
        "regulatory_news": [],
        "dividend_update": False,
        "capital_ratio": False,
    }

    try:
        keywords = f"{ticker} Fed rate OR interest rate OR loan growth OR regulation OR dividend"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:5]:
            title = item.find("title")
            if title:
                title_lower = title.text.lower()

                if "fed" in title_lower or "interest rate" in title_lower:
                    catalysts["fed_rate_impact"].append(title.text)
                if "loan" in title_lower and ("growth" in title_lower or "demand" in title_lower):
                    catalysts["loan_growth"].append(title.text)
                if "regulat" in title_lower or "compliance" in title_lower:
                    catalysts["regulatory_news"].append(title.text)
                if "dividend" in title_lower:
                    catalysts["dividend_update"] = True
                if "capital" in title_lower and "ratio" in title_lower:
                    catalysts["capital_ratio"] = True
    except:
        pass

    return catalysts


def get_industrial_catalysts(ticker: str, company_name: str) -> dict:
    """산업재 촉매 분석"""
    catalysts = {
        "contracts": [],
        "gov_spending": [],
        "defense_budget": [],
        "supply_chain": False,
        "pmi_update": False,
    }

    try:
        keywords = f"{ticker} contract OR government OR defense budget OR supply chain OR manufacturing"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:5]:
            title = item.find("title")
            if title:
                title_lower = title.text.lower()

                if "contract" in title_lower and ("win" in title_lower or "award" in title_lower):
                    catalysts["contracts"].append(title.text)
                if "government" in title_lower and "spend" in title_lower:
                    catalysts["gov_spending"].append(title.text)
                if "defense" in title_lower and "budget" in title_lower:
                    catalysts["defense_budget"].append(title.text)
                if "supply chain" in title_lower:
                    catalysts["supply_chain"] = True
                if "pmi" in title_lower or "manufacturing index" in title_lower:
                    catalysts["pmi_update"] = True
    except:
        pass

    return catalysts


def get_realestate_catalysts(ticker: str, company_name: str) -> dict:
    """부동산/리츠 촉매 분석"""
    catalysts = {
        "rate_impact": [],
        "occupancy": [],
        "acquisitions": [],
        "cap_rate": False,
        "noi_growth": False,
    }

    try:
        keywords = f"{ticker} interest rate OR occupancy OR acquisition OR cap rate OR NOI"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:5]:
            title = item.find("title")
            if title:
                title_lower = title.text.lower()

                if "rate" in title_lower and ("cut" in title_lower or "hike" in title_lower):
                    catalysts["rate_impact"].append(title.text)
                if "occupancy" in title_lower:
                    catalysts["occupancy"].append(title.text)
                if "acqui" in title_lower or "purchase" in title_lower:
                    catalysts["acquisitions"].append(title.text)
                if "cap rate" in title_lower:
                    catalysts["cap_rate"] = True
                if "noi" in title_lower or "net operating" in title_lower:
                    catalysts["noi_growth"] = True
    except:
        pass

    return catalysts
