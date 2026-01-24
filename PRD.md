# Daily Stock Story 웹앱 PRD

개인용 주식 대시보드 PWA. 포트폴리오 현황, 추천 종목, RegSHO, 블로거 인사이트를 한 화면에서 확인.

---

## 기술 스택
- Frontend: SvelteKit
- Backend: FastAPI (Python 3.12, uvicorn)
- Database: PostgreSQL (기존 continuous_claude DB)
- Hosting: Caddy + systemd

## 도메인
- 프론트: https://stock.sean8320.dedyn.io (→ localhost:3000)
- API: https://stock-api.sean8320.dedyn.io (→ localhost:8340)

---

## 기존 시스템 (변경 금지!)

### Cron Jobs (이미 동작 중)
```cron
0 9,18 * * * uv run python stock_collector.py    # 주가, RegSHO, 블로그
0 21 * * *   uv run python day_trader_scanner.py  # 단타 추천
0 9,21 * * * uv run python swing_long_scanner.py  # 스윙/장기 추천
```

### 기존 DB 테이블 (읽기 전용)
| 테이블 | 용도 | 소스 |
|--------|------|------|
| stock_briefing | 포트폴리오 브리핑 JSON | stock_collector.py |
| stock_prices | 주가 히스토리 | stock_collector.py |
| regsho_list | RegSHO 목록 | stock_collector.py |
| blog_posts | 블로그 포스트 | stock_collector.py |
| blogger_tickers | 블로거 언급 티커 | stock_collector.py |
| day_trade_recommendations | 단타 추천 | day_trader_scanner.py |
| swing_recommendations | 스윙 추천 | swing_long_scanner.py |
| longterm_recommendations | 장기 추천 | swing_long_scanner.py |

### 참조 코드 (로직 재사용)
- `read_briefing.py` → /api/briefing 엔드포인트에서 로직 참조
- `get_briefing()`, `get_day_trade_recommendations()`, `get_new_blog_posts()` 함수 참조

---

## 신규 DB 테이블 (생성 필요)

```sql
-- 종목 메모
CREATE TABLE stock_notes (
  id SERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  content TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- 푸시 구독
CREATE TABLE push_subscriptions (
  id SERIAL PRIMARY KEY,
  endpoint TEXT NOT NULL,
  keys JSONB NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

-- 매매 이력
CREATE TABLE trade_history (
  id SERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  action VARCHAR(10) NOT NULL,
  quantity INTEGER NOT NULL,
  price DECIMAL(10, 4) NOT NULL,
  traded_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

-- 사용자 설정
CREATE TABLE user_settings (
  key VARCHAR(50) PRIMARY KEY,
  value JSONB NOT NULL,
  updated_at TIMESTAMP DEFAULT NOW()
);

-- 관심 종목
CREATE TABLE watchlist (
  id SERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL UNIQUE,
  added_at TIMESTAMP DEFAULT NOW(),
  removed_at TIMESTAMP NULL,
  is_active BOOLEAN DEFAULT TRUE
);

-- 추천 히스토리 (성과 추적용)
CREATE TABLE recommendation_history (
  id SERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  recommendation_type VARCHAR(20) NOT NULL,
  recommended_at TIMESTAMP NOT NULL,
  entry_price DECIMAL(10, 4),
  target_price DECIMAL(10, 4),
  stop_loss DECIMAL(10, 4),
  actual_high DECIMAL(10, 4),
  actual_low DECIMAL(10, 4),
  is_watched BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Tasks

### Phase 1: 프로젝트 셋업
- [x] api/ 폴더 생성, FastAPI 프로젝트 초기화 (main.py)
- [x] requirements.txt 생성 (fastapi, uvicorn, psycopg2-binary, python-dotenv)
- [x] .env 파일 생성 (DATABASE_URL=postgresql://claude:claude_dev@localhost:5432/continuous_claude)
- [x] GET /health 엔드포인트 구현 → {"status": "ok", "timestamp": "..."}
- [x] PostgreSQL 연결 함수 (db.py) - 기존 read_briefing.py의 get_db() 참조
- [x] 신규 테이블 6개 생성 SQL 실행
- [x] web/ 폴더 생성, SvelteKit 프로젝트 초기화 (npm create svelte@latest web)
- [x] Caddy 설정 추가: stock-api.sean8320.dedyn.io reverse_proxy localhost:8340
- [x] Caddy 설정 추가: stock.sean8320.dedyn.io reverse_proxy localhost:3000
- [x] systemd 서비스 파일 생성: /etc/systemd/system/stock-api.service (uvicorn api.main:app --port 8340)

### Phase 2: API 구현 (기존 테이블 읽기)
- [x] GET /api/briefing - stock_briefing 테이블에서 최신 데이터 조회 (read_briefing.py의 get_briefing() 참조)
- [x] GET /api/portfolio - stock_briefing의 portfolio 필드 파싱, 현재가는 stock_prices에서
- [x] GET /api/recommendations - day_trade_recommendations, swing_recommendations, longterm_recommendations 조회
- [x] GET /api/regsho - regsho_list 테이블 조회, 보유 종목(BNAI, GLSI) 등재 여부 표시
- [x] GET /api/blog-posts - blog_posts 테이블에서 최근 10개 조회, is_read=false 필터 옵션
- [x] Pydantic 모델 정의 (schemas.py): BriefingResponse, PortfolioItem, Recommendation, RegSHOItem, BlogPost
- [x] 에러 핸들링 미들웨어 추가

### Phase 3: 프론트엔드 UI
- [x] 다크 모드 글로벌 CSS 설정 (배경 #0d1117, 텍스트 #c9d1d9)
- [x] +layout.svelte: 공통 레이아웃, 하단 네비게이션 (홈/관심/이력/설정)
- [x] +page.svelte (홈): API 호출하여 대시보드 표시
- [x] PortfolioCard.svelte: 종목별 카드 (수익 #3fb950, 손실 #f85149)
- [x] RecommendationTabs.svelte: 단타/스윙/장기 탭 UI
- [x] RegSHOBadge.svelte: 보유 종목 RegSHO 등재 표시
- [x] BlogInsights.svelte: 블로그 요약 + 원문 링크
- [x] API 연동 (fetch, SvelteKit load 함수)
- [x] 로딩 스켈레톤, 에러 상태 UI

### Phase 4: PWA + PIN 인증
- [x] static/manifest.json 생성 (name, icons, display: standalone, theme_color: #0d1117)
- [x] 앱 아이콘 생성 (192x192, 512x512 PNG)
- [x] src/service-worker.ts: 정적 자산 캐싱, /api/briefing 응답 캐싱 (오프라인용)
- [x] /login 라우트: PIN 4자리 입력 UI (숫자 키패드)
- [ ] PIN 검증 로직: localStorage에 해시 저장, 24시간 세션
- [ ] 최초 접속 시 PIN 설정 화면
- [ ] 인증 안 된 상태면 /login으로 리다이렉트

### Phase 5: 푸시 알림
- [ ] VAPID 키 생성 (npx web-push generate-vapid-keys), .env에 저장
- [ ] POST /api/push/subscribe: push_subscriptions 테이블에 저장
- [ ] DELETE /api/push/subscribe: 구독 삭제
- [ ] 푸시 전송 서비스 (services/push.py): pywebpush 사용
- [ ] APScheduler로 정기 알림 스케줄 (main.py에 추가)
  - 09:00 KST: 아침 브리핑
  - 18:00 KST: 퇴근 브리핑
  - 21:00 KST: 미장 전 추천
- [ ] RegSHO 변동 알림: stock_collector.py 실행 후 보유 종목 등재/해제 감지 → 푸시
- [ ] 프론트엔드: 알림 권한 요청 버튼, 구독 상태 표시

### Phase 6: 부가 기능
- [ ] GET/POST/PUT/DELETE /api/notes/{ticker}: 종목 메모 CRUD
- [ ] GET /api/watchlist: 관심 종목 목록
- [ ] POST /api/watchlist/{ticker}: 관심 추가
- [ ] DELETE /api/watchlist/{ticker}: 관심 해제 (is_active=false, removed_at 기록)
- [ ] 추천 종목 클릭 시 recommendation_history에 저장
- [ ] GET /api/calculator?ticker=X&target_price=Y: 익절 계산 (22% 세금, 250만원 공제)
- [ ] GET /api/history/{date}: 해당 날짜 브리핑 조회
- [ ] /watchlist 페이지: 관심 종목 카드 목록
- [ ] /history 페이지: 캘린더로 날짜 선택 → 과거 브리핑
- [ ] /settings 페이지: PIN 변경, 알림 시간 설정, 푸시 on/off
- [ ] 추천 성과 추적: recommendation_history의 actual_high/low 업데이트 (stock_collector.py 수정 또는 별도 스크립트)

---

## UI 색상
| 용도 | 색상 |
|------|------|
| 배경 | #0d1117 |
| 텍스트 | #c9d1d9 |
| 수익 | #3fb950 |
| 손실 | #f85149 |
| 강조 | #58a6ff |
| 카드 배경 | #161b22 |
| 테두리 | #30363d |

---

## 참조 문서
- 상세 스펙: thoughts/shared/specs/2026-01-24-daily-stock-story-webapp.md
- 구현 계획: docs/plans/PLAN_daily-stock-story-webapp.md
- 기존 브리핑: read_briefing.py (로직 참조)
