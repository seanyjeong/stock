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
│   └── trades.py            # 거래 API
├── web/                      # 프론트엔드 (SvelteKit)
│   ├── src/
│   │   ├── routes/          # 페이지
│   │   └── lib/             # 컴포넌트
│   └── package.json
├── stock_collector.py        # 데이터 수집 (cron)
├── day_trader_scanner.py     # 단타 추천
├── swing_long_scanner.py     # 스윙/장기 추천
├── .env                      # 환경 변수
├── CLAUDE.md                 # Claude 설정
├── HANDOFF.md                # 작업 인수인계
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
| GET | `/api/recommendations` | 추천 종목 |
| GET | `/api/blog` | 블로그 포스트 |
| GET | `/api/announcements/` | 공지사항 |

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

## 현재 버전
- **프론트엔드**: v1.9.2
- **문서 업데이트**: 2026-01-25
