#!/usr/bin/env python3
"""
네이버 블로그 스크래핑 도구
- stock_moonrabbit 블로그 최신 포스팅 수집
- 마크다운으로 저장
- 종목 분석 키워드 추출
"""

import asyncio
import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from playwright.async_api import async_playwright

BLOG_ID = "stock_moonrabbit"
BASE_URL = f"https://m.blog.naver.com/{BLOG_ID}"
OUTPUT_DIR = Path(__file__).parent / "blog_posts"


async def get_post_list(page, limit=5):
    """블로그 포스트 목록 가져오기"""
    # PostList 페이지로 이동 (전체글보기)
    list_url = f"https://m.blog.naver.com/PostList.naver?blogId={BLOG_ID}&categoryNo=0"
    await page.goto(list_url)
    await page.wait_for_timeout(2000)

    # 스크롤해서 더 많은 포스트 로드
    for _ in range(3):
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await page.wait_for_timeout(1000)

    posts = []
    seen_ids = set()

    # logNo가 있는 포스트 링크 찾기
    post_links = await page.query_selector_all('a[href*="logNo"]')
    print(f"  발견된 포스트 링크: {len(post_links)}개")

    for link in post_links:
        try:
            href = await link.get_attribute("href")
            if not href or "logNo=" not in href:
                continue

            # 포스트 ID 추출
            post_id = href.split("logNo=")[-1].split("&")[0]
            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)

            # 텍스트 추출 (제목)
            text = await link.inner_text()
            text = text.replace('\n', ' ').strip()

            # "사진 개수 X" 같은 건 실제 제목이 아님 - 나중에 페이지에서 가져옴
            if text.startswith("사진 개수") or len(text) < 5:
                title = f"(포스트 {post_id})"
            else:
                title = text[:100]

            # URL 정규화
            if not href.startswith("http"):
                href = f"https://m.blog.naver.com{href}"

            posts.append({
                "id": post_id,
                "title": title,
                "date": "",
                "url": href
            })

            if len(posts) >= limit:
                break

        except Exception as e:
            print(f"  포스트 파싱 오류: {e}")
            continue

    return posts


async def get_post_content(page, post_url):
    """개별 포스트 내용 가져오기 - 제목, 날짜, 본문 반환"""
    await page.goto(post_url)
    await page.wait_for_timeout(2000)

    result = {"title": "", "date": "", "content": ""}

    # 제목 추출
    for sel in ["h3.se_title", "[class*='title']", "h3", ".tit_h3"]:
        title_elem = await page.query_selector(sel)
        if title_elem:
            result["title"] = (await title_elem.inner_text()).strip()
            if result["title"]:
                break

    # 날짜 추출
    for sel in ["[class*='date']", "time", ".blog_date", "span.se_publishDate"]:
        date_elem = await page.query_selector(sel)
        if date_elem:
            date_text = await date_elem.inner_text()
            if date_text and any(c.isdigit() for c in date_text):
                result["date"] = date_text.strip()
                break

    # 본문 추출
    for sel in ["div.se-main-container", "div#postViewArea", "div.post-view",
                "[class*='post_content']", "[class*='se_component_wrap']"]:
        content_elem = await page.query_selector(sel)
        if content_elem:
            result["content"] = (await content_elem.inner_text()).strip()
            if len(result["content"]) > 50:
                break

    return result


def extract_tickers(text):
    """텍스트에서 티커 심볼 추출"""
    # 대문자 2-5글자 패턴 (일반적인 티커)
    tickers = re.findall(r'\b([A-Z]{2,5})\b', text)

    # 한글로 된 종목명도 찾기
    korean_stocks = re.findall(r'([가-힣]+)\s*\(([A-Z]{2,5})\)', text)

    # 일반적인 단어 제외
    common_words = {'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL',
                   'CAN', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'ETF', 'CEO',
                   'IPO', 'FDA', 'SEC', 'NYSE', 'NASDAQ', 'USD', 'KRW'}

    filtered = [t for t in tickers if t not in common_words]

    return {
        "tickers": list(set(filtered)),
        "korean_names": korean_stocks
    }


def extract_keywords(text):
    """투자 관련 키워드 추출"""
    keywords = {
        "숏스퀴즈": ["숏스퀴즈", "short squeeze", "숏커버", "공매도"],
        "급등": ["급등", "폭등", "상승", "상한가"],
        "급락": ["급락", "폭락", "하락", "하한가"],
        "실적": ["실적", "어닝", "earnings", "매출"],
        "FDA": ["FDA", "승인", "임상", "신약"],
        "인수합병": ["인수", "합병", "M&A", "merger"],
        "배당": ["배당", "dividend"],
        "테마": ["테마", "섹터", "AI", "반도체", "2차전지", "바이오"]
    }

    found = []
    text_lower = text.lower()

    for category, terms in keywords.items():
        for term in terms:
            if term.lower() in text_lower:
                found.append(category)
                break

    return list(set(found))


async def scrape_blog(days_back=2, limit=10):
    """블로그 스크래핑 메인 함수"""
    OUTPUT_DIR.mkdir(exist_ok=True)

    cutoff_date = datetime.now() - timedelta(days=days_back)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print(f"📡 {BLOG_ID} 블로그 스크래핑 시작...")

        # 포스트 목록 가져오기
        posts = await get_post_list(page, limit=limit)
        print(f"📝 {len(posts)}개 포스트 발견")

        results = []

        for post in posts:
            print(f"  → {post['title'][:30]}...")

            # 내용 가져오기 (제목, 날짜, 본문)
            post_detail = await get_post_content(page, post['url'])

            # 제목이 비어있으면 페이지에서 가져온 제목 사용
            if post['title'].startswith("(포스트") and post_detail['title']:
                post['title'] = post_detail['title']
            if post_detail['date']:
                post['date'] = post_detail['date']

            content = post_detail['content']

            # 분석
            tickers = extract_tickers(content)
            keywords = extract_keywords(content)

            post_data = {
                **post,
                "content": content,
                "tickers": tickers,
                "keywords": keywords,
                "scraped_at": datetime.now().isoformat()
            }

            results.append(post_data)

            # 마크다운으로 저장
            safe_title = re.sub(r'[^\w\s-]', '', post['title'])[:50]
            filename = f"{post.get('date', 'unknown')[:10]}_{safe_title}.md"
            filepath = OUTPUT_DIR / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# {post['title']}\n\n")
                f.write(f"- **날짜**: {post.get('date', 'N/A')}\n")
                f.write(f"- **URL**: {post['url']}\n")
                f.write(f"- **티커**: {', '.join(tickers['tickers']) or 'N/A'}\n")
                f.write(f"- **키워드**: {', '.join(keywords) or 'N/A'}\n\n")
                f.write("---\n\n")
                f.write(content)

            print(f"    ✅ 저장: {filename}")

        await browser.close()

        # 요약 JSON 저장
        summary_path = OUTPUT_DIR / "latest_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 완료! {len(results)}개 포스트 저장됨")
        print(f"📁 저장 위치: {OUTPUT_DIR}")

        return results


def print_summary(results):
    """결과 요약 출력"""
    print("\n" + "="*50)
    print("📊 블로그 분석 요약")
    print("="*50)

    all_tickers = set()
    all_keywords = set()

    for post in results:
        print(f"\n### {post['title'][:40]}...")
        print(f"    티커: {', '.join(post['tickers']['tickers']) or '-'}")
        print(f"    키워드: {', '.join(post['keywords']) or '-'}")

        all_tickers.update(post['tickers']['tickers'])
        all_keywords.update(post['keywords'])

    print("\n" + "-"*50)
    print(f"🎯 전체 언급 티커: {', '.join(sorted(all_tickers)) or 'N/A'}")
    print(f"🏷️ 전체 키워드: {', '.join(sorted(all_keywords)) or 'N/A'}")

    return {
        "all_tickers": list(all_tickers),
        "all_keywords": list(all_keywords)
    }


if __name__ == "__main__":
    results = asyncio.run(scrape_blog(days_back=2, limit=5))
    summary = print_summary(results)
