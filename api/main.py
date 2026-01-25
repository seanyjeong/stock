"""
Daily Stock Story API
FastAPI backend for stock briefing and portfolio management
"""
import logging
import traceback
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor

from db import get_db
from api.auth import router as auth_router
from api.portfolio import router as portfolio_router
from api.trades import router as trades_router
from api.watchlist import router as watchlist_router
from api.notifications import router as notifications_router
from api.announcements import router as announcements_router
from api.indicators import router as indicators_router
from api.chart import router as chart_router
from api.profile import router as profile_router
from api.realtime import router as realtime_router
from api.reports import router as reports_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Daily Stock Story API",
    description="Stock briefing, portfolio tracking, and scanner API",
    version="0.1.0",
)

# CORS middleware for frontend access
# Note: allow_origins=["*"] is NOT compatible with allow_credentials=True
# Must specify exact origins when using credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://stock-six-phi.vercel.app",  # Vercel production
        "http://localhost:5173",              # Local dev (Vite)
        "http://localhost:3000",              # Local dev
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include auth router
app.include_router(auth_router)
app.include_router(portfolio_router)
app.include_router(trades_router)
app.include_router(watchlist_router)
app.include_router(notifications_router)
app.include_router(announcements_router)
app.include_router(indicators_router)
app.include_router(chart_router)
app.include_router(profile_router)
app.include_router(realtime_router)
app.include_router(reports_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent format"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "detail": exc.detail,
            "path": str(request.url.path),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions with logging"""
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}\n"
        f"{traceback.format_exc()}"
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "status_code": 500,
            "detail": "Internal server error",
            "path": str(request.url.path),
        },
    )


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "Daily Stock Story API"}


@app.get("/health")
async def health():
    """Health check for monitoring"""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/briefing")
async def get_briefing():
    """Get latest stock briefing from stock_briefing table"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT briefing_json, created_at FROM stock_briefing ORDER BY created_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="No briefing data found")

        return {
            "data": row["briefing_json"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/portfolio")
async def get_portfolio():
    """
    Get portfolio with current prices from stock_prices table.
    Returns portfolio items from stock_briefing with refreshed prices.
    """
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get portfolio from stock_briefing
        cur.execute(
            "SELECT briefing_json->'portfolio' as portfolio, "
            "briefing_json->'total' as total, "
            "briefing_json->'exchange_rate' as exchange_rate, "
            "created_at FROM stock_briefing ORDER BY created_at DESC LIMIT 1"
        )
        briefing = cur.fetchone()

        if not briefing or not briefing["portfolio"]:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="No portfolio data found")

        portfolio = briefing["portfolio"]
        exchange_rate = float(briefing["exchange_rate"]) if briefing["exchange_rate"] else 1450.0

        # Get latest prices for each ticker
        tickers = [item["ticker"] for item in portfolio]
        if tickers:
            cur.execute(
                """
                SELECT DISTINCT ON (ticker)
                    ticker, regular_price, afterhours_price, premarket_price, collected_at
                FROM stock_prices
                WHERE ticker = ANY(%s)
                ORDER BY ticker, collected_at DESC
                """,
                (tickers,)
            )
            prices = {row["ticker"]: row for row in cur.fetchall()}

            # Get company names
            cur.execute(
                "SELECT ticker, company_name FROM ticker_info WHERE ticker = ANY(%s)",
                (tickers,)
            )
            company_names = {row["ticker"]: row["company_name"] for row in cur.fetchall()}
        else:
            prices = {}
            company_names = {}

        cur.close()
        conn.close()

        # Update portfolio with current prices and recalculate values
        total_value = 0.0
        total_cost = 0.0
        result_portfolio = []

        for item in portfolio:
            ticker = item["ticker"]
            shares = item["shares"]
            avg_cost = item["avg_cost"]

            # Get current price (afterhours > premarket > regular)
            if ticker in prices:
                price_row = prices[ticker]
                current_price = (
                    float(price_row["afterhours_price"]) if price_row["afterhours_price"]
                    else float(price_row["premarket_price"]) if price_row["premarket_price"]
                    else float(price_row["regular_price"]) if price_row["regular_price"]
                    else item.get("current_price", 0)
                )
                regular_price = float(price_row["regular_price"]) if price_row["regular_price"] else None
                afterhours_price = float(price_row["afterhours_price"]) if price_row["afterhours_price"] else None
                premarket_price = float(price_row["premarket_price"]) if price_row["premarket_price"] else None
            else:
                current_price = item.get("current_price", 0)
                regular_price = item.get("regular_price")
                afterhours_price = item.get("afterhours_price")
                premarket_price = item.get("premarket_price")

            value = shares * current_price
            cost = shares * avg_cost
            gain = value - cost
            gain_pct = (gain / cost * 100) if cost > 0 else 0

            total_value += value
            total_cost += cost

            result_portfolio.append({
                "ticker": ticker,
                "company_name": company_names.get(ticker),
                "shares": shares,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "regular_price": regular_price,
                "afterhours_price": afterhours_price,
                "premarket_price": premarket_price,
                "value": round(value, 2),
                "gain": round(gain, 2),
                "gain_pct": round(gain_pct, 1),
            })

        total_gain = total_value - total_cost
        total_gain_pct = (total_gain / total_cost * 100) if total_cost > 0 else 0

        return {
            "portfolio": result_portfolio,
            "total": {
                "value_usd": round(total_value, 2),
                "value_krw": round(total_value * exchange_rate, 0),
                "cost_usd": round(total_cost, 2),
                "gain_usd": round(total_gain, 2),
                "gain_pct": round(total_gain_pct, 1),
            },
            "exchange_rate": exchange_rate,
            "briefing_updated_at": briefing["created_at"].isoformat() if briefing["created_at"] else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/regsho")
async def get_regsho():
    """
    Get RegSHO Threshold Securities List.
    Returns all securities on the list with portfolio holdings highlighted.
    """
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get portfolio tickers from briefing
        cur.execute(
            "SELECT briefing_json->'portfolio' as portfolio "
            "FROM stock_briefing ORDER BY created_at DESC LIMIT 1"
        )
        briefing = cur.fetchone()
        portfolio_tickers = set()
        if briefing and briefing["portfolio"]:
            portfolio_tickers = {item["ticker"] for item in briefing["portfolio"]}

        # Get latest RegSHO list with days on list
        cur.execute(
            """
            SELECT ticker, security_name, market_category, collected_date, collected_at,
                   first_seen_date,
                   (CURRENT_DATE - first_seen_date) as days_on_list
            FROM regsho_list
            WHERE collected_date = (SELECT MAX(collected_date) FROM regsho_list)
            ORDER BY ticker
            """
        )
        regsho_list = cur.fetchall()

        cur.close()
        conn.close()

        if not regsho_list:
            raise HTTPException(status_code=404, detail="No RegSHO data found")

        # Mark portfolio holdings
        result = []
        holdings_on_list = []
        for row in regsho_list:
            days = row["days_on_list"] if row["days_on_list"] else 0
            item = {
                "ticker": row["ticker"],
                "security_name": row["security_name"],
                "market_category": row["market_category"],
                "is_holding": row["ticker"] in portfolio_tickers,
                "days_on_list": days.days if hasattr(days, 'days') else int(days),
            }
            result.append(item)
            if item["is_holding"]:
                holdings_on_list.append(row["ticker"])

        return {
            "regsho_list": result,
            "total_count": len(result),
            "holdings_on_list": holdings_on_list,
            "collected_date": regsho_list[0]["collected_date"].isoformat() if regsho_list else None,
            "collected_at": regsho_list[0]["collected_at"].isoformat() if regsho_list[0]["collected_at"] else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/blog")
async def get_blog_posts():
    """
    Get recent blog posts from 까꿍토끼.
    Returns posts with extracted tickers and keywords.
    """
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            SELECT id, title, url, tickers, keywords, post_date, is_new, collected_at
            FROM blog_posts
            ORDER BY collected_at DESC
            LIMIT 20
            """
        )
        posts = cur.fetchall()

        cur.close()
        conn.close()

        result = []
        for post in posts:
            result.append({
                "id": post["id"],
                "title": post["title"],
                "url": post["url"],
                "tickers": post["tickers"] if post["tickers"] else [],
                "keywords": post["keywords"] if post["keywords"] else [],
                "published_at": post["post_date"],
                "is_read": not post["is_new"],
            })

        return {
            "posts": result,
            "total_count": len(result),
            "unread_count": sum(1 for p in result if not p["is_read"]),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recommendations")
async def get_recommendations(authorization: str = Header(None)):
    """
    Get recommendations based on user's investment profile.
    - aggressive: sorted by day_trade_score
    - balanced: sorted by swing_score
    - conservative: sorted by longterm_score
    """
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 1. 사용자 프로필 조회 (로그인된 경우)
        profile_type = "balanced"  # 기본값
        if authorization and authorization.startswith("Bearer "):
            token = authorization.split(" ")[1]
            try:
                from api.auth import verify_jwt_token
                payload = verify_jwt_token(token)
                if payload:
                    user_id = payload.get("user_id")
                    cur.execute(
                        "SELECT profile_type FROM user_profiles WHERE user_id = %s",
                        (user_id,)
                    )
                    profile_row = cur.fetchone()
                    if profile_row:
                        profile_type = profile_row["profile_type"]
            except:
                pass  # 토큰 오류 시 기본값 사용

        # 2. 오늘 스캔 결과 조회
        cur.execute(
            "SELECT results, created_at FROM daily_scan_results "
            "WHERE scan_date = CURRENT_DATE "
            "ORDER BY created_at DESC LIMIT 1"
        )
        scan_row = cur.fetchone()

        result = {"profile_type": profile_type}

        if scan_row and scan_row["results"]:
            import json
            raw_results = scan_row["results"]
            if isinstance(raw_results, str):
                raw_results = json.loads(raw_results)

            # 새 형식 (v2): {"day_trade": [...], "swing": [...], "longterm": [...]}
            if isinstance(raw_results, dict) and "day_trade" in raw_results:
                def format_picks(items, category):
                    """추천 목록 포맷팅 (v3 - 숏스퀴즈/촉매 포함)"""
                    picks = []
                    for item in items[:5]:
                        pick = {
                            "ticker": item.get("ticker"),
                            "company_name": item.get("company_name", item.get("ticker")),
                            "current_price": item.get("current_price"),
                            "score": item.get("score", 0),
                            "recommended_entry": item.get("recommended_entry"),
                            "stop_loss": item.get("stop_loss"),
                            "target": item.get("target"),
                            "rsi": item.get("rsi"),
                            "macd_cross": item.get("macd_cross"),
                            "news_score": item.get("news_score", 0),
                            "sector": item.get("sector", "Unknown"),
                            "industry": item.get("industry", ""),
                            "recommendation_reason": item.get("recommendation_reason", ""),
                            "rating": item.get("rating", ""),
                            "rr_ratio": item.get("rr_ratio", 0),
                            "split_entries": item.get("split_entries", [])
                        }
                        # 단타: 숏스퀴즈 데이터
                        if category == "day_trade":
                            pick["squeeze_score"] = item.get("squeeze_score", 0)
                            pick["squeeze_signals"] = item.get("squeeze_signals", [])
                            pick["volume_ratio"] = item.get("volume_ratio", 0)
                        # 스윙: 촉매 데이터
                        elif category == "swing":
                            pick["catalyst_score"] = item.get("catalyst_score", 0)
                            pick["catalyst_signals"] = item.get("catalyst_signals", [])
                            pick["max_pain"] = item.get("max_pain")
                            pick["options_signal"] = item.get("options_signal")
                        # 장기: 기관 데이터
                        elif category == "longterm":
                            pick["dividend_yield"] = item.get("dividend_yield", 0)
                            pick["pe_ratio"] = item.get("pe_ratio")
                            pick["institutional_pct"] = item.get("institutional_pct")
                            pick["institutional_signal"] = item.get("institutional_signal")
                            pick["score_breakdown"] = item.get("score_breakdown", {})
                        picks.append(pick)
                    return picks

                result["all_recommendations"] = {
                    "day_trade": format_picks(raw_results.get("day_trade", []), "day_trade"),
                    "swing": format_picks(raw_results.get("swing", []), "swing"),
                    "longterm": format_picks(raw_results.get("longterm", []), "longterm")
                }
                # 업데이트 시간 추가 (둘 다 포함 - 호환성)
                timestamp = scan_row["created_at"].isoformat() if scan_row.get("created_at") else None
                result["updated_at"] = timestamp
                result["created_at"] = timestamp
            else:
                # 이전 형식 (v1): flat list
                scan_results = raw_results if isinstance(raw_results, list) else []

                def get_top_picks(items, score_key, entry_key, limit=5):
                    """성향별 상위 종목 추출"""
                    sorted_items = sorted(items, key=lambda x: -x.get(score_key, 0))
                    picks = []
                    for item in sorted_items[:limit]:
                        picks.append({
                            "ticker": item.get("ticker"),
                            "company_name": item.get("company_name", item.get("ticker")),
                            "current_price": item.get("current_price"),
                            "score": item.get(score_key, 0),
                            "recommended_entry": item.get(entry_key),
                            "stop_loss": item.get("stop_loss"),
                            "target": item.get("target"),
                            "rsi": item.get("rsi"),
                            "macd_cross": item.get("macd_cross"),
                            "news_score": item.get("news_score", 0),
                            "sector": item.get("sector", "Unknown"),
                            "recommendation_reason": item.get("recommendation_reason", ""),
                            "rating": item.get("rating", ""),
                            "rr_ratio": item.get("rr_ratio", 0),
                            "split_entries": item.get("split_entries", [])
                        })
                    return picks

                result["all_recommendations"] = {
                    "day_trade": get_top_picks(scan_results, "day_trade_score", "entry_aggressive"),
                    "swing": get_top_picks(scan_results, "swing_score", "entry_balanced"),
                    "longterm": get_top_picks(scan_results, "longterm_score", "entry_conservative")
                }

            # 사용자 프로필에 맞는 추천
            if profile_type == "aggressive":
                result["recommendations"] = result["all_recommendations"]["day_trade"]
            elif profile_type == "conservative":
                result["recommendations"] = result["all_recommendations"]["longterm"]
            else:
                result["recommendations"] = result["all_recommendations"]["swing"]

            result["created_at"] = scan_row["created_at"].isoformat() if scan_row["created_at"] else None

        # 3. 기존 추천도 유지 (fallback)
        if "recommendations" not in result or not result["recommendations"]:
            # Day trade recommendations
            cur.execute(
                "SELECT recommendations, created_at FROM day_trade_recommendations "
                "ORDER BY created_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                result["day_trade"] = {
                    "recommendations": row["recommendations"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }

            # Swing recommendations
            cur.execute(
                "SELECT recommendations, created_at FROM swing_recommendations "
                "ORDER BY created_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                result["swing"] = {
                    "recommendations": row["recommendations"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }

            # Longterm recommendations
            cur.execute(
                "SELECT recommendations, created_at FROM longterm_recommendations "
                "ORDER BY created_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                result["longterm"] = {
                    "recommendations": row["recommendations"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }

        cur.close()
        conn.close()

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/squeeze")
async def get_squeeze_analysis(authorization: str = Header(None)):
    """
    Get short squeeze analysis data.
    Returns squeeze scores with borrow rate, short interest, days to cover.
    Combines with RegSHO days for comprehensive analysis.
    """
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get latest squeeze data for each ticker (v2: 새 컬럼 포함)
        cur.execute("""
            SELECT DISTINCT ON (s.ticker)
                s.ticker,
                s.borrow_rate,
                s.short_interest,
                s.days_to_cover,
                s.short_volume,
                s.squeeze_score,
                s.available_shares,
                s.float_shares,
                s.dilution_protected,
                s.has_positive_news,
                s.has_negative_news,
                s.collected_at,
                t.company_name,
                r.days_on_list
            FROM squeeze_data s
            LEFT JOIN ticker_info t ON s.ticker = t.ticker
            LEFT JOIN (
                SELECT ticker, (CURRENT_DATE - first_seen_date) as days_on_list
                FROM regsho_list
                WHERE collected_date = (SELECT MAX(collected_date) FROM regsho_list)
            ) r ON s.ticker = r.ticker
            WHERE s.collected_at > NOW() - INTERVAL '2 days'
            ORDER BY s.ticker, s.collected_at DESC
        """)
        squeeze_list = cur.fetchall()

        # Get portfolio tickers from logged-in user's holdings
        portfolio_tickers = set()
        if authorization and authorization.startswith("Bearer "):
            try:
                import jwt
                token = authorization.split(" ")[1]
                payload = jwt.decode(token, options={"verify_signature": False})
                user_id = int(payload.get("sub", 0))
                if user_id:
                    cur.execute("SELECT ticker FROM user_holdings WHERE user_id = %s", (user_id,))
                    portfolio_tickers = {row["ticker"] for row in cur.fetchall()}
            except Exception:
                pass  # 토큰 없거나 만료되면 빈 set

        cur.close()
        conn.close()

        # Format results with combined score
        result = []
        for row in squeeze_list:
            # Recalculate combined score with RegSHO days
            squeeze_score = float(row["squeeze_score"]) if row["squeeze_score"] else 0
            regsho_days = row["days_on_list"].days if row["days_on_list"] and hasattr(row["days_on_list"], 'days') else (int(row["days_on_list"]) if row["days_on_list"] else 0)

            # Add RegSHO bonus (up to 15 points for 30+ days)
            regsho_bonus = min(regsho_days / 2, 15) if regsho_days else 0
            combined_score = round(squeeze_score + regsho_bonus, 1)

            # Determine rating
            if combined_score >= 60:
                rating = "HOT"
            elif combined_score >= 40:
                rating = "WATCH"
            else:
                rating = "COLD"

            # Zero Borrow 판정
            is_zero_borrow = row["borrow_rate"] and float(row["borrow_rate"]) >= 999

            result.append({
                "ticker": row["ticker"],
                # 핵심 지표
                "short_interest": float(row["short_interest"]) if row["short_interest"] else None,
                "borrow_rate": float(row["borrow_rate"]) if row["borrow_rate"] else None,
                "days_to_cover": float(row["days_to_cover"]) if row["days_to_cover"] else None,
                # v2 지표
                "zero_borrow": is_zero_borrow,
                "available_shares": int(row["available_shares"]) if row["available_shares"] else None,
                "float_shares": int(row["float_shares"]) if row["float_shares"] else None,
                "dilution_protected": bool(row["dilution_protected"]) if row["dilution_protected"] is not None else False,
                "has_positive_news": bool(row["has_positive_news"]) if row["has_positive_news"] is not None else False,
                "has_negative_news": bool(row["has_negative_news"]) if row["has_negative_news"] is not None else False,
                # 점수
                "squeeze_score": squeeze_score,
                "combined_score": combined_score,
                "rating": rating,
                "is_holding": row["ticker"] in portfolio_tickers,
            })

        # Sort by combined score (highest first)
        result.sort(key=lambda x: x["combined_score"], reverse=True)

        return {
            "squeeze_list": result,
            "total_count": len(result),
            "hot_count": sum(1 for r in result if r["rating"] == "HOT"),
            "holdings_count": sum(1 for r in result if r["is_holding"]),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))