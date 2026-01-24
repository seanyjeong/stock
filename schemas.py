"""
Pydantic 모델 정의
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PortfolioItem(BaseModel):
    """포트폴리오 개별 종목"""
    ticker: str
    shares: int
    avg_cost: float
    regular_price: Optional[float] = None
    afterhours_price: Optional[float] = None
    premarket_price: Optional[float] = None
    current_price: float
    value: float
    gain: float
    gain_pct: float


class TotalSummary(BaseModel):
    """포트폴리오 총합"""
    value_usd: float
    value_krw: float
    gain_usd: float
    gain_krw: float
    gain_pct: float


class TaxInfo(BaseModel):
    """세금 정보"""
    taxable_krw: float
    tax_krw: float
    net_profit_krw: float


class RegSHOItem(BaseModel):
    """RegSHO Threshold 종목"""
    ticker: str
    date: Optional[str] = None


class RegSHOSummary(BaseModel):
    """RegSHO 요약"""
    total_count: int
    holdings_on_list: list[str]
    top_tickers: list[str]


class BlogPost(BaseModel):
    """블로그 포스트"""
    post_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    tickers: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    date: Optional[str] = None
    post_date: Optional[datetime] = None
    is_new: bool = True


class Recommendation(BaseModel):
    """단타 추천 종목"""
    symbol: str
    entry: float
    target: float
    stop_loss: float
    current_price: float
    gap_pct: float
    score: int
    reasons: list[str]
    on_regsho: bool = False
    rsi: float
    volume_surge: float


class BriefingResponse(BaseModel):
    """브리핑 응답 모델"""
    timestamp: str
    exchange_rate: float
    portfolio: list[PortfolioItem]
    total: TotalSummary
    tax: TaxInfo
    regSHO: RegSHOSummary
    new_blog_posts: list[BlogPost] = Field(default_factory=list)
    blogger_mentioned_tickers: list[str] = Field(default_factory=list)
    blogger_ticker_info: dict = Field(default_factory=dict)
