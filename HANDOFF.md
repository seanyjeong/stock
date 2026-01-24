# 달러농장 핸드오프

**작성일**: 2026-01-24
**버전**: v1.4.0

---

## 다음 세션에서 할 일

### 1. 캔들스틱 차트 안 나오는 문제
- API는 정상 (`/api/chart/BNAI` 데이터 잘 나옴)
- 프론트엔드 문제 - 브라우저 콘솔 확인 필요
- lightweight-charts import 또는 렌더링 타이밍 문제 가능성

### 2. 관리자 공지사항 작성 기능
- `/admin` 페이지에 공지사항 CRUD 추가
- API: `/api/announcements/` (이미 있음)
- 현재는 DB에서 직접 입력해야 함

### 3. 가격 알림 기능
- 관심종목 목표가/알림가 도달 시 푸시 알림
- 백엔드 스케줄러 필요 (cron 또는 별도 워커)
- `user_watchlist.target_price`, `alert_price` 활용

### 4. 더 나은 Tooltip 컴포넌트
- 현재 title 속성 사용 (기본 브라우저 툴팁)
- 커스텀 Tooltip 컴포넌트로 교체하면 더 예쁨

---

## 이번 세션 완료

1. **종목 상세 페이지** - `/stock/[ticker]` (캔들스틱 + RSI + MACD)
2. **차트 API** - `/api/chart/{ticker}` OHLCV 시계열
3. **관심종목 UI 개선** - 선택 시 현재가/지표 표시, 삭제 버튼 위치 수정
4. **홈 세후 금액 표시** - 총평가금 옆에 (세후 ₩XXX)
5. **RegSHO 더보기** - 접기/펼치기 버튼
6. **BNAI 평단 수정** - 9.55로 DB 업데이트
7. **git history 시크릿 제거** - force push 완료

---

## 배포 현황

| 항목 | URL |
|------|-----|
| GitHub | https://github.com/seanyjeong/stock |
| Vercel | https://stock-six-phi.vercel.app |
| API | https://stock-api.sean8320.dedyn.io |

---

## API 엔드포인트

| 엔드포인트 | 설명 |
|-----------|------|
| `/api/chart/{ticker}` | 캔들스틱 OHLCV + RSI/MACD 시계열 |
| `/api/indicators/{ticker}` | RSI, MACD 기술적 지표 요약 |
| `/api/watchlist/` | 관심 종목 (현재가 포함) |
| `/api/portfolio/my` | 내 포트폴리오 |
| `/api/notifications/*` | 푸시 알림 |
| `/api/announcements/` | 공지사항 |

---

## 파일 구조

```
api/
├── main.py
├── chart.py         # 캔들스틱 API (신규)
├── indicators.py    # RSI/MACD
├── auth.py          # 카카오 로그인
├── portfolio.py     # 포트폴리오 CRUD
├── watchlist.py     # 관심 종목
├── notifications.py # 푸시 알림
└── announcements.py # 공지사항

web/src/routes/
├── +page.svelte         # 대시보드
├── stock/[ticker]/      # 종목 상세 차트 (신규)
├── portfolio/
├── watchlist/
├── admin/
└── settings/
```

---

## 커밋 히스토리 (최신)

```
5ebdf0a feat: RegSHO 더보기 버튼 추가
0ee72fe feat: 홈 총평가금에 세후 금액 표시
94661d1 fix: 관심종목 UI 개선 + 차트 렌더링 수정
396f6f7 security: 환경변수 제거 (보안)
25e626f chore: v1.4.0 버전업
ab9deda feat: 종목 상세 페이지 + 캔들스틱 차트
```

---

## 주의사항

- **시크릿 키 교체 필요**: git history에 노출됨 (force push로 제거했지만 GitHub 캐시 90일 보관)
  - KAKAO_CLIENT_SECRET
  - JWT_SECRET
  - VAPID_PRIVATE_KEY

---

*Handoff: 2026-01-24 23:45*
