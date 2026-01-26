#!/usr/bin/env python3
"""
🔥 초정밀 주식 분석기 v4 (Deep Stock Analyzer) - 나스닥의 신 에디션
Zero Borrow 감지 + Gemini AI 분석 + 섹터별 특화 분석!

v4 새 기능:
- 섹터별 특화 뉴스 (바이오텍/AI·Tech/에너지/일반)
- 바이오텍 촉매 분석 (FDA Fast Track, ClinicalTrials.gov 연동)
- 8-K 주요 이벤트 파싱 (FDA 승인, 임상결과, 계약 등)
- 구글 뉴스 백업 + 최근 60일 필터
- SPAC/Earnout 조건 자동 추출

v3 기능:
- SPAC/Earnout 조건 자동 추출 (S-4, DEFM14A)
- 락업 가격 추출 개선 (가격 기반 락업)
- google.genai 새 SDK 마이그레이션

Usage:
    uv run python deep_analyzer.py BNAI
    uv run python deep_analyzer.py BNAI --no-ai   # AI 분석 스킵
    uv run python deep_analyzer.py GLSI --normal  # 일반 분석 모드
"""

import sys
import os
from datetime import datetime
import yfinance as yf

# Gemini API (새 SDK)
from google import genai

# 번역 (사업 설명 한글화)
try:
    from deep_translator import GoogleTranslator
    translator = GoogleTranslator(source='en', target='ko')
except:
    translator = None

# ============================================================
# lib/ 패키지에서 공통 수집 함수 import
# ============================================================
from lib import (
    check_regsho, fetch_historical_regsho,
    get_borrow_data, get_fintel_data,
    get_sec_info, get_ftd_data, get_sec_filings, parse_8k_content,
    get_social_sentiment,
    get_news, search_recent_news, get_sector_news, get_finviz_news,
    get_biotech_news, get_tech_news, get_energy_news,
    get_automotive_news, get_retail_news, get_consumer_news,
    get_financial_news, get_industrial_news, get_realestate_news,
    get_technicals, get_fibonacci_levels, get_volume_profile,
    get_options_data,
    get_darkpool_data,
    get_officers, get_insider_transactions, get_institutional_holders,
    get_institutional_changes, get_peer_comparison, get_short_history,
    get_catalyst_calendar, get_biotech_catalysts, get_automotive_catalysts,
    get_retail_catalysts, get_financial_catalysts, get_industrial_catalysts,
    get_realestate_catalysts,
)
from lib.base import get_db, DB_CONFIG, HEADERS, fmt_num, fmt_pct

# ============================================================
# Gemini 설정
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


# ============================================================
# 출력 유틸리티 (deep_analyzer 전용)
# ============================================================

def section(title: str, emoji: str = "📊"):
    """섹션 헤더"""
    print(f"\n{'='*70}")
    print(f"{emoji} {title}")
    print(f"{'='*70}")


def subsection(title: str):
    """서브섹션"""
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


# ============================================================
# 1. 기본 정보 (yfinance)
# ============================================================

def get_basic_info(ticker: str) -> dict:
    """yfinance에서 모든 기본 정보 수집"""
    stock = yf.Ticker(ticker)
    info = stock.info

    return {
        "info": info,
        "stock": stock,
        "name": info.get("shortName") or info.get("longName", ticker),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "website": info.get("website"),
        "description": info.get("longBusinessSummary"),
        "employees": info.get("fullTimeEmployees"),
        "exchange": info.get("exchange"),
        "quote_type": info.get("quoteType"),
        # 가격
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "prev_close": info.get("previousClose"),
        "open": info.get("open"),
        "day_high": info.get("dayHigh"),
        "day_low": info.get("dayLow"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "50d_avg": info.get("fiftyDayAverage"),
        "200d_avg": info.get("twoHundredDayAverage"),
        "pre_market": info.get("preMarketPrice"),
        "post_market": info.get("postMarketPrice"),
        # 거래량
        "volume": info.get("volume"),
        "avg_volume": info.get("averageVolume"),
        "avg_volume_10d": info.get("averageVolume10days"),
        # 시총/주식수
        "market_cap": info.get("marketCap"),
        "enterprise_value": info.get("enterpriseValue"),
        "shares_outstanding": info.get("sharesOutstanding"),
        "float_shares": info.get("floatShares"),
        # 재무
        "revenue": info.get("totalRevenue"),
        "revenue_growth": info.get("revenueGrowth"),
        "ebitda": info.get("ebitda"),
        "net_income": info.get("netIncomeToCommon"),
        "eps": info.get("trailingEps"),
        "pe_ratio": info.get("trailingPE"),
        "total_cash": info.get("totalCash"),
        "total_debt": info.get("totalDebt"),
        "debt_to_equity": info.get("debtToEquity"),
        # 숏
        "short_ratio": info.get("shortRatio"),
        "short_pct_float": info.get("shortPercentOfFloat"),
        "shares_short": info.get("sharesShort"),
        "shares_short_prior": info.get("sharesShortPriorMonth"),
        "short_date": info.get("dateShortInterest"),
        # 내부자/기관
        "insider_pct": info.get("heldPercentInsiders"),
        "institution_pct": info.get("heldPercentInstitutions"),
        # 기타
        "beta": info.get("beta"),
        "target_mean": info.get("targetMeanPrice"),
        "recommendation": info.get("recommendationKey"),
    }


# ============================================================
# 숏스퀴즈 점수 계산 (v3 - Zero Borrow 반영)
# ============================================================

def calculate_squeeze_score_v3(data: dict, borrow: dict, regsho_info: dict, tech: dict) -> dict:
    """
    숏스퀴즈 점수 v3 (0-100) - Zero Borrow 반영!

    핵심: Zero Borrow = 새 숏 진입 불가 = 스퀴즈 최적 조건
    """
    score = 0
    details = []
    risks = []
    bullish = []

    # ========== ZERO BORROW (최대 30점) ==========
    if borrow.get("is_zero_borrow"):
        score += 30
        details.append("🔥 ZERO BORROW (빌릴 주식 없음): +30점")
        bullish.append("새 숏 진입 불가능 - 기존 숏만 커버해야 함")
    elif borrow.get("is_hard_to_borrow"):
        score += 15
        details.append("⚠️ Hard to Borrow: +15점")

    # ========== Borrow Rate (0-20점) ==========
    br = borrow.get("borrow_rate")
    if br and br < 999:
        if br > 100:
            score += 20
            details.append(f"Borrow Rate {br:.1f}% (극단적): +20점")
        elif br > 50:
            score += 15
            details.append(f"Borrow Rate {br:.1f}% (높음): +15점")
        elif br > 20:
            score += 10
            details.append(f"Borrow Rate {br:.1f}%: +10점")

    # ========== Short Interest (0-20점) ==========
    si = data.get("short_pct_float")
    if si:
        si_pct = si * 100 if si < 1 else si
        if si_pct > 30:
            score += 20
            details.append(f"Short % of Float {si_pct:.1f}% (높음): +20점")
        elif si_pct > 20:
            score += 15
            details.append(f"Short % of Float {si_pct:.1f}%: +15점")
        elif si_pct > 10:
            score += 10
            details.append(f"Short % of Float {si_pct:.1f}%: +10점")

    # ========== RegSHO (0-30점) ==========
    if regsho_info.get("listed"):
        score += 15
        details.append("RegSHO Threshold 등재: +15점")
        bullish.append("FTD 다수 발생 - 강제 커버링 압력")

        days = regsho_info.get("days", 0)
        if days >= 13:
            score += 15
            details.append(f"RegSHO 연속 {days}일 (강제 바이인 구간!): +15점")
            bullish.append(f"13일 이상 연속 등재 - 브로커 강제 바이인 가능!")
        elif days >= 8:
            score += 10
            details.append(f"RegSHO 연속 {days}일 (위험 구간): +10점")
            bullish.append(f"강제 바이인까지 {13-days}일 남음")
        elif days >= 3:
            score += 5
            details.append(f"RegSHO 연속 {days}일: +5점")

    # ========== Low Float (0-10점) ==========
    float_shares = data.get("float_shares")
    if float_shares:
        if float_shares < 5_000_000:
            score += 10
            details.append(f"극소형 Float ({fmt_num(float_shares)}): +10점")
            bullish.append("작은 Float = 매수 압력에 민감")
        elif float_shares < 10_000_000:
            score += 5
            details.append(f"Low Float ({fmt_num(float_shares)}): +5점")

    # ========== 대차가능 주식 (0-10점) ==========
    avail = borrow.get("available_shares")
    if avail is not None:
        if avail == 0:
            score += 10
            details.append("대차가능 주식 0: +10점")
        elif avail < 50000:
            score += 5
            details.append(f"대차가능 부족 ({fmt_num(avail)}): +5점")

    # ========== 거래량 급증 (0-5점) ==========
    vol_ratio = tech.get("vol_ratio", 1) if tech else 1
    if vol_ratio > 3:
        score += 5
        details.append(f"거래량 급증 {vol_ratio:.1f}x: +5점")
        bullish.append("높은 관심도 & 유동성")

    # ========== 내부자 보유율 (0-5점) ==========
    insider = data.get("insider_pct")
    if insider and insider > 0.3:
        score += 5
        details.append(f"내부자 보유 {insider*100:.1f}%: +5점")
        bullish.append("내부자 락업 = Float 축소 효과")

    # ========== 리스크 분석 ==========

    rsi = tech.get("rsi") if tech else None
    if rsi:
        if rsi > 85:
            risks.append(f"🔴 RSI {rsi:.1f} - 극단적 과매수, 급락 위험")
        elif rsi > 70:
            risks.append(f"🟡 RSI {rsi:.1f} - 과매수 구간")

    bb_pos = tech.get("bb_position") if tech else None
    if bb_pos and bb_pos > 100:
        risks.append(f"🟡 볼린저 상단 돌파 ({bb_pos:.1f}%) - 과열")

    atr_pct = tech.get("atr_pct") if tech else None
    if atr_pct and atr_pct > 15:
        risks.append(f"🟡 극단적 변동성 (ATR {atr_pct:.1f}%)")

    curr = data.get("shares_short")
    prev = data.get("shares_short_prior")
    if curr and prev and prev > 0:
        change = ((curr - prev) / prev) * 100
        if change < -30:
            risks.append(f"⚠️ Short Interest {change:.1f}% 급감 - 커버링 마무리 단계?")

    return {
        "score": min(round(score, 1), 100),
        "details": details,
        "risks": risks,
        "bullish": bullish
    }


# ============================================================
# Gemini AI 분석
# ============================================================

def analyze_with_gemini(ticker: str, data: dict, borrow: dict, tech: dict,
                        regsho_info: dict, score_info: dict, news: list,
                        force_normal: bool = False, sec_info: dict = None,
                        sec_filings: dict = None) -> str:
    """Gemini AI로 종합 분석"""
    sec_info = sec_info or {}
    sec_filings = sec_filings or {}

    rsi_val = f"{tech.get('rsi'):.1f}" if tech.get('rsi') else 'N/A'
    bb_val = f"{tech.get('bb_position'):.1f}" if tech.get('bb_position') else 'N/A'
    vol_val = f"{tech.get('vol_ratio'):.2f}" if tech.get('vol_ratio') else 'N/A'

    eps = data.get('eps', 0) or 0
    pe = data.get('pe_ratio')
    debt_equity = data.get('debt_to_equity')
    cash = data.get('total_cash', 0) or 0
    debt = data.get('total_debt', 0) or 0
    revenue = data.get('revenue', 0) or 0
    net_income = data.get('net_income', 0) or 0

    summary = f"""
## {ticker} ({data.get('name', ticker)}) 분석 데이터

### 기본 정보
- 현재가: ${data.get('price', 'N/A')}
- 애프터마켓: ${data.get('post_market', 'N/A')}
- 시가총액: {fmt_num(data.get('market_cap'), '$')}
- Float: {fmt_num(data.get('float_shares'))}
- 섹터: {data.get('sector', 'N/A')}
- 직원수: {data.get('employees', 'N/A')}명

### 재무 상태 (중요!)
- EPS: ${eps:.2f}
- P/E: {pe if pe else 'N/A (적자)'}
- 매출: {fmt_num(revenue, '$')}
- 순이익: {fmt_num(net_income, '$')}
- 총 현금: {fmt_num(cash, '$')}
- 총 부채: {fmt_num(debt, '$')}
- 부채비율(D/E): {debt_equity if debt_equity else 'N/A'}

### 숏 포지션
- Short % of Float: {fmt_pct(data.get('short_pct_float'))}
- Short Shares: {fmt_num(data.get('shares_short'))}
- Days to Cover: {data.get('short_ratio', 'N/A')}
- Zero Borrow: {'✅ YES (빌릴 주식 없음!)' if borrow.get('is_zero_borrow') else '❌ NO'}
- Borrow Rate: {borrow.get('borrow_rate', 'N/A')}%
- RegSHO 등재: {'✅ YES (연속 ' + str(regsho_info.get("days", 0)) + '일)' if regsho_info.get("listed") else '❌ NO'}

### 기술적 지표
- RSI: {rsi_val}
- 볼린저 위치: {bb_val}%
- 거래량 비율: {vol_val}x
- 1일 변화: {tech.get('change_1d', 0):.2f}%
- 5일 변화: {tech.get('change_5d', 0):.2f}%
- 20일 변화: {tech.get('change_20d', 0):.2f}%

### 숏스퀴즈 점수
- 점수: {score_info.get('score', 0)}/100
- 주요 요소: {', '.join(score_info.get('details', [])[:3])}
- 리스크: {', '.join(score_info.get('risks', [])[:3]) if score_info.get('risks') else '없음'}

### 최근 뉴스
{chr(10).join([f"- {n.get('title', 'N/A')}" for n in news[:3]]) if news else '뉴스 없음'}

### SEC 공시 분석 (희석/빚/Covenant)
- Warrant 언급: {sec_info.get('warrant_mentions', 0)}건 {'⚠️ 희석 위험!' if sec_info.get('has_warrant_risk') else '✅ OK'}
- Dilution 언급: {sec_info.get('dilution_mentions', 0)}건 {'⚠️ 희석 위험!' if sec_info.get('dilution_risk') else '✅ OK'}
- Covenant/빚 조항: {sec_info.get('covenant_mentions', 0)}건 {'⚠️ 빚 있음!' if sec_info.get('has_debt_covenant') else '✅ OK'}
- Debt 언급: {sec_info.get('debt_mentions', 0)}건
- Lock-up 언급: {sec_info.get('lockup_mentions', 0)}건 {'🔒 내부자 매도 제한' if sec_info.get('has_lockup') else ''}
- S-3/424B 오퍼링: {sec_info.get('offering_mentions', 0)}건 {'⚠️ 오퍼링 위험!' if sec_info.get('has_offering_risk') else '✅ OK'}
- 호재 공시: {sec_info.get('positive_news', 0)}건 {'🔥' if sec_info.get('has_positive_news') else ''}
- 악재 공시: {sec_info.get('negative_news', 0)}건 {'❌' if sec_info.get('has_negative_news') else ''}

### SPAC/Earnout 정보
- SPAC 여부: {'🚀 SPAC 합병 종목!' if sec_filings and sec_filings.get('is_spac') else '❌ 아님'}
- 내부자 락업 가격: {sec_filings.get('insider_lockup_price', '정보없음') if sec_filings else '정보없음'}
- Earnout 조건 가격: {', '.join(sec_filings.get('earnout_prices', [])) if sec_filings and sec_filings.get('earnout_prices') else '정보없음'}
- Earnout 주식 수: {sec_filings.get('earnout_shares', '정보없음') if sec_filings else '정보없음'}
"""

    is_squeeze_play = False if force_normal else (
        borrow.get('is_zero_borrow') or (data.get('short_pct_float') and data.get('short_pct_float') > 0.2)
    )

    if is_squeeze_play:
        prompt = f"""
너는 숏스퀴즈 전문 트레이더야. 핵심만 분석해줘.

{summary}

⚠️ 중요: 이건 **숏스퀴즈 플레이**야! 펀더멘털 분석은 의미없어.
숏스퀴즈는 수급 싸움이야. 펀더멘털 안좋아도 숏들이 강제로 사야하면 폭등해.

다음을 분석해줘:

## 1. 수급 분석 (가장 중요!)
- Zero Borrow 상태면: 숏들이 **새로 못 들어오고, 나가려면 시장에서 사야함**
- Short % of Float 29%면: Float의 거의 1/3이 숏포지션
- Float 296만주면: 극소형, 매수 압력에 민감
- 이 수급 구조에서 **숏들이 강제청산하면 어떻게 되냐?**

## 2. 모멘텀 분석
- 애프터 +255% 갭업이면: 내일 장시작 때 **FOMO** 폭발
- 해외 투자자들 반응 예상
- RSI 88이라도 숏스퀴즈에선 100 넘게 가기도 함

## 3. 타이밍 분석
- 지금이 **초입**이냐, **중반**이냐, **끝물**이냐?
- Days to Cover 0.16일이면 빨리 청산된다는 뜻
- 근데 Zero Borrow면 빌릴 주식이 없어서 못 빠짐

## 4. 전략 (숏스퀴즈 기준!)
- 신규 진입: 언제 들어가면 좋냐, 위험하냐
- 홀딩 중이면: 언제까지 들고갈만 하냐
- 목표가: 숏커버링 완료 시 예상 가격대
- 손절가: 스퀴즈 실패 시 탈출 라인

## 5. 펀더멘털 (참고용)
- 회사 상태가 어떤지 간단히
- 근데 숏스퀴즈엔 펀더멘털 의미없다는 것도 언급

핵심: 숏스퀴즈는 **수급 게임**이야.
펀더멘털 안좋아도 숏들이 청산해야하면 가격은 폭등해.
GME, AMC 다 그랬잖아.
"""
    else:
        prompt = f"""
너는 주식 분석가야. 이 종목 투자할만한지 분석해줘.

{summary}

다음을 분석해줘:

## 1. 펀더멘털 분석
- 이 회사가 돈을 버는 회사인지
- 매출, 이익, 성장성
- 부채 상태, 현금 보유
- 밸류에이션이 적정한지

## 2. 기술적 분석
- 현재 추세
- RSI, 볼린저밴드 상태
- 지지선/저항선

## 3. 리스크 요인
- 어떤 위험이 있는지
- 급락 가능성

## 4. 투자 의견
- 매수/홀드/매도 중 뭐가 맞는지
- 목표가, 손절가
- 투자 시 주의점

구체적인 숫자와 근거를 들어서 분석해줘.
"""

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents={'text': prompt},
        )
        return response.text
    except Exception as e:
        return f"⚠️ Gemini 분석 실패: {e}"


# ============================================================
# 출력 함수들
# ============================================================

def print_basic_info(data: dict):
    """기본 정보 출력"""
    section("회사 개요", "🏢")

    print(f"  회사명: {data['name']}")
    print(f"  섹터: {data['sector'] or 'N/A'} / {data['industry'] or 'N/A'}")
    print(f"  직원수: {fmt_num(data['employees'])}명")
    print(f"  웹사이트: {data['website'] or 'N/A'}")

    desc = data.get('description')
    if desc:
        subsection("사업 내용 (뭘로 돈 버나?)")
        if translator:
            try:
                desc_short = desc[:800] if len(desc) > 800 else desc
                desc_ko = translator.translate(desc_short)
                print(f"  {desc_ko}")
            except Exception:
                print(f"  {desc[:500]}..." if len(desc) > 500 else f"  {desc}")
        else:
            print(f"  {desc[:500]}..." if len(desc) > 500 else f"  {desc}")


def print_financials(data: dict):
    """재무 정보 출력"""
    section("재무 현황", "💵")

    revenue = data.get('revenue')
    net_income = data.get('net_income')
    ebitda = data.get('ebitda')
    revenue_growth = data.get('revenue_growth')
    eps = data.get('eps')
    pe = data.get('pe_ratio')
    total_cash = data.get('total_cash')
    total_debt = data.get('total_debt')
    de_ratio = data.get('debt_to_equity')

    subsection("매출 & 이익")
    print(f"  매출 (TTM): {fmt_num(revenue, '$')}")
    print(f"  순이익: {fmt_num(net_income, '$')}")
    print(f"  EBITDA: {fmt_num(ebitda, '$')}")
    if revenue_growth:
        print(f"  매출 성장률: {revenue_growth*100:+.1f}%")

    subsection("수익성")
    print(f"  EPS: ${eps:.2f}" if eps else "  EPS: N/A (적자)")
    print(f"  P/E: {pe:.1f}" if pe else "  P/E: N/A (적자 또는 데이터 없음)")

    if net_income:
        if net_income > 0:
            print(f"  💰 흑자 기업")
        else:
            print(f"  🔴 적자 기업 (순손실: {fmt_num(abs(net_income), '$')})")

    subsection("재무 건전성")
    print(f"  현금: {fmt_num(total_cash, '$')}")
    print(f"  부채: {fmt_num(total_debt, '$')}")
    if de_ratio:
        print(f"  부채비율 (D/E): {de_ratio:.1f}%")

    if total_cash and total_debt:
        if total_cash > total_debt:
            print(f"  ✅ 현금이 부채보다 많음 (재무 양호)")
        else:
            diff = total_debt - total_cash
            print(f"  ⚠️ 부채가 현금보다 {fmt_num(diff, '$')} 많음")


def print_price_info(data: dict):
    """가격 정보"""
    section("가격 정보", "💰")

    price = data['price']
    prev = data['prev_close']
    change = ((price / prev) - 1) * 100 if price and prev else 0
    emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"

    print(f"  현재가: ${price:.2f} {emoji} {change:+.2f}%" if price else "  현재가: N/A")

    if data.get('pre_market'):
        pm_change = ((data['pre_market'] / price) - 1) * 100 if price else 0
        print(f"  프리마켓: ${data['pre_market']:.2f} ({pm_change:+.2f}%)")

    if data.get('post_market'):
        am_change = ((data['post_market'] / price) - 1) * 100 if price else 0
        print(f"  애프터마켓: ${data['post_market']:.2f} ({am_change:+.2f}%) 🔥")

    print(f"\n  52주: ${data['52w_low']:.2f} ~ ${data['52w_high']:.2f}" if data['52w_low'] else "")
    print(f"  시가총액: {fmt_num(data['market_cap'], '$')}")
    print(f"  Float: {fmt_num(data['float_shares'])}")


def print_short_data(data: dict, borrow: dict, regsho_info: dict):
    """숏 데이터"""
    section("숏 포지션 분석", "🩳")

    if borrow.get("is_zero_borrow"):
        print(f"\n  {'🔥'*10}")
        print(f"  🚨 ZERO BORROW! 빌릴 주식 없음! 🚨")
        print(f"  → 새로운 숏 포지션 진입 불가능")
        print(f"  → 기존 숏은 시장에서 사야만 탈출 가능")
        print(f"  {'🔥'*10}\n")
    elif borrow.get("is_hard_to_borrow"):
        print(f"\n  ⚠️ HARD TO BORROW - 대차 어려움\n")

    si_pct = data['short_pct_float']
    print(f"  Short % of Float: {fmt_pct(si_pct)}")
    print(f"  Short Shares: {fmt_num(data['shares_short'])}")
    print(f"  Days to Cover: {data['short_ratio']:.2f}일" if data['short_ratio'] else "")

    curr = data['shares_short']
    prev = data['shares_short_prior']
    if curr and prev:
        change = ((curr - prev) / prev) * 100
        emoji = "📈 증가" if change > 0 else "📉 감소"
        print(f"  Short 변화: {emoji} {change:+.1f}%")

    subsection("Borrow Rate")
    br = borrow.get('borrow_rate')
    if br == 999:
        print(f"  Borrow Rate: ∞ (Zero Borrow)")
    elif br:
        print(f"  Borrow Rate: {br:.1f}%")
    else:
        print(f"  Borrow Rate: N/A")

    print(f"  대차가능 주식: {fmt_num(borrow.get('available_shares'))}")

    subsection("RegSHO Threshold")
    if regsho_info.get("listed"):
        days = regsho_info.get("days", 0)
        if days > 0:
            print(f"  ✅ 등재됨 - 연속 {days}일째")
            if days >= 13:
                print(f"  🚨 강제 바이인 구간! (13일 이상)")
            elif days >= 8:
                print(f"  ⚠️ 강제 바이인까지 {13-days}일 남음")
        else:
            print(f"  ✅ 등재됨 - FTD 다수 발생")
    else:
        print(f"  ❌ 미등재")


def print_technicals(tech: dict, price: float):
    """기술적 지표"""
    section("기술적 분석", "📈")

    if not tech:
        print("  데이터 없음")
        return

    rsi = tech.get('rsi')
    if rsi:
        status = "🔴 극단적 과매수" if rsi > 80 else "🟠 과매수" if rsi > 70 else "🟢 과매도" if rsi < 30 else "⚪ 중립"
        print(f"  RSI(14): {rsi:.2f} {status}")

    macd_hist = tech.get('macd_hist')
    if macd_hist is not None:
        trend = "📈 상승" if macd_hist > 0 else "📉 하락"
        print(f"  MACD Histogram: {macd_hist:.4f} {trend}")

    bb_pos = tech.get('bb_position')
    if bb_pos is not None:
        status = "🔴 상단 돌파" if bb_pos > 100 else "🟢 하단 이탈" if bb_pos < 0 else ""
        print(f"  볼린저 위치: {bb_pos:.1f}% {status}")

    vol_ratio = tech.get('vol_ratio', 1)
    vol_status = "🔥🔥🔥" if vol_ratio > 5 else "🔥" if vol_ratio > 2 else ""
    print(f"  거래량 비율: {vol_ratio:.2f}x {vol_status}")

    atr_pct = tech.get('atr_pct')
    if atr_pct:
        print(f"  변동성(ATR%): {atr_pct:.2f}%")

    subsection("가격 변화")
    print(f"  1일: {tech.get('change_1d', 0):+.2f}%")
    print(f"  5일: {tech.get('change_5d', 0):+.2f}%")
    print(f"  20일: {tech.get('change_20d', 0):+.2f}%")


def print_squeeze_score(score_info: dict, regsho_info: dict):
    """스퀴즈 점수"""
    section("숏스퀴즈 종합 점수", "🎰")

    score = score_info['score']
    in_regsho = regsho_info.get("listed", False)

    if score >= 80:
        grade = "🔥🔥🔥🔥 극단적 (숏 지옥)"
    elif score >= 60:
        grade = "🔥🔥🔥 매우 높음"
    elif score >= 40:
        grade = "🔥🔥 높음"
    elif score >= 20:
        grade = "🔥 보통"
    else:
        grade = "❄️ 낮음"

    if score >= 40 and in_regsho:
        label = "🚨 SQUEEZE"
    elif score >= 40:
        label = "👀 SQUEEZE WATCH"
    else:
        label = ""

    bar_filled = int(score / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    print(f"\n  [{bar}] {score}/100")
    print(f"  등급: {grade}")
    if label:
        print(f"  판정: {label}")

    if score_info.get('details'):
        subsection("점수 구성")
        for detail in score_info['details']:
            print(f"    • {detail}")

    if score_info.get('bullish'):
        subsection("🟢 강세 요인")
        for b in score_info['bullish']:
            print(f"    ✅ {b}")

    if score_info.get('risks'):
        subsection("🔴 리스크 요인")
        for risk in score_info['risks']:
            print(f"    {risk}")


def print_officers(officers: list):
    """경영진"""
    section("경영진", "👔")

    if not officers:
        print("  정보 없음")
        return

    for i, o in enumerate(officers[:5], 1):
        name = o.get("name", "N/A")
        title = o.get("title", "N/A")
        age = o.get("age")
        pay = o.get("totalPay")

        print(f"\n  [{i}] {name}")
        print(f"      {title}")
        if age:
            print(f"      나이: {age}세")
        if pay:
            print(f"      보수: {fmt_num(pay, '$')}")


def print_news(news: list):
    """뉴스"""
    section("최근 뉴스", "📰")

    if not news:
        print("  뉴스 없음")
        return

    for i, n in enumerate(news[:5], 1):
        title = n.get('title', 'N/A')
        publisher = n.get('publisher', '')
        print(f"\n  [{i}] {title}")
        if publisher:
            print(f"      출처: {publisher}")


def print_sector_news(sector_news: dict):
    """섹터별 특화 뉴스 출력"""
    source = sector_news.get("source", "General")
    section(f"섹터별 뉴스 ({source})", "📡")

    specific = sector_news.get("sector_specific", [])
    if specific:
        subsection(f"{source} 전문 뉴스 (최근 60일)")
        for i, n in enumerate(specific[:5], 1):
            title = n.get('title', 'N/A')[:70]
            src = n.get('source', '')
            print(f"  [{i}] {title}...")
            if src:
                print(f"      📌 {src}")
    else:
        print("  섹터 특화 뉴스 없음")

    general = sector_news.get("general_news", [])
    if general:
        subsection("일반 뉴스 (Google)")
        for i, n in enumerate(general[:3], 1):
            title = n.get('title', 'N/A')[:70]
            print(f"  [{i}] {title}...")


def print_biotech_catalysts(catalysts: dict):
    """바이오텍 촉매 출력"""
    section("바이오텍 촉매 분석", "💊")

    if catalysts.get("fast_track"):
        print("  🚀 FDA Fast Track 지정!")
    if catalysts.get("breakthrough"):
        print("  ⭐ FDA Breakthrough 지정!")
    if catalysts.get("orphan_drug"):
        print("  🏥 Orphan Drug 지정!")

    fda_status = catalysts.get("fda_status", [])
    if fda_status:
        subsection("FDA 관련 뉴스")
        for i, news in enumerate(fda_status[:3], 1):
            headline = news.get('headline', '')[:70]
            print(f"  [{i}] {headline}...")

    trials = catalysts.get("clinical_trials", [])
    if trials:
        subsection("진행 중인 임상시험 (ClinicalTrials.gov)")
        for trial in trials[:3]:
            nct = trial.get('nct_id', '')
            title = trial.get('title', '')[:60]
            phase = trial.get('phase', 'N/A')
            status = trial.get('status', '')
            completion = trial.get('completion', 'N/A')
            sponsor = trial.get('sponsor', '')

            status_emoji = "🟢" if status == "RECRUITING" else "🟡" if "ACTIVE" in status.upper() else "⚪"
            print(f"  {status_emoji} [{phase}] {title}...")
            print(f"      NCT: {nct} | 완료예정: {completion}")
            if sponsor:
                print(f"      스폰서: {sponsor}")
    else:
        print("  임상시험 정보 없음 (또는 검색 실패)")


def print_automotive_catalysts(catalysts: dict):
    """자동차/EV 촉매 출력"""
    section("자동차/EV 촉매 분석", "🚗")

    if catalysts.get("ev_credits"):
        print("  ⚡ EV 세액공제 관련 뉴스!")
    if catalysts.get("battery_partnership"):
        print("  🔋 배터리 파트너십 뉴스!")
    if catalysts.get("autonomous_update"):
        print("  🤖 자율주행 업데이트!")

    production = catalysts.get("production_numbers", [])
    if production:
        subsection("생산/배송 뉴스")
        for i, news in enumerate(production[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    models = catalysts.get("new_models", [])
    if models:
        subsection("신모델 출시")
        for i, news in enumerate(models[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    if not production and not models:
        print("  최근 자동차 관련 촉매 없음")


def print_retail_catalysts(catalysts: dict):
    """리테일 촉매 출력"""
    section("리테일 촉매 분석", "🛒")

    if catalysts.get("holiday_sales"):
        print("  🎄 연말 쇼핑 시즌 뉴스!")
    if catalysts.get("inventory_update"):
        print("  📦 재고 관련 업데이트!")

    sss = catalysts.get("same_store_sales", [])
    if sss:
        subsection("동일점포 매출")
        for i, news in enumerate(sss[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    ecom = catalysts.get("ecommerce_growth", [])
    if ecom:
        subsection("이커머스 성장")
        for i, news in enumerate(ecom[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    stores = catalysts.get("store_openings", [])
    if stores:
        subsection("매장 오픈/폐쇄")
        for i, news in enumerate(stores[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    if not sss and not ecom and not stores:
        print("  최근 리테일 관련 촉매 없음")


def print_financial_catalysts(catalysts: dict):
    """금융 촉매 출력"""
    section("금융 촉매 분석", "🏦")

    if catalysts.get("dividend_update"):
        print("  💰 배당 관련 뉴스!")
    if catalysts.get("capital_ratio"):
        print("  📊 자본비율 관련 뉴스!")

    fed = catalysts.get("fed_rate_impact", [])
    if fed:
        subsection("금리 영향")
        for i, news in enumerate(fed[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    loan = catalysts.get("loan_growth", [])
    if loan:
        subsection("대출 성장")
        for i, news in enumerate(loan[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    reg = catalysts.get("regulatory_news", [])
    if reg:
        subsection("규제 뉴스")
        for i, news in enumerate(reg[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    if not fed and not loan and not reg:
        print("  최근 금융 관련 촉매 없음")


def print_industrial_catalysts(catalysts: dict):
    """산업재 촉매 출력"""
    section("산업재 촉매 분석", "🏭")

    if catalysts.get("supply_chain"):
        print("  🚚 공급망 관련 뉴스!")
    if catalysts.get("pmi_update"):
        print("  📈 PMI/제조업 지수 뉴스!")

    contracts = catalysts.get("contracts", [])
    if contracts:
        subsection("수주/계약")
        for i, news in enumerate(contracts[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    gov = catalysts.get("gov_spending", [])
    if gov:
        subsection("정부 지출")
        for i, news in enumerate(gov[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    defense = catalysts.get("defense_budget", [])
    if defense:
        subsection("국방 예산")
        for i, news in enumerate(defense[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    if not contracts and not gov and not defense:
        print("  최근 산업재 관련 촉매 없음")


def print_realestate_catalysts(catalysts: dict):
    """부동산/리츠 촉매 출력"""
    section("부동산/리츠 촉매 분석", "🏠")

    if catalysts.get("cap_rate"):
        print("  📉 Cap Rate 관련 뉴스!")
    if catalysts.get("noi_growth"):
        print("  📈 NOI 성장 관련 뉴스!")

    rate = catalysts.get("rate_impact", [])
    if rate:
        subsection("금리 영향")
        for i, news in enumerate(rate[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    occ = catalysts.get("occupancy", [])
    if occ:
        subsection("점유율")
        for i, news in enumerate(occ[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    acq = catalysts.get("acquisitions", [])
    if acq:
        subsection("인수/매각")
        for i, news in enumerate(acq[:3], 1):
            print(f"  [{i}] {news[:70]}...")

    if not rate and not occ and not acq:
        print("  최근 부동산 관련 촉매 없음")


def print_8k_events(events: list):
    """8-K 이벤트 출력"""
    section("8-K 주요 공시", "📢")

    if not events:
        print("  최근 8-K 공시 없음")
        return

    for event in events[:5]:
        date = event.get('date', '')
        event_type = event.get('type', '기타')
        importance = event.get('importance', '')

        print(f"  {importance} {date}: {event_type}")


def print_sec_info(sec_info: dict):
    """SEC 공시 정보"""
    section("SEC 공시 분석", "📋")

    subsection("SEC 키워드 언급 횟수 (2024년~)")
    print(f"  Warrant 언급: {sec_info.get('warrant_mentions', 0)}건")
    print(f"  Dilution 언급: {sec_info.get('dilution_mentions', 0)}건")
    print(f"  Covenant/빚 조항: {sec_info.get('covenant_mentions', 0)}건")
    print(f"  Debt 언급: {sec_info.get('debt_mentions', 0)}건")
    print(f"  Lock-up 언급: {sec_info.get('lockup_mentions', 0)}건")
    print(f"  S-3/424B (오퍼링): {sec_info.get('offering_mentions', 0)}건")

    subsection("뉴스 분석 (2025년)")
    print(f"  호재 관련: {sec_info.get('positive_news', 0)}건")
    print(f"  악재 관련: {sec_info.get('negative_news', 0)}건")

    subsection("리스크 해석")
    risks = []
    safe = []

    if sec_info.get("has_warrant_risk"):
        risks.append("⚠️ 워런트 리스크 (희석 가능성)")
    else:
        safe.append("✅ 워런트 리스크 낮음")

    if sec_info.get("dilution_risk"):
        risks.append("⚠️ 희석 리스크 (Dilution 언급 多)")
    else:
        safe.append("✅ 희석 리스크 낮음")

    if sec_info.get("has_debt_covenant"):
        risks.append("⚠️ 빚/Covenant 조항 있음")
    else:
        safe.append("✅ Covenant 리스크 낮음")

    if sec_info.get("has_offering_risk"):
        risks.append("⚠️ 오퍼링 리스크 (S-3/424B 등록)")
    else:
        safe.append("✅ 오퍼링 리스크 낮음")

    if sec_info.get("has_lockup"):
        print("  🔒 Lock-up 조항 존재 (내부자 매도 제한)")

    if sec_info.get("has_positive_news"):
        safe.append("🔥 호재 공시 多")
    if sec_info.get("has_negative_news"):
        risks.append("❌ 악재 공시 多")

    if risks:
        for r in risks:
            print(f"  {r}")
    if safe:
        for s in safe:
            print(f"  {s}")

    if not risks and not safe:
        print("  특이사항 없음")


def print_ftd_data(ftd: dict):
    """FTD 데이터 출력"""
    section("FTD (Failure to Deliver)", "📦")

    if not ftd.get("recent_ftd"):
        print("  FTD 데이터 없음")
        return

    print(f"  총 FTD: {fmt_num(ftd.get('total_ftd'))}주")
    print(f"  평균 FTD: {fmt_num(ftd.get('avg_ftd'))}주")
    print(f"  최대 FTD: {fmt_num(ftd.get('max_ftd'))}주")
    print(f"  추세: {ftd.get('ftd_trend', 'N/A')}")

    if ftd.get("has_significant_ftd"):
        print(f"\n  🔥 유의미한 FTD 감지! (10만주+)")

    subsection("최근 FTD")
    for f in ftd.get("recent_ftd", [])[:5]:
        print(f"    {f['date']}: {fmt_num(f['quantity'])}주")


def print_options_data(opt: dict):
    """옵션 데이터 출력"""
    section("옵션 체인 분석", "📊")

    if not opt.get("has_options"):
        print("  옵션 거래 없음")
        return

    print(f"  가장 가까운 만기: {opt.get('nearest_expiry')}")
    print(f"  콜 OI 총합: {fmt_num(opt.get('total_call_oi'))}")
    print(f"  풋 OI 총합: {fmt_num(opt.get('total_put_oi'))}")
    print(f"  Put/Call 비율: {opt.get('put_call_ratio', 0):.2f}")
    print(f"  Max Pain: ${opt.get('max_pain', 0):.2f}")
    print(f"  ITM 콜 OI: {fmt_num(opt.get('itm_calls'))}")

    if opt.get("gamma_exposure"):
        subsection("감마 집중 구간 (OI Top 5)")
        for g in opt.get("gamma_exposure", []):
            print(f"    ${g['strike']:.2f}: {fmt_num(g['oi'])} OI")


def print_social_sentiment(sent: dict):
    """소셜 센티먼트 출력"""
    section("소셜 센티먼트", "💬")

    print(f"  종합 센티먼트: {sent.get('overall_sentiment', 'N/A')}")

    if sent.get("stocktwits_sentiment"):
        print(f"  Stocktwits: {sent['stocktwits_sentiment']} ({sent.get('stocktwits_messages', 0)}개 메시지)")

    if sent.get("watchlist_count"):
        print(f"  관심목록 등록: {fmt_num(sent.get('watchlist_count'))}명")

    if sent.get("reddit_mentions"):
        print(f"  Reddit 언급: {sent['reddit_mentions']}개")

    if sent.get("recent_posts"):
        subsection("최근 포스트")
        for p in sent.get("recent_posts", [])[:5]:
            source = p.get('source', 'Unknown')
            sentiment = p.get('sentiment', 'N/A')
            emoji = "🟢" if sentiment == 'Bullish' else "🔴" if sentiment == 'Bearish' else "⚪"
            print(f"    [{source}] {emoji} {p['body'][:50]}...")


def print_catalyst(cat: dict):
    """촉매 일정 출력"""
    section("촉매(Catalyst) 일정", "📅")

    if cat.get("next_earnings"):
        print(f"  다음 어닝: {cat['next_earnings']}")

    if cat.get("recent_earnings_surprise"):
        print(f"  최근 어닝 서프라이즈: {cat['recent_earnings_surprise']}")

    if cat.get("ex_dividend_date"):
        print(f"  배당락일: {cat['ex_dividend_date']}")

    if cat.get("earnings_estimate"):
        print(f"  목표가 평균: ${cat['earnings_estimate']:.2f}")

    if not any([cat.get("next_earnings"), cat.get("ex_dividend_date")]):
        print("  예정된 촉매 없음")


def print_fibonacci(fib: dict):
    """피보나치 레벨 출력"""
    section("피보나치 & 지지/저항", "📐")

    if not fib.get("levels"):
        print("  데이터 부족")
        return

    print(f"  현재 위치: {fib.get('current_zone', 'N/A')}")

    subsection("피보나치 레벨")
    for level, price in fib.get("levels", {}).items():
        print(f"    {level}: ${price}")

    if fib.get("support_levels"):
        subsection("지지선 (현재가 아래)")
        for s in fib.get("support_levels", [])[:3]:
            print(f"    {s['level']}: ${s['price']} ({s['distance']} 아래)")

    if fib.get("resistance_levels"):
        subsection("저항선 (현재가 위)")
        for r in fib.get("resistance_levels", [])[:3]:
            print(f"    {r['level']}: ${r['price']} ({r['distance']} 위)")

    if fib.get("gaps"):
        subsection("갭 분석 (최근 20일)")
        for g in fib.get("gaps", [])[:5]:
            print(f"    {g['date']}: {g['type']} ${g['gap_start']}-${g['gap_end']} [{g['filled']}]")


def print_volume_profile(vp: dict):
    """볼륨 프로파일 출력"""
    section("볼륨 프로파일", "📊")

    if not vp.get("poc"):
        print("  데이터 부족")
        return

    print(f"  POC (거래량 집중가): ${vp.get('poc')}")
    print(f"  Value Area High: ${vp.get('value_area_high')}")
    print(f"  Value Area Low: ${vp.get('value_area_low')}")

    if vp.get("high_volume_zones"):
        subsection("고거래량 가격대")
        for z in vp.get("high_volume_zones", [])[:5]:
            print(f"    ${z['price']}: {fmt_num(z['volume'])}주")


def print_darkpool(dp: dict):
    """다크풀 데이터 출력"""
    section("다크풀 & 숏볼륨", "🌑")

    if dp.get("source"):
        print(f"  📡 소스: {dp['source']}")

    if dp.get("short_volume_percent"):
        print(f"  숏 볼륨 비율: {dp['short_volume_percent']}%")

    if dp.get("off_exchange_percent"):
        print(f"  장외거래(다크풀) 비율: {dp['off_exchange_percent']}%")

    if dp.get("darkpool_volume"):
        print(f"  다크풀 거래량: {fmt_num(dp['darkpool_volume'])}주")

    if dp.get("warning"):
        print(f"\n  {dp['warning']}")

    if dp.get("dp_warning"):
        print(f"  {dp['dp_warning']}")

    if not dp.get("short_volume_percent") and not dp.get("off_exchange_percent"):
        print("  데이터 없음")


def print_sec_filings(filings: dict):
    """SEC Filing 출력"""
    section("SEC Filing 상세", "📑")

    if filings.get("company_name"):
        print(f"  SEC 등록명: {filings['company_name']}")

    if filings.get("cik"):
        print(f"  CIK: {filings['cik']}")

    if filings.get("insider_lockup_price"):
        print(f"\n  🔒 내부자 락업 가격: {filings['insider_lockup_price']}")

    if filings.get("lockup_info"):
        print(f"  🔒 락업 정보: {filings['lockup_info']}")

    if filings.get("is_spac"):
        print(f"\n  🚀 SPAC 합병 종목!")

    if filings.get("earnout_prices"):
        subsection("Earnout 조건 (락업 해제 가격)")
        for price in filings["earnout_prices"]:
            print(f"    🎯 주가 {price} 도달 시 → 주식 락업 해제")
        print(f"    💡 이 가격들에서 내부자/스폰서가 매도 가능해짐 (공급 증가)")

    if filings.get("earnout_shares"):
        print(f"  📈 Earnout 대상 주식 수: {filings['earnout_shares']}주")

    if filings.get("warrant_details"):
        subsection("워런트 행사가")
        for w in filings["warrant_details"]:
            print(f"    💰 {w}")

    if filings.get("debt_details"):
        subsection("빚/대출 정보")
        for d in filings["debt_details"]:
            print(f"    💳 {d}")

    if filings.get("offering_info"):
        subsection("오퍼링 이력")
        for o in filings["offering_info"]:
            print(f"    📄 {o['date']}: {o['shares']}주 @ {o['price']} ({o['form']})")

    if filings.get("recent_filings"):
        subsection("최근 SEC 공시")
        for f in filings["recent_filings"][:7]:
            form_emoji = "📋"
            if f['form'] in ['S-1', 'S-3', '424B4', '424B5']:
                form_emoji = "⚠️"
            elif f['form'] in ['S-4', 'S-4/A', 'DEFM14A']:
                form_emoji = "🚀"
            elif f['form'] == '8-K':
                form_emoji = "📢"
            elif f['form'] in ['10-K', '10-Q']:
                form_emoji = "📊"
            print(f"    {form_emoji} {f['date']}: {f['form']}")

    if not filings.get("recent_filings") and not filings.get("insider_lockup_price"):
        print("  SEC 데이터 없음")


def print_institutional(inst: dict):
    """기관 보유 출력"""
    section("기관 보유 현황", "🏛️")

    print(f"  기관 보유 비율: {inst.get('institutional_percent', 'N/A')}")
    print(f"  기관 수: {inst.get('total_institutional', 0)}개")

    if inst.get("top_holders"):
        subsection("Top 5 기관")
        for h in inst["top_holders"]:
            print(f"    {h['holder'][:25]}: {fmt_num(h['shares'])}주 ({h['pct_out']})")


def print_peer_comparison(peer: dict):
    """동종업체 비교 출력"""
    section("동종업체 비교", "🏭")

    print(f"  섹터: {peer.get('sector', 'N/A')}")
    print(f"  산업: {peer.get('industry', 'N/A')}")
    print(f"  섹터 평균 PE: {peer.get('sector_avg_pe', 'N/A')}")
    print(f"  상대 밸류에이션: {peer.get('relative_valuation', 'N/A')}")


def print_short_history(sh: dict):
    """Short Interest 히스토리 출력"""
    section("Short Interest 추이", "📉")

    if sh.get("current_si"):
        print(f"  현재 SI: {fmt_num(sh['current_si'])}주")
    if sh.get("prior_si"):
        print(f"  전월 SI: {fmt_num(sh['prior_si'])}주")

    print(f"  30일 변화: {sh.get('change_30d', 'N/A')}")
    print(f"  추세: {sh.get('trend', 'N/A')}")

    if sh.get("short_float_pct"):
        print(f"  Short Float %: {sh['short_float_pct']}")

    if sh.get("short_ratio"):
        print(f"  Short Ratio: {sh['short_ratio']}일")

    if sh.get("short_volume"):
        print(f"  Short Volume: {fmt_num(int(sh['short_volume']))}주")


# ============================================================
# 메인 분석
# ============================================================

def analyze(ticker: str, use_ai: bool = True, force_normal: bool = False):
    """종합 분석 실행"""

    mode = "일반 투자" if force_normal else "자동 (숏스퀴즈/일반)"
    print(f"\n{'#'*70}")
    print(f"#  🔍 {ticker} 초정밀 분석 리포트 v3 (똥꾸멍 주름 에디션)")
    print(f"#  📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"#  🤖 Gemini AI: {'ON' if use_ai else 'OFF'}")
    print(f"#  📊 분석 모드: {mode}")
    print(f"{'#'*70}")

    try:
        # ========== 데이터 수집 ==========
        print("\n⏳ 데이터 수집 중... (초정밀 분석 v3)")

        # 1. yfinance 기본 정보
        print("  → yfinance 기본 정보...")
        data = get_basic_info(ticker)
        stock = data['stock']

        # 2. Borrow 데이터 (Zero Borrow 포함)
        print("  → Borrow Rate & Zero Borrow...")
        borrow = get_borrow_data(ticker)

        # 3. RegSHO
        print("  → RegSHO Threshold...")
        regsho_info = check_regsho(ticker)

        # 4. 기술적 지표
        print("  → 기술적 분석...")
        tech = get_technicals(stock)

        # 5. 경영진 & 내부자
        print("  → 경영진 & 내부자...")
        officers = get_officers(stock)
        insider_tx = get_insider_transactions(stock)
        inst_holders = get_institutional_holders(stock)

        # 6. 뉴스 (섹터별 특화)
        print("  → 뉴스...")
        news = get_news(stock)
        if not news:
            news = search_recent_news(ticker)

        # 6.5 섹터별 특화 뉴스
        print("  → 섹터별 특화 뉴스...")
        sector = data.get('sector', '')
        industry = data.get('industry', '')
        sector_news = get_sector_news(ticker, sector, industry)

        # 6.6 섹터별 촉매 분석
        sector_catalysts = None
        sector_catalyst_type = None
        company_name = data.get('name', ticker)
        industry_lower = (industry or "").lower()
        sector_lower = (sector or "").lower()

        if "biotech" in industry_lower or "pharma" in industry_lower or "healthcare" in sector_lower:
            print("  → 바이오텍 촉매 분석 (FDA/임상)...")
            sector_catalysts = get_biotech_catalysts(ticker, company_name)
            sector_catalyst_type = "biotech"
        elif "auto" in industry_lower or "vehicle" in industry_lower or "ev" in industry_lower:
            print("  → 자동차/EV 촉매 분석...")
            sector_catalysts = get_automotive_catalysts(ticker, company_name)
            sector_catalyst_type = "automotive"
        elif "real estate" in sector_lower or "reit" in industry_lower:
            print("  → 부동산/리츠 촉매 분석...")
            sector_catalysts = get_realestate_catalysts(ticker, company_name)
            sector_catalyst_type = "realestate"
        elif "retail" in industry_lower or "e-commerce" in industry_lower or "store" in industry_lower:
            print("  → 리테일 촉매 분석...")
            sector_catalysts = get_retail_catalysts(ticker, company_name)
            sector_catalyst_type = "retail"
        elif "food" in industry_lower or "beverage" in industry_lower or "consumer" in sector_lower:
            print("  → 소비재 촉매 분석...")
            sector_catalysts = get_retail_catalysts(ticker, company_name)
            sector_catalyst_type = "consumer"
        elif "bank" in industry_lower or "financial" in sector_lower or "insurance" in industry_lower:
            print("  → 금융 촉매 분석...")
            sector_catalysts = get_financial_catalysts(ticker, company_name)
            sector_catalyst_type = "financial"
        elif "industrial" in sector_lower or "aerospace" in industry_lower or "defense" in industry_lower:
            print("  → 산업재 촉매 분석...")
            sector_catalysts = get_industrial_catalysts(ticker, company_name)
            sector_catalyst_type = "industrial"

        # 7. SEC 공시 정보 (빚, covenant, 희석 리스크)
        print("  → SEC 공시 키워드 분석...")
        sec_info = get_sec_info(ticker)

        # 8. FTD 데이터
        print("  → FTD (Failure to Deliver)...")
        ftd_data = get_ftd_data(ticker)

        # 9. 옵션 체인
        print("  → 옵션 체인 분석...")
        options_data = get_options_data(stock)

        # 10. 소셜 센티먼트
        print("  → 소셜 센티먼트 (Stocktwits)...")
        sentiment_data = get_social_sentiment(ticker)

        # 11. 촉매 일정
        print("  → 촉매 일정...")
        catalyst_data = get_catalyst_calendar(stock)

        # 12. 피보나치 & 지지/저항
        print("  → 피보나치 레벨...")
        fib_data = get_fibonacci_levels(stock)

        # 13. 볼륨 프로파일
        print("  → 볼륨 프로파일...")
        volume_profile = get_volume_profile(stock)

        # 14. 다크풀
        print("  → 다크풀 데이터...")
        darkpool_data = get_darkpool_data(ticker)

        # 15. SEC Filing 상세 (S-1, 락업, 워런트)
        print("  → SEC Filing 상세 파싱...")
        sec_filings = get_sec_filings(ticker)

        # 15.5 8-K 주요 이벤트 파싱
        print("  → 8-K 주요 이벤트 파싱...")
        cik = sec_filings.get("cik", "")
        eight_k_events = parse_8k_content(ticker, cik)

        # 16. 기관 보유 변화
        print("  → 기관 보유 분석...")
        institutional_data = get_institutional_changes(stock)

        # 17. 동종업체 비교
        print("  → 동종업체 비교...")
        peer_data = get_peer_comparison(stock, ticker)

        # 18. Short Interest 히스토리
        print("  → Short Interest 추이...")
        short_history = get_short_history(ticker)

        # 19. 스퀴즈 점수
        print("  → 스퀴즈 점수 계산...")
        score_info = calculate_squeeze_score_v3(data, borrow, regsho_info, tech)

        print("\n✅ 데이터 수집 완료!")

        # ========== 출력 ==========

        print_basic_info(data)
        print_price_info(data)
        print_financials(data)

        print_short_data(data, borrow, regsho_info)
        print_short_history(short_history)
        print_ftd_data(ftd_data)

        print_technicals(tech, data.get('price', 0))
        print_fibonacci(fib_data)
        print_volume_profile(volume_profile)

        print_options_data(options_data)
        print_darkpool(darkpool_data)

        print_squeeze_score(score_info, regsho_info)

        print_sec_info(sec_info)
        print_sec_filings(sec_filings)

        print_institutional(institutional_data)
        print_peer_comparison(peer_data)

        print_catalyst(catalyst_data)
        print_social_sentiment(sentiment_data)

        print_officers(officers)
        print_news(news)

        print_sector_news(sector_news)

        print_8k_events(eight_k_events)

        if sector_catalysts:
            if sector_catalyst_type == "biotech":
                print_biotech_catalysts(sector_catalysts)
            elif sector_catalyst_type == "automotive":
                print_automotive_catalysts(sector_catalysts)
            elif sector_catalyst_type == "retail" or sector_catalyst_type == "consumer":
                print_retail_catalysts(sector_catalysts)
            elif sector_catalyst_type == "financial":
                print_financial_catalysts(sector_catalysts)
            elif sector_catalyst_type == "industrial":
                print_industrial_catalysts(sector_catalysts)
            elif sector_catalyst_type == "realestate":
                print_realestate_catalysts(sector_catalysts)

        # ========== Gemini AI 분석 ==========

        if use_ai:
            section("Gemini AI 종합 분석", "🤖")
            print("\n  ⏳ AI 분석 중...")
            ai_analysis = analyze_with_gemini(
                ticker, data, borrow, tech, regsho_info, score_info, news, force_normal, sec_info, sec_filings
            )
            print(f"\n{ai_analysis}")

        # ========== 최종 요약 ==========

        section("최종 요약", "💡")

        price = data.get('price', 0)
        post = data.get('post_market')
        score = score_info['score']

        print(f"\n  📊 {data['name']} ({ticker})")
        print(f"  💰 현재가: ${price:.2f}")
        if post:
            print(f"  🌙 애프터: ${post:.2f} ({((post/price)-1)*100:+.1f}%)")
        print(f"  🎰 스퀴즈 점수: {score}/100")

        if borrow.get("is_zero_borrow"):
            print(f"\n  🔥 ZERO BORROW 상태!")
            print(f"     → 새 숏 진입 불가")
            print(f"     → 기존 숏 탈출 = 시장 매수 필수")
            print(f"     → 스퀴즈 조건 충족!")

        if regsho_info.get("listed"):
            days = regsho_info.get("days", 0)
            if days > 0:
                print(f"\n  📋 RegSHO Threshold 등재 ({days}일째)")
                if days >= 13:
                    print(f"     → 🚨 강제 바이인 구간!")
            else:
                print(f"\n  📋 RegSHO Threshold 등재됨")

        if score >= 40 and regsho_info.get("listed"):
            print(f"\n  🚨 SQUEEZE 판정!")
        elif score >= 40:
            print(f"\n  👀 SQUEEZE WATCH 판정")

        print(f"\n{'='*70}")
        print(f"⚠️ 투자 결정은 본인 책임입니다.")
        print(f"{'='*70}\n")

        return {
            "data": data,
            "borrow": borrow,
            "tech": tech,
            "regsho_info": regsho_info,
            "score_info": score_info
        }

    except Exception as e:
        print(f"\n❌ 분석 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python deep_analyzer.py <TICKER> [OPTIONS]")
        print("Example: uv run python deep_analyzer.py BNAI")
        print("         uv run python deep_analyzer.py BNAI --no-ai")
        print("         uv run python deep_analyzer.py GLSI --normal  # 일반 투자 분석")
        sys.exit(1)

    ticker = sys.argv[1].upper()
    use_ai = "--no-ai" not in sys.argv
    force_normal = "--normal" in sys.argv

    analyze(ticker, use_ai, force_normal)


if __name__ == "__main__":
    main()
