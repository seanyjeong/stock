"""
lib/social.py - 소셜 센티먼트
Stocktwits + Reddit + Finviz 통합, 한글화 (강세/약세/혼조)
"""

import re
import requests
from lib.base import HEADERS


def get_social_sentiment(ticker: str) -> dict:
    """Stocktwits + Reddit + 웹 스크래핑으로 센티먼트 수집"""
    sentiment_info = {
        "stocktwits_sentiment": None,
        "stocktwits_messages": 0,
        "trending": False,
        "watchlist_count": 0,
        "recent_posts": [],
        "reddit_mentions": 0,
        "twitter_sentiment": None,
        "overall_sentiment": None,
    }

    bullish_total = 0
    bearish_total = 0

    # 1. Stocktwits
    try:
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
        resp = requests.get(url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            data = resp.json()

            symbol_data = data.get('symbol', {})
            sentiment_info["watchlist_count"] = symbol_data.get('watchlist_count', 0)
            sentiment_info["trending"] = symbol_data.get('is_following', False)

            messages = data.get('messages', [])
            sentiment_info["stocktwits_messages"] = len(messages)

            bullish = 0
            bearish = 0

            for msg in messages[:20]:
                entities = msg.get('entities', {})
                sent = entities.get('sentiment', {})
                if sent:
                    if sent.get('basic') == 'Bullish':
                        bullish += 1
                    elif sent.get('basic') == 'Bearish':
                        bearish += 1

                if len(sentiment_info["recent_posts"]) < 3:
                    sentiment_info["recent_posts"].append({
                        "body": msg.get('body', '')[:100],
                        "sentiment": sent.get('basic', 'Neutral') if sent else 'Neutral',
                        "source": "Stocktwits"
                    })

            bullish_total += bullish
            bearish_total += bearish

            if bullish > bearish * 1.5:
                sentiment_info["stocktwits_sentiment"] = "Bullish 🟢"
            elif bearish > bullish * 1.5:
                sentiment_info["stocktwits_sentiment"] = "Bearish 🔴"
            else:
                sentiment_info["stocktwits_sentiment"] = "Neutral ⚪"

    except:
        pass

    # 2. Reddit
    try:
        reddit_url = f"https://www.reddit.com/search.json?q={ticker}&sort=new&limit=10"
        resp = requests.get(reddit_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
        }, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            posts = data.get('data', {}).get('children', [])
            sentiment_info["reddit_mentions"] = len(posts)

            for post in posts[:5]:
                title = post.get('data', {}).get('title', '').lower()
                subreddit = post.get('data', {}).get('subreddit', '')

                bull_words = ['moon', 'rocket', 'buy', 'calls', 'squeeze', 'bullish', 'long', '🚀', '💎']
                bear_words = ['sell', 'puts', 'short', 'bearish', 'crash', 'dump', 'avoid']

                if any(w in title for w in bull_words):
                    bullish_total += 1
                elif any(w in title for w in bear_words):
                    bearish_total += 1

                if len(sentiment_info["recent_posts"]) < 5:
                    sentiment_info["recent_posts"].append({
                        "body": post.get('data', {}).get('title', '')[:100],
                        "sentiment": "Reddit",
                        "source": f"r/{subreddit}"
                    })

    except:
        pass

    # 3. Finviz 뉴스 센티먼트
    try:
        finviz_url = f"https://finviz.com/quote.ashx?t={ticker}"
        resp = requests.get(finviz_url, headers=HEADERS, timeout=10)

        if resp.status_code == 200:
            rating_match = re.search(r'Recom.*?(\d+\.?\d*)', resp.text)
            if rating_match:
                rating = float(rating_match.group(1))
                if rating <= 2:
                    bullish_total += 2
                elif rating >= 4:
                    bearish_total += 2

    except:
        pass

    # 4. 종합 센티먼트 결정
    if bullish_total > bearish_total * 1.5:
        sentiment_info["overall_sentiment"] = "🟢 강세 (Bullish) - 매수 분위기"
    elif bearish_total > bullish_total * 1.5:
        sentiment_info["overall_sentiment"] = "🔴 약세 (Bearish) - 매도 분위기"
    elif bullish_total > 0 or bearish_total > 0:
        sentiment_info["overall_sentiment"] = "⚪ 혼조 (Mixed) - 의견 갈림"
    else:
        sentiment_info["overall_sentiment"] = "❓ 데이터 부족"

    return sentiment_info
