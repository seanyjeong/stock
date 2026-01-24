# 달러농장 핸드오프

**작성일**: 2026-01-24
**버전**: v1.4.0

---

## 다음 세션에서 할 일

### 1. 종목 상세 페이지 (`/stock/[ticker]`)
- 캔들스틱 차트 (lightweight-charts)
- RSI/MACD 지표 표시
- `/api/indicators/{ticker}` API 활용

### 2. 용어 설명 컴포넌트 (Tooltip)
```svelte
<span>RSI <Tooltip text="RSI 70↑ 과매수, 30↓ 과매도" /></span>
```
- 작은 (?) 아이콘, 호버/클릭 시 설명

### 3. 차트 라이브러리 설치
```bash
cd web && npm install lightweight-charts
```

---

## 이번 세션 완료

1. **알림 페이지 수정** - 아이콘 + VAPID 설명 제거
2. **테스트 데이터 정리** - BNAI 474→464주
3. **관심 종목 실시간 현재가** - yfinance 조회
4. **기술적 지표 API** - RSI/MACD (`/api/indicators/{ticker}`)

---

## 배포 현황

| 항목 | URL |
|------|-----|
| GitHub | https://github.com/seanyjeong/stock |
| Vercel | https://stock-six-phi.vercel.app |
| API | https://stock-api.sean8320.dedyn.io |

---

## 환경변수 (.env)

```
DATABASE_URL=postgresql://claude:claude_dev@localhost:5432/continuous_claude
JWT_SECRET=***REMOVED***
KAKAO_REST_API_KEY=***REMOVED***
KAKAO_REDIRECT_URI=https://stock-six-phi.vercel.app/login
KAKAO_CLIENT_SECRET=***REMOVED***
VAPID_PUBLIC_KEY=***REMOVED***
VAPID_PRIVATE_KEY=***REMOVED***
VAPID_EMAIL=mailto:sean8320@gmail.com
```

---

## API 엔드포인트

| 엔드포인트 | 설명 |
|-----------|------|
| `/api/indicators/{ticker}` | RSI, MACD 기술적 지표 |
| `/api/watchlist/` | 관심 종목 (현재가 포함) |
| `/api/portfolio/my` | 내 포트폴리오 |
| `/api/notifications/*` | 푸시 알림 |
| `/api/blog` | 블로거 인사이트 |

---

## 파일 구조

```
api/
├── main.py
├── auth.py          # 카카오 로그인
├── portfolio.py     # 포트폴리오 CRUD
├── trades.py        # 매매 기록
├── watchlist.py     # 관심 종목 + 실시간 현재가
├── notifications.py # 푸시 알림
├── announcements.py # 공지사항
└── indicators.py    # RSI/MACD (신규)

web/src/
├── lib/components/
│   └── Icons.svelte # SVG 아이콘
└── routes/
    ├── +page.svelte     # 대시보드
    ├── portfolio/
    ├── watchlist/
    ├── history/
    ├── calculator/
    ├── notifications/
    └── settings/
```

---

## 커밋 히스토리

```
0556d22 feat: 기술적 지표 API 추가 (RSI, MACD)
d8dc431 feat: 관심 종목 실시간 현재가 조회
d77e889 fix: 알림 페이지 아이콘 및 안내 문구 수정
46a6e5e feat: 달러농장 v1.3.0 - UI 개선 및 푸시 알림
```

---

*Handoff: 2026-01-24*
