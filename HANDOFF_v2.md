# 종목 추천 시스템 v2 핸드오프

## 현재 버전: v2.0.0

## 완료된 작업 (Phase 1-3)

### Phase 1: 투자성향 시스템 ✅
- `api/profile.py` - 프로필 CRUD API
- `web/src/routes/survey/+page.svelte` - 5문항 설문
- `user_profiles` 테이블 - 성향 저장
- 로그인 → 설문 → 승인대기 플로우
- 설정/관리자 페이지 성향 뱃지

### Phase 2: 스캐너 시스템 ✅
- `scanners/news_collector.py` - 뉴스 수집 (SEC/Finviz/Yahoo)
- `scanners/full_market_scanner.py` - 성향별 점수 계산
- `api/main.py` - /api/recommendations 성향별 필터링
- `ProfileRecommendations.svelte` - 홈 맞춤 추천 UI
- `watchlist_folders` - 관심종목 폴더 기능

### Phase 3: AI 추천 고도화 ✅
- **Gemini 2.0 Flash** - 한글 추천 이유 생성
- **R/R 기반 등급** - ★★★/★★/★
- **분할매수 제안** - 3단계 (40%/30%/30%)
- **상세 분석 모달** - RecommendationModal.svelte

---

## 주요 파일

| 파일 | 용도 |
|------|------|
| `scanners/news_collector.py` | 뉴스 수집 (SEC/Finviz/Yahoo) |
| `scanners/full_market_scanner.py` | 시장 스캔 + Gemini AI |
| `api/main.py` | 추천 API |
| `web/src/lib/components/ProfileRecommendations.svelte` | 추천 UI |
| `web/src/lib/components/RecommendationModal.svelte` | 상세 분석 모달 |

---

## 실행 순서

```bash
# 1. 뉴스 수집
uv run python scanners/news_collector.py

# 2. 시장 스캔 (Gemini 추천 이유 생성)
uv run python scanners/full_market_scanner.py

# 3. API 재시작
sudo systemctl restart stock-api
```

---

## DB 테이블

- `user_profiles` - 투자성향
- `news_mentions` - 뉴스 수집
- `daily_news_scores` - 일일 뉴스 점수
- `daily_scan_results` - 스캔 결과 (JSONB)
- `watchlist_folders` - 폴더 관리

---

## 환경 변수

```bash
# .env
GEMINI_API_KEY=xxx  # Gemini 2.0 Flash API
```

---

## 추천 데이터 구조

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
  "stop_loss": 46.52,
  "target": 76.57,
  "recommendation_reason": "RSI 32로 과매도 구간. 거래량 2.3배 증가. 뉴스 점수 15로 호재 발생.",
  "rating": "★★★",
  "rr_ratio": 1.75,
  "split_entries": [
    {"price": 58.54, "pct": 40, "label": "현재가"},
    {"price": 52.00, "pct": 30, "label": "1차 지지"},
    {"price": 46.00, "pct": 30, "label": "강한 지지"}
  ]
}
```

---

## 성향별 추천

| 성향 | 정렬 기준 | 매수가 |
|------|----------|--------|
| 🔥 공격형 | day_trade_score | entry_aggressive |
| ⚖️ 균형형 | swing_score | entry_balanced |
| 🛡️ 안정형 | longterm_score | entry_conservative |
