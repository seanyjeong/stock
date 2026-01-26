"""
lib/news.py - 뉴스 수집
일반 뉴스 + 섹터별 특화 뉴스 (Google, Finviz, 섹터별 사이트)
"""

import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from lib.base import HEADERS


def get_news(stock) -> list:
    """yfinance 뉴스"""
    try:
        news = stock.news
        return news[:10] if news else []
    except:
        return []


def search_recent_news(ticker: str, days: int = 60) -> list:
    """구글 뉴스 검색 (최근 N일 필터)"""
    try:
        cutoff_date = datetime.now() - timedelta(days=days)

        url = f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        news = []
        for item in soup.find_all("item")[:15]:
            title = item.find("title")
            link = item.find("link")
            pub_date = item.find("pubDate")

            if title:
                date_str = pub_date.text if pub_date else ""
                try:
                    parsed_date = datetime.strptime(date_str[:16], "%a, %d %b %Y")
                    if parsed_date < cutoff_date:
                        continue
                except:
                    pass

                news.append({
                    "title": title.text,
                    "link": link.text if link else "",
                    "date": date_str
                })
        return news[:10]
    except:
        return []


def get_sector_news(ticker: str, sector: str, industry: str) -> dict:
    """섹터별 특화 뉴스 수집 (최근 60일)"""
    sector_news = {
        "general_news": [],
        "sector_specific": [],
        "catalysts": [],
        "source": None,
    }

    sector_lower = (sector or "").lower()
    industry_lower = (industry or "").lower()

    # 1. 일반 구글 뉴스 (백업)
    sector_news["general_news"] = search_recent_news(ticker, days=60)

    # 2. 섹터별 특화 뉴스
    if "biotech" in industry_lower or "pharma" in industry_lower or "healthcare" in sector_lower:
        sector_news["sector_specific"] = get_biotech_news(ticker)
        sector_news["source"] = "🧬 Biotech"
    elif "software" in industry_lower or "semiconductor" in industry_lower or "technology" in sector_lower:
        sector_news["sector_specific"] = get_tech_news(ticker)
        sector_news["source"] = "🤖 Tech/AI"
    elif "energy" in sector_lower or "oil" in industry_lower or "gas" in industry_lower:
        sector_news["sector_specific"] = get_energy_news(ticker)
        sector_news["source"] = "⛽ Energy"
    elif "auto" in industry_lower or "vehicle" in industry_lower or "ev" in industry_lower:
        sector_news["sector_specific"] = get_automotive_news(ticker)
        sector_news["source"] = "🚗 Automotive"
    elif "real estate" in sector_lower or "reit" in industry_lower:
        sector_news["sector_specific"] = get_realestate_news(ticker)
        sector_news["source"] = "🏠 Real Estate"
    elif "retail" in industry_lower or "e-commerce" in industry_lower or "store" in industry_lower:
        sector_news["sector_specific"] = get_retail_news(ticker)
        sector_news["source"] = "🛒 Retail"
    elif "food" in industry_lower or "beverage" in industry_lower or "consumer" in sector_lower:
        sector_news["sector_specific"] = get_consumer_news(ticker)
        sector_news["source"] = "🍔 Consumer"
    elif "bank" in industry_lower or "financial" in sector_lower or "insurance" in industry_lower:
        sector_news["sector_specific"] = get_financial_news(ticker)
        sector_news["source"] = "🏦 Financial"
    elif "industrial" in sector_lower or "aerospace" in industry_lower or "defense" in industry_lower:
        sector_news["sector_specific"] = get_industrial_news(ticker)
        sector_news["source"] = "🏭 Industrial"
    else:
        sector_news["sector_specific"] = get_finviz_news(ticker)
        sector_news["source"] = "📰 General"

    return sector_news


def _google_news_search(ticker: str, keywords_suffix: str, source_label: str, limit: int = 7) -> list:
    """공통 구글 뉴스 검색 헬퍼"""
    news = []
    try:
        keywords = f"{ticker} {keywords_suffix}"
        url = f"https://news.google.com/rss/search?q={keywords}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")

        for item in soup.find_all("item")[:limit]:
            title = item.find("title")
            if title:
                news.append({
                    "title": title.text,
                    "link": item.find("link").text if item.find("link") else "",
                    "source": source_label
                })
    except:
        pass
    return news


def get_biotech_news(ticker: str) -> list:
    """바이오텍 전용 뉴스 (BioSpace, FiercePharma)"""
    news = []

    # 1. BioSpace 검색
    try:
        url = f"https://www.biospace.com/search?q={ticker}"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            articles = soup.select("article h3 a, .article-title a")[:5]
            for a in articles:
                news.append({
                    "title": a.text.strip(),
                    "link": a.get("href", ""),
                    "source": "BioSpace"
                })
    except:
        pass

    # 2. 구글 뉴스 바이오텍 키워드
    news.extend(_google_news_search(ticker, "FDA OR clinical OR trial OR Phase OR approval", "Google/FDA", 5))

    return news


def get_tech_news(ticker: str) -> list:
    """AI/Tech 전용 뉴스"""
    return _google_news_search(ticker, "AI OR artificial intelligence OR GPU OR datacenter OR cloud", "Google/AI")


def get_energy_news(ticker: str) -> list:
    """에너지 전용 뉴스"""
    return _google_news_search(ticker, "oil OR gas OR drilling OR OPEC OR energy", "Google/Energy")


def get_automotive_news(ticker: str) -> list:
    """자동차/EV 전용 뉴스"""
    return _google_news_search(ticker, "EV OR electric vehicle OR battery OR autonomous OR Tesla OR charging", "Google/Auto")


def get_retail_news(ticker: str) -> list:
    """리테일/이커머스 전용 뉴스"""
    return _google_news_search(ticker, "retail OR e-commerce OR consumer spending OR sales OR store", "Google/Retail")


def get_consumer_news(ticker: str) -> list:
    """소비재/식품 전용 뉴스"""
    return _google_news_search(ticker, "food OR beverage OR consumer goods OR grocery OR brand", "Google/Consumer")


def get_financial_news(ticker: str) -> list:
    """금융/핀테크 전용 뉴스"""
    return _google_news_search(ticker, "bank OR fintech OR interest rate OR Fed OR lending OR credit", "Google/Finance")


def get_industrial_news(ticker: str) -> list:
    """산업재/제조 전용 뉴스"""
    return _google_news_search(ticker, "manufacturing OR industrial OR defense OR aerospace OR contract", "Google/Industrial")


def get_realestate_news(ticker: str) -> list:
    """부동산/리츠 전용 뉴스"""
    return _google_news_search(ticker, "REIT OR real estate OR property OR mortgage OR housing", "Google/RealEstate")


def get_finviz_news(ticker: str) -> list:
    """Finviz 뉴스 스크래핑"""
    news = []

    try:
        url = f"https://finviz.com/quote.ashx?t={ticker}"
        resp = requests.get(url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            news_table = soup.find("table", {"id": "news-table"})

            if news_table:
                rows = news_table.find_all("tr")[:7]
                for row in rows:
                    link = row.find("a")
                    if link:
                        news.append({
                            "title": link.text.strip(),
                            "link": link.get("href", ""),
                            "source": "Finviz"
                        })
    except:
        pass

    return news
