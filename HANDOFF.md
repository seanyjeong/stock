# Daily Stock Story - Handoff

**작성일**: 2026-01-24
**세션**: v1.1 구현 완료

---

## 현재 상태

### ✅ 배포 완료
- **GitHub**: https://github.com/seanyjeong/stock
- **Vercel**: https://web-lyart-rho-73.vercel.app
- **API**: https://stock-api.sean8320.dedyn.io
- **버전**: v1.2.0

### ✅ 구현 완료 (v1.1)
1. 블로거 인사이트 UI
2. 세금 계산 표시 (22%, 250만원 공제)
3. 하단 네비게이션 (홈/포트폴리오/관심/이력/설정)
4. 카카오 로그인 API
5. 사용자 승인 시스템 (관리자 페이지)
6. 온보딩 UI
7. 포트폴리오 CRUD (검색/추가/수정/삭제)
8. 매매 기록 + 손절/익절
9. 익절 계산기
10. 관심 종목 (Watchlist) - 목표가/알림가 설정
11. 푸시 알림 - Service Worker + Web Push API (VAPID 키 필요)

### ❌ 미구현
- 실제 푸시 발송 (VAPID 키 생성 및 cron job 필요)

---

## 다음 세션에서 할 일

### P1: VAPID 키 생성 및 푸시 발송 구현
```bash
# VAPID 키 생성
npx web-push generate-vapid-keys

# .env에 추가
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_EMAIL=mailto:admin@example.com
```

### P2: 푸시 트리거 cron job
```
- 목표가/알림가 도달 체크
- RegSHO 등재/해제 감지
- 블로그 새 글 알림
```

---

## API 엔드포인트

| 경로 | 설명 |
|------|------|
| `/api/portfolio` | 기존 포트폴리오 (읽기 전용) |
| `/api/regsho` | RegSHO 리스트 |
| `/api/recommendations` | 추천 종목 |
| `/api/blog` | 블로거 인사이트 |
| `/api/auth/*` | 인증 (카카오 로그인, 관리자) |
| `/api/portfolio/*` | 포트폴리오 CRUD |
| `/api/trades/*` | 매매 기록 |
| `/api/watchlist/*` | 관심 종목 CRUD |
| `/api/notifications/*` | 푸시 알림 설정/구독 |

---

## 파일 구조

```
~/dailystockstory/
├── api/
│   ├── main.py          # FastAPI 메인
│   ├── auth.py          # 카카오 로그인 + 관리자
│   ├── portfolio.py     # 포트폴리오 CRUD
│   ├── trades.py        # 매매 기록
│   ├── watchlist.py     # 관심 종목
│   └── notifications.py # 푸시 알림
├── web/src/routes/
│   ├── +page.svelte     # 대시보드 (세금 계산 포함)
│   ├── login/           # 카카오 로그인
│   ├── pending-approval/ # 승인 대기
│   ├── admin/           # 관리자 페이지
│   ├── onboarding/      # 온보딩
│   ├── portfolio/       # 포트폴리오 관리
│   ├── history/         # 매매 이력
│   ├── watchlist/       # 관심 종목
│   ├── calculator/      # 익절 계산기
│   ├── notifications/   # 알림 설정
│   └── settings/        # 설정
├── stock_collector.py   # 데이터 수집 (cron)
└── read_briefing.py     # 브리핑 CLI
```

---

## 환경 변수

### API (.env)
```
DATABASE_URL=postgresql://claude:claude_dev@localhost:5432/continuous_claude
JWT_SECRET=your-secret-key
KAKAO_REST_API_KEY=...
KAKAO_REDIRECT_URI=https://web-lyart-rho-73.vercel.app/login
KAKAO_CLIENT_SECRET=...
```

### Web (Vercel)
```
API_URL=https://stock-api.sean8320.dedyn.io
VITE_API_URL=https://stock-api.sean8320.dedyn.io
```

---

## 명령어

```bash
# 브리핑 확인
uv run python ~/dailystockstory/read_briefing.py

# API 서버 (수동)
cd ~/dailystockstory && uv run uvicorn api.main:app --host 0.0.0.0 --port 8340

# 배포
git push  # → Vercel 자동 배포
```

---

## ⚠️ 주의사항

**절대 건드리지 말 것:**
- `stock_collector.py`
- `read_briefing.py`
- 기존 DB 테이블들
- Cron jobs

**새로 추가된 DB 테이블:**
- `users` - 사용자
- `user_holdings` - 사용자 포트폴리오
- `trades` - 매매 기록
- `user_watchlist` - 관심 종목
- `push_subscriptions` - 푸시 구독
- `notification_settings` - 알림 설정

---

*Handoff 작성: 2026-01-24*
