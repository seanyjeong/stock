# Daily Stock Story - Handoff

**작성일**: 2026-01-24
**세션**: v1.1 구현 시작

---

## 현재 상태

### ✅ 배포 완료
- **GitHub**: https://github.com/seanyjeong/stock
- **Vercel**: https://web-lyart-rho-73.vercel.app
- **API**: https://stock-api.sean8320.dedyn.io
- **버전**: v1.0.0

### ✅ 구현됨
- 포트폴리오 조회 (읽기 전용)
- 추천 종목 (단타/스윙/장기)
- RegSHO 리스트
- 모바일 UI + 한글화
- GitHub → Vercel 자동 배포

### ❌ 미구현
- 카카오 로그인
- 블로그 인사이트 (API만 있음)
- 포트폴리오 CRUD
- 매매 기록
- 세금 계산 표시

---

## 다음 세션에서 할 일

### 즉시 시작: 블로거 인사이트 UI (#1)
```
/ralph-loop:ralph-loop 블로거 인사이트 UI 추가 - API /api/blog 있음, +page.svelte에 섹션 추가, 티커/키워드 태그, 원문 링크
```

**구현 내용:**
- web/src/lib/types.ts에 BlogPost, BlogResponse 타입 추가
- web/src/routes/+page.server.ts에 blog fetch 추가
- web/src/routes/+page.svelte에 블로그 섹션 추가
- 티커/키워드 태그 표시
- 원문 링크 버튼

### 다음 P0 태스크
- #3: 세금 계산 표시 (포트폴리오에 22% 세금 계산 추가)
- #8: 하단 네비게이션 ([홈][포트폴리오][이력][설정])

### P1 태스크 (카카오 로그인)
- #7: 카카오 로그인 API (~/mprojects/ 참고)
- #5: 사용자 승인 시스템
- #12: 온보딩 UI
- #4: 포트폴리오 CRUD API
- #6: 포트폴리오 CRUD UI

### P2 태스크
- #2: 매매 기록 + 손절/익절
- #11: 관심 종목
- #10: 익절 계산기
- #9: 푸시 알림

---

## 파일 구조

```
~/dailystockstory/
├── api/main.py          # FastAPI (포트 8340)
├── web/                  # SvelteKit 웹앱
│   └── src/routes/
│       ├── +page.svelte  # 메인 대시보드
│       └── login/        # 로그인 페이지 (미연결)
├── docs/plans/
│   └── PLAN_v1.1-features.md  # 다음 버전 계획
├── stock_collector.py    # 데이터 수집 (cron)
└── read_briefing.py      # 브리핑 CLI
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

## 환경

- **Vercel 토큰**: `~/.config/opencode/.env`
- **Caddy**: stock.sean8320.dedyn.io, stock-api.sean8320.dedyn.io

---

## 포트폴리오 데이터 (보존!)

```
portfolio.md에서 DB로 마이그레이션할 것!

| 티커 | 수량 | 평단 |
|------|------|------|
| BNAI | 464 | $9.55 |
| GLSI | 67 | $25.22 |
```

**절대 삭제 금지**: `portfolio.md`

---

## 참고 문서

| 문서 | 경로 |
|------|------|
| PRD | `docs/PRD_daily-stock-story.md` |
| v1.1 계획 | `docs/plans/PLAN_v1.1-features.md` |
| 카카오 로그인 참고 | `~/mprojects/` |
| 포트폴리오 원본 | `portfolio.md` (DB 마이그레이션 시 사용)

---

---

## ⚠️ 주의사항

**절대 건드리지 말 것 (잘 작동 중):**
- `stock_collector.py` - 데이터 수집
- `read_briefing.py` - CLI 브리핑
- `day_trader_scanner.py` - 단타 추천
- `swing_long_scanner.py` - 스윙/장기 추천
- 기존 DB 테이블들 (stock_briefing, stock_prices 등)
- Cron jobs

**새로 추가만 할 것:**
- users, portfolio, notification_settings 테이블
- 인증/권한 API
- 웹 UI 페이지

---

*Handoff 작성: 2026-01-24*
