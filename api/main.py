"""
Daily Stock Story API
FastAPI backend for stock briefing and portfolio management
"""
import logging
import traceback
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Daily Stock Story API",
    description="Stock briefing, portfolio tracking, and scanner API",
    version="0.1.0",
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
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
async def get_recommendations():
    """
    Get latest recommendations from all scanner tables.
    Returns day_trade, swing, and longterm recommendations.
    """
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        result = {}

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

        if not result:
            raise HTTPException(status_code=404, detail="No recommendations found")

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/squeeze")
async def get_squeeze_analysis():
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

        # Get portfolio tickers
        cur.execute(
            "SELECT briefing_json->'portfolio' as portfolio "
            "FROM stock_briefing ORDER BY created_at DESC LIMIT 1"
        )
        briefing = cur.fetchone()
        portfolio_tickers = set()
        if briefing and briefing["portfolio"]:
            portfolio_tickers = {item["ticker"] for item in briefing["portfolio"]}

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
                "company_name": row["company_name"],
                # 핵심 지표
                "short_interest": float(row["short_interest"]) if row["short_interest"] else None,
                "borrow_rate": float(row["borrow_rate"]) if row["borrow_rate"] else None,
                "days_to_cover": float(row["days_to_cover"]) if row["days_to_cover"] else None,
                # v2 지표
                "zero_borrow": is_zero_borrow,
                "available_shares": int(row["available_shares"]) if row["available_shares"] else None,
                "float_shares": int(row["float_shares"]) if row["float_shares"] else None,
                "dilution_protected": bool(row["dilution_protected"]) if row["dilution_protected"] is not None else False,
                # RegSHO
                "regsho_days": regsho_days,
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