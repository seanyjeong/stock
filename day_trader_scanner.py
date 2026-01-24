#!/usr/bin/env python3
"""
Day Trader Scanner v1
- 프리마켓 갭업 스캔
- 기술적 지표 (RSI, MACD, 볼린저)
- 모멘텀 점수 계산
- 단타 후보 3개 추천
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
    """RSI 계산"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.empty else 50


def calculate_macd(prices: pd.Series) -> dict:
    """MACD 계산"""
    exp1 = prices.ewm(span=12, adjust=False).mean()
    exp2 = prices.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    return {
        'macd': macd.iloc[-1],
        'signal': signal.iloc[-1],
        'histogram': histogram.iloc[-1],
        'bullish': histogram.iloc[-1] > 0 and histogram.iloc[-1] > histogram.iloc[-2]
    }


def calculate_bollinger(prices: pd.Series, period: int = 20) -> dict:
    """볼린저 밴드 계산"""
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = sma + (std * 2)
    lower = sma - (std * 2)
    current = prices.iloc[-1]
    
    # %B 계산 (0 = 하단, 1 = 상단)
    pct_b = (current - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1])
    
    return {
        'upper': upper.iloc[-1],
        'middle': sma.iloc[-1],
        'lower': lower.iloc[-1],
        'pct_b': pct_b,
        'near_lower': pct_b < 0.2  # 하단 근처 = 반등 가능
    }


def get_volume_surge(ticker: yf.Ticker) -> float:
    """거래량 급증 비율 (평균 대비)"""
    try:
        hist = ticker.history(period="1mo")
        if hist.empty or len(hist) < 5:
            return 1.0
        avg_volume = hist['Volume'].iloc[:-1].mean()
        current_volume = hist['Volume'].iloc[-1]
        return current_volume / avg_volume if avg_volume > 0 else 1.0
    except:
        return 1.0


def scan_premarket_movers() -> list:
    """프리마켓 갭업 종목 스캔"""
    # 주요 스캐닝 대상 (소형주 + 모멘텀 주)
    # 실제로는 더 넓은 스캔이 필요하지만, 일단 핫한 종목 위주
    scan_list = [
        # 최근 핫한 종목들
        'BNAI', 'GLSI', 'HIMS', 'SOUN', 'MARA', 'RIOT', 'COIN',
        # 바이오/제약 (변동성 큼)
        'MRNA', 'BNTX', 'NVAX', 'VKTX', 'SMMT',
        # AI/테크
        'PLTR', 'AI', 'BBAI', 'BIGC', 'PATH',
        # 소형 모멘텀
        'MULN', 'FFIE', 'GOEV', 'RIVN', 'LCID',
        # 밈/숏스퀴즈 후보
        'GME', 'AMC', 'BBBY', 'KOSS', 'EXPR',
        # 기타 변동성
        'TSLA', 'NVDA', 'AMD', 'META', 'GOOGL'
    ]
    
    movers = []
    
    for symbol in scan_list:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # 기본 정보
            current_price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
            prev_close = info.get('previousClose', 0) or info.get('regularMarketPreviousClose', 0)
            pre_market = info.get('preMarketPrice', 0)
            post_market = info.get('postMarketPrice', 0)
            
            if not prev_close or prev_close == 0:
                continue
            
            # 갭업 계산 (프리마켓 or 애프터마켓 기준)
            reference_price = pre_market or post_market or current_price
            if not reference_price:
                continue
                
            gap_pct = ((reference_price - prev_close) / prev_close) * 100
            
            # 시가총액 필터 (너무 작은 건 제외, 너무 큰 건 변동성 낮음)
            market_cap = info.get('marketCap', 0)
            
            # 기술적 지표 계산
            hist = ticker.history(period="3mo")
            if hist.empty or len(hist) < 30:
                continue
                
            closes = hist['Close']
            
            rsi = calculate_rsi(closes)
            macd = calculate_macd(closes)
            bollinger = calculate_bollinger(closes)
            volume_surge = get_volume_surge(ticker)
            
            # 모멘텀 점수 계산 (100점 만점)
            score = 0
            reasons = []
            
            # 갭업 점수 (최대 30점)
            if gap_pct >= 10:
                score += 30
                reasons.append(f"강한 갭업 +{gap_pct:.1f}%")
            elif gap_pct >= 5:
                score += 20
                reasons.append(f"갭업 +{gap_pct:.1f}%")
            elif gap_pct >= 2:
                score += 10
                reasons.append(f"소폭 갭업 +{gap_pct:.1f}%")
            
            # RSI 점수 (최대 20점)
            if 30 <= rsi <= 50:
                score += 20
                reasons.append(f"RSI 반등구간 ({rsi:.0f})")
            elif 50 < rsi <= 70:
                score += 15
                reasons.append(f"RSI 상승추세 ({rsi:.0f})")
            elif rsi > 70:
                score += 5
                reasons.append(f"RSI 과매수 주의 ({rsi:.0f})")
            
            # MACD 점수 (최대 20점)
            if macd['bullish']:
                score += 20
                reasons.append("MACD 골든크로스")
            elif macd['histogram'] > 0:
                score += 10
                reasons.append("MACD 양수")
            
            # 볼린저 점수 (최대 15점)
            if bollinger['near_lower']:
                score += 15
                reasons.append("볼린저 하단 반등")
            elif bollinger['pct_b'] < 0.5:
                score += 10
                reasons.append("볼린저 중간 이하")
            
            # 거래량 점수 (최대 15점)
            if volume_surge >= 3:
                score += 15
                reasons.append(f"거래량 폭증 {volume_surge:.1f}x")
            elif volume_surge >= 1.5:
                score += 10
                reasons.append(f"거래량 증가 {volume_surge:.1f}x")
            
            movers.append({
                'symbol': symbol,
                'current_price': reference_price,
                'prev_close': prev_close,
                'gap_pct': gap_pct,
                'rsi': rsi,
                'macd_bullish': macd['bullish'],
                'bollinger_pct_b': bollinger['pct_b'],
                'volume_surge': volume_surge,
                'market_cap': market_cap,
                'score': score,
                'reasons': reasons
            })
            
        except Exception as e:
            print(f"  {symbol}: 에러 - {e}")
            continue
    
    # 점수순 정렬
    movers.sort(key=lambda x: x['score'], reverse=True)
    return movers


def get_regSHO_list() -> list:
    """RegSHO 리스트 가져오기"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT symbol FROM regsho_list ORDER BY collected_at DESC LIMIT 100")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [r['symbol'] for r in rows]
    except:
        return []


def generate_recommendations(movers: list, regSHO: list) -> list:
    """상위 3개 추천 생성"""
    recommendations = []
    
    for mover in movers[:10]:  # 상위 10개 중 선별
        symbol = mover['symbol']
        price = mover['current_price']
        
        # RegSHO 보너스
        on_regsho = symbol in regSHO
        if on_regsho:
            mover['score'] += 10
            mover['reasons'].append("RegSHO 등재 (숏스퀴즈)")
        
        # 진입/목표/손절 계산
        entry = price
        target = price * 1.05  # 5% 목표
        stop_loss = price * 0.97  # 3% 손절
        
        recommendations.append({
            'symbol': symbol,
            'entry': round(entry, 2),
            'target': round(target, 2),
            'stop_loss': round(stop_loss, 2),
            'current_price': round(price, 2),
            'gap_pct': round(mover['gap_pct'], 1),
            'score': mover['score'],
            'reasons': mover['reasons'][:4],  # 상위 4개 이유
            'on_regsho': on_regsho,
            'rsi': round(mover['rsi'], 0),
            'volume_surge': round(mover['volume_surge'], 1)
        })
    
    # 최종 점수순 정렬 후 상위 3개
    recommendations.sort(key=lambda x: x['score'], reverse=True)
    return recommendations[:3]


def save_recommendations(recommendations: list):
    """추천 결과 DB 저장"""
    conn = get_db()
    cur = conn.cursor()
    
    # 테이블 생성 (없으면)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS day_trade_recommendations (
            id SERIAL PRIMARY KEY,
            recommendations JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # 저장
    cur.execute(
        "INSERT INTO day_trade_recommendations (recommendations) VALUES (%s)",
        (Json(recommendations),)
    )
    
    conn.commit()
    cur.close()
    conn.close()


def main():
    print("=" * 60)
    print(f"🎯 Day Trader Scanner - {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}")
    print("=" * 60)
    
    print("\n📊 프리마켓/모멘텀 스캔 중...")
    movers = scan_premarket_movers()
    print(f"  스캔 완료: {len(movers)}개 종목")
    
    print("\n📋 RegSHO 리스트 확인...")
    regSHO = get_regSHO_list()
    print(f"  RegSHO: {len(regSHO)}개 종목")
    
    print("\n🎯 추천 종목 선정...")
    recommendations = generate_recommendations(movers, regSHO)
    
    if recommendations:
        save_recommendations(recommendations)
        print(f"  ✅ {len(recommendations)}개 추천 저장 완료")
        
        print("\n" + "=" * 60)
        print("🎯 오늘의 단타 후보")
        print("=" * 60)
        
        for i, rec in enumerate(recommendations, 1):
            print(f"\n{i}. **{rec['symbol']}** (점수: {rec['score']})")
            print(f"   현재가: ${rec['current_price']} | 갭: {rec['gap_pct']:+.1f}%")
            print(f"   진입: ${rec['entry']} → 목표: ${rec['target']} (5%) | 손절: ${rec['stop_loss']}")
            print(f"   RSI: {rec['rsi']} | 거래량: {rec['volume_surge']}x")
            if rec['on_regsho']:
                print(f"   ⚡ RegSHO 등재!")
            print(f"   이유: {', '.join(rec['reasons'])}")
    else:
        print("  ❌ 추천 조건 충족 종목 없음")
    
    print("\n⚠️ 주의: 단타는 고위험! 참고용이며 투자 책임은 본인에게 있음")
    print("=" * 60)


if __name__ == "__main__":
    main()
