# Daily Stock Story 웹앱 구현 계획

**CRITICAL INSTRUCTIONS**: After completing each phase:
1. Check off completed task checkboxes
2. Run all quality gate validation commands
3. Verify ALL quality gate items pass
4. Update "Last Updated" date
5. Document learnings in Notes section
6. Only then proceed to next phase

DO NOT skip quality gates or proceed with failing checks

---

## Overview

| 항목 | 내용 |
|------|------|
| **프로젝트** | Daily Stock Story 웹앱 |
| **목표** | 개인용 주식 대시보드 PWA |
| **스펙** | `thoughts/shared/specs/2026-01-24-daily-stock-story-webapp.md` |
| **시작일** | 2026-01-24 |
| **Last Updated** | 2026-01-24 |

### 도메인
| 용도 | URL |
|------|-----|
| 프론트엔드 | https://stock.sean8320.dedyn.io |
| 백엔드 API | https://stock-api.sean8320.dedyn.io |

### 기술 스택
| Layer | Technology |
|-------|------------|
| Frontend | SvelteKit |
| Backend | FastAPI (Python) |
| Database | PostgreSQL (기존) |
| Hosting | Caddy (현재 서버) |
| Push | Web Push API |

---

## Phase 1: 프로젝트 셋업 & 인프라

**Goal**: FastAPI + SvelteKit 프로젝트 구조 생성, DB 테이블 추가, Caddy 설정

**Dependencies**: 없음 (시작 단계)

### Tasks

#### RED (Tests First)
- [ ] FastAPI 프로젝트 초기화 (`~/dailystockstory/api/`)
- [ ] pytest 설정 및 health check 테스트 작성
- [ ] SvelteKit 프로젝트 초기화 (`~/dailystockstory/web/`)
- [ ] Playwright/Vitest 설정

#### GREEN (Implementation)
- [ ] FastAPI health endpoint 구현 (`GET /health`)
- [ ] DB 연결 설정 (기존 PostgreSQL 활용)
- [ ] 신규 테이블 생성
  ```sql
  stock_notes, push_subscriptions, trade_history, user_settings,
  watchlist, recommendation_history
  ```
- [ ] SvelteKit 기본 레이아웃 (다크 모드)
- [ ] 환경변수 설정 (`.env`)

#### REFACTOR (Polish)
- [ ] Caddy 설정 추가
  ```
  stock-api.sean8320.dedyn.io → localhost:8340
  stock.sean8320.dedyn.io → localhost:3000
  ```
- [ ] systemd 서비스 파일 생성 (`stock-api.service`)
- [ ] 프로젝트 구조 정리

### Quality Gate
- [ ] `pytest api/tests/` 통과
- [ ] `npm run check` (SvelteKit) 통과
- [ ] API health check 응답: `curl https://stock-api.sean8320.dedyn.io/health`
- [ ] 프론트 접속 확인: `https://stock.sean8320.dedyn.io`
- [ ] DB 테이블 생성 확인

### Rollback
- Caddy 설정 롤백: 추가한 블록 제거
- systemd 서비스 중지 및 제거
- DB 테이블 DROP (신규 4개만)

---

## Phase 2: 대시보드 API 구현

**Goal**: 기존 데이터를 JSON으로 제공하는 API 엔드포인트

**Dependencies**: Phase 1 완료

### Tasks

#### RED (Tests First)
- [ ] `/api/briefing` 테스트 작성
- [ ] `/api/portfolio` 테스트 작성
- [ ] `/api/recommendations` 테스트 작성
- [ ] `/api/regsho` 테스트 작성
- [ ] `/api/blog-posts` 테스트 작성

#### GREEN (Implementation)
- [ ] Pydantic 모델 정의 (응답 스키마)
- [ ] `GET /api/briefing` - 오늘의 브리핑
  - 기존 `read_briefing.py` 로직 재사용
- [ ] `GET /api/portfolio` - 포트폴리오 현황
  - 종목별 수익률, 평가금액, 환율
- [ ] `GET /api/recommendations` - 추천 종목
  - 단타/스윙/장기 탭별 데이터
- [ ] `GET /api/regsho` - RegSHO 목록
  - 보유 종목 등재 여부 표시
- [ ] `GET /api/blog-posts` - 블로거 인사이트
  - 최근 5개, 티커/키워드 + 링크

#### REFACTOR (Polish)
- [ ] 응답 캐싱 (5분)
- [ ] 에러 핸들링 통일
- [ ] API 문서 자동 생성 (FastAPI Swagger)

### Quality Gate
- [ ] 모든 API 테스트 통과
- [ ] Swagger UI에서 모든 엔드포인트 확인
- [ ] 응답 시간 < 500ms
- [ ] 타입 검증 통과

### Rollback
- API 라우터 파일 삭제
- Pydantic 모델 삭제

---

## Phase 3: 프론트엔드 대시보드 UI

**Goal**: 메인 대시보드 화면 구현 (다크 모드, 모바일 퍼스트)

**Dependencies**: Phase 2 완료

### Tasks

#### RED (Tests First)
- [ ] 대시보드 컴포넌트 테스트 (Vitest)
- [ ] API 연동 테스트 (msw mock)

#### GREEN (Implementation)
- [ ] 공통 레이아웃 (`+layout.svelte`)
  - 다크 모드 테마 (GitHub Dark 색상)
  - 하단 네비게이션 바
- [ ] 포트폴리오 카드 컴포넌트
  - 종목별 수익률 (색상: 수익 녹색, 손실 빨강)
  - 총 평가금액 (원화)
  - 세금 계산 표시
- [ ] 추천 섹션 컴포넌트
  - 탭 UI (단타/스윙/장기)
  - 종목 카드 (진입가, 목표가, 손절가)
- [ ] RegSHO 상태 컴포넌트
  - 보유 종목 등재 여부 배지
- [ ] 블로거 인사이트 컴포넌트
  - 티커/키워드 태그
  - 원문 링크 버튼

#### REFACTOR (Polish)
- [ ] 반응형 디자인 (모바일/태블릿/PC)
- [ ] 로딩 스켈레톤
- [ ] 에러 상태 UI

### Quality Gate
- [ ] 모바일에서 정상 표시 (Chrome DevTools)
- [ ] PC에서 정상 표시
- [ ] 다크 모드 색상 일관성
- [ ] 컴포넌트 테스트 통과

### Rollback
- 컴포넌트 파일 삭제
- 라우트 파일 롤백

---

## Phase 4: PWA + PIN 인증

**Goal**: PWA 설정, 오프라인 지원, PIN 인증

**Dependencies**: Phase 3 완료

### Tasks

#### RED (Tests First)
- [ ] PIN 인증 로직 테스트
- [ ] 서비스 워커 등록 테스트

#### GREEN (Implementation)
- [ ] PWA manifest 설정 (`manifest.json`)
  - 앱 이름, 아이콘, 테마 색상
  - display: standalone
- [ ] 서비스 워커 구현
  - 정적 자산 캐싱
  - 마지막 브리핑 캐싱 (오프라인용)
- [ ] PIN 인증 화면
  - 4자리 숫자 패드
  - 로컬 스토리지 해시 저장
  - 24시간 세션 유지
- [ ] PIN 설정 화면 (최초 접속 시)

#### REFACTOR (Polish)
- [ ] 앱 아이콘 생성 (다크 배경)
- [ ] 스플래시 스크린
- [ ] iOS Safari 메타 태그

### Quality Gate
- [ ] "홈 화면에 추가" 작동 (Android Chrome)
- [ ] "홈 화면에 추가" 작동 (iOS Safari)
- [ ] 오프라인에서 마지막 브리핑 표시
- [ ] PIN 인증 우회 불가

### Rollback
- manifest.json 삭제
- 서비스 워커 해제
- PIN 관련 코드 제거

---

## Phase 5: 푸시 알림

**Goal**: Web Push 알림 (정기 브리핑 + RegSHO 변동)

**Dependencies**: Phase 4 완료

### Tasks

#### RED (Tests First)
- [ ] 푸시 구독 API 테스트
- [ ] 알림 전송 로직 테스트

#### GREEN (Implementation)
- [ ] VAPID 키 생성 및 설정
- [ ] 푸시 구독 API
  - `POST /api/push/subscribe` - 구독 등록
  - `DELETE /api/push/subscribe` - 구독 해제
- [ ] 알림 전송 서비스 (FastAPI)
  - pywebpush 라이브러리 사용
- [ ] 스케줄러 설정 (APScheduler 또는 cron)
  - 09:00 KST - 아침 브리핑
  - 18:00 KST - 퇴근 브리핑
  - 21:00 KST - 미장 전 추천
- [ ] RegSHO 변동 알림
  - 보유 종목 등재/해제 시 즉시 알림
- [ ] 프론트엔드 알림 권한 요청 UI

#### REFACTOR (Polish)
- [ ] 알림 설정 페이지 (시간 조정)
- [ ] 알림 이력 로깅

### Quality Gate
- [ ] 푸시 구독 DB 저장 확인
- [ ] 테스트 푸시 수신 (Android)
- [ ] 테스트 푸시 수신 (iOS - 제한적)
- [ ] 스케줄러 정상 동작

### Rollback
- 스케줄러 중지
- push_subscriptions 테이블 truncate
- 푸시 관련 코드 제거

---

## Phase 6: 부가 기능

**Goal**: 종목 메모, 익절 계산기, 이력 조회, 포트폴리오 관리

**Dependencies**: Phase 5 완료

### Tasks

#### RED (Tests First)
- [ ] 종목 메모 CRUD 테스트
- [ ] 익절 계산기 로직 테스트
- [ ] 포트폴리오 수정 API 테스트

#### GREEN (Implementation)
- [ ] 종목 메모 기능
  - `GET /api/notes/{ticker}` - 메모 조회
  - `POST /api/notes` - 메모 생성
  - `PUT /api/notes/{id}` - 메모 수정
  - `DELETE /api/notes/{id}` - 메모 삭제
  - 프론트엔드: 종목 상세 → 메모 탭
- [ ] **관심 종목(Watchlist) 기능** (브레인스토밍 추가)
  - 추천 종목 히스토리 DB 저장 (recommendation_history 테이블)
  - `POST /api/watchlist/{ticker}` - 관심 추가
  - `DELETE /api/watchlist/{ticker}` - 관심 해제 (기록은 유지)
  - `GET /api/watchlist` - 관심 목록 조회
  - 관심 종목은 브리핑에 별도 섹션으로 표시
  - 프론트엔드: 종목 카드에 ⭐ 버튼
- [ ] 익절 계산기
  - `GET /api/calculator` - 계산 (query params)
  - 목표가 입력 → 예상 수익/세금
  - 분할 매도 시뮬레이션
- [ ] 이력 조회
  - `GET /api/history/{date}` - 날짜별 브리핑
  - 캘린더 UI로 날짜 선택
- [ ] 포트폴리오 관리
  - `PUT /api/portfolio/{ticker}` - 수정
  - `POST /api/portfolio` - 추가
  - `DELETE /api/portfolio/{ticker}` - 삭제
  - portfolio.md 동기화 (선택)

#### REFACTOR (Polish)
- [ ] 설정 페이지 (PIN 변경, 알림 설정)
- [ ] 시스템 상태 표시 (OOM 알림 등)
- [ ] **추천 성과 추적** (브레인스토밍 추가)
  - 과거 추천 종목이 실제로 얼마나 올랐는지 통계
  - 스캐너별 승률 표시
- [ ] 최종 UI 다듬기

### Quality Gate
- [ ] 모든 CRUD 테스트 통과
- [ ] 계산기 정확성 검증
- [ ] 이력 데이터 정상 표시
- [ ] 포트폴리오 수정 후 DB 반영 확인

### Rollback
- 관련 API 라우터 제거
- 컴포넌트 파일 삭제

---

## Risk Assessment

| 리스크 | 확률 | 영향 | 완화 전략 |
|--------|------|------|-----------|
| iOS 푸시 제한 | 높음 | 중간 | iOS 17+ 필요, 사용자 안내 |
| 서버 OOM | 중간 | 높음 | 메모리 모니터링, 제한 유지 |
| SvelteKit 학습곡선 | 낮음 | 낮음 | 공식 문서 참조 |
| VAPID 키 관리 | 낮음 | 중간 | 환경변수로 안전 보관 |

---

## 폴더 구조 (예상)

```
~/dailystockstory/
├── api/                    # FastAPI 백엔드
│   ├── main.py
│   ├── routers/
│   │   ├── briefing.py
│   │   ├── portfolio.py
│   │   ├── recommendations.py
│   │   ├── regsho.py
│   │   ├── blog.py
│   │   ├── notes.py
│   │   ├── push.py
│   │   └── calculator.py
│   ├── models/
│   ├── services/
│   └── tests/
├── web/                    # SvelteKit 프론트엔드
│   ├── src/
│   │   ├── routes/
│   │   │   ├── +layout.svelte
│   │   │   ├── +page.svelte        # 대시보드
│   │   │   ├── login/
│   │   │   ├── history/
│   │   │   └── settings/
│   │   ├── lib/
│   │   │   ├── components/
│   │   │   └── stores/
│   │   └── service-worker.ts
│   ├── static/
│   │   ├── manifest.json
│   │   └── icons/
│   └── tests/
├── docs/plans/             # 이 파일
├── thoughts/shared/specs/  # 스펙
├── stock_collector.py      # 기존 수집기
├── read_briefing.py        # 기존 브리핑 (참조용)
└── CLAUDE.md
```

---

## Notes & Learnings

_각 Phase 완료 후 학습 내용 기록_

### Phase 1
-

### Phase 2
-

### Phase 3
-

### Phase 4
-

### Phase 5
-

### Phase 6
-

---

*계획 작성: 2026-01-24*
*Based on: Discovery Interview + Spec*
