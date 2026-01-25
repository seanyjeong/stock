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


def render_report_html(ticker: str, data: dict) -> str:
    """리포트 HTML 렌더링"""
    basic = data.get("basic_info", {})
    borrow = data.get("borrow_data", {})
    tech = data.get("technicals", {})
    squeeze = data.get("squeeze_score", {})
    fib = data.get("fibonacci", {})
    ai = data.get("ai_analysis", {})
    holding = data.get("holding_info")

    # 가격 정보
    price = basic.get("price", 0)
    change_pct = basic.get("change_percent", 0)
    change_class = "positive" if change_pct >= 0 else "negative"

    # 스퀴즈 점수
    score = squeeze.get("score", 0)
    grade = squeeze.get("grade", "N/A")

    # 피보나치 레벨
    fib_levels = fib.get("levels", {})

    # AI 분석 섹션
    ai_strengths = ai.get("strengths", []) if ai else []
    ai_weaknesses = ai.get("weaknesses", []) if ai else []
    ai_strategy = ai.get("strategy", "") if ai else ""
    ai_summary = ai.get("summary", "") if ai else ""

    html = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>{ticker} 분석 리포트</title>
</head>
<body>
    <div class="report">
        <header class="report-header">
            <div class="logo">Daily Stock Story</div>
            <div class="report-date">{datetime.now().strftime("%Y년 %m월 %d일")}</div>
        </header>

        <h1 class="ticker-title">{ticker}</h1>
        <p class="company-name">{basic.get("name", "")}</p>

        <section class="overview">
            <h2>회사 개요</h2>
            <table class="info-table">
                <tr><td>섹터</td><td>{basic.get("sector", "N/A")}</td></tr>
                <tr><td>업종</td><td>{basic.get("industry", "N/A")}</td></tr>
                <tr><td>시가총액</td><td>{format_number(basic.get("market_cap"))}</td></tr>
                <tr><td>Float</td><td>{format_number(basic.get("float_shares"))}</td></tr>
                <tr><td>52주 범위</td><td>${basic.get("fifty_two_week_low", 0):.2f} - ${basic.get("fifty_two_week_high", 0):.2f}</td></tr>
            </table>
        </section>

        <section class="price-section">
            <h2>현재 가격</h2>
            <div class="price-box">
                <span class="current-price">${price:.2f}</span>
                <span class="change {change_class}">{change_pct:+.2f}%</span>
            </div>
        </section>

        <section class="short-section">
            <h2>숏 포지션 분석</h2>
            <table class="info-table">
                <tr><td>Short Interest</td><td>{borrow.get("short_interest", "N/A")}</td></tr>
                <tr><td>Borrow Rate</td><td>{borrow.get("borrow_rate", "N/A")}</td></tr>
                <tr><td>Days to Cover</td><td>{borrow.get("days_to_cover", "N/A")}</td></tr>
                <tr><td>Zero Borrow</td><td>{"Yes" if borrow.get("zero_borrow") else "No"}</td></tr>
                <tr><td>RegSHO</td><td>{"등재" if data.get("in_regsho") else "미등재"}</td></tr>
            </table>
        </section>

        <section class="technical-section">
            <h2>기술적 분석</h2>
            <table class="info-table">
                <tr><td>RSI (14)</td><td>{tech.get("rsi", "N/A")}</td></tr>
                <tr><td>MACD</td><td>{tech.get("macd_signal", "N/A")}</td></tr>
                <tr><td>볼린저 위치</td><td>{tech.get("bb_position", "N/A")}</td></tr>
                <tr><td>ATR</td><td>{tech.get("atr", "N/A")}</td></tr>
            </table>
        </section>

        <section class="fibonacci-section">
            <h2>피보나치 레벨</h2>
            <table class="fib-table">
                <tr><th>레벨</th><th>가격</th></tr>
                {"".join(f'<tr><td>{k}</td><td>${v:.2f}</td></tr>' for k, v in fib_levels.items() if isinstance(v, (int, float)))}
            </table>
        </section>

        <section class="squeeze-section">
            <h2>숏스퀴즈 점수</h2>
            <div class="score-box">
                <span class="score">{score:.0f}</span>
                <span class="grade grade-{grade.lower()}">{grade}</span>
            </div>
            <p class="score-breakdown">{squeeze.get("breakdown", "")}</p>
        </section>

        {"" if not holding else f'''
        <section class="portfolio-section">
            <h2>내 포지션</h2>
            <table class="info-table">
                <tr><td>보유 수량</td><td>{holding.get("shares", 0):,.2f}주</td></tr>
                <tr><td>평균 매수가</td><td>${holding.get("avg_cost", 0):.2f}</td></tr>
                <tr><td>현재 평가액</td><td>${holding.get("shares", 0) * price:,.2f}</td></tr>
                <tr><td>수익률</td><td>{((price / holding.get("avg_cost", price)) - 1) * 100:+.2f}%</td></tr>
            </table>
        </section>
        '''}

        {"" if not ai else f'''
        <section class="ai-section">
            <h2>AI 종합 분석</h2>
            <div class="ai-summary">{ai_summary}</div>

            <h3>강점</h3>
            <ul class="strengths">
                {"".join(f"<li>{s}</li>" for s in ai_strengths)}
            </ul>

            <h3>약점</h3>
            <ul class="weaknesses">
                {"".join(f"<li>{w}</li>" for w in ai_weaknesses)}
            </ul>

            <h3>투자 전략</h3>
            <p class="strategy">{ai_strategy}</p>
        </section>
        '''}

        <footer class="report-footer">
            <p>본 리포트는 투자 참고 자료이며, 투자 결정은 본인 책임입니다.</p>
            <p>Daily Stock Story &copy; {datetime.now().year}</p>
        </footer>
    </div>
</body>
</html>
"""
    return html


def format_number(n):
    """숫자 포맷팅"""
    if n is None:
        return "N/A"
    if abs(n) >= 1e12:
        return f"${n/1e12:.2f}T"
    if abs(n) >= 1e9:
        return f"${n/1e9:.2f}B"
    if abs(n) >= 1e6:
        return f"${n/1e6:.2f}M"
    return f"${n:,.0f}"


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

        return ReportStatusResponse(**job)
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

        return {"reports": [dict(j) for j in jobs]}
    finally:
        cur.close()
        conn.close()
