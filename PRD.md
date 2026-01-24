# Daily Stock Story 웹앱 PRD

개인용 주식 대시보드 PWA. 포트폴리오 현황, 추천 종목, RegSHO, 블로거 인사이트를 한 화면에서 확인.

**현재 버전:** v1.0.0
**배포:** https://web-lyart-rho-73.vercel.app
**API:** https://stock-api.sean8320.dedyn.io

---

## 기술 스택
- Frontend: SvelteKit 5 + Svelte 5 (adapter-vercel)
- Backend: FastAPI (Python 3.12, uvicorn)
- Database: PostgreSQL (continuous_claude DB)
- Hosting: Vercel (프론트) + Caddy/systemd (API)

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

### 절대 건드리지 말 것
- `stock_collector.py` - 데이터 수집
- `read_briefing.py` - CLI 브리핑
- `day_trader_scanner.py` - 단타 추천
- `swing_long_scanner.py` - 스윙/장기 추천
- 기존 DB 테이블들
- Cron jobs

---

## 신규 DB 테이블 (v1.1)

```sql
-- 사용자 (카카오 로그인)
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  kakao_id BIGINT UNIQUE NOT NULL,
  nickname VARCHAR(100),
  profile_image TEXT,
  role VARCHAR(20) DEFAULT 'pending',  -- admin, user, pending
  onboarding_done BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW(),
  approved_at TIMESTAMP
);

-- 포트폴리오 (사용자별)
CREATE TABLE portfolio (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  ticker VARCHAR(10) NOT NULL,
  shares INTEGER NOT NULL,
  avg_cost DECIMAL(10,4) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(user_id, ticker)
);

-- 알림 설정
CREATE TABLE notification_settings (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) UNIQUE,
  push_enabled BOOLEAN DEFAULT FALSE,
  briefing_times JSONB DEFAULT '["09:00", "18:00", "21:00"]',
  created_at TIMESTAMP DEFAULT NOW()
);

-- 매매 이력
CREATE TABLE trade_history (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  ticker VARCHAR(10) NOT NULL,
  action VARCHAR(10) NOT NULL,  -- buy/sell/add
  shares INTEGER NOT NULL,
  price DECIMAL(10, 4) NOT NULL,
  note TEXT,
  traded_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

-- 가격 알림 (손절/익절)
CREATE TABLE price_alerts (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  ticker VARCHAR(10) NOT NULL,
  target_price DECIMAL(10,4),
  stop_loss DECIMAL(10,4),
  is_active BOOLEAN DEFAULT TRUE,
  triggered_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);

-- 관심 종목
CREATE TABLE watchlist (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  ticker VARCHAR(10) NOT NULL,
  added_at TIMESTAMP DEFAULT NOW(),
  is_active BOOLEAN DEFAULT TRUE,
  UNIQUE(user_id, ticker)
);
```

---

## Tasks

### Phase 1: 프로젝트 셋업 ✅
- [x] api/ 폴더 생성, FastAPI 프로젝트 초기화
- [x] web/ 폴더 생성, SvelteKit 프로젝트 초기화
- [x] PostgreSQL 연결 (db.py)
- [x] Caddy 설정 (stock-api.sean8320.dedyn.io)
- [x] Vercel 배포 + GitHub 연동

### Phase 2: API 구현 ✅
- [x] GET /api/briefing - stock_briefing 테이블 조회
- [x] GET /api/portfolio - 포트폴리오 + 현재가
- [x] GET /api/recommendations - 단타/스윙/장기 추천
- [x] GET /api/regsho - RegSHO 목록, 보유 종목 표시
- [x] GET /api/blog - 블로그 포스트 조회
- [x] 에러 핸들링 미들웨어

### Phase 3: 프론트엔드 UI ✅
- [x] 다크 모드 글로벌 CSS
- [x] 모바일 최적화 레이아웃 (max-width: 500px)
- [x] 한글화
- [x] 포트폴리오 카드 (수익/손실 색상)
- [x] 추천 종목 탭 UI
- [x] RegSHO 배지
- [x] API 연동 (SvelteKit load 함수)
- [x] 로딩/에러 상태 UI

### Phase 4: PWA 기본 ✅
- [x] manifest.json
- [x] 앱 아이콘 (192x192, 512x512)
- [x] service-worker.ts
- [x] /login 라우트 (UI만, 미연결)

---

## TODO (v1.1)

- [ ] 블로거 인사이트 UI 추가
- [ ] 세금 계산 표시 추가
- [ ] 하단 네비게이션 추가
- [ ] 카카오 로그인 API 구현
- [ ] 사용자 승인 시스템 구현
- [ ] 온보딩 UI 구현
- [ ] 포트폴리오 CRUD API 구현
- [ ] 포트폴리오 CRUD UI 구현
- [ ] 매매 기록 및 손절익절 구현
- [ ] 관심 종목 기능 추가
- [ ] 익절 계산기 추가
- [ ] 푸시 알림 구현

---

## 포트폴리오 데이터 (보존!)

```
| 티커 | 수량 | 평단 |
|------|------|------|
| BNAI | 464 | $9.55 |
| GLSI | 67 | $25.22 |
```

**절대 삭제 금지**: `portfolio.md`

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
| 문서 | 경로 |
|------|------|
| 인증 설계 | `docs/plans/2026-01-24-v1.1-auth-design.md` |
| 기능 계획 | `docs/plans/PLAN_v1.1-features.md` |
| 핸드오프 | `HANDOFF.md` |
| 포트폴리오 | `portfolio.md` |
| 카카오 로그인 참고 | `~/mprojects/` |

---

*최종 업데이트: 2026-01-24*
