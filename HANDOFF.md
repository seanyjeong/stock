# Daily Stock Story - Handoff

**작성일**: 2026-01-24
**버전**: v1.2.0

---

## 현재 상태

### ✅ 배포 완료
- **GitHub**: https://github.com/seanyjeong/stock
- **Vercel**: https://stock-six-phi.vercel.app
- **API**: https://stock-api.sean8320.dedyn.io

### ✅ 구현 완료
1. 블로거 인사이트 UI
2. 세금 계산 표시 (22%, 250만원 공제)
3. 하단 네비게이션 (홈/포트폴리오/관심/이력/설정)
4. 카카오 로그인 API
5. 사용자 승인 시스템
6. 온보딩 UI
7. 포트폴리오 CRUD
8. 매매 기록
9. 익절 계산기
10. 관심 종목 (Watchlist)
11. 푸시 알림 (기반 구현)

---

## 환경변수

### API (.env)
```
DATABASE_URL=postgresql://claude:claude_dev@localhost:5432/continuous_claude
JWT_SECRET=***REMOVED***
KAKAO_REST_API_KEY=***REMOVED***
KAKAO_REDIRECT_URI=https://stock-six-phi.vercel.app/login
KAKAO_CLIENT_SECRET=***REMOVED***
```

### Vercel
```
VITE_API_URL=https://stock-api.sean8320.dedyn.io
```

---

## 카카오 설정

**개발자 콘솔 필수 설정:**
1. Redirect URI: `https://stock-six-phi.vercel.app/login`
2. Client Secret: 활성화
3. 동의항목: 닉네임 (필수)

---

## 명령어

```bash
# API 재시작
sudo systemctl restart stock-api

# 로그 확인
sudo journalctl -u stock-api -f

# 사용자 승인 (DB)
uv run python -c "
from db import get_db
conn = get_db()
cur = conn.cursor()
cur.execute('UPDATE users SET is_approved = TRUE, is_admin = TRUE WHERE id = 1')
conn.commit()
"
```

---

## 알려진 이슈

**401 토큰 오류 발생 시:**
- API 재시작 후 기존 토큰 무효화됨
- 해결: 로그아웃 → 재로그인

---

## 파일 구조

```
api/
├── main.py
├── auth.py          # 카카오 로그인
├── portfolio.py     # 포트폴리오 CRUD
├── trades.py        # 매매 기록
├── watchlist.py     # 관심 종목
└── notifications.py # 푸시 알림

web/src/routes/
├── +page.svelte     # 대시보드
├── login/
├── portfolio/
├── watchlist/
├── history/
├── calculator/
├── notifications/
└── settings/
```

---

*Handoff: 2026-01-24*
