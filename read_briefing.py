#!/usr/bin/env python3
"""
Stock Briefing Reader v3
- 내 포트폴리오 브리핑
- 단타 추천 (기술적 분석 기반)
- 시스템 알림 (OOM 등)
- 블로그 인사이트
"""

import subprocess
import re
from datetime import datetime, timedelta, timezone

from psycopg2.extras import RealDictCursor

from db import get_db

KST = timezone(timedelta(hours=9))


def to_kst(dt):
    """UTC datetime을 KST로 변환"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST)


def get_system_alerts():
    """최근 24시간 OOM 등 시스템 알림"""
    alerts = []
    try:
        result = subprocess.run(
            ["journalctl", "--since", "24 hours ago", "-p", "err", "--no-pager", "-o", "short-iso"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.strip().split('\n'):
            if 'Out of memory' in line or 'oom-kill' in line:
                match = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
                timestamp = match.group(1) if match else "unknown"
                proc_match = re.search(r'Killed process \d+ \((\w+)\)', line)
                process = proc_match.group(1) if proc_match else "unknown"
                mem_match = re.search(r'anon-rss:(\d+)kB', line)
                memory_gb = int(mem_match.group(1)) / 1024 / 1024 if mem_match else 0
                alerts.append({'type': 'OOM', 'timestamp': timestamp, 'process': process, 'memory_gb': memory_gb})

        mem_result = subprocess.run(
            ["systemctl", "show", "code-server@sean", "--property=MemoryMax,MemoryHigh"],
            capture_output=True, text=True, timeout=5
        )
        mem_info = dict(line.split('=', 1) for line in mem_result.stdout.strip().split('\n') if '=' in line)
        if mem_info.get('MemoryMax') and mem_info['MemoryMax'] != 'infinity':
            high_gb = int(mem_info.get('MemoryHigh', 0)) / 1024**3
            max_gb = int(mem_info.get('MemoryMax', 0)) / 1024**3
            alerts.append({'type': 'INFO', 'message': f"code-server 메모리 제한: {high_gb:.0f}GB / {max_gb:.0f}GB"})
    except:
        pass
    return alerts


def get_briefing():
    """포트폴리오 브리핑 데이터"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT briefing_json, created_at FROM stock_briefing ORDER BY created_at DESC LIMIT 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return (row["briefing_json"], row["created_at"]) if row else (None, None)


def get_day_trade_recommendations():
    """단타 추천 데이터"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT recommendations, created_at FROM day_trade_recommendations ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        return (row["recommendations"], row["created_at"]) if row else (None, None)
    except:
        return None, None


def get_new_blog_posts():
    """새 블로그 글"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT post_id, title, url, tickers, keywords, post_date FROM blog_posts WHERE is_new = TRUE ORDER BY collected_at DESC")
    posts = cur.fetchall()
    cur.close()
    conn.close()
    return posts


def mark_posts_as_read():
    """블로그 글 읽음 처리"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE blog_posts SET is_new = FALSE WHERE is_new = TRUE")
    conn.commit()
    cur.close()
    conn.close()


def format_briefing(data, updated_at, day_trade, day_trade_time, new_posts, alerts):
    """전체 브리핑 포맷"""
    if not data:
        return "❌ 브리핑 데이터 없음. `uv run python stock_collector.py` 실행 필요."

    lines = []
    lines.append("## 📊 Daily Stock Briefing")
    lines.append(f"*데이터 수집: {to_kst(updated_at).strftime('%Y-%m-%d %H:%M KST')}*")
    lines.append("")

    # ===== 시스템 알림 =====
    oom_alerts = [a for a in alerts if a.get('type') == 'OOM']
    if oom_alerts:
        lines.append("### ⚠️ 시스템 알림")
        lines.append("")
        for alert in oom_alerts[-3:]:
            lines.append(f"- **{alert['timestamp']}** - {alert['process']} OOM ({alert['memory_gb']:.1f}GB)")
        for info in [a for a in alerts if a.get('type') == 'INFO']:
            lines.append(f"ℹ️ {info['message']}")
        lines.append("")

    # ===== 내 포트폴리오 =====
    lines.append("### 💰 내 포트폴리오")
    lines.append("")
    lines.append("| 종목 | 수량 | 평단 | 종가 | AH | 현재가 | 평가금 | 손익 |")
    lines.append("|------|------|------|------|-----|--------|--------|------|")
    
    for p in data.get("portfolio", []):
        emoji = "🔥" if p["gain_pct"] > 100 else ("📈" if p["gain_pct"] > 0 else "📉")
        regular = f"${p['regular_price']:.2f}" if p.get('regular_price') else "-"
        ah = f"${p['afterhours_price']:.2f}" if p.get('afterhours_price') else "-"
        lines.append(f"| **{p['ticker']}** | {p['shares']}주 | ${p['avg_cost']:.2f} | {regular} | {ah} | **${p['current_price']:.2f}** | ${p['value']:,.0f} | +${p['gain']:,.0f} (+{p['gain_pct']:.0f}%) {emoji} |")
    lines.append("")

    total = data.get("total", {})
    rate = data.get("exchange_rate", 1450)
    lines.append(f"**총 평가금:** ${total.get('value_usd', 0):,.0f} (₩{total.get('value_krw', 0):,.0f})")
    lines.append(f"**총 손익:** +${total.get('gain_usd', 0):,.0f} (+{total.get('gain_pct', 0):.0f}%)")
    lines.append(f"**환율:** $1 = ₩{rate:,.2f}")
    lines.append("")

    # ===== 세금 =====
    tax = data.get("tax", {})
    lines.append("### 💸 세금 계산 (실현 시)")
    lines.append("")
    lines.append(f"| 총 수익 | ₩{total.get('gain_krw', 0):,.0f} |")
    lines.append(f"| 기본공제 | -₩2,500,000 |")
    lines.append(f"| **예상 세금 (22%)** | **₩{tax.get('tax_krw', 0):,.0f}** |")
    lines.append(f"| **세후 순수익** | **₩{tax.get('net_profit_krw', 0):,.0f}** |")
    lines.append("")

    # ===== RegSHO =====
    regSHO = data.get("regSHO", {})
    holdings_on_list = regSHO.get("holdings_on_list", [])
    lines.append("### 📋 RegSHO Threshold")
    lines.append("")
    if holdings_on_list:
        lines.append(f"✅ **보유 종목 등재:** {', '.join(holdings_on_list)}")
    else:
        lines.append("❌ 보유 종목 중 등재 없음")
    lines.append(f"총 {regSHO.get('total_count', 0)}개 종목 등재")
    lines.append("")

    # ===== 단타 추천 =====
    if day_trade:
        lines.append("### 🎯 오늘의 단타 후보 (5% 목표)")
        lines.append(f"*스캔: {to_kst(day_trade_time).strftime('%H:%M KST')}*")
        lines.append("")
        
        for i, rec in enumerate(day_trade, 1):
            regsho = " ⚡RegSHO" if rec.get('on_regsho') else ""
            lines.append(f"**{i}. {rec['symbol']}**{regsho} (점수: {rec['score']})")
            lines.append(f"- 현재: ${rec['current_price']} | 갭: {rec['gap_pct']:+.1f}%")
            lines.append(f"- 진입: ${rec['entry']} → 목표: ${rec['target']} | 손절: ${rec['stop_loss']}")
            lines.append(f"- RSI: {rec['rsi']} | 거래량: {rec['volume_surge']}x")
            lines.append(f"- 📌 {', '.join(rec['reasons'])}")
            lines.append("")
        
        lines.append("> ⚠️ 단타는 고위험! 참고용이며 투자 책임은 본인에게 있음")
        lines.append("")
    else:
        lines.append("### 🎯 단타 추천")
        lines.append("아직 스캔 안 됨. `uv run python day_trader_scanner.py` 실행")
        lines.append("")

    # ===== 블로그 =====
    if new_posts:
        lines.append("### 📝 새 블로그 글 (까꿍토끼)")
        lines.append("")
        for post in new_posts[:5]:
            title = post.get("title", "")[:40]
            url = post.get("url", "")
            tickers = ", ".join(post.get("tickers", [])[:3]) or "-"
            keywords = ", ".join(post.get("keywords", [])[:3]) or "-"
            lines.append(f"**[{title}...]({url})**")
            lines.append(f"- 티커: {tickers} | 키워드: {keywords}")
            lines.append("")
    else:
        lines.append("### 📝 블로그: 새 글 없음")
        lines.append("")

    return "\n".join(lines)


def main():
    alerts = get_system_alerts()
    data, updated_at = get_briefing()
    day_trade, day_trade_time = get_day_trade_recommendations()
    new_posts = get_new_blog_posts()
    
    print(format_briefing(data, updated_at, day_trade, day_trade_time, new_posts, alerts))
    
    if new_posts:
        print(f"\n💡 새 글 {len(new_posts)}개 읽음 처리: uv run python -c \"from read_briefing import mark_posts_as_read; mark_posts_as_read()\"")


if __name__ == "__main__":
    main()
