"""
scanners/scoring.py - 점수/등급/AI 추천

공통 유틸리티:
- calculate_rating(score) → A+/A/B/C 등급
- generate_recommendation(result) → Gemini AI 추천 이유 (2문장)
- calculate_split_entry(price, support, atr) → 분할매수 제안
"""

import os

from google import genai

# Gemini 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def calculate_rating(score: float) -> tuple[str, float]:
    """등급 계산 (A+/A/B+/B/C)

    Returns:
        (rating, rr_ratio)
    """
    if score >= 80:
        return 'A+', round(score / 25, 2)
    elif score >= 65:
        return 'A', round(score / 30, 2)
    elif score >= 50:
        return 'B+', round(score / 35, 2)
    elif score >= 40:
        return 'B', round(score / 40, 2)
    else:
        return 'C', round(score / 50, 2)


def generate_recommendation(result: dict) -> str:
    """AI 추천 이유 생성 (Gemini 2문장)"""
    if not gemini_client:
        return f"{result['ticker']} - 점수 {result['score']}"

    category_kr = {
        'day_trade': '단타',
        'swing': '스윙',
        'longterm': '장기',
    }

    prompt = f"""주식 추천 이유를 한국어로 2문장 이내로 작성해주세요.

종목: {result['ticker']} ({result.get('company_name', '')})
투자 유형: {category_kr.get(result['category'], '단타')}
현재가: ${result['current_price']}
점수: {result['score']}점
"""

    if result['category'] == 'day_trade':
        prompt += f"""RSI: {result.get('rsi', 'N/A')}
거래량 급증: {result.get('volume_ratio', 1)}배
뉴스 점수: {result.get('news_score', 0)}
"""
        if result.get('squeeze_signals'):
            prompt += f"숏스퀴즈 신호: {', '.join(result['squeeze_signals'])}\n"

    elif result['category'] == 'swing':
        prompt += f"""RSI: {result.get('rsi', 'N/A')}
MACD: {result.get('macd_cross', 'neutral')}
20일선: ${result.get('ma20', 'N/A')}
"""
        if result.get('catalyst_signals'):
            prompt += f"촉매: {', '.join(result['catalyst_signals'])}\n"

    else:  # longterm
        prompt += f"""배당수익률: {result.get('dividend_yield', 0)}%
P/E: {result.get('pe_ratio', 'N/A')}
섹터: {result.get('sector', 'N/A')}
"""

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        print(f"  Gemini 오류: {e}")
        return f"{result['ticker']} 추천"


def calculate_split_entry(current_price: float, support: float, atr: float) -> list:
    """분할매수 제안"""
    if atr == 0:
        atr = current_price * 0.03

    return [
        {'price': round(current_price, 2), 'pct': 40, 'label': '현재가'},
        {'price': round(current_price - atr, 2), 'pct': 30, 'label': '1차 조정'},
        {'price': round(support, 2), 'pct': 30, 'label': '지지선'},
    ]
