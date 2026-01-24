# PRD: Daily Stock Story 웹앱

**Product Requirements Document**

| 항목 | 내용 |
|------|------|
| **제품명** | Daily Stock Story |
| **버전** | 1.0 |
| **작성일** | 2026-01-24 |
| **상태** | Draft |

---

## 1. 개요

### 1.1 제품 요약
개인용 주식 대시보드 PWA. 포트폴리오 현황, 단타/스윙/장기 추천, RegSHO 모니터링, 블로거 인사이트를 한 화면에서 확인하고, 정기 푸시 알림으로 중요 정보를 받는다.

### 1.2 목표
1. 아침에 눈 뜨면 푸시 알림으로 브리핑 확인 (< 3초)
2. 어디서든 모바일/PC로 대시보드 접근
3. 매매 결정에 필요한 모든 정보를 한 화면에
4. 익절 시 세금 계산 즉시 확인
5. 추천 종목 성과 추적 및 관심 종목 관리

### 1.3 대상 사용자
- **Sean** - 개인 투자자 (단일 사용자)
- 미국 주식 투자 (나노캡, 숏스퀴즈 중심)
- 모바일 + PC 동시 사용

---

## 2. 기술 스택

| Layer | Technology | 비고 |
|-------|------------|------|
| Frontend | SvelteKit | 가볍고 빠름 |
| Backend | FastAPI (Python) | 기존 수집기와 통합 |
| Database | PostgreSQL | 기존 DB 활용 |
| Hosting | Caddy + systemd | 현재 서버 |
| Push | Web Push API | pywebpush |

### 도메인
| 용도 | URL |
|------|-----|
| 프론트엔드 | https://stock.sean8320.dedyn.io |
| 백엔드 API | https://stock-api.sean8320.dedyn.io |

---

## 3. 기능 요구사항

### 3.1 P0 (Must Have) - MVP

#### 3.1.1 통합 대시보드
| 기능 | 설명 | 수락 기준 |
|------|------|-----------|
| 포트폴리오 현황 | 종목별 수익률, 평가금액, 총 수익 | 실시간 데이터 표시 |
| 환율 표시 | USD/KRW 환율 | 최신 환율 반영 |
| 세금 계산 | 22% 양도세 자동 계산 | 250만원 공제 적용 |
| 추천 섹션 | 단타/스윙/장기 탭 UI | 각 3종목씩 표시 |
| RegSHO 상태 | 보유 종목 등재 여부 | 배지로 표시 |
| 블로거 인사이트 | 최근 5개 + 원문 링크 | 티커/키워드 태그 |

#### 3.1.2 인증
| 기능 | 설명 | 수락 기준 |
|------|------|-----------|
| PIN 인증 | 4자리 숫자 | 로컬 해시 저장 |
| 세션 유지 | 24시간 | 자동 로그아웃 |

#### 3.1.3 PWA
| 기능 | 설명 | 수락 기준 |
|------|------|-----------|
| 설치 | 홈 화면 추가 | iOS + Android |
| 오프라인 | 마지막 브리핑 캐시 | 네트워크 없어도 표시 |

### 3.2 P1 (Should Have)

#### 3.2.1 푸시 알림
| 기능 | 설명 | 수락 기준 |
|------|------|-----------|
| 정기 브리핑 | 09:00, 18:00, 21:00 KST | 정시 발송 |
| RegSHO 변동 | 보유 종목 등재/해제 | 즉시 발송 |
| 알림 설정 | 시간 조정 가능 | 설정 페이지 |

#### 3.2.2 포트폴리오 관리
| 기능 | 설명 | 수락 기준 |
|------|------|-----------|
| CRUD | 종목 추가/수정/삭제 | UI에서 직접 |
| 동기화 | portfolio.md 연동 | 양방향 (선택) |
| 매매 이력 | 매수/매도 기록 | DB 저장 |

#### 3.2.3 종목 메모
| 기능 | 설명 | 수락 기준 |
|------|------|-----------|
| CRUD | 종목별 노트 | 마크다운 지원 |

### 3.3 P2 (Nice to Have)

#### 3.3.1 관심 종목 (Watchlist)
| 기능 | 설명 | 수락 기준 |
|------|------|-----------|
| 관심 추가 | 추천 종목 클릭 → ⭐ | DB 저장 |
| 관심 해제 | 기록 유지, 목록에서만 제거 | is_active=false |
| 브리핑 포함 | 관심 종목 별도 섹션 | 매일 브리핑 |

#### 3.3.2 추천 성과 추적
| 기능 | 설명 | 수락 기준 |
|------|------|-----------|
| 히스토리 저장 | 모든 추천 DB 저장 | recommendation_history |
| 성과 계산 | 추천 후 최고가/최저가 | 자동 업데이트 |
| 승률 표시 | 스캐너별 성공률 | 통계 UI |

#### 3.3.3 익절 계산기
| 기능 | 설명 | 수락 기준 |
|------|------|-----------|
| 세금 계산 | 목표가 → 예상 수익/세금 | 22% 적용 |
| 분할 매도 | 시뮬레이션 | 여러 시나리오 |

#### 3.3.4 이력 조회
| 기능 | 설명 | 수락 기준 |
|------|------|-----------|
| 날짜별 브리핑 | 과거 브리핑 조회 | 캘린더 UI |

---

## 4. API 명세

### 4.1 엔드포인트

```
# 브리핑 & 데이터
GET  /api/health                # 헬스체크
GET  /api/briefing              # 오늘의 브리핑
GET  /api/portfolio             # 포트폴리오 현황
PUT  /api/portfolio/{ticker}    # 포트폴리오 수정
POST /api/portfolio             # 포트폴리오 추가
DELETE /api/portfolio/{ticker}  # 포트폴리오 삭제

# 추천
GET  /api/recommendations       # 추천 종목 (단타/스윙/장기)
GET  /api/recommendations/history  # 추천 히스토리

# RegSHO & 블로그
GET  /api/regsho                # RegSHO 목록
GET  /api/blog-posts            # 블로거 인사이트

# 관심 종목
GET  /api/watchlist             # 관심 목록
POST /api/watchlist/{ticker}    # 관심 추가
DELETE /api/watchlist/{ticker}  # 관심 해제

# 메모
GET  /api/notes/{ticker}        # 메모 조회
POST /api/notes                 # 메모 생성
PUT  /api/notes/{id}            # 메모 수정
DELETE /api/notes/{id}          # 메모 삭제

# 푸시 알림
POST /api/push/subscribe        # 푸시 구독
DELETE /api/push/subscribe      # 푸시 해제

# 유틸리티
GET  /api/calculator            # 익절 계산
GET  /api/history/{date}        # 히스토리 조회
```

### 4.2 응답 예시

**GET /api/briefing**
```json
{
  "updated_at": "2026-01-24T16:38:00+09:00",
  "portfolio": {
    "items": [
      {
        "ticker": "BNAI",
        "quantity": 464,
        "avg_price": 9.55,
        "current_price": 58.54,
        "gain_pct": 513.0,
        "gain_usd": 22731,
        "is_regsho": true
      }
    ],
    "total_value_usd": 28905,
    "total_value_krw": 41911622,
    "total_gain_pct": 372,
    "exchange_rate": 1450.00,
    "tax_estimate_krw": 6717977
  },
  "recommendations": {
    "day_trade": [...],
    "swing": [...],
    "long_term": [...]
  },
  "watchlist": [...],
  "regsho": {
    "held_tickers": ["BNAI"],
    "total_count": 57
  },
  "blog_posts": [...],
  "system_alerts": [...]
}
```

---

## 5. 데이터 모델

### 5.1 신규 테이블

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

-- 추천 히스토리
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

### 5.2 기존 테이블 (참조)
- `stock_briefing` - 브리핑 캐시
- `stock_prices` - 주가
- `day_trade_recommendations` - 단타 추천
- `swing_recommendations` - 스윙 추천
- `longterm_recommendations` - 장기 추천
- `regSHO_list` - RegSHO 목록
- `blog_posts` - 블로그 포스트

---

## 6. UI/UX 디자인

### 6.1 디자인 시스템

| 항목 | 값 |
|------|-----|
| 테마 | 다크 모드 (OLED) |
| 배경색 | #0d1117 |
| 수익 색상 | #3fb950 |
| 손실 색상 | #f85149 |
| 강조 색상 | #58a6ff |
| 폰트 | System UI |

### 6.2 모바일 레이아웃

```
┌─────────────────────────┐
│ 📊 Daily Stock Story    │ ← 헤더
├─────────────────────────┤
│ 💰 Portfolio            │
│ BNAI +513% ⭐ | GLSI +3%│ ← 관심 표시
│ Total: ₩41,911,622      │
├─────────────────────────┤
│ ⭐ Watchlist (2)        │ ← 관심 종목 섹션
│ • BNAI $58.54 +5%       │
│ • AMC $1.59 -2%         │
├─────────────────────────┤
│ 🎯 Today's Picks        │
│ [단타] [스윙] [장기]     │
│ • BNAI $58.54 ⭐        │ ← 클릭하면 관심 추가
│ • AMC $1.59             │
├─────────────────────────┤
│ 📋 RegSHO: BNAI ✅      │
├─────────────────────────┤
│ 📝 Blog Insights        │
│ • BNAI 숏스퀴즈 →       │
└─────────────────────────┘
│ [홈] [관심] [이력] [설정]│ ← 네비게이션
└─────────────────────────┘
```

---

## 7. 비기능 요구사항

| 항목 | 요구사항 |
|------|----------|
| 초기 로딩 | < 2초 |
| API 응답 | < 500ms |
| 가용성 | 99% |
| 오프라인 | 마지막 브리핑 캐시 |
| 브라우저 | Chrome, Safari |

---

## 8. 보안

| 항목 | 방안 |
|------|------|
| 인증 | PIN 4자리 (로컬 해시) |
| 전송 | HTTPS (Caddy TLS) |
| 세션 | 24시간 만료 |
| 데이터 | 개인용 (낮은 위험) |

---

## 9. 구현 일정

| Phase | 목표 | 예상 |
|-------|------|------|
| 1 | 프로젝트 셋업 | Day 1 |
| 2 | API 구현 | Day 2-3 |
| 3 | 프론트엔드 UI | Day 4-5 |
| 4 | PWA + 인증 | Day 6 |
| 5 | 푸시 알림 | Day 7 |
| 6 | 부가 기능 | Day 8-9 |

**상세 계획:** `docs/plans/PLAN_daily-stock-story-webapp.md`

---

## 10. 범위 외 (Out of Scope)

- 자동 매매 기능
- 실시간 차트 (외부 링크로 대체)
- 다중 사용자 지원
- 증권사 API 연동
- 알림 사운드 커스터마이징

---

## 11. 리스크

| 리스크 | 확률 | 영향 | 완화 |
|--------|------|------|------|
| iOS 푸시 제한 | 높음 | 중간 | iOS 17+ 필요, 안내 |
| 서버 OOM | 중간 | 높음 | 메모리 제한 유지 |
| VAPID 키 관리 | 낮음 | 중간 | 환경변수 보관 |

---

## 12. 참조 문서

- **스펙:** `thoughts/shared/specs/2026-01-24-daily-stock-story-webapp.md`
- **구현 계획:** `docs/plans/PLAN_daily-stock-story-webapp.md`
- **기존 브리핑:** `read_briefing.py`

---

*PRD 작성: 2026-01-24*
*Status: Ready for Implementation*
