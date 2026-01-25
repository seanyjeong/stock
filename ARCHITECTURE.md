# Daily Stock Story - 시스템 아키텍처

## 기술 스택

| 구분 | 기술 | 버전 |
|------|------|------|
| **프론트엔드** | SvelteKit | 2.x |
| **UI 프레임워크** | Svelte 5 | 5.x |
| **차트** | Lightweight Charts | 5.x |
| **백엔드** | FastAPI (Python) | - |
| **런타임** | uv + uvicorn | - |
| **데이터베이스** | PostgreSQL | 14+ |
| **웹서버** | Caddy | 2.x |
| **프로세스 관리** | systemd | - |
| **프론트 배포** | Vercel | - |
| **인증** | 카카오 OAuth | - |
| **AI** | Gemini 2.0 Flash | google-genai |

---

## 인프라 구성

### 서버 정보
- **호스트**: Intel N100, 16GB RAM, 512GB SSD
- **OS**: Ubuntu Linux
- **도메인**: sean8320.dedyn.io (DeDyn DDNS)

### 도메인 매핑
| 서브도메인 | 용도 | 포트 |
|------------|------|------|
| `stock.sean8320.dedyn.io` | 프론트엔드 (Vercel) | - |
| `stock-api.sean8320.dedyn.io` | 백엔드 API | 8340 |

### Caddy 설정 (`/etc/caddy/Caddyfile`)
```
stock.sean8320.dedyn.io {
    reverse_proxy localhost:3000
}
stock-api.sean8320.dedyn.io {
    reverse_proxy localhost:8340
}
```

### Systemd 서비스 (`/etc/systemd/system/stock-api.service`)
```ini
[Unit]
Description=Daily Stock Story API
After=network.target

[Service]
Type=simple
User=sean
WorkingDirectory=/home/sean/dailystockstory
EnvironmentFile=/home/sean/dailystockstory/.env
ExecStart=/home/sean/.local/bin/uv run uvicorn api.main:app --host 0.0.0.0 --port 8340
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**관리 명령:**
```bash
sudo systemctl restart stock-api   # 재시작
sudo systemctl status stock-api    # 상태 확인
sudo journalctl -u stock-api -f    # 로그 확인
```

---

## 디렉토리 구조

```
~/dailystockstory/
├── api/                      # 백엔드 API
│   ├── main.py              # FastAPI 메인
│   ├── auth.py              # 인증 (카카오 OAuth)
│   ├── profile.py           # 투자성향 프로필 API
│   ├── realtime.py          # 실시간 가격 (Finnhub polling)
│   └── trades.py            # 거래 API
├── scanners/                 # 스캐너 시스템 (v2)
│   ├── news_collector.py    # 뉴스 수집 (SEC/Finviz/Yahoo)
│   └── full_market_scanner.py # 시장 스캔 + Gemini AI
├── web/                      # 프론트엔드 (SvelteKit)
│   ├── src/
│   │   ├── routes/          # 페이지
│   │   └── lib/
│   │       └── components/
│   │           ├── ProfileRecommendations.svelte  # 맞춤 추천
│   │           └── RecommendationModal.svelte     # 상세 분석 모달
│   └── package.json
├── stock_collector.py        # 데이터 수집 (cron)
├── .env                      # 환경 변수 (GEMINI_API_KEY 포함)
├── CLAUDE.md                 # Claude 설정
├── HANDOFF_v2.md             # 작업 인수인계
└── ARCHITECTURE.md           # 이 문서
```

---

## 데이터베이스 스키마

**DB 정보:**
- Host: `localhost:5432`
- Database: `continuous_claude`
- User: `claude`

### 사용자 관련

#### users
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| kakao_id | bigint | 카카오 고유 ID |
| nickname | varchar | 닉네임 |
| email | varchar | 이메일 |
| profile_image | text | 프로필 이미지 URL |
| is_approved | boolean | 승인 여부 |
| is_admin | boolean | 관리자 여부 |
| created_at | timestamp | 가입일 |
| last_login | timestamp | 마지막 로그인 |

#### user_holdings
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| user_id | integer | FK → users |
| ticker | varchar | 종목 티커 |
| shares | numeric | 보유 수량 |
| avg_cost | numeric | 평균 매수가 |
| created_at | timestamp | 생성일 |
| updated_at | timestamp | 수정일 |

#### trades
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| user_id | integer | FK → users |
| ticker | varchar | 종목 티커 |
| trade_type | varchar | buy/sell |
| shares | numeric | 거래 수량 |
| price | numeric | 거래 단가 |
| total_amount | numeric | 총 금액 |
| note | text | 메모 |
| traded_at | timestamp | 거래일시 |

#### user_watchlist
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| user_id | integer | FK → users |
| ticker | varchar | 종목 티커 |
| note | text | 메모 |
| target_price | numeric | 목표가 |
| alert_price | numeric | 알림가 |
| folder_id | integer | FK → watchlist_folders (nullable) |

#### watchlist_folders
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| user_id | integer | FK → users |
| name | varchar(50) | 폴더명 (UNIQUE per user) |
| color | varchar(7) | HEX 색상 (#3b82f6) |
| is_default | boolean | 기본 폴더 여부 (삭제 불가) |
| sort_order | integer | 정렬 순서 |

#### user_profiles
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| user_id | integer | FK → users (UNIQUE) |
| experience | varchar(20) | 투자 경험 (under_1y, 1_3y, over_3y) |
| risk_tolerance | varchar(20) | 손실 허용 (under_5, under_10, under_20, over_20) |
| duration_preference | varchar(20) | 기간 선호 (day, swing, long, mixed) |
| profit_expectation | varchar(20) | 수익 기대 (stable, moderate, aggressive) |
| sectors | text[] | 관심 섹터 배열 |
| profile_type | varchar(20) | 계산된 성향 (conservative, balanced, aggressive) |
| created_at | timestamp | 생성일 |
| updated_at | timestamp | 수정일 |

### 주식 데이터

#### stock_prices
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| ticker | varchar | 종목 티커 |
| regular_price | numeric | 정규장 가격 |
| afterhours_price | numeric | 애프터 가격 |
| premarket_price | numeric | 프리마켓 가격 |
| change_percent | numeric | 변동률 |
| source | varchar | 데이터 소스 |
| collected_at | timestamp | 수집일시 |

#### regsho_list
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| ticker | varchar | 종목 티커 |
| security_name | text | 종목명 |
| market_category | varchar | 시장 구분 |
| collected_date | date | 수집일 |
| first_seen_date | date | 최초 등재일 |

#### squeeze_data
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| ticker | varchar | 종목 티커 |
| borrow_rate | numeric | 대차이자 (%) |
| short_interest | numeric | 공매도 비율 (%) |
| days_to_cover | numeric | DTC |
| available_shares | bigint | 대차 가능 수량 |
| float_shares | bigint | 유통주식수 |
| squeeze_score | numeric | 스퀴즈 점수 |
| dilution_protected | boolean | 희석 방어 여부 |
| has_positive_news | boolean | 호재 여부 |
| has_negative_news | boolean | 악재 여부 |

#### exchange_rates
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| from_currency | varchar | 원화 |
| to_currency | varchar | 달러 |
| rate | numeric | 환율 |
| collected_at | timestamp | 수집일시 |

### 추천/콘텐츠

#### day_trade_recommendations
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| recommendations | jsonb | 추천 데이터 |
| created_at | timestamp | 생성일 |

#### swing_recommendations
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| recommendations | jsonb | 추천 데이터 |
| created_at | timestamp | 생성일 |

#### longterm_recommendations
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| recommendations | jsonb | 추천 데이터 |
| created_at | timestamp | 생성일 |

#### blog_posts
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| post_id | varchar | 블로그 포스트 ID |
| title | text | 제목 |
| content | text | 내용 |
| tickers | array | 언급된 티커 |
| keywords | array | 키워드 |
| url | text | 원본 URL |
| is_new | boolean | 신규 여부 |

#### announcements
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| title | varchar | 제목 |
| content | text | 내용 |
| is_important | boolean | 중요 공지 여부 |
| is_active | boolean | 활성 여부 |
| created_by | integer | FK → users |

### 스캐너 시스템 (v2)

#### news_mentions
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| ticker | varchar | 종목 티커 |
| source | varchar | 소스 (SEC, Finviz, Yahoo) |
| headline | text | 헤드라인 |
| url | text | URL |
| sentiment | varchar | 감성 (positive, negative, neutral) |
| weight | integer | 가중치 |
| collected_at | timestamp | 수집일시 |

#### daily_news_scores
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| scan_date | date | 스캔 날짜 (UNIQUE) |
| ticker | varchar | 종목 티커 |
| total_score | numeric | 뉴스 총점 |
| positive_count | integer | 긍정 뉴스 수 |
| negative_count | integer | 부정 뉴스 수 |

#### daily_scan_results
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| scan_date | date | 스캔 날짜 (UNIQUE) |
| results | jsonb | 스캔 결과 (모든 성향 점수 + AI 분석 포함) |
| created_at | timestamp | 생성일 |

**results JSONB 구조:**
```json
{
  "ticker": "BNAI",
  "current_price": 58.54,
  "day_trade_score": 75.0,
  "swing_score": 50.0,
  "longterm_score": 20.0,
  "entry_aggressive": 59.71,
  "entry_balanced": 42.27,
  "entry_conservative": 25.73,
  "recommendation_reason": "RSI 32로 과매도 구간...",
  "rating": "★★★",
  "rr_ratio": 1.75,
  "split_entries": [
    {"price": 58.54, "pct": 40, "label": "현재가"},
    {"price": 52.00, "pct": 30, "label": "1차 지지"},
    {"price": 46.00, "pct": 30, "label": "강한 지지"}
  ]
}
```

### 알림

#### notification_settings
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| user_id | integer | FK → users |
| data_update_alerts | boolean | 데이터 업데이트 알림 |
| price_alerts | boolean | 가격 알림 |
| regsho_alerts | boolean | RegSHO 알림 |
| blog_alerts | boolean | 블로그 알림 |

#### push_subscriptions
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | integer | PK |
| user_id | integer | FK → users |
| endpoint | text | Push 엔드포인트 |
| p256dh | text | 암호화 키 |
| auth | text | 인증 키 |

---

## API 엔드포인트

### 인증
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/auth/kakao` | 카카오 로그인 시작 |
| GET | `/api/auth/kakao/callback` | 카카오 콜백 |
| GET | `/api/auth/me` | 현재 사용자 정보 |

### 투자성향 프로필
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/profile/check` | 프로필 존재 여부 확인 |
| GET | `/api/profile/` | 프로필 조회 |
| POST | `/api/profile/` | 프로필 생성 (최초 설문) |
| PUT | `/api/profile/` | 프로필 수정 (다시하기) |

### 포트폴리오
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/portfolio/my` | 내 포트폴리오 |
| GET | `/api/portfolio/search` | 종목 검색 |

### 거래
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/trades/` | 거래 이력 |
| POST | `/api/trades/` | 거래 등록 |
| DELETE | `/api/trades/{id}` | 거래 삭제 |

### 데이터
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/regsho` | RegSHO 목록 |
| GET | `/api/squeeze` | 스퀴즈 분석 |
| GET | `/api/recommendations` | 추천 종목 (all_recommendations: 단타/스윙/장기) |
| GET | `/api/blog` | 블로그 포스트 |
| GET | `/api/announcements/` | 공지사항 |
| POST | `/api/announcements/draft` | **AI 공지사항 초안** (Gemini, 관리자) |

### 실시간 가격 (하이브리드)
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/realtime/hybrid?tickers=AAPL,TSLA` | **하이브리드 가격** (정규장: Finnhub, 장외: yfinance) |
| GET | `/realtime/prices?tickers=AAPL,TSLA` | Finnhub 전용 (10초 캐싱) |
| GET | `/realtime/quote/{ticker}` | 단일 종목 시세 |
| GET | `/realtime/market-status` | 현재 시장 상태 (정규/프리/애프터/마감) |
| GET | `/realtime/dst-status` | 섬머타임 상태 + 전환 7일전 경고 |

> **하이브리드 로직:**
> - 정규장 (KST 23:30~06:00): Finnhub 실시간 (10초 캐싱)
> - 장외 (프리/애프터/마감): yfinance (60초 캐싱)
> - 주말/마감 시 애프터마켓 가격 우선 사용

### 관심종목
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/watchlist/` | 관심 종목 목록 (폴더 정보 포함) |
| POST | `/api/watchlist/` | 관심 종목 추가 (folder_id 옵션) |
| PUT | `/api/watchlist/{id}` | 관심 종목 수정 |
| DELETE | `/api/watchlist/{id}` | 관심 종목 삭제 |
| PUT | `/api/watchlist/{id}/folder` | 종목 폴더 이동 |
| GET | `/api/watchlist/folders` | 폴더 목록 조회 |
| POST | `/api/watchlist/folders` | 폴더 생성 |
| PUT | `/api/watchlist/folders/{id}` | 폴더 수정 |
| DELETE | `/api/watchlist/folders/{id}` | 폴더 삭제 (기본폴더 제외) |

### 알림
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/notifications/settings` | 알림 설정 조회 |
| PUT | `/api/notifications/settings` | 알림 설정 변경 |
| POST | `/api/notifications/subscribe` | 푸시 구독 |

---

## Cron 작업

```bash
# 데이터 수집 (매일 09:00 KST)
0 9 * * * cd ~/dailystockstory && uv run python stock_collector.py

# 단타 추천 (22:00 KST, 월-금)
0 22 * * 1-5 cd ~/dailystockstory && uv run python day_trader_scanner.py

# 스윙/장기 추천 (10:00 KST, 화-토)
0 10 * * 2-6 cd ~/dailystockstory && uv run python swing_long_scanner.py
```

---

## 환경 변수 (.env)

```bash
DATABASE_URL=postgresql://claude:***@localhost:5432/continuous_claude
KAKAO_CLIENT_ID=***
KAKAO_CLIENT_SECRET=***
JWT_SECRET=***
VAPID_PRIVATE_KEY=***
VAPID_PUBLIC_KEY=***
```

---

## 배포 프로세스

### 프론트엔드 (Vercel)
```bash
git push  # GitHub → Vercel 자동 배포
```

### 백엔드
```bash
git pull
sudo systemctl restart stock-api
```

### 버전 업데이트
1. `web/package.json` - version 변경
2. `web/src/routes/settings/+page.svelte` - 표시 버전
3. `git commit -m "chore: vX.X.X"`

---

## 스퀴즈 점수 계산 로직

```
총점 = Base Score + Bonuses - Penalties (최대 100점)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Base Score (0-60점)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
├─ Short Interest (0-25점)
│   └─ 50%+ = 25점, 비례 계산
├─ Borrow Rate (0-20점)
│   └─ 200%+ = 20점, 비례 계산
└─ Days to Cover (0-15점)
    └─ 10일+ = 15점, 비례 계산

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Squeeze Pressure Bonus (0-25점)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
├─ Zero Borrow (대차 불가): +10점
├─ Low Float (<10M): +5점
└─ Dilution Protected (워런트/약정): +10점

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Catalyst Bonus (0-10점)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
└─ Positive News (SEC 호재 50건+): +10점

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Risk Penalty (-15점)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
└─ Negative News (SEC 악재 20건+): -15점

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Urgency Bonus (0-15점)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
├─ Borrow Rate > 300%: +10점
└─ Short Interest > 40%: +5점

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
등급 분류
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOT   : 60점 이상 (빨강)
WATCH : 40-59점 (주황)
COLD  : 40점 미만 (회색)
```

---

## 프론트엔드 컴포넌트 구조

```
web/src/
├── routes/                     # 페이지 (SvelteKit 라우팅)
│   ├── +layout.svelte         # 공통 레이아웃 (네비게이션)
│   ├── +page.svelte           # 홈 (포트폴리오, RegSHO Top5)
│   ├── +page.server.ts        # 서버사이드 데이터 로드
│   ├── login/+page.svelte     # 카카오 로그인
│   ├── portfolio/+page.svelte # 포트폴리오 관리
│   ├── history/+page.svelte   # 거래 이력
│   ├── squeeze/+page.svelte   # 스퀴즈 분석 (전체)
│   ├── stock/[ticker]/        # 종목 상세 + 관심종목 추가 버튼
│   ├── watchlist/+page.svelte # 관심 종목 (폴더별 관리)
│   ├── calculator/+page.svelte# 세금 계산기
│   ├── settings/+page.svelte  # 설정 (버전 표시)
│   ├── notifications/         # 알림 설정
│   ├── admin/+page.svelte     # 관리자 (공지 관리)
│   └── onboarding/            # 온보딩 (승인 대기)
│
├── lib/
│   ├── components/            # 재사용 컴포넌트
│   │   ├── Icons.svelte       # 아이콘 (Lucide)
│   │   ├── BottomNav.svelte   # 하단 네비게이션 (6개: 홈/포폴/이력/스퀴즈/관심/설정)
│   │   ├── RegSHOBadge.svelte # RegSHO 뱃지
│   │   ├── ProfileRecommendations.svelte # 맞춤 추천 + 관심종목 추가
│   │   └── RecommendationModal.svelte # 추천 상세 모달 + 관심종목 추가
│   ├── types.ts               # TypeScript 타입 정의
│   └── api.ts                 # API 헬퍼 함수
│
└── app.html                   # HTML 템플릿
```

### 주요 컴포넌트 역할

| 컴포넌트 | 역할 |
|----------|------|
| `+layout.svelte` | 네비게이션, 공통 스타일, 인증 체크 |
| `Icons.svelte` | Lucide 아이콘 래퍼 (chart, wallet, fire 등) |
| `RegSHOBadge.svelte` | RegSHO 등재 여부 뱃지 |
| `RecommendationTabs.svelte` | 단타/스윙/장기 탭 전환 |

---

## 에러 처리 / 예외 케이스

### API 에러 처리
```python
# api/main.py
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
```

### 프론트엔드 에러 처리
```typescript
// 401 Unauthorized → 로그인 페이지로 리다이렉트
if (response.status === 401) {
    localStorage.removeItem('access_token');
    goto('/login');
}

// API 실패 → 에러 메시지 표시
if (!response.ok) {
    error = '데이터를 불러올 수 없습니다';
}
```

### 예외 케이스 처리

| 케이스 | 처리 |
|--------|------|
| 토큰 만료 | 401 → 자동 로그아웃 → 로그인 페이지 |
| API 서버 다운 | 로딩 실패 메시지 + 재시도 버튼 |
| 승인 대기 유저 | 온보딩 페이지로 리다이렉트 |
| 데이터 없음 | "보유 종목이 없습니다" 안내 |
| 네트워크 오류 | try/catch → 에러 상태 표시 |
| 잘못된 티커 | 404 → "종목을 찾을 수 없습니다" |

### 데이터 수집 예외
```python
# stock_collector.py
try:
    ticker = yf.Ticker(symbol)
    info = ticker.info
except Exception as e:
    logger.error(f"Failed to fetch {symbol}: {e}")
    continue  # 다음 종목으로 건너뛰기
```

---

## CLI 분석 도구

### deep_analyzer.py (v4) - 나스닥의 신 에디션 🔥
**초정밀 주식 분석기** - 숏스퀴즈 + 섹터별 특화 + Gemini AI

```bash
# 사용법
uv run python deep_analyzer.py BNAI          # AI 분석 포함
uv run python deep_analyzer.py BNAI --no-ai  # AI 스킵 (빠름)
uv run python deep_analyzer.py GLSI --normal # 일반 분석 모드 강제
```

**v4 신규 기능:**
| 기능 | 설명 |
|------|------|
| **섹터별 뉴스** | Biotech/AI·Tech/에너지/일반 자동 분류 |
| **바이오텍 촉매** | FDA Fast Track/Breakthrough, ClinicalTrials.gov 연동 |
| **8-K 이벤트 파싱** | FDA 승인, 임상결과, 계약, 유증 등 자동 분류 |
| **뉴스 필터** | 최근 60일 기사만 (구글뉴스 백업) |

**분석 항목:**
| 구분 | 항목 |
|------|------|
| **기본** | 회사 개요, 가격, 시가총액, Float |
| **숏 데이터** | Zero Borrow, Short %, Borrow Rate, DTC |
| **기술적** | RSI, MACD, 볼린저, ATR |
| **SEC** | 워런트/희석/Covenant/빚/락업 키워드 검색 |
| **FTD** | Failure to Deliver 추이 |
| **옵션** | 콜/풋 OI, Max Pain, 감마 집중 |
| **소셜** | Stocktwits + Reddit + Finviz 센티먼트 |
| **피보나치** | 지지/저항선, 미충전 갭 |
| **볼륨 프로파일** | POC, Value Area |
| **다크풀** | 숏 볼륨, 장외거래 비율 |
| **SEC Filing** | S-1/S-4/DEFM14A 파싱, SPAC Earnout |
| **섹터 뉴스** | 바이오텍(FDA), AI/Tech, 에너지 특화 |
| **8-K 공시** | 주요 이벤트 자동 분류 |
| **임상시험** | ClinicalTrials.gov API (바이오텍) |
| **기관** | Top 5 기관 보유 |
| **동종업체** | 섹터 PE 비교 |
| **AI** | Gemini 종합 분석 (숏스퀴즈/일반 모드 자동 전환) |

**스퀴즈 점수 (0-100):**
- Zero Borrow: +30점
- Short % 높음: +15점
- Float 작음: +10점
- 내부자 보유 높음: +5점

---

## 현재 버전
- **프론트엔드**: v2.2.2
- **deep_analyzer**: v4 (나스닥의 신)
- **문서 업데이트**: 2026-01-25

## 변경 이력

### deep_analyzer v4 (2026-01-25)
- 섹터별 특화 뉴스 (바이오텍/AI·Tech/에너지/일반 자동 감지)
- 바이오텍 촉매 분석 (FDA Fast Track, ClinicalTrials.gov 연동)
- 8-K 주요 이벤트 파싱 (FDA 승인, 임상결과, 계약, 유증 자동 분류)
- 구글 뉴스 백업 + 최근 60일 필터
- google.genai 새 SDK 마이그레이션

### v2.2.2 (2026-01-25)
- 공지사항 팝업 모달 (24시간 숨기기)
- AI 공지사항 초안 (Gemini, SaaS 규칙)
- 주말/장마감 시 애프터마켓 가격 우선

### v2.2.0 (2026-01-25)
- 하이브리드 가격 API (Finnhub+yfinance)
- 섬머타임 상태 API + 전환 7일전 경고
- 시장 상태 태그 (🟢 실시간/🟡 PM/AH)
- 장기 점수 연속 체계 (score_breakdown)
- 스캐너 --type 옵션 (day/swing/long 분리)
- cron 분리: 단타 22:30, 스윙/장기 09:00 KST

### deep_analyzer v3 (2026-01-25)
- SPAC Earnout 조건 자동 추출 (S-4, DEFM14A)
- 락업 가격 추출 개선 (가격 기반 락업)
- google.genai 새 SDK 마이그레이션
- 한글화 완료 (강세/약세/혼조)

### v1.9.5 (2026-01-25)
- 투자성향 프로필 시스템 추가
  - 5개 설문 (경험, 리스크허용, 기간선호, 수익기대, 관심섹터)
  - 성향 자동 계산 (안정형/균형형/공격형)
  - 로그인 → 설문 → 승인대기 플로우
- user_profiles 테이블 추가
- /api/profile 엔드포인트 추가
- 설정 페이지에 투자성향 표시 및 다시하기 기능
