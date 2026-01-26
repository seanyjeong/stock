"""
lib/sec.py - SEC EDGAR
SEC 공시 분석 (워런트/희석/빚/락업), FTD, 8-K 이벤트
"""

import re
import io
import zipfile
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from lib.base import SEC_HEADERS


def get_sec_info(ticker: str) -> dict:
    """SEC EDGAR Full-Text Search로 워런트/희석/빚/covenant 정보 수집"""

    sec_info = {
        "warrant_mentions": 0,
        "dilution_mentions": 0,
        "covenant_mentions": 0,
        "debt_mentions": 0,
        "lockup_mentions": 0,
        "offering_mentions": 0,
        "positive_news": 0,
        "negative_news": 0,
        "has_warrant_risk": False,
        "has_debt_covenant": False,
        "dilution_risk": False,
        "has_lockup": False,
        "has_offering_risk": False,
        "has_positive_news": False,
        "has_negative_news": False,
    }

    try:
        keywords = [
            ("warrant", "warrant_mentions"),
            ("dilution", "dilution_mentions"),
            ("covenant", "covenant_mentions"),
            ("debt", "debt_mentions"),
            ("lock-up OR lockup", "lockup_mentions"),
            ("S-3 OR 424B", "offering_mentions"),
        ]

        for keyword, field in keywords:
            search_url = f'https://efts.sec.gov/LATEST/search-index?q="{keyword}" AND "{ticker}"&dateRange=custom&startdt=2024-01-01'
            try:
                resp = requests.get(search_url, headers=SEC_HEADERS, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    count = data.get("hits", {}).get("total", {}).get("value", 0)
                    sec_info[field] = count
            except:
                pass

        # 호재 키워드 (2025년)
        positive_keywords = ["deal", "partnership", "contract", "agreement", "FDA approval"]
        for pk in positive_keywords:
            search_url = f'https://efts.sec.gov/LATEST/search-index?q="{pk}" AND "{ticker}"&dateRange=custom&startdt=2025-01-01'
            try:
                resp = requests.get(search_url, headers=SEC_HEADERS, timeout=15)
                if resp.status_code == 200:
                    count = resp.json().get("hits", {}).get("total", {}).get("value", 0)
                    sec_info["positive_news"] += count
            except:
                pass

        # 악재 키워드 (2025년)
        negative_keywords = ["lawsuit", "bankruptcy", "default", "fraud", "investigation", "delisting"]
        for nk in negative_keywords:
            search_url = f'https://efts.sec.gov/LATEST/search-index?q="{nk}" AND "{ticker}"&dateRange=custom&startdt=2025-01-01'
            try:
                resp = requests.get(search_url, headers=SEC_HEADERS, timeout=15)
                if resp.status_code == 200:
                    count = resp.json().get("hits", {}).get("total", {}).get("value", 0)
                    sec_info["negative_news"] += count
            except:
                pass

        # 해석 (임계값)
        sec_info["has_warrant_risk"] = sec_info["warrant_mentions"] > 10
        sec_info["has_debt_covenant"] = sec_info["covenant_mentions"] > 3
        sec_info["dilution_risk"] = sec_info["dilution_mentions"] > 5
        sec_info["has_lockup"] = sec_info["lockup_mentions"] > 2
        sec_info["has_offering_risk"] = sec_info["offering_mentions"] > 3
        sec_info["has_positive_news"] = sec_info["positive_news"] > 50
        sec_info["has_negative_news"] = sec_info["negative_news"] > 20

    except Exception as e:
        print(f"    ⚠️ SEC 검색 오류: {e}")

    return sec_info


def get_ftd_data(ticker: str) -> dict:
    """SEC에서 FTD 데이터 수집 (최근 2개월)"""
    ftd_info = {
        "total_ftd": 0,
        "recent_ftd": [],
        "avg_ftd": 0,
        "max_ftd": 0,
        "ftd_trend": "unknown",
        "has_significant_ftd": False,
    }

    try:
        now = datetime.now()

        months_to_check = []
        for i in range(3):
            check_date = now - timedelta(days=30 * i)
            months_to_check.append(check_date.strftime("%Y%m"))

        all_ftd = []

        for month in months_to_check[:2]:
            url1 = f"https://www.sec.gov/files/data/fails-deliver-data/cnsfails{month}a.zip"
            url2 = f"https://www.sec.gov/files/data/fails-deliver-data/cnsfails{month}b.zip"

            for url in [url1, url2]:
                try:
                    resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
                    if resp.status_code == 200:
                        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                            for filename in z.namelist():
                                with z.open(filename) as f:
                                    content = f.read().decode('utf-8', errors='ignore')
                                    for line in content.split('\n'):
                                        if ticker.upper() in line.upper():
                                            parts = line.split('|')
                                            if len(parts) >= 5:
                                                try:
                                                    date = parts[0]
                                                    qty = int(parts[3]) if parts[3].isdigit() else 0
                                                    if qty > 0:
                                                        all_ftd.append({
                                                            "date": date,
                                                            "quantity": qty
                                                        })
                                                except:
                                                    pass
                except:
                    pass

        if all_ftd:
            all_ftd.sort(key=lambda x: x['date'], reverse=True)
            ftd_info["recent_ftd"] = all_ftd[:10]
            ftd_info["total_ftd"] = sum(f['quantity'] for f in all_ftd)
            ftd_info["avg_ftd"] = ftd_info["total_ftd"] // len(all_ftd) if all_ftd else 0
            ftd_info["max_ftd"] = max(f['quantity'] for f in all_ftd)

            if len(all_ftd) >= 4:
                recent_avg = sum(f['quantity'] for f in all_ftd[:2]) / 2
                older_avg = sum(f['quantity'] for f in all_ftd[2:4]) / 2
                if recent_avg > older_avg * 1.5:
                    ftd_info["ftd_trend"] = "increasing 📈"
                elif recent_avg < older_avg * 0.5:
                    ftd_info["ftd_trend"] = "decreasing 📉"
                else:
                    ftd_info["ftd_trend"] = "stable"

            ftd_info["has_significant_ftd"] = ftd_info["max_ftd"] > 100000

    except Exception as e:
        print(f"    ⚠️ FTD 수집 오류: {e}")

    return ftd_info


def get_sec_filings(ticker: str) -> dict:
    """SEC EDGAR에서 최근 filing 목록 및 주요 내용 (개선판)"""
    filings_info = {
        "recent_filings": [],
        "lockup_info": None,
        "warrant_details": [],
        "debt_details": [],
        "insider_lockup_price": None,
        "offering_info": [],
        "company_name": None,
        "cik": None,
        "is_spac": False,
        "spac_merger_date": None,
        "earnout_conditions": [],
        "earnout_prices": [],
        "earnout_shares": None,
    }

    try:
        cik = None

        # 1. SEC 공식 티커-CIK 매핑 JSON 사용
        try:
            tickers_url = "https://www.sec.gov/files/company_tickers.json"
            resp = requests.get(tickers_url, headers=SEC_HEADERS, timeout=15)
            if resp.status_code == 200:
                tickers_data = resp.json()
                for key, company in tickers_data.items():
                    if company.get('ticker', '').upper() == ticker.upper():
                        cik = str(company.get('cik_str', '')).zfill(10)
                        filings_info["company_name"] = company.get('title')
                        break
        except:
            pass

        # 2. 백업: EDGAR 검색
        if not cik:
            try:
                ticker_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type=&dateb=&owner=include&count=10&output=atom"
                resp = requests.get(ticker_url, headers=SEC_HEADERS, timeout=15)
                cik_match = re.search(r'CIK=(\d+)', resp.text)
                if cik_match:
                    cik = cik_match.group(1).zfill(10)
            except:
                pass

        if not cik:
            return filings_info
        filings_info["cik"] = cik

        # 2. 최근 filings 가져오기 (JSON API)
        filings_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        resp = requests.get(filings_url, headers=SEC_HEADERS, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            filings_info["company_name"] = data.get('name')

            recent = data.get('filings', {}).get('recent', {})

            forms = recent.get('form', [])
            dates = recent.get('filingDate', [])
            accessions = recent.get('accessionNumber', [])
            descriptions = recent.get('primaryDocument', [])

            important_forms = ["S-1", "S-1/A", "S-3", "S-4", "S-4/A", "424B4", "424B5", "10-K", "10-Q", "8-K", "DEF 14A", "DEFM14A"]

            for i in range(min(30, len(forms))):
                form_type = forms[i]
                if form_type in important_forms or len(filings_info["recent_filings"]) < 10:
                    filings_info["recent_filings"].append({
                        "form": form_type,
                        "date": dates[i],
                        "accession": accessions[i].replace('-', ''),
                        "document": descriptions[i] if i < len(descriptions) else ""
                    })

            # 3. 주요 문서에서 정보 추출
            for filing in filings_info["recent_filings"][:5]:
                form_type = filing["form"]

                if form_type in ["S-1", "S-1/A", "S-4", "S-4/A", "424B4", "424B5", "DEF 14A", "DEFM14A", "10-K"]:
                    try:
                        acc_formatted = filing['accession']
                        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc_formatted}/{filing['document']}"

                        doc_resp = requests.get(doc_url, headers=SEC_HEADERS, timeout=20)

                        if doc_resp.status_code == 200:
                            doc_text = doc_resp.text.lower()

                            # Lock-up 가격/기간 찾기
                            if not filings_info["insider_lockup_price"]:
                                lockup_patterns = [
                                    r'lock-?up.*?(?:release[sd]?|terminate[sd]?).*?(?:stock\s*)?price.*?(?:equals?\s*or\s*)?exceeds?\s*\$?([\d,]+\.?\d*)',
                                    r'(?:lock-?up|restriction).*?(?:expire[sd]?|release[sd]?).*?(?:when|if).*?\$([\d,]+\.?\d*)',
                                    r'lock-?up.*?(?:price|until).*?(\$[\d,]+\.?\d*)',
                                    r'may not (?:sell|transfer).*?until.*?(?:closing price|stock price).*?(\$[\d,]+\.?\d*)',
                                    r'(?:180|90|365)\s*days?\s*(?:after|following).*?ipo',
                                    r'insider.*?lock.*?(\$[\d,]+\.?\d*)',
                                    r'(?:founder|insider|officer|sponsor).*?(?:may not sell|restricted|cannot transfer).*?(\$[\d,]+)',
                                    r'(?:shares?|stock).*?(?:released?|unlocked?).*?(?:if|when).*?price.*?(?:reaches?|exceeds?|equals?)\s*\$?([\d,]+\.?\d*)',
                                    r'(?:restriction|lock-?up).*?(?:waived?|removed?).*?(?:stock\s*)?price.*?\$?([\d,]+\.?\d*)',
                                ]

                                for pattern in lockup_patterns:
                                    match = re.search(pattern, doc_text)
                                    if match:
                                        if match.groups() and match.group(1):
                                            price_str = match.group(1).replace(',', '')
                                            try:
                                                price_val = float(price_str)
                                                if 10 <= price_val <= 500:
                                                    filings_info["insider_lockup_price"] = f"${price_val}"
                                                    break
                                            except:
                                                pass
                                        else:
                                            filings_info["lockup_info"] = "180일 락업 존재"
                                            break

                            # 워런트 정보
                            if not filings_info["warrant_details"]:
                                warrant_patterns = [
                                    r'warrant.*?exercise\s*price.*?(\$[\d,]+\.?\d*)',
                                    r'warrants?\s*(?:to purchase|exercisable).*?(\$[\d,]+\.?\d*)',
                                    r'exercise\s*price\s*(?:of|is)\s*(\$[\d,]+\.?\d*)\s*per\s*share',
                                ]

                                for pattern in warrant_patterns:
                                    matches = re.findall(pattern, doc_text)
                                    if matches:
                                        filings_info["warrant_details"] = list(set(matches))[:5]
                                        break

                            # 빚/Debt 정보
                            if not filings_info["debt_details"]:
                                debt_patterns = [
                                    r'(credit facility|term loan|senior note|convertible note).*?(\$[\d,]+\.?\d*\s*(?:million|billion)?)',
                                    r'(indebtedness|borrowing).*?(\$[\d,]+\.?\d*\s*(?:million|billion)?)',
                                    r'outstanding\s*(debt|loan).*?(\$[\d,]+\.?\d*\s*(?:million|billion)?)',
                                ]

                                for pattern in debt_patterns:
                                    matches = re.findall(pattern, doc_text)
                                    if matches:
                                        filings_info["debt_details"] = [
                                            f"{m[0].title()}: {m[1]}" for m in matches[:5]
                                        ]
                                        break

                            # Offering 정보
                            if form_type in ["S-3", "424B4", "424B5"]:
                                offering_match = re.search(r'(?:offering|issuance).*?(\d[\d,]*)\s*shares.*?(\$[\d,]+\.?\d*)', doc_text)
                                if offering_match:
                                    filings_info["offering_info"].append({
                                        "shares": offering_match.group(1),
                                        "price": offering_match.group(2),
                                        "date": filing["date"],
                                        "form": form_type
                                    })

                            # SPAC / Earnout 정보
                            if form_type in ["S-4", "S-4/A", "DEFM14A", "8-K"]:
                                spac_keywords = ['business combination', 'spac', 'blank check', 'de-spac', 'merger agreement']
                                if any(kw in doc_text for kw in spac_keywords):
                                    filings_info["is_spac"] = True

                                earnout_patterns = [
                                    r'(?:closing|stock)\s*price\s*(?:equals?\s*or\s*)?exceeds?\s*\$?([\d,]+\.?\d*)\s*(?:per\s*share\s*)?(?:for|during)\s*(\d+)\s*(?:trading\s*)?days?',
                                    r'vwap\s*(?:equals?\s*or\s*)?exceeds?\s*\$?([\d,]+\.?\d*)',
                                    r'stock\s*price\s*(?:of\s*the\s*company\s*)?reaches?\s*\$?([\d,]+\.?\d*)',
                                    r'earnout\s*shares?.*?\$?([\d,]+\.?\d*)\s*(?:per\s*share)?',
                                    r'if\s*(?:the\s*)?(?:closing\s*)?price.*?exceeds?\s*\$?([\d,]+\.?\d*)',
                                ]

                                for pattern in earnout_patterns:
                                    matches = re.findall(pattern, doc_text)
                                    for match in matches:
                                        if isinstance(match, tuple):
                                            price = match[0]
                                        else:
                                            price = match
                                        try:
                                            price_val = float(price.replace(',', ''))
                                            if 10 <= price_val <= 500:
                                                if f"${price_val}" not in filings_info["earnout_prices"]:
                                                    filings_info["earnout_prices"].append(f"${price_val}")
                                        except:
                                            pass

                                # Earnout 주식 수 찾기
                                earnout_shares_patterns = [
                                    r'(\d[\d,]*)\s*(?:earnout|contingent)\s*shares?',
                                    r'(?:earnout|contingent)\s*shares?\s*(?:of\s*)?(\d[\d,]*)',
                                    r'up\s*to\s*(\d[\d,]*)\s*additional\s*shares?',
                                ]
                                for pattern in earnout_shares_patterns:
                                    match = re.search(pattern, doc_text)
                                    if match:
                                        filings_info["earnout_shares"] = match.group(1)
                                        break

                                # 락업 조건 (SPAC 특화)
                                spac_lockup_patterns = [
                                    r'(?:founder|sponsor|insider)\s*shares?.*?(?:lock-?up|may\s*not\s*(?:sell|transfer)).*?(?:until|unless).*?(?:stock\s*)?price.*?\$?([\d,]+\.?\d*)',
                                    r'(?:lock-?up|restriction).*?(?:released?|terminate[sd]?).*?(?:stock\s*)?price.*?(?:equals?\s*or\s*)?exceeds?\s*\$?([\d,]+\.?\d*)',
                                    r'shares?\s*(?:may\s*)?(?:not\s*)?(?:be\s*)?(?:sold|transferred).*?until.*?(?:\$|price\s*of\s*)([\d,]+\.?\d*)',
                                ]
                                for pattern in spac_lockup_patterns:
                                    match = re.search(pattern, doc_text)
                                    if match and not filings_info["insider_lockup_price"]:
                                        try:
                                            price_val = float(match.group(1).replace(',', ''))
                                            if 10 <= price_val <= 500:
                                                filings_info["insider_lockup_price"] = f"${price_val}"
                                        except:
                                            pass

                    except Exception as e:
                        pass

    except Exception as e:
        print(f"    ⚠️ SEC Filing 파싱 오류: {e}")

    return filings_info


def parse_8k_content(ticker: str, cik: str) -> list:
    """최근 8-K 공시에서 주요 이벤트 추출"""
    events = []

    if not cik:
        return events

    try:
        filings_url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
        resp = requests.get(filings_url, headers=SEC_HEADERS, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            recent = data.get('filings', {}).get('recent', {})

            forms = recent.get('form', [])
            dates = recent.get('filingDate', [])
            accessions = recent.get('accessionNumber', [])
            descriptions = recent.get('primaryDocument', [])

            eight_k_count = 0
            for i in range(min(50, len(forms))):
                if forms[i] == "8-K" and eight_k_count < 5:
                    eight_k_count += 1

                    try:
                        acc = accessions[i].replace('-', '')
                        doc = descriptions[i] if i < len(descriptions) else ""
                        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc}/{doc}"

                        doc_resp = requests.get(doc_url, headers=SEC_HEADERS, timeout=15)

                        if doc_resp.status_code == 200:
                            text = doc_resp.text.lower()

                            event_type = "기타"
                            importance = "보통"

                            if "fda" in text and ("approv" in text or "clear" in text):
                                event_type = "FDA 승인/허가"
                                importance = "🔥 중요"
                            elif "phase" in text and ("result" in text or "data" in text):
                                event_type = "임상 결과 발표"
                                importance = "🔥 중요"
                            elif "agreement" in text or "partnership" in text or "collaborat" in text:
                                event_type = "계약/파트너십"
                                importance = "⚡ 주목"
                            elif "offering" in text or "securities" in text:
                                event_type = "유증/공모"
                                importance = "⚠️ 희석"
                            elif "executive" in text or "officer" in text or "director" in text:
                                event_type = "임원 변동"
                                importance = "보통"
                            elif "earning" in text or "financial" in text or "quarter" in text:
                                event_type = "실적 발표"
                                importance = "📊 실적"

                            events.append({
                                "date": dates[i],
                                "type": event_type,
                                "importance": importance,
                                "accession": accessions[i]
                            })
                    except:
                        pass

    except:
        pass

    return events
