"""
lib/institutional.py - 기관/내부자/동종업체
기관 보유, 내부자 거래, 경영진, 동종업체 비교, SI 히스토리
"""

import re
import requests
import yfinance as yf
from lib.base import HEADERS, fmt_num


def get_officers(stock) -> list:
    """경영진 정보"""
    try:
        return stock.info.get("companyOfficers", [])
    except:
        return []


def get_insider_transactions(stock) -> list:
    """내부자 거래"""
    try:
        insider = stock.insider_transactions
        if insider is not None and not insider.empty:
            return insider.to_dict('records')
        return []
    except:
        return []


def get_institutional_holders(stock) -> list:
    """기관 보유"""
    try:
        holders = stock.institutional_holders
        if holders is not None and not holders.empty:
            return holders.to_dict('records')
        return []
    except:
        return []


def get_institutional_changes(stock) -> dict:
    """기관 보유 변화 분석"""
    inst_info = {
        "total_institutional": 0,
        "top_holders": [],
        "recent_changes": [],
        "net_institutional_change": "unknown",
    }

    try:
        holders = stock.institutional_holders
        if holders is not None and not holders.empty:
            inst_info["total_institutional"] = len(holders)

            for _, row in holders.head(5).iterrows():
                inst_info["top_holders"].append({
                    "holder": row.get('Holder', 'N/A'),
                    "shares": int(row.get('Shares', 0)),
                    "value": int(row.get('Value', 0)),
                    "pct_out": f"{row.get('pctHeld', 0) * 100:.2f}%" if row.get('pctHeld') else 'N/A'
                })

        info = stock.info
        inst_pct = info.get('heldPercentInstitutions')
        if inst_pct:
            inst_info["institutional_percent"] = f"{inst_pct * 100:.1f}%"

    except Exception as e:
        print(f"    ⚠️ 기관 보유 분석 오류: {e}")

    return inst_info


def get_peer_comparison(stock, ticker: str) -> dict:
    """동종업체 비교 분석"""
    peer_info = {
        "sector": None,
        "industry": None,
        "peers": [],
        "sector_avg_pe": None,
        "relative_valuation": None,
    }

    try:
        info = stock.info
        peer_info["sector"] = info.get('sector')
        peer_info["industry"] = info.get('industry')

        my_pe = info.get('trailingPE')

        sector_pe_avg = {
            "Technology": 25,
            "Healthcare": 20,
            "Financial Services": 12,
            "Consumer Cyclical": 18,
            "Communication Services": 20,
            "Industrials": 16,
            "Energy": 10,
            "Basic Materials": 12,
            "Consumer Defensive": 22,
            "Real Estate": 35,
            "Utilities": 18,
        }

        sector = info.get('sector')
        if sector and sector in sector_pe_avg:
            peer_info["sector_avg_pe"] = sector_pe_avg[sector]

            if my_pe and my_pe > 0:
                ratio = my_pe / sector_pe_avg[sector]
                if ratio > 1.5:
                    peer_info["relative_valuation"] = "고평가 ⚠️"
                elif ratio < 0.7:
                    peer_info["relative_valuation"] = "저평가 💰"
                else:
                    peer_info["relative_valuation"] = "적정"
            else:
                peer_info["relative_valuation"] = "적자기업 (PE 없음)"

    except Exception as e:
        print(f"    ⚠️ 동종업체 비교 오류: {e}")

    return peer_info


def get_short_history(ticker: str) -> dict:
    """Short Interest 변화 추이 (여러 소스 시도)"""
    short_hist = {
        "history": [],
        "trend": "unknown",
        "change_30d": None,
        "current_si": None,
        "prior_si": None,
    }

    try:
        # 1. yfinance에서 기본 Short 데이터
        stock = yf.Ticker(ticker)
        info = stock.info

        current = info.get('sharesShort')
        prior = info.get('sharesShortPriorMonth')

        if current:
            short_hist["current_si"] = current
        if prior:
            short_hist["prior_si"] = prior

        if current and prior and prior > 0:
            change = ((current - prior) / prior) * 100
            short_hist["change_30d"] = f"{change:+.1f}%"

            if change > 50:
                short_hist["trend"] = "급증 📈🔥"
            elif change > 20:
                short_hist["trend"] = "급증 📈"
            elif change > 5:
                short_hist["trend"] = "증가 ↗️"
            elif change < -30:
                short_hist["trend"] = "급감 📉 (커버링?)"
            elif change < -10:
                short_hist["trend"] = "감소 ↘️"
            else:
                short_hist["trend"] = "안정"

            short_hist["history"].append({
                "date": "현재",
                "short_interest": current,
            })
            short_hist["history"].append({
                "date": "전월",
                "short_interest": prior,
            })

        # 2. Finviz에서 추가 데이터 시도
        try:
            finviz_url = f"https://finviz.com/quote.ashx?t={ticker}"
            resp = requests.get(finviz_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }, timeout=10)

            if resp.status_code == 200:
                # <b> 태그 안의 값 추출 (CSS w-[8%] 오매칭 방지)
                match = re.search(r'>Short Float<.*?<b[^>]*>(?:<[^>]+>)*(\d+\.?\d*)%', resp.text)
                if match:
                    short_hist["short_float_pct"] = f"{match.group(1)}%"

                match2 = re.search(r'>Short Ratio<.*?<b[^>]*>(\d+\.?\d*)', resp.text)
                if match2:
                    short_hist["short_ratio"] = float(match2.group(1))

        except:
            pass

        # 3. Chartexchange 백업
        try:
            ce_url = f"https://chartexchange.com/symbol/nasdaq-{ticker.lower()}/"
            resp = requests.get(ce_url, headers=HEADERS, timeout=10)

            if resp.status_code == 200:
                sv_match = re.search(r'short\s*volume[:\s]*(\d[\d,]*)', resp.text.lower())
                if sv_match:
                    short_hist["short_volume"] = sv_match.group(1).replace(',', '')

        except:
            pass

    except Exception as e:
        print(f"    ⚠️ Short History 오류: {e}")

    return short_hist
