# Daily Stock Story - Handoff

**작성일**: 2026-01-24 (세션 2)

---

## 현재 상태: ralphy 실행 중

```bash
cd ~/dailystockstory
ralphy --max-iterations 30
```

---

## 완료된 작업

### 1. Discovery Interview
- 요구사항 수집 완료
- 핵심: 올인원 대시보드, 모바일/PC, 다크 모드

### 2. Feature Planner
- 6 Phase 계획 수립
- `docs/plans/PLAN_daily-stock-story-webapp.md`

### 3. 브레인스토밍
- 관심 종목(Watchlist) 기능 추가
- 추천 성과 추적 기능 추가

### 4. PRD 작성
- ralphy 형식 (체크박스) 완성
- **`PRD.md`** (루트)
- 기존 시스템 분석 반영
- 신규 테이블 SQL 포함

---

## 문서 위치

| 문서 | 경로 |
|------|------|
| **PRD (ralphy용)** | `PRD.md` |
| PRD 상세 | `docs/PRD_daily-stock-story.md` |
| 스펙 | `thoughts/shared/specs/2026-01-24-daily-stock-story-webapp.md` |
| 계획 | `docs/plans/PLAN_daily-stock-story-webapp.md` |

---

## 기존 시스템 (변경 금지!)

### Cron Jobs
```cron
0 9,18 * * * uv run python stock_collector.py    # 주가, RegSHO, 블로그
0 21 * * *   uv run python day_trader_scanner.py  # 단타 추천
0 9,21 * * * uv run python swing_long_scanner.py  # 스윙/장기 추천
```

### 기존 DB 테이블
- stock_briefing, stock_prices, regsho_list
- blog_posts, blogger_tickers
- day_trade_recommendations, swing_recommendations, longterm_recommendations

### 신규 테이블 (생성 필요)
- stock_notes, push_subscriptions, trade_history
- user_settings, watchlist, recommendation_history

---

## 기술 스택

| Layer | Tech |
|-------|------|
| Frontend | SvelteKit |
| Backend | FastAPI (Python) |
| DB | PostgreSQL (continuous_claude) |
| Hosting | Caddy + systemd |

### 도메인
- 프론트: https://stock.sean8320.dedyn.io → localhost:3000
- API: https://stock-api.sean8320.dedyn.io → localhost:8340

---

## 다음 단계

1. **ralphy 완료 확인**
   ```bash
   # 진행 상황 확인
   cat .ralphy/progress.txt
   ```

2. **테스트**
   - API: `curl https://stock-api.sean8320.dedyn.io/health`
   - 프론트: 브라우저에서 `https://stock.sean8320.dedyn.io`

3. **문제 시 ralph-loop으로 수정**
   ```bash
   /ralph-loop "테스트 실패 수정. pytest api/tests/ 통과시켜." --max-iterations 20
   ```

---

## 포트폴리오 현황 (참고)

- **BNAI**: 464주 @ $9.55 → **+513%**
- **GLSI**: 67주 @ $25.22 → +3%
- **총 평가**: ₩41,911,622

---

---

## TODO: MCP 서버 설정 필요

다음 세션에서:
```bash
# GitHub MCP
npx @anthropic/create-mcp-server github

# n8n MCP (API 기반)
# n8n API: http://localhost:5678/api/v1
# API Key: ~/.config/opencode/.env의 PACA_N8N_API_KEY
```

---

## 플러그인 설정 (완료)

**활성화됨:**
- code-review, commit-commands, frontend-design
- pr-review-toolkit, superpowers

**비활성화 (CC v3 훅 충돌):**
- ralph-loop (Stop hook)
- security-guidance (hook)

---

*Handoff 작성: 2026-01-24*
