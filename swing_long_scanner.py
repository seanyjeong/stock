#!/usr/bin/env python3
"""
Swing & Long-term Stock Scanner v1
- 스윙 (7일): 기술적 반등 포인트
- 장기 성장주: 펀더멘털 + 성장성
"""

import os
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import yfinance as yf
import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor, Json

DB_URL = os.getenv("DATABASE_URL", "postgresql://claude:claude_dev@localhost:5432/continuous_claude")
KST = timezone(timedelta(hours=9))


def get_db():
    return psycopg2.connect(DB_URL)


def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.empty else 50


def calculate_macd(prices: pd.Series) -> dict:
    exp1 = prices.ewm(span=12, adjust=False).mean()
    exp2 = prices.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    return {
        'macd': macd.iloc[-1],
        'signal': signal.iloc[-1],
        'histogram': histogram.iloc[-1],
        'bullish': histogram.iloc[-1] > 0 and histogram.iloc[-1] > histogram.iloc[-2] if len(histogram) > 1 else False,
        'golden_cross': macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2] if len(macd) > 1 else False
    }


def calculate_support_resistance(prices: pd.Series) -> dict:
    """지지/저항선 계산"""
    recent = prices.tail(20)
    support = recent.min()
    resistance = recent.max()
    current = prices.iloc[-1]
    
    # 지지선 근접도 (0~1, 1이 지지선에 가까움)
    if resistance - support > 0:
        support_proximity = 1 - (current - support) / (resistance - support)
    else:
        support_proximity = 0.5
    
    return {
        'support': support,
        'resistance': resistance,
        'current': current,
        'support_proximity': support_proximity,
        'near_support': support_proximity > 0.7  # 지지선 근처
    }


def calculate_trend(prices: pd.Series) -> dict:
    """추세 분석 (20일, 50일 이평선)"""
    ma20 = prices.rolling(window=20).mean()
    ma50 = prices.rolling(window=50).mean()
    current = prices.iloc[-1]
    
    uptrend = current > ma20.iloc[-1] > ma50.iloc[-1] if len(ma50.dropna()) > 0 else False
    
    # 20일선 기울기
    if len(ma20.dropna()) >= 5:
        slope = (ma20.iloc[-1] - ma20.iloc[-5]) / ma20.iloc[-5] * 100
    else:
        slope = 0
    
    return {
        'ma20': ma20.iloc[-1] if not pd.isna(ma20.iloc[-1]) else current,
        'ma50': ma50.iloc[-1] if len(ma50.dropna()) > 0 and not pd.isna(ma50.iloc[-1]) else current,
        'uptrend': uptrend,
        'slope_pct': slope
    }


def get_fundamentals(ticker: yf.Ticker) -> dict:
    """펀더멘털 데이터"""
    try:
        info = ticker.info
        return {
            'market_cap': info.get('marketCap', 0),
            'pe_ratio': info.get('trailingPE') or info.get('forwardPE', 0),
            'peg_ratio': info.get('pegRatio', 0),
            'revenue_growth': info.get('revenueGrowth', 0),
            'earnings_growth': info.get('earningsGrowth', 0),
            'profit_margin': info.get('profitMargins', 0),
            'sector': info.get('sector', ''),
            'industry': info.get('industry', ''),
            'name': info.get('shortName', ''),
            'current_price': info.get('currentPrice') or info.get('regularMarketPrice', 0)
        }
    except:
        return {}


def scan_swing_candidates() -> list:
    """스윙 후보 스캔 (7일 보유)"""
    # 스윙에 적합한 종목 (중소형주 + 변동성)
    scan_list = [
        # 테크
        'PLTR', 'SNOW', 'CRWD', 'NET', 'DDOG', 'ZS', 'OKTA',
        # 바이오
        'MRNA', 'BNTX', 'REGN', 'VRTX', 'BIIB',
        # 성장주
        'SQ', 'SHOP', 'ROKU', 'PINS', 'SNAP', 'UBER', 'LYFT',
        # 에너지/소재
        'FSLR', 'ENPH', 'ALB', 'LAC',
        # 기타
        'COIN', 'HOOD', 'AFRM', 'SOFI', 'UPST',
        # AI 관련
        'AI', 'BBAI', 'PATH', 'UKG',
        # 반도체
        'AMD', 'NVDA', 'MRVL', 'ON', 'SWKS'
    ]
    
    candidates = []
    
    for symbol in scan_list:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="3mo")
            
            if hist.empty or len(hist) < 50:
                continue
            
            closes = hist['Close']
            
            # 기술적 분석
            rsi = calculate_rsi(closes)
            macd = calculate_macd(closes)
            support = calculate_support_resistance(closes)
            trend = calculate_trend(closes)
            
            # 스윙 점수 (100점 만점)
            score = 0
            reasons = []
            
            # RSI 과매도 반등 (30점)
            if rsi < 35:
                score += 30
                reasons.append(f"RSI 과매도 ({rsi:.0f})")
            elif rsi < 45:
                score += 20
                reasons.append(f"RSI 저점권 ({rsi:.0f})")
            
            # 지지선 근처 (25점)
            if support['near_support']:
                score += 25
                reasons.append("지지선 근처 반등 기대")
            
            # MACD 골든크로스 (25점)
            if macd['golden_cross']:
                score += 25
                reasons.append("MACD 골든크로스!")
            elif macd['bullish']:
                score += 15
                reasons.append("MACD 상승 전환")
            
            # 추세 (20점)
            if trend['slope_pct'] > 0:
                score += 10
                reasons.append("상승 추세")
            if trend['uptrend']:
                score += 10
                reasons.append("이평선 정배열")
            
            if score >= 30:  # 최소 점수
                current = closes.iloc[-1]
                candidates.append({
                    'symbol': symbol,
                    'current_price': round(current, 2),
                    'entry': round(current, 2),
                    'target': round(current * 1.10, 2),  # 10% 목표
                    'stop_loss': round(current * 0.95, 2),  # 5% 손절
                    'score': score,
                    'rsi': round(rsi, 0),
                    'support': round(support['support'], 2),
                    'resistance': round(support['resistance'], 2),
                    'reasons': reasons[:4],
                    'hold_days': 7
                })
        except Exception as e:
            continue
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:3]


def scan_longterm_growth() -> list:
    """장기 성장주 스캔"""
    # 장기 투자에 적합한 우량 성장주
    scan_list = [
        # 빅테크
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        # 성장 SaaS
        'CRM', 'NOW', 'ADBE', 'INTU', 'WDAY',
        # 핀테크
        'V', 'MA', 'PYPL', 'SQ',
        # 클라우드
        'AMZN', 'MSFT', 'GOOGL', 'SNOW', 'NET',
        # 헬스케어
        'UNH', 'JNJ', 'LLY', 'NVO', 'ISRG',
        # 반도체
        'NVDA', 'AMD', 'AVGO', 'ASML', 'TSM',
        # 신성장
        'ABNB', 'UBER', 'DKNG', 'RBLX'
    ]
    
    # 중복 제거
    scan_list = list(set(scan_list))
    
    candidates = []
    
    for symbol in scan_list:
        try:
            ticker = yf.Ticker(symbol)
            fund = get_fundamentals(ticker)
            
            if not fund or not fund.get('current_price'):
                continue
            
            hist = ticker.history(period="1y")
            if hist.empty:
                continue
            
            closes = hist['Close']
            
            # 1년 수익률
            yearly_return = (closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0] * 100 if len(closes) > 0 else 0
            
            # 장기 투자 점수
            score = 0
            reasons = []
            
            # 매출 성장 (25점)
            rev_growth = fund.get('revenue_growth', 0) or 0
            if rev_growth > 0.3:
                score += 25
                reasons.append(f"매출 +{rev_growth*100:.0f}%")
            elif rev_growth > 0.15:
                score += 15
                reasons.append(f"매출 성장 +{rev_growth*100:.0f}%")
            
            # PEG (25점) - 낮을수록 좋음
            peg = fund.get('peg_ratio', 0) or 0
            if 0 < peg < 1:
                score += 25
                reasons.append(f"저평가 PEG {peg:.1f}")
            elif 0 < peg < 2:
                score += 15
                reasons.append(f"적정 PEG {peg:.1f}")
            
            # 수익성 (20점)
            margin = fund.get('profit_margin', 0) or 0
            if margin > 0.2:
                score += 20
                reasons.append(f"고수익 마진 {margin*100:.0f}%")
            elif margin > 0.1:
                score += 10
                reasons.append(f"양호 마진 {margin*100:.0f}%")
            
            # 1년 성과 (15점)
            if yearly_return > 50:
                score += 15
                reasons.append(f"1년 +{yearly_return:.0f}%")
            elif yearly_return > 20:
                score += 10
                reasons.append(f"1년 +{yearly_return:.0f}%")
            
            # 시총 안정성 (15점)
            mcap = fund.get('market_cap', 0) or 0
            if mcap > 100e9:  # 1000억 달러 이상
                score += 15
                reasons.append("대형주 안정성")
            elif mcap > 10e9:
                score += 10
                reasons.append("중형주")
            
            if score >= 30:
                candidates.append({
                    'symbol': symbol,
                    'name': fund.get('name', symbol),
                    'sector': fund.get('sector', ''),
                    'current_price': round(fund['current_price'], 2),
                    'market_cap_b': round(mcap / 1e9, 1),  # 십억 달러
                    'pe_ratio': round(fund.get('pe_ratio', 0) or 0, 1),
                    'peg_ratio': round(peg, 2),
                    'revenue_growth_pct': round((rev_growth or 0) * 100, 0),
                    'yearly_return_pct': round(yearly_return, 0),
                    'score': score,
                    'reasons': reasons[:4],
                    'hold_months': '6-12'
                })
        except Exception as e:
            continue
    
    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:3]


def save_recommendations(swing: list, longterm: list):
    """추천 결과 DB 저장"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS swing_recommendations (
            id SERIAL PRIMARY KEY,
            recommendations JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS longterm_recommendations (
            id SERIAL PRIMARY KEY,
            recommendations JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    cur.execute("INSERT INTO swing_recommendations (recommendations) VALUES (%s)", (Json(swing),))
    cur.execute("INSERT INTO longterm_recommendations (recommendations) VALUES (%s)", (Json(longterm),))
    
    conn.commit()
    cur.close()
    conn.close()


def main():
    print("=" * 60)
    print(f"📈 Swing & Long-term Scanner - {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}")
    print("=" * 60)
    
    print("\n📈 스윙 후보 스캔 (7일 보유)...")
    swing = scan_swing_candidates()
    print(f"  ✅ {len(swing)}개 스윙 후보")
    
    print("\n🚀 장기 성장주 스캔...")
    longterm = scan_longterm_growth()
    print(f"  ✅ {len(longterm)}개 장기 성장주")
    
    save_recommendations(swing, longterm)
    print("\n💾 DB 저장 완료")
    
    # 스윙 출력
    print("\n" + "=" * 60)
    print("📈 스윙 추천 (7일 보유, 10% 목표)")
    print("=" * 60)
    for i, rec in enumerate(swing, 1):
        print(f"\n{i}. **{rec['symbol']}** (점수: {rec['score']})")
        print(f"   현재: ${rec['current_price']} | RSI: {rec['rsi']}")
        print(f"   진입: ${rec['entry']} → 목표: ${rec['target']} | 손절: ${rec['stop_loss']}")
        print(f"   지지: ${rec['support']} | 저항: ${rec['resistance']}")
        print(f"   이유: {', '.join(rec['reasons'])}")
    
    # 장기 출력
    print("\n" + "=" * 60)
    print("🚀 장기 성장주 (6-12개월)")
    print("=" * 60)
    for i, rec in enumerate(longterm, 1):
        print(f"\n{i}. **{rec['symbol']}** - {rec['name']} (점수: {rec['score']})")
        print(f"   현재: ${rec['current_price']} | 시총: ${rec['market_cap_b']}B")
        print(f"   P/E: {rec['pe_ratio']} | PEG: {rec['peg_ratio']}")
        print(f"   매출성장: +{rec['revenue_growth_pct']}% | 1년: +{rec['yearly_return_pct']}%")
        print(f"   이유: {', '.join(rec['reasons'])}")
    
    print("\n" + "=" * 60)
    print("⚠️ 투자 참고용! 책임은 본인에게 있음")
    print("=" * 60)


if __name__ == "__main__":
    main()
