# Daily Stock Story v1.1 기능 추가 계획

**작성일:** 2026-01-24
**현재 버전:** v1.0.0
**목표 버전:** v1.1.0

---

## 현재 상태 (v1.0.0)

### ✅ 완료
- 포트폴리오 조회 (읽기 전용)
- 추천 종목 (단타/스윙/장기)
- RegSHO 리스트
- 모바일 UI + 한글화
- Vercel 배포 + GitHub 연동

### ❌ 미완료
- 블로그 인사이트 (API만 있음)
- PIN 인증
- 포트폴리오 CRUD
- 매매 기록
- 세금 계산
- 하단 네비게이션

---

## v1.1 목표 기능

### Phase 1: 핵심 기능 (P0)

#### 1.1 PIN 인증
```
목표: 친구들한테 공유 가능하게
- 4자리 PIN 설정
- 로컬 스토리지에 해시 저장
- 세션 24시간 유지
- 로그인 페이지 이미 있음 → 연결만
```

**API:**
```
POST /api/auth/verify  { pin: "1234" }
→ { success: true, token: "..." }
```

#### 1.2 블로그 인사이트 UI
```
목표: 까꿍토끼 블로그 최신 글 표시
- API: /api/blog 이미 있음
- 웹에 섹션 추가
- 티커/키워드 태그
- 원문 링크
```

#### 1.3 세금 계산 표시
```
목표: 익절 시 예상 세금 바로 확인
- 총 수익 × 22% (250만원 공제 후)
- 포트폴리오 카드에 표시
```

---

### Phase 2: 포트폴리오 관리 (P1)

#### 2.1 포트폴리오 CRUD
```
목표: 종목 추가/수정/삭제
현재: portfolio.md 하드코딩

API:
POST   /api/portfolio           # 종목 추가
PUT    /api/portfolio/{ticker}  # 수정 (수량, 평단)
DELETE /api/portfolio/{ticker}  # 삭제

DB 테이블:
portfolio (
  id SERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL UNIQUE,
  shares INTEGER NOT NULL,
  avg_cost DECIMAL(10,4) NOT NULL,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)
```

#### 2.2 매매 기록
```
목표: 매수/매도/추매 기록
- 매매할 때마다 자동 기록
- 과거 이력 조회

API:
POST /api/trades  { ticker, action, shares, price, date }
GET  /api/trades?ticker=BNAI

action: "buy" | "sell" | "add" (추매)

DB 테이블:
trade_history (
  id SERIAL PRIMARY KEY,
  ticker VARCHAR(10),
  action VARCHAR(10),  -- buy/sell/add
  shares INTEGER,
  price DECIMAL(10,4),
  traded_at TIMESTAMP,
  note TEXT,
  created_at TIMESTAMP
)
```

#### 2.3 손절/익절 알림 설정
```
목표: 목표가/손절가 설정 → 도달 시 알림
- 종목별 목표가/손절가 설정
- 현재가 도달 시 체크

API:
POST /api/alerts { ticker, target_price, stop_loss }
GET  /api/alerts

DB 테이블:
price_alerts (
  id SERIAL PRIMARY KEY,
  ticker VARCHAR(10),
  target_price DECIMAL(10,4),
  stop_loss DECIMAL(10,4),
  is_active BOOLEAN DEFAULT TRUE,
  triggered_at TIMESTAMP,
  created_at TIMESTAMP
)
```

---

### Phase 3: UI 개선 (P1)

#### 3.1 하단 네비게이션
```
[🏠 홈] [📊 포트폴리오] [📝 이력] [⚙️ 설정]

- 홈: 현재 대시보드
- 포트폴리오: CRUD UI
- 이력: 매매 기록
- 설정: PIN, 알림 등
```

#### 3.2 종목 상세 페이지
```
/stock/BNAI

- 현재가, 차트 (외부 링크)
- 매매 기록
- 메모
- 손절/익절 설정
```

---

### Phase 4: 추가 기능 (P2)

#### 4.1 관심 종목 (Watchlist)
```
- 추천 종목 → ⭐ 클릭 → 관심 추가
- 관심 종목 별도 섹션
```

#### 4.2 익절 계산기
```
- 목표가 입력 → 예상 수익/세금 계산
- 분할 매도 시뮬레이션
```

#### 4.3 푸시 알림
```
- 정기 브리핑 (09:00, 18:00, 21:00 KST)
- 손절/익절 도달 알림
- RegSHO 등재/해제 알림
```

---

## 구현 순서

```
1. PIN 인증 + 블로그 UI + 세금 표시  ← 1일
2. 포트폴리오 DB + CRUD API          ← 1일
3. 포트폴리오 CRUD UI                ← 1일
4. 매매 기록 API + UI               ← 1일
5. 하단 네비게이션                   ← 0.5일
6. 손절/익절 설정                    ← 1일
7. 관심 종목 + 계산기               ← 1일
```

---

## 기술 메모

### API 서버
- 위치: `~/dailystockstory/api/main.py`
- 포트: 8340
- 재시작: `sudo systemctl restart stock-api` (서비스 만들어야 함)

### 웹앱
- 위치: `~/dailystockstory/web/`
- 배포: GitHub push → Vercel 자동

### DB
- PostgreSQL (continuous_claude DB 사용 중)
- 테이블: stock_briefing, stock_prices, regsho_list, blog_posts 등

### 환경변수
- `~/.config/opencode/.env` → VERCEL_TOKEN 등

---

## 다음 세션에서 할 일

1. API 서버 systemd 서비스 등록
2. PIN 인증 구현
3. 블로그 UI 추가
4. 포트폴리오 DB 테이블 생성
5. CRUD API 구현

---

*계획 작성: 2026-01-24*
