"""
scanners/runner.py - 스캐너 오케스트레이터

CLI 진입점:
    uv run python -m scanners.runner --type day|swing|long|all [--test] [--force]

각 스캐너를 독립 실행하고 카테고리별 MERGE 저장 (덮어쓰기 방지)
"""

import sys
import os
import time
import argparse
from datetime import datetime, date

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanners.screener import get_day_candidates, get_swing_candidates, get_long_candidates
from scanners.scoring import calculate_rating, generate_recommendation, calculate_split_entry
from scanners.storage import init_tables, save_category
from scanners import day_scanner, swing_scanner, long_scanner


def is_us_market_holiday() -> bool:
    """미국 증시 휴장일 체크"""
    today = date.today()

    if today.weekday() >= 5:
        return True

    holidays_2026 = [
        date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16),
        date(2026, 4, 3), date(2026, 5, 25), date(2026, 7, 3),
        date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25),
    ]

    return today in holidays_2026


def _enrich_result(result: dict) -> dict:
    """공통 후처리: AI 추천 + 등급 + 분할매수"""
    result['recommendation_reason'] = generate_recommendation(result)

    rating, rr = calculate_rating(result['score'])
    result['rating'] = rating
    result['rr_ratio'] = rr

    if result['category'] == 'longterm':
        result['split_entries'] = [
            {'price': result['current_price'], 'pct': 30, 'label': '1차 매수'},
            {'price': round(result['current_price'] * 0.95, 2), 'pct': 40, 'label': '-5% 추가'},
            {'price': round(result['current_price'] * 0.90, 2), 'pct': 30, 'label': '-10% 적극'},
        ]
    else:
        result['split_entries'] = calculate_split_entry(
            result['current_price'],
            result.get('support', result['current_price'] * 0.95),
            result['current_price'] * 0.03,
        )

    return result


def run_day(test: bool = False) -> list:
    """단타 스캔 실행"""
    print("\n[단타] 뉴스 핫 종목 스캔 중...")
    candidates = get_day_candidates(30)

    if not candidates:
        print("  뉴스 데이터 없음")
        return []

    pool = candidates[:10] if test else candidates
    results = []

    for item in pool:
        ticker = item['ticker']
        result = day_scanner.analyze(ticker, item['total_score'] or 0)
        if result:
            result = _enrich_result(result)
            results.append(result)
        time.sleep(0.3)

    print(f"  단타 추천: {len(results)}개")
    return results


def run_swing(test: bool = False) -> list:
    """스윙 스캔 실행"""
    print("\n[스윙] 중형 성장주 스캔 중...")
    candidates = get_swing_candidates()
    pool = candidates[:15] if test else candidates
    results = []

    for ticker in pool:
        result = swing_scanner.analyze(ticker)
        if result:
            result = _enrich_result(result)
            results.append(result)
        time.sleep(0.3)

    print(f"  스윙 추천: {len(results)}개")
    return results


def run_long(test: bool = False) -> list:
    """장기 스캔 실행"""
    print("\n[장기] 대형 배당주 스캔 중...")
    candidates = get_long_candidates()
    pool = candidates[:15] if test else candidates
    results = []

    for ticker in pool:
        result = long_scanner.analyze(ticker)
        if result:
            result = _enrich_result(result)
            results.append(result)
        time.sleep(0.3)

    print(f"  장기 추천: {len(results)}개")
    return results


def _print_results(day_results, swing_results, long_results):
    """결과 출력"""
    print("\n" + "=" * 60)

    if day_results:
        print("\n[단타] TOP 5")
        print("-" * 60)
        for i, r in enumerate(sorted(day_results, key=lambda x: -x['score'])[:5], 1):
            print(f"  {i}. {r['ticker']:6} | {r['score']:5.1f}점 {r['rating']:3} | "
                  f"RSI: {r['rsi']:5.1f} | 거래량: {r['volume_ratio']:.1f}x | ${r['current_price']:.2f}")

    if swing_results:
        print("\n[스윙] TOP 5 (4-7일)")
        print("-" * 60)
        for i, r in enumerate(sorted(swing_results, key=lambda x: -x['score'])[:5], 1):
            print(f"  {i}. {r['ticker']:6} | {r['score']:5.1f}점 {r['rating']:3} | "
                  f"RSI: {r['rsi']:5.1f} | MACD: {r['macd_cross']:7} | ${r['current_price']:.2f}")

    if long_results:
        print("\n[장기] TOP 5 (3개월+)")
        print("-" * 60)
        for i, r in enumerate(sorted(long_results, key=lambda x: -x['score'])[:5], 1):
            div = r.get('dividend_yield', 0)
            pe = r.get('pe_ratio', 0) or 0
            print(f"  {i}. {r['ticker']:6} | {r['score']:5.1f}점 {r['rating']:3} | "
                  f"배당: {div:.1f}% | P/E: {pe:.1f} | ${r['current_price']:.2f}")


def _send_notifications(scan_type, day_results, swing_results, long_results):
    """푸시 알림 발송"""
    print("\n푸시 알림 발송...")
    try:
        from api.notifications import send_recommendation_notification

        if scan_type in ('all', 'day') and day_results:
            result = send_recommendation_notification('day_trade', min(len(day_results), 5))
            print(f"  - 단타: {result.get('sent', 0)}건 발송")

        if scan_type in ('all', 'swing') and swing_results:
            result = send_recommendation_notification('swing', min(len(swing_results), 5))
            print(f"  - 스윙: {result.get('sent', 0)}건 발송")

        if scan_type in ('all', 'long') and long_results:
            result = send_recommendation_notification('longterm', min(len(long_results), 5))
            print(f"  - 장기: {result.get('sent', 0)}건 발송")
    except Exception as e:
        print(f"  - 알림 발송 실패: {e}")


def main():
    parser = argparse.ArgumentParser(description='시장 스캐너 v3')
    parser.add_argument('--test', action='store_true', help='테스트 모드 (소량만)')
    parser.add_argument('--force', action='store_true', help='휴장일 무시')
    parser.add_argument('--type', choices=['all', 'day', 'swing', 'long'], default='all',
                        help='스캔 유형')
    args = parser.parse_args()

    print("=" * 60)
    print("시장 스캐너 v3")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"모드: {args.type}" + (" (테스트)" if args.test else ""))
    print("=" * 60)

    if is_us_market_holiday() and not args.force:
        print("미국 증시 휴장일 - 스캔 건너뜀")
        return

    init_tables()

    day_results = []
    swing_results = []
    long_results = []

    # 각 스캐너 독립 실행 + 카테고리별 저장
    if args.type in ('all', 'day'):
        day_results = run_day(args.test)
        if day_results:
            save_category('day_trade', day_results)
    else:
        print("\n[단타] 스킵")

    if args.type in ('all', 'swing'):
        swing_results = run_swing(args.test)
        if swing_results:
            save_category('swing', swing_results)
    else:
        print("\n[스윙] 스킵")

    if args.type in ('all', 'long'):
        long_results = run_long(args.test)
        if long_results:
            save_category('longterm', long_results)
    else:
        print("\n[장기] 스킵")

    print("\n결과 저장 완료")

    _print_results(day_results, swing_results, long_results)

    _send_notifications(args.type, day_results, swing_results, long_results)

    print("\n스캔 완료!")


if __name__ == '__main__':
    main()
