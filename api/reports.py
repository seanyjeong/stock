"""
리포트 생성 API
- 백그라운드 분석 실행
- PDF 생성 (WeasyPrint)
- 진행률 폴링
"""
import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor
import json

from db import get_db
from api.auth import require_approved_user

# deep_analyzer 함수들 import
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from deep_analyzer import (
    get_basic_info, get_borrow_data, get_fintel_data, get_sec_info,
    get_ftd_data, get_options_data, get_social_sentiment, get_catalyst_calendar,
    get_fibonacci_levels, get_volume_profile, get_darkpool_data, get_sec_filings,
    get_institutional_changes, get_peer_comparison, get_short_history,
    check_regsho, get_technicals, get_officers, get_insider_transactions,
    get_institutional_holders, get_news, search_recent_news, get_sector_news,
    get_biotech_catalysts, parse_8k_content, calculate_squeeze_score_v3,
    analyze_with_gemini, get_finviz_news
)
import yfinance as yf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["reports"])

# 리포트 저장 디렉토리
REPORTS_DIR = Path(__file__).parent.parent / "reports" / "generated"
TEMPLATES_DIR = Path(__file__).parent.parent / "reports" / "templates"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# 진행 중인 작업 추적 (메모리 캐시)
active_jobs: dict[str, dict] = {}

# 분석 단계 정의 (22단계)
ANALYSIS_STEPS = [
    (5, "기본 정보 수집"),
    (10, "대차 데이터 조회"),
    (15, "RegSHO 확인"),
    (20, "기술적 분석"),
    (25, "경영진 정보"),
    (30, "뉴스 수집"),
    (35, "섹터별 뉴스"),
    (40, "촉매 이벤트"),
    (45, "SEC 키워드 분석"),
    (50, "FTD 데이터"),
    (55, "옵션 체인"),
    (60, "소셜 센티먼트"),
    (65, "촉매 일정"),
    (70, "피보나치 레벨"),
    (75, "볼륨 프로파일"),
    (78, "다크풀 데이터"),
    (82, "SEC Filing 파싱"),
    (85, "8-K 이벤트"),
    (88, "스퀴즈 점수 계산"),
    (92, "AI 종합 분석"),
    (96, "PDF 생성"),
    (100, "완료"),
]


class ReportGenerateRequest(BaseModel):
    ticker: str
    include_portfolio: bool = False


class ReportStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    current_step: Optional[str] = None
    error_message: Optional[str] = None
    pdf_path: Optional[str] = None


def update_job_progress(job_id: str, progress: int, step: str):
    """작업 진행률 업데이트 (DB + 메모리)"""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE report_jobs
            SET progress = %s, current_step = %s
            WHERE job_id = %s
        """, (progress, step, job_id))
        conn.commit()

        # 메모리 캐시도 업데이트
        if job_id in active_jobs:
            active_jobs[job_id]["progress"] = progress
            active_jobs[job_id]["current_step"] = step
    finally:
        cur.close()
        conn.close()


def complete_job(job_id: str, result_data: dict, pdf_path: str):
    """작업 완료 처리"""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE report_jobs
            SET status = 'completed', progress = 100, current_step = '완료',
                result_data = %s, pdf_path = %s, completed_at = %s
            WHERE job_id = %s
        """, (json.dumps(result_data, ensure_ascii=False, default=str),
              pdf_path, datetime.now(timezone.utc), job_id))
        conn.commit()

        if job_id in active_jobs:
            del active_jobs[job_id]
    finally:
        cur.close()
        conn.close()


def fail_job(job_id: str, error_message: str):
    """작업 실패 처리"""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE report_jobs
            SET status = 'failed', error_message = %s, completed_at = %s
            WHERE job_id = %s
        """, (error_message, datetime.now(timezone.utc), job_id))
        conn.commit()

        if job_id in active_jobs:
            del active_jobs[job_id]
    finally:
        cur.close()
        conn.close()


async def run_analysis(job_id: str, ticker: str, user_id: int, include_portfolio: bool):
    """백그라운드 분석 실행"""
    try:
        ticker = ticker.upper().strip()
        result_data = {"ticker": ticker}

        # 1. 기본 정보
        update_job_progress(job_id, 5, "기본 정보 수집")
        stock = yf.Ticker(ticker)
        basic_info = get_basic_info(ticker)
        result_data["basic_info"] = basic_info

        # 가격 변화율 계산 (5일, 20일)
        try:
            hist = stock.history(period="1mo")
            if len(hist) >= 20:
                price_now = basic_info.get("price", 0) or hist['Close'].iloc[-1]
                price_5d = hist['Close'].iloc[-5] if len(hist) >= 5 else price_now
                price_20d = hist['Close'].iloc[-20] if len(hist) >= 20 else price_now
                result_data["price_changes"] = {
                    "change_5d": ((price_now / price_5d) - 1) * 100 if price_5d > 0 else 0,
                    "change_20d": ((price_now / price_20d) - 1) * 100 if price_20d > 0 else 0
                }
            else:
                result_data["price_changes"] = {"change_5d": 0, "change_20d": 0}
        except Exception as e:
            logger.warning(f"Price changes calculation failed: {e}")
            result_data["price_changes"] = {"change_5d": 0, "change_20d": 0}

        await asyncio.sleep(0.1)  # 비동기 컨텍스트 유지

        # 2. 대차 데이터
        update_job_progress(job_id, 10, "대차 데이터 조회")
        borrow_data = get_borrow_data(ticker)
        result_data["borrow_data"] = borrow_data
        await asyncio.sleep(0.1)

        # 3. RegSHO 확인
        update_job_progress(job_id, 15, "RegSHO 확인")
        in_regsho = check_regsho(ticker)
        result_data["in_regsho"] = in_regsho
        await asyncio.sleep(0.1)

        # 4. 기술적 분석
        update_job_progress(job_id, 20, "기술적 분석")
        technicals = get_technicals(stock)
        result_data["technicals"] = technicals
        await asyncio.sleep(0.1)

        # 5. 경영진 정보
        update_job_progress(job_id, 25, "경영진 정보")
        officers = get_officers(stock)
        result_data["officers"] = officers
        await asyncio.sleep(0.1)

        # 6. 뉴스 수집
        update_job_progress(job_id, 30, "뉴스 수집")
        news = search_recent_news(ticker, days=60)
        finviz_news = get_finviz_news(ticker)
        result_data["news"] = news[:10] if news else []
        result_data["finviz_news"] = finviz_news[:5] if finviz_news else []
        await asyncio.sleep(0.1)

        # 7. 섹터별 뉴스
        update_job_progress(job_id, 35, "섹터별 뉴스")
        sector = basic_info.get("sector", "")
        industry = basic_info.get("industry", "")
        sector_news = get_sector_news(ticker, sector, industry)
        result_data["sector_news"] = sector_news
        await asyncio.sleep(0.1)

        # 8. 촉매 이벤트
        update_job_progress(job_id, 40, "촉매 이벤트")
        company_name = basic_info.get("name", ticker)
        if "biotech" in (sector or "").lower() or "pharma" in (industry or "").lower():
            catalysts = get_biotech_catalysts(ticker, company_name)
            result_data["biotech_catalysts"] = catalysts
        await asyncio.sleep(0.1)

        # 9. SEC 키워드 분석
        update_job_progress(job_id, 45, "SEC 키워드 분석")
        sec_info = get_sec_info(ticker)
        result_data["sec_info"] = sec_info
        await asyncio.sleep(0.1)

        # 10. FTD 데이터
        update_job_progress(job_id, 50, "FTD 데이터")
        ftd_data = get_ftd_data(ticker)
        result_data["ftd_data"] = ftd_data
        await asyncio.sleep(0.1)

        # 11. 옵션 체인
        update_job_progress(job_id, 55, "옵션 체인")
        options_data = get_options_data(stock)
        result_data["options_data"] = options_data
        await asyncio.sleep(0.1)

        # 12. 소셜 센티먼트
        update_job_progress(job_id, 60, "소셜 센티먼트")
        sentiment = get_social_sentiment(ticker)
        result_data["sentiment"] = sentiment
        await asyncio.sleep(0.1)

        # 13. 촉매 일정
        update_job_progress(job_id, 65, "촉매 일정")
        catalyst_calendar = get_catalyst_calendar(stock)
        result_data["catalyst_calendar"] = catalyst_calendar
        await asyncio.sleep(0.1)

        # 14. 피보나치 레벨
        update_job_progress(job_id, 70, "피보나치 레벨")
        fibonacci = get_fibonacci_levels(stock)
        result_data["fibonacci"] = fibonacci
        await asyncio.sleep(0.1)

        # 15. 볼륨 프로파일
        update_job_progress(job_id, 75, "볼륨 프로파일")
        volume_profile = get_volume_profile(stock)
        result_data["volume_profile"] = volume_profile
        await asyncio.sleep(0.1)

        # 16. 다크풀 데이터
        update_job_progress(job_id, 78, "다크풀 데이터")
        darkpool = get_darkpool_data(ticker)
        result_data["darkpool"] = darkpool
        await asyncio.sleep(0.1)

        # 17. SEC Filing 파싱
        update_job_progress(job_id, 82, "SEC Filing 파싱")
        sec_filings = get_sec_filings(ticker)
        result_data["sec_filings"] = sec_filings
        await asyncio.sleep(0.1)

        # 18. 8-K 이벤트
        update_job_progress(job_id, 85, "8-K 이벤트")
        cik = sec_filings.get("cik", "")
        if cik:
            events_8k = parse_8k_content(ticker, cik)
            result_data["events_8k"] = events_8k[:5] if events_8k else []
        await asyncio.sleep(0.1)

        # 18.5 Short Interest 히스토리
        try:
            short_history = get_short_history(ticker)
            result_data["short_history"] = short_history
        except Exception as e:
            logger.warning(f"Short history failed: {e}")
            result_data["short_history"] = {}

        # 18.6 기관 보유 데이터
        try:
            inst_holders = get_institutional_holders(stock)
            result_data["institutional_holders"] = inst_holders[:10] if inst_holders else []
        except Exception as e:
            logger.warning(f"Institutional holders failed: {e}")
            result_data["institutional_holders"] = []

        # 19. 스퀴즈 점수 계산
        update_job_progress(job_id, 88, "스퀴즈 점수 계산")
        squeeze_score = calculate_squeeze_score_v3(basic_info, borrow_data, in_regsho, technicals)
        result_data["squeeze_score"] = squeeze_score
        await asyncio.sleep(0.1)

        # 20. AI 종합 분석
        update_job_progress(job_id, 92, "AI 종합 분석")
        try:
            ai_analysis = analyze_with_gemini(
                ticker, basic_info, borrow_data, technicals,
                squeeze_score, sec_info, result_data.get("news", [])
            )
            result_data["ai_analysis"] = ai_analysis
        except Exception as e:
            logger.warning(f"AI 분석 실패: {e}")
            result_data["ai_analysis"] = None
        await asyncio.sleep(0.1)

        # 포트폴리오 정보 포함
        if include_portfolio:
            conn = get_db()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            try:
                cur.execute("""
                    SELECT shares, avg_cost FROM user_holdings
                    WHERE user_id = %s AND ticker = %s
                """, (user_id, ticker))
                holding = cur.fetchone()
                if holding:
                    result_data["holding_info"] = dict(holding)
            finally:
                cur.close()
                conn.close()

        # 21. PDF 생성
        update_job_progress(job_id, 96, "PDF 생성")
        pdf_path = await generate_pdf(job_id, ticker, result_data)

        # 22. 완료
        complete_job(job_id, result_data, pdf_path)

    except Exception as e:
        logger.error(f"Analysis failed for {ticker}: {e}")
        fail_job(job_id, str(e))


async def generate_pdf(job_id: str, ticker: str, data: dict) -> str:
    """PDF 생성"""
    from weasyprint import HTML, CSS

    # HTML 템플릿 렌더링
    html_content = render_report_html(ticker, data)

    # PDF 파일 경로
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"{ticker}_{timestamp}.pdf"
    pdf_path = REPORTS_DIR / pdf_filename

    # PDF 생성
    css_path = TEMPLATES_DIR / "report.css"
    css_content = ""
    if css_path.exists():
        css_content = css_path.read_text()

    HTML(string=html_content).write_pdf(
        str(pdf_path),
        stylesheets=[CSS(string=css_content)] if css_content else None
    )

    return str(pdf_path)


def safe_get(d, key, default=None):
    """안전하게 dict에서 값 가져오기"""
    if not isinstance(d, dict):
        return default
    return d.get(key, default) or default


def emoji_to_text(text: str) -> str:
    """이모지를 PDF 호환 텍스트로 변환"""
    replacements = {
        '🔥': '[HOT]',
        '⚠️': '[!]',
        '✅': '[OK]',
        '❌': '[X]',
        '⭐': '*',
        '☆': '-',
        '😱': '(!)',
        '🟢': '[+]',
        '🟡': '[~]',
        '🔴': '[-]',
        '⚪': '[.]',
        '📊': '',
        '💰': '$',
        '🎯': '[>]',
        '📈': '[UP]',
        '📉': '[DN]',
        '🚨': '[!!]',
        '⚡': '[*]',
        '📄': '',
        '❄️': '[COLD]',
    }
    for emoji, text_rep in replacements.items():
        text = text.replace(emoji, text_rep)
    return text


def fmt_num(n, prefix=""):
    """숫자 포맷팅 (K, M, B 단위)"""
    if n is None:
        return "N/A"
    try:
        n = float(n)
        if abs(n) >= 1e12:
            return f"{prefix}{n/1e12:.2f}T"
        if abs(n) >= 1e9:
            return f"{prefix}{n/1e9:.2f}B"
        if abs(n) >= 1e6:
            return f"{prefix}{n/1e6:.2f}M"
        if abs(n) >= 1e3:
            return f"{prefix}{n/1e3:.1f}K"
        return f"{prefix}{n:,.0f}"
    except:
        return str(n)


def get_market_cap_label(mc):
    """시가총액 등급"""
    if mc is None:
        return ""
    if mc < 50_000_000:  # 50M 이하
        return "(나노캡)"
    if mc < 300_000_000:  # 300M 이하
        return "(마이크로캡)"
    if mc < 2_000_000_000:  # 2B 이하
        return "(스몰캡)"
    if mc < 10_000_000_000:  # 10B 이하
        return "(미드캡)"
    return "(라지캡)"


def translate_business_to_korean(description: str, sector: str, industry: str, ai_analysis: dict) -> str:
    """사업 내용을 한글로 요약 (AI 분석 활용)"""
    if not description:
        return "정보 없음"

    # AI 분석에서 한글 요약 추출
    if ai_analysis and isinstance(ai_analysis, dict):
        summary = ai_analysis.get("business_summary_kr") or ai_analysis.get("summary", "")
        if summary and len(summary) > 20:
            return summary[:500]

    # 기본 영문 설명 (처음 300자)
    return description[:300] + "..." if len(description) > 300 else description


def render_report_html(ticker: str, data: dict) -> str:
    """리포트 HTML 렌더링 - daily/*.md 형식과 동일하게"""

    # 데이터 추출 (안전하게)
    basic = data.get("basic_info") or {}
    borrow = data.get("borrow_data") or {}
    tech = data.get("technicals") or {}
    squeeze = data.get("squeeze_score") or {}
    fib = data.get("fibonacci") or {}
    ai = data.get("ai_analysis")
    holding = data.get("holding_info")
    sec_info = data.get("sec_info") or {}
    ftd = data.get("ftd_data") or {}
    news = data.get("news") or []
    finviz_news = data.get("finviz_news") or []
    events_8k = data.get("events_8k") or []
    inst_holders = data.get("institutional_holders") or []
    short_history = data.get("short_history") or {}
    price_changes = data.get("price_changes") or {}

    # dict 타입 체크
    if not isinstance(basic, dict): basic = {}
    if not isinstance(borrow, dict): borrow = {}
    if not isinstance(tech, dict): tech = {}
    if not isinstance(squeeze, dict): squeeze = {}
    if not isinstance(fib, dict): fib = {}
    if not isinstance(ai, dict): ai = {}
    if not isinstance(sec_info, dict): sec_info = {}
    if not isinstance(ftd, dict): ftd = {}
    if not isinstance(short_history, dict): short_history = {}
    if not isinstance(price_changes, dict): price_changes = {}

    # 기본 정보
    name = safe_get(basic, "name", ticker)
    sector = safe_get(basic, "sector", "N/A")
    industry = safe_get(basic, "industry", "N/A")
    employees = safe_get(basic, "employees", "N/A")
    website = safe_get(basic, "website", "")
    description = safe_get(basic, "description", "")

    # 가격 정보
    price = safe_get(basic, "price", 0) or 0
    prev_close = safe_get(basic, "prev_close", price) or price
    post_market = safe_get(basic, "post_market")
    week_high = safe_get(basic, "52w_high", 0) or 0
    week_low = safe_get(basic, "52w_low", 0) or 0
    market_cap = safe_get(basic, "market_cap", 0) or 0
    float_shares = safe_get(basic, "float_shares", 0) or 0

    # 가격 변화율 계산
    change_1d = ((price / prev_close) - 1) * 100 if prev_close > 0 else 0
    change_5d = safe_get(price_changes, "change_5d", 0) or 0
    change_20d = safe_get(price_changes, "change_20d", 0) or 0
    post_change = ((post_market / price) - 1) * 100 if post_market and price > 0 else 0

    # 재무 정보
    revenue = safe_get(basic, "revenue", 0)
    revenue_growth = safe_get(basic, "revenue_growth", 0)
    net_income = safe_get(basic, "net_income", 0)
    ebitda = safe_get(basic, "ebitda", 0)
    eps = safe_get(basic, "eps", 0)
    pe_ratio = safe_get(basic, "pe_ratio")
    total_cash = safe_get(basic, "total_cash", 0)
    total_debt = safe_get(basic, "total_debt", 0)
    debt_to_equity = safe_get(basic, "debt_to_equity", 0)

    # 숏 데이터
    short_pct = (safe_get(basic, "short_pct_float", 0) or 0) * 100 if safe_get(basic, "short_pct_float", 0) else 0
    if short_pct == 0:
        short_pct = safe_get(borrow, "short_pct_float", 0) or 0
    short_shares = safe_get(basic, "shares_short", 0) or 0
    dtc = safe_get(borrow, "days_to_cover") or safe_get(basic, "short_ratio", 0) or 0
    zero_borrow = safe_get(borrow, "is_zero_borrow", False)
    borrow_rate = safe_get(borrow, "borrow_rate", "N/A")
    avail_shares = safe_get(borrow, "available_shares", 0)
    short_change = safe_get(short_history, "change_30d", "N/A")

    # 기술적 지표
    rsi = safe_get(tech, "rsi", 0) or 0
    macd_hist = safe_get(tech, "macd_hist", 0) or 0
    bb_pct = safe_get(tech, "bb_position", 0) or 0
    atr_pct = safe_get(tech, "atr_pct", 0) or 0

    # RSI 해석
    if rsi < 20:
        rsi_text = "극단적 과매도!"
        rsi_emoji = "🟢"
    elif rsi < 30:
        rsi_text = "과매도"
        rsi_emoji = "🟢"
    elif rsi > 80:
        rsi_text = "극단적 과매수!"
        rsi_emoji = "🔴"
    elif rsi > 70:
        rsi_text = "과매수"
        rsi_emoji = "🔴"
    else:
        rsi_text = "중립"
        rsi_emoji = "⚪"

    # 스퀴즈 점수
    score = safe_get(squeeze, "score", 0) or 0
    details = safe_get(squeeze, "details", "") or ""
    strengths = squeeze.get("strengths", []) or []
    weaknesses = squeeze.get("weaknesses", []) or []

    # 등급
    if score >= 60:
        grade = "HOT"
        grade_emoji = "🔥🔥🔥"
    elif score >= 40:
        grade = "WATCH"
        grade_emoji = "🔥🔥"
    else:
        grade = "COLD"
        grade_emoji = "❄️"

    # 피보나치 레벨
    fib_levels = safe_get(fib, "levels", {})
    if not isinstance(fib_levels, dict): fib_levels = {}
    current_fib_position = safe_get(fib, "current_position", "")

    # SEC 리스크
    warrant_cnt = safe_get(sec_info, "warrant_mentions", 0) or 0
    dilution_cnt = safe_get(sec_info, "dilution_mentions", 0) or 0
    debt_cnt = safe_get(sec_info, "debt_mentions", 0) or 0
    covenant_cnt = safe_get(sec_info, "covenant_mentions", 0) or 0
    offering_cnt = safe_get(sec_info, "offering_mentions", 0) or 0

    # FTD
    ftd_total = safe_get(ftd, "total_ftd", 0) or 0
    ftd_max = safe_get(ftd, "max_ftd", 0) or 0

    # AI 분석
    ai_summary = ""
    ai_strengths = []
    ai_weaknesses = []
    ai_strategy = ""
    if ai and isinstance(ai, dict):
        ai_summary = safe_get(ai, "summary", "")
        ai_strengths = ai.get("strengths", []) or []
        ai_weaknesses = ai.get("weaknesses", []) or []
        ai_strategy = safe_get(ai, "strategy", "")

    # ========== HTML 구성 ==========

    # 1. 헤더
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>{ticker} 데일리 리포트 - 달러농장</title>
</head>
<body>
<div class="report">
    <header class="report-header">
        <div class="logo">달러농장</div>
        <div class="report-date">{datetime.now().strftime("%Y년 %m월 %d일")}</div>
    </header>

    <h1 class="ticker-title">{ticker} 데일리 리포트</h1>
    <p class="analyzer-info">deep_analyzer v4 + Gemini AI</p>
    <hr>
"""

    # 2. 회사 개요
    html += f"""
    <section>
        <h2>회사 개요</h2>
        <table class="info-table">
            <tr><td>회사명</td><td>{name}</td></tr>
            <tr><td>섹터</td><td>{sector} / {industry}</td></tr>
            <tr><td>직원수</td><td>{employees}명</td></tr>
            {"<tr><td>웹사이트</td><td>" + website + "</td></tr>" if website else ""}
        </table>

        <h3>사업 내용 (뭘로 돈 버나?)</h3>
        <div class="business-desc">
            {ai_summary if ai_summary else (description[:500] + "..." if len(description) > 500 else description)}
        </div>
    </section>
    <hr>
"""

    # 3. 가격 정보
    mc_label = get_market_cap_label(market_cap)
    price_class = "positive" if change_1d >= 0 else "negative"

    html += f"""
    <section>
        <h2>가격 정보</h2>
        <table class="info-table">
            <tr><td>현재가</td><td class="{price_class}"><strong>${price:.2f}</strong> ({change_1d:+.2f}%)</td></tr>
            {"<tr><td>애프터마켓</td><td>$" + f"{post_market:.2f} ({post_change:+.2f}%)</td></tr>" if post_market else ""}
            <tr><td>52주 범위</td><td>${week_low:.2f} ~ ${week_high:.2f}</td></tr>
            <tr><td>시가총액</td><td><strong>{fmt_num(market_cap, "$")}</strong> {mc_label}</td></tr>
            <tr><td>Float</td><td>{fmt_num(float_shares)}</td></tr>
        </table>

        <h3>가격 변화</h3>
        <table class="info-table">
            <tr><td>1일</td><td class="{price_class}">{change_1d:+.2f}%</td></tr>
            <tr><td>5일</td><td class="{"positive" if change_5d >= 0 else "negative"}">{change_5d:+.2f}%</td></tr>
            <tr><td>20일</td><td class="{"positive" if change_20d >= 0 else "negative"}">{change_20d:+.2f}% {"😱" if abs(change_20d) > 50 else ""}</td></tr>
        </table>
        {"<p class='alert alert-warn'>⚠️ 20일 동안 " + f"{abs(change_20d):.0f}% {'폭락' if change_20d < 0 else '폭등'}!</p>" if abs(change_20d) > 50 else ""}
    </section>
    <hr>
"""

    # 4. 재무 현황
    revenue_growth_pct = (revenue_growth * 100) if revenue_growth and revenue_growth < 10 else revenue_growth
    html += f"""
    <section>
        <h2>재무 현황</h2>
        <table class="info-table">
            <tr><td>매출 (TTM)</td><td>{fmt_num(revenue, "$")}</td></tr>
            <tr><td>매출 성장률</td><td class="{"positive" if revenue_growth_pct and revenue_growth_pct > 0 else "negative"}">{f"{revenue_growth_pct:+.1f}%" if revenue_growth_pct else "N/A"} {"좋음!" if revenue_growth_pct and revenue_growth_pct > 20 else ""}</td></tr>
            <tr><td>순이익</td><td class="{"positive" if net_income and net_income > 0 else "negative"}">{fmt_num(net_income, "$")} {"적자" if net_income and net_income < 0 else ""}</td></tr>
            <tr><td>EBITDA</td><td>{fmt_num(ebitda, "$")}</td></tr>
            <tr><td>EPS</td><td>{f"${eps:.2f}" if isinstance(eps, (int, float)) else "N/A"}</td></tr>
            <tr><td>P/E</td><td>{f"{pe_ratio:.1f}" if pe_ratio else "N/A (적자 기업)"}</td></tr>
        </table>

        <h3>재무 건전성</h3>
        <table class="info-table">
            <tr><td>현금</td><td>{fmt_num(total_cash, "$")}</td></tr>
            <tr><td>부채</td><td>{fmt_num(total_debt, "$")}</td></tr>
            <tr><td>부채비율 (D/E)</td><td>{f"{debt_to_equity:.1f}%" if debt_to_equity else "N/A"}</td></tr>
        </table>
        {"<p class='positive'>✅ 현금이 부채보다 많음 (재무 건전)</p>" if total_cash and total_debt and total_cash > total_debt else ""}
        {"<p class='negative'>⚠️ 부채가 현금보다 많음 (주의)</p>" if total_cash and total_debt and total_debt > total_cash else ""}
    </section>
    <hr>
"""

    # 5. 숏 포지션 분석
    zero_borrow_alert = ""
    if zero_borrow:
        zero_borrow_alert = """
        <div class="alert alert-hot">
            <h3>🔥🔥🔥 ZERO BORROW! 🔥🔥🔥</h3>
            <p>🚨 빌릴 주식 없음!<br>
            → 새로운 숏 포지션 진입 불가능<br>
            → 기존 숏은 시장에서 사야만 탈출 가능</p>
        </div>
        """

    html += f"""
    <section>
        <h2>숏 포지션 분석</h2>
        {zero_borrow_alert}
        <table class="info-table">
            <tr><td>Short % of Float</td><td>{short_pct:.2f}%</td></tr>
            <tr><td>Short Shares</td><td>{fmt_num(short_shares)}</td></tr>
            <tr><td>Days to Cover</td><td>{dtc:.2f}일</td></tr>
            <tr><td>Short 변화</td><td>{short_change}</td></tr>
            <tr><td><strong>Zero Borrow</strong></td><td class="{"hot" if zero_borrow else ""}"><strong>{"✅ YES!" if zero_borrow else "No"}</strong> {"🔥" if zero_borrow else ""}</td></tr>
            <tr><td>Borrow Rate</td><td>{borrow_rate}</td></tr>
            <tr><td>대차가능 주식</td><td><strong>{fmt_num(avail_shares)}</strong></td></tr>
            <tr><td>RegSHO</td><td>{"🔴 등재" if data.get("in_regsho") else "미등재"}</td></tr>
        </table>
"""

    # FTD
    if ftd_total > 0:
        html += f"""
        <h3>FTD (Failure to Deliver)</h3>
        <ul>
            <li>총 FTD: <strong>{fmt_num(ftd_total)}주</strong></li>
            <li>최대 FTD: {fmt_num(ftd_max)}주</li>
            {"<li>🔥 유의미한 FTD 감지! (10만주+)</li>" if ftd_max > 100000 else ""}
        </ul>
"""
    html += """
    </section>
    <hr>
"""

    # 6. 기술적 분석
    html += f"""
    <section>
        <h2>기술적 분석</h2>
        <table class="info-table">
            <tr><td>RSI(14)</td><td><strong>{rsi:.2f}</strong> {rsi_emoji} <strong>{rsi_text}</strong></td></tr>
            <tr><td>MACD Histogram</td><td>{macd_hist:.4f} {"상승 전환" if macd_hist > 0 else "하락"}</td></tr>
            <tr><td>볼린저 위치</td><td>{bb_pct:.1f}% {"하단" if bb_pct < 30 else "상단" if bb_pct > 70 else "중간"}</td></tr>
            <tr><td>변동성(ATR%)</td><td><strong>{atr_pct:.2f}%</strong> {"극단적!" if atr_pct > 20 else ""}</td></tr>
        </table>
        {"<p class='oversold'>⚠️ RSI " + f"{rsi:.0f} = {rsi_text} → 반등 가능성</p>" if rsi < 30 else ""}
        {"<p class='overbought'>⚠️ RSI " + f"{rsi:.0f} = {rsi_text} → 조정 가능성</p>" if rsi > 70 else ""}
    </section>
    <hr>
"""

    # 7. 피보나치 레벨
    if fib_levels:
        fib_rows = ""
        for level, price_val in sorted(fib_levels.items(), key=lambda x: float(x[0].replace('%', '')) if '%' in str(x[0]) else 0, reverse=True):
            if isinstance(price_val, (int, float)):
                fib_rows += f"<tr><td>{level}</td><td>${price_val:.2f}</td><td></td></tr>"

        html += f"""
    <section>
        <h2>피보나치 레벨</h2>
        <table class="fib-table">
            <tr><th>레벨</th><th>가격</th><th>비고</th></tr>
            {fib_rows}
        </table>
        {"<p><strong>현재 위치</strong>: " + current_fib_position + "</p>" if current_fib_position else ""}
    </section>
    <hr>
"""

    # 8. 숏스퀴즈 점수
    # 프로그레스바 생성
    filled = int(score / 5)  # 20칸 중 몇 개 채울지
    bar = "█" * filled + "░" * (20 - filled)

    html += f"""
    <section>
        <h2>숏스퀴즈 점수</h2>
        <div class="score-box">
            <span class="score-bar">[{bar}]</span>
            <span class="score">{score:.0f}/100</span>
            <span class="grade grade-{grade.lower()}">{grade_emoji} {grade}</span>
        </div>
"""

    # 점수 구성
    if details:
        if isinstance(details, list):
            details_html = "<ul>" + "".join(f"<li>{d}</li>" for d in details) + "</ul>"
        else:
            details_html = f"<p>{details}</p>"
        html += f"""
        <h3>점수 구성</h3>
        <div class="score-breakdown">{details_html}</div>
"""

    # 강세/리스크 요인
    if strengths or weaknesses:
        html += """
        <div class="factors">
"""
        if strengths:
            html += """
            <h3>강세 요인</h3>
            <ul class="strengths">
"""
            for s in strengths[:5]:
                html += f"<li>✅ {s}</li>"
            html += "</ul>"

        if weaknesses:
            html += """
            <h3>리스크 요인</h3>
            <ul class="weaknesses">
"""
            for w in weaknesses[:5]:
                html += f"<li>🟡 {w}</li>"
            html += "</ul>"
        html += "</div>"

    html += """
    </section>
    <hr>
"""

    # 9. SEC 공시 리스크
    html += f"""
    <section>
        <h2>SEC 공시 리스크</h2>
        <table class="info-table">
            <tr><td>Warrant</td><td>{warrant_cnt}건 {"⚠️ 희석 가능성" if warrant_cnt > 50 else ""}</td></tr>
            <tr><td>Dilution</td><td>{dilution_cnt}건 {"⚠️ 높음" if dilution_cnt > 50 else ""}</td></tr>
            <tr><td>Debt</td><td>{debt_cnt}건</td></tr>
            <tr><td>Covenant</td><td>{covenant_cnt}건</td></tr>
            <tr><td>S-3/424B</td><td>{offering_cnt}건 {"✅ 오퍼링 리스크 낮음" if offering_cnt == 0 else "⚠️"}</td></tr>
        </table>
"""

    # 8-K 이벤트
    if events_8k and isinstance(events_8k, list) and len(events_8k) > 0:
        html += """
        <h3>8-K 주요 공시</h3>
        <ul>
"""
        for e in events_8k[:5]:
            if isinstance(e, dict):
                date = e.get("date", "")
                etype = e.get("type", "")
                emoji = "⚡" if "계약" in etype or "파트너" in etype else "⚠️" if "유증" in etype or "공모" in etype else "📄"
                html += f"<li>{emoji} {date}: {etype}</li>"
        html += "</ul>"

    html += """
    </section>
    <hr>
"""

    # 10. 최근 뉴스
    all_news = []
    if news and isinstance(news, list):
        all_news.extend(news[:5])
    if finviz_news and isinstance(finviz_news, list):
        all_news.extend(finviz_news[:3])

    if all_news:
        html += """
    <section class="news-section">
        <h2>최근 뉴스</h2>
        <ul class="news-list">
"""
        for n in all_news[:8]:
            if isinstance(n, dict):
                title = n.get("title", "")
                date = n.get("date", n.get("published", n.get("providerPublishTime", "")))
                # 날짜 포맷팅
                if date:
                    if isinstance(date, (int, float)):
                        from datetime import datetime as dt
                        try:
                            date = dt.fromtimestamp(date).strftime("%Y-%m-%d")
                        except:
                            date = ""
                    elif isinstance(date, str) and len(date) > 10:
                        date = date[:10]
                date_str = f"<span class='news-date'>[{date}]</span> " if date else ""
                html += f"<li>{date_str}{title}</li>"
            else:
                html += f"<li>{str(n)}</li>"
        html += """
        </ul>
    </section>
    <hr>
"""

    # 11. 기관 보유
    if inst_holders and isinstance(inst_holders, list) and len(inst_holders) > 0:
        html += """
    <section>
        <h2>기관 보유</h2>
        <table class="info-table">
            <tr><th>기관</th><th>보유량</th><th>비율</th></tr>
"""
        total_inst_pct = 0
        for holder in inst_holders[:5]:
            if isinstance(holder, dict):
                name = holder.get("name", holder.get("holder", "Unknown"))
                shares = holder.get("shares", holder.get("position", 0))
                pct = holder.get("pct", holder.get("pctHeld", 0))
                if pct and pct < 1:
                    pct = pct * 100
                total_inst_pct += pct or 0
                html += f"<tr><td>{name}</td><td>{fmt_num(shares)}주</td><td>{pct:.2f}%</td></tr>"
        html += f"""
        </table>
        <p><strong>총 기관 보유 비율</strong>: {total_inst_pct:.1f}% {"- 매우 낮음" if total_inst_pct < 10 else ""}</p>
    </section>
    <hr>
"""

    # 12. AI 종합 분석
    if ai_summary or ai_strengths or ai_weaknesses:
        html += """
    <section class="ai-section">
        <h2>AI 종합 분석 (Gemini)</h2>
"""
        if ai_summary:
            html += f"""
        <h3>핵심 요약</h3>
        <div class="ai-summary">{ai_summary}</div>
"""

        if ai_strengths:
            html += """
        <h3>수급 상황</h3>
        <ul class="strengths">
"""
            for s in ai_strengths[:5]:
                html += f"<li>✅ {s}</li>"
            html += "</ul>"

        if ai_strategy:
            html += f"""
        <h3>투자 전략</h3>
        <table class="info-table">
            <tr><td>제안</td><td>{ai_strategy}</td></tr>
        </table>
"""

        if ai_weaknesses:
            html += """
        <h3>주의사항</h3>
        <ol>
"""
            for i, w in enumerate(ai_weaknesses[:5], 1):
                html += f"<li>{w}</li>"
            html += "</ol>"

        html += """
    </section>
    <hr>
"""

    # 13. 보유 현황 (있으면)
    if holding and isinstance(holding, dict):
        h_shares = float(holding.get("shares", 0) or 0)
        h_avg_cost = float(holding.get("avg_cost", 0) or 0)
        if h_shares > 0 and h_avg_cost > 0:
            total_cost = h_shares * h_avg_cost
            current_value = h_shares * price
            profit = current_value - total_cost
            profit_pct = (profit / total_cost) * 100 if total_cost > 0 else 0

            html += f"""
    <section class="portfolio-section">
        <h2>📊 내 보유 현황</h2>
        <table class="info-table">
            <tr><td>보유 수량</td><td>{h_shares:,.0f}주</td></tr>
            <tr><td>평균 매수가</td><td>${h_avg_cost:.2f}</td></tr>
            <tr><td>매수 총액</td><td>${total_cost:,.0f}</td></tr>
            <tr><td>현재 평가액</td><td>${current_value:,.0f}</td></tr>
            <tr><td>수익/손실</td><td class="{"positive" if profit >= 0 else "negative"}"><strong>${profit:+,.0f} ({profit_pct:+.1f}%)</strong></td></tr>
        </table>
    </section>
    <hr>
"""

    # 14. 결론
    # 등급 계산
    squeeze_stars = 4 if score >= 60 else 3 if score >= 40 else 2
    daytrading_stars = 3 if atr_pct > 10 else 2
    swing_stars = 3 if score >= 40 and rsi < 40 else 2
    longterm_stars = 1 if market_cap < 100_000_000 else 2

    def stars(n):
        return "⭐" * n + "☆" * (5 - n)

    total_stars = (squeeze_stars + daytrading_stars + swing_stars) // 3

    html += f"""
    <section class="conclusion">
        <h2>결론</h2>
        <table class="info-table">
            <tr><td>숏스퀴즈</td><td>{stars(squeeze_stars)} <strong>{"Zero Borrow!" if zero_borrow else ""}</strong></td></tr>
            <tr><td>단타 적합</td><td>{stars(daytrading_stars)} {"변동성 극심" if atr_pct > 20 else ""}</td></tr>
            <tr><td>스윙 적합</td><td>{stars(swing_stars)}</td></tr>
            <tr><td>장기 투자</td><td>{stars(longterm_stars)} {mc_label}</td></tr>
        </table>

        <div class="rating-box">
            <p><strong>최종 등급</strong>: {stars(total_stars)} ({total_stars}점 만점 중 {total_stars}점)</p>
        </div>

        <div class="key-points">
            <h3>핵심 포인트</h3>
            <ul>
"""

    # 핵심 포인트 자동 생성
    if zero_borrow:
        html += "<li>✅ Zero Borrow = 숏 진입 불가, 스퀴즈 조건</li>"
    if rsi < 30:
        html += f"<li>✅ RSI {rsi:.0f} = 과매도, 반등 가능</li>"
    if rsi > 70:
        html += f"<li>⚠️ RSI {rsi:.0f} = 과매수, 조정 주의</li>"
    if abs(change_20d) > 50:
        html += f"<li>⚠️ 20일 {change_20d:+.0f}% = {'폭락' if change_20d < 0 else '폭등'} 중</li>"
    if market_cap < 50_000_000:
        html += f"<li>⚠️ 시총 {fmt_num(market_cap, '$')} = 나노캡, 극변동성</li>"
    if score >= 60:
        html += f"<li>🎯 스퀴즈 점수 {score:.0f}/100 = HOT!</li>"

    html += """
            </ul>
        </div>
    </section>
    <hr>
"""

    # 15. 푸터
    html += f"""
    <footer class="report-footer">
        <p><em>이 리포트는 투자 참고용이며, 투자 결정은 본인 책임입니다.</em></p>
        <p>달러농장 &copy; {datetime.now().year}</p>
    </footer>
</div>
</body>
</html>
"""

    # 이모지를 PDF 호환 텍스트로 변환
    return emoji_to_text(html)


@router.post("/generate")
async def generate_report(
    request: ReportGenerateRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_approved_user)
):
    """리포트 생성 시작"""
    ticker = request.ticker.upper().strip()
    user_id = user["id"]

    # 동시 작업 제한 체크
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT job_id FROM report_jobs
            WHERE user_id = %s AND status IN ('pending', 'running')
        """, (user_id,))
        existing = cur.fetchone()
        if existing:
            raise HTTPException(
                status_code=429,
                detail=f"이미 진행 중인 리포트가 있습니다. (job_id: {existing['job_id']})"
            )

        # 새 작업 생성
        job_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO report_jobs (job_id, user_id, ticker, status, include_portfolio)
            VALUES (%s, %s, %s, 'running', %s)
        """, (job_id, user_id, ticker, request.include_portfolio))
        conn.commit()

        # 메모리 캐시에 추가
        active_jobs[job_id] = {
            "ticker": ticker,
            "progress": 0,
            "current_step": "시작"
        }

    finally:
        cur.close()
        conn.close()

    # 백그라운드 작업 시작
    asyncio.create_task(run_analysis(job_id, ticker, user_id, request.include_portfolio))

    return {"job_id": job_id, "status": "started"}


@router.get("/{job_id}/status")
async def get_report_status(
    job_id: str,
    user: dict = Depends(require_approved_user)
):
    """리포트 생성 상태 조회"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT job_id, status, progress, current_step, error_message, pdf_path
            FROM report_jobs
            WHERE job_id = %s AND user_id = %s
        """, (job_id, user["id"]))
        job = cur.fetchone()

        if not job:
            raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다")

        # UUID를 string으로 변환
        job_dict = dict(job)
        job_dict["job_id"] = str(job_dict["job_id"])
        return ReportStatusResponse(**job_dict)
    finally:
        cur.close()
        conn.close()


@router.get("/{job_id}/download")
async def download_report(
    job_id: str,
    user: dict = Depends(require_approved_user)
):
    """PDF 다운로드"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT pdf_path, ticker FROM report_jobs
            WHERE job_id = %s AND user_id = %s AND status = 'completed'
        """, (job_id, user["id"]))
        job = cur.fetchone()

        if not job or not job["pdf_path"]:
            raise HTTPException(status_code=404, detail="PDF를 찾을 수 없습니다")

        pdf_path = Path(job["pdf_path"])
        if not pdf_path.exists():
            raise HTTPException(status_code=404, detail="PDF 파일이 삭제되었습니다")

        return FileResponse(
            path=str(pdf_path),
            filename=f"{job['ticker']}_report.pdf",
            media_type="application/pdf"
        )
    finally:
        cur.close()
        conn.close()


@router.get("/history")
async def get_report_history(
    user: dict = Depends(require_approved_user),
    limit: int = 10
):
    """내 리포트 목록"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT job_id, ticker, status, progress, created_at, completed_at
            FROM report_jobs
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (user["id"], limit))
        jobs = cur.fetchall()

        # UUID와 datetime 변환
        result = []
        for j in jobs:
            job_dict = dict(j)
            job_dict["job_id"] = str(job_dict["job_id"])
            if job_dict.get("created_at"):
                job_dict["created_at"] = job_dict["created_at"].isoformat()
            if job_dict.get("completed_at"):
                job_dict["completed_at"] = job_dict["completed_at"].isoformat()
            result.append(job_dict)

        return {"reports": result}
    finally:
        cur.close()
        conn.close()
