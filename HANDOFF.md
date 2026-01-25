# Daily Stock Story 핸드오프

## 현재 버전: v1.9.5

---

## v1.9.5 - 투자성향 시스템 (Phase 1)

### 완료된 작업

| 작업 | 상태 | 설명 |
|------|------|------|
| DB: user_profiles 테이블 | ✅ | 투자성향 저장 |
| API: /api/profile CRUD | ✅ | 조회/생성/수정/체크 |
| 설문 페이지 | ✅ | /survey - 5개 질문 |
| 로그인 플로우 | ✅ | 로그인 → 설문(없으면) → 대기 |
| 설정 성향 표시 | ✅ | 🛡️안정/⚖️균형/🔥공격 + 다시하기 |
| 승인대기 성향 표시 | ✅ | /pending-approval 페이지 |
| 관심종목 폴더 API | ✅ | 폴더 CRUD, 종목 폴더 이동 |
| 관심종목 폴더 UI | ✅ | 폴더 탭, 생성, 필터링 |
| 관리자 성향 표시 | ✅ | 승인 목록에 사용자 성향 뱃지 |

### 남은 작업

| 우선순위 | 작업 | 설명 |
|---------|------|------|
| 🔴 P0 | 뉴스 수집 스캐너 | SEC EDGAR, Reddit, Benzinga 스크래핑 |
| 🔴 P0 | 전체 시장 스캔 | 나스닥 전체 → 성향별 점수 계산 |
| 🟡 P1 | 추천 API 성향 필터링 | /api/recommendations에서 성향별 반환 |
| 🟢 P2 | 홈화면 성향별 UI | 안정형=장기, 공격형=단타 강조 |

---

## 성향 시스템 상세

### 설문 항목 (5개)
1. **경험**: 1년 미만 / 1-3년 / 3년 이상
2. **손실 허용**: 5% / 10% / 20% / 20%+
3. **투자 기간**: 단타 / 스윙 / 장기 / 혼합
4. **수익 기대**: 안정 5-10% / 중간 10-30% / 공격 30%+
5. **관심 섹터**: 기술 / 바이오 / 에너지 / 금융 / 전체

### 성향 계산 알고리즘
```
점수 = 경험(0-2) + 리스크(0-3) + 기간(0-3) + 수익기대(0-3)
- 0~4점: conservative (🛡️ 안정형)
- 5~8점: balanced (⚖️ 균형형)
- 9~12점: aggressive (🔥 공격형)
```

### 플로우
```
로그인 → 프로필 체크 → 없으면 /survey → 완료 → /pending-approval
                     → 있으면 /pending-approval 또는 /
```

---

## 폴더 시스템

### DB 테이블
- `watchlist_folders`: 폴더 관리 (id, user_id, name, color, sort_order)
- `user_watchlist.folder_id`: 종목-폴더 연결

### API
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/watchlist/folders | 폴더 목록 |
| POST | /api/watchlist/folders | 폴더 생성 |
| PUT | /api/watchlist/folders/{id} | 폴더 수정 |
| DELETE | /api/watchlist/folders/{id} | 폴더 삭제 |
| PUT | /api/watchlist/{id}/folder | 종목 폴더 이동 |

---

## 파일 변경 이력 (v1.9.5)

### 신규 생성
- `api/profile.py` - 프로필 API
- `web/src/routes/survey/+page.svelte` - 설문 페이지

### 수정
- `api/main.py` - profile_router 등록
- `api/auth.py` - list_users에 profile_type JOIN
- `api/watchlist.py` - 폴더 기능 추가
- `web/src/lib/types.ts` - UserProfile 타입
- `web/src/lib/api.ts` - 프로필 API 함수
- `web/src/routes/login/+page.svelte` - 설문 리다이렉트
- `web/src/routes/settings/+page.svelte` - 성향 표시
- `web/src/routes/pending-approval/+page.svelte` - 성향 뱃지
- `web/src/routes/admin/+page.svelte` - 성향 뱃지
- `web/src/routes/watchlist/+page.svelte` - 폴더 UI

---

## 다음 단계 (스캐너 구현)

### 1. 뉴스 수집기 (P0)
```bash
# 위치: scanners/news_collector.py
# 실행: uv run python scanners/news_collector.py
# Cron: 21:00 KST (월-금)
```

**데이터 소스:**
- SEC EDGAR (8-K, 10-K, 13F)
- Reddit (r/wallstreetbets, r/stocks)
- Benzinga, MarketWatch, Reuters

**Gemini Flash 활용:**
- 뉴스 감성 분석 (긍정/부정/중립)
- temperature: 0 (할루시네이션 방지)

### 2. 전체 시장 스캐너 (P0)
```bash
# 위치: scanners/full_market_scanner.py
# 실행: uv run python scanners/full_market_scanner.py
# Cron: 21:30 KST (월-금)
```

**스캔 순서:**
1. 뉴스 상위 50개 종목 필터링
2. 기술적 분석 (RSI, MACD, Volume)
3. 성향별 점수 3개 동시 계산
4. DB 저장 (daily_scan_results)

### 3. 추천 API 수정 (P1)
```python
# /api/recommendations
# 유저 성향에 따라 다른 결과 반환
if profile_type == "aggressive":
    score_key = "day_trade_score"
elif profile_type == "balanced":
    score_key = "swing_score"
else:
    score_key = "longterm_score"
```

---

## 기존 v1.9.2 내용

### 숏스퀴즈 스코어
```
Base Score (0-60):
├─ Short Interest (0-25): 50%+ = 만점
├─ Borrow Rate (0-20): 200%+ = 만점
└─ Days to Cover (0-15): 10일+ = 만점

Squeeze Pressure Bonus (0-25):
├─ Zero Borrow (available=0): +10점
├─ Low Float (<10M): +5점
└─ Warrant/Covenant: +10점

Catalyst Bonus (0-10):
└─ Positive News (50건+): +10점

Risk Penalty (-15):
└─ Negative News (20건+): -15점
```

---

## 서버 관리

```bash
# API 재시작
sudo systemctl restart stock-api
sudo systemctl status stock-api

# 로그 확인
journalctl -u stock-api -f

# Cron 확인
crontab -l
```

---

## 버전 업데이트 체크리스트

1. `web/package.json` → `"version": "x.x.x"`
2. `web/src/routes/settings/+page.svelte` → 버전 표시
3. `HANDOFF.md` → 변경 이력
4. `ARCHITECTURE.md` → 구조 변경 시
5. 커밋: `chore: vX.X.X`
