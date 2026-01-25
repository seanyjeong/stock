# 종목 추천 시스템 v2 - TODO

## Phase 1: 투자성향 시스템 ✅ 완료

- [x] DB: user_profiles 테이블
- [x] API: /api/profile CRUD
- [x] 설문 페이지 (/survey)
- [x] 로그인 플로우 (로그인→설문→대기)
- [x] 설정 성향 표시 + 다시하기
- [x] 승인대기 성향 표시
- [x] 관심종목 폴더 API
- [x] 관심종목 폴더 UI
- [x] 관리자 성향 뱃지

---

## Phase 2: 스캐너 시스템 ✅ 완료

- [x] 뉴스 수집 스캐너 (SEC/Finviz/Yahoo)
- [x] 전체 시장 스캐너 (성향별 점수)
- [x] 추천 API 성향별 필터링
- [x] 홈 UI ProfileRecommendations

---

## Phase 3: AI 추천 고도화 ✅ 완료

### Task 1: 한글 추천 이유 생성 (Gemini API) ✅
- [x] Gemini 2.0 Flash API 연동 (google-genai SDK)
- [x] 추천 이유 프롬프트 설계 (할루시네이션 방지)
- [x] `generate_recommendation_reason()` 함수
- [x] 스캐너에서 이유 생성 후 DB 저장
- [x] 프론트엔드에 이유 표시

### Task 2: AI 자가 검증 ✅
- [x] R/R (Risk/Reward) 비율 계산
- [x] 추천 등급 (★★★/★★/★) - R/R 기반

### Task 3: 상세 분석 모달 ✅
- [x] RecommendationModal.svelte 생성
- [x] 추천 카드 클릭 시 모달 오픈
- [x] 전체 분석 내용 표시 (AI 분석, 기술적 지표, 가격, 분할매수)

### Task 4: 분할매수 제안 ✅
- [x] calculate_split_entry() 함수
- [x] 지지선 기반 3단계 분할 (현재가 40%, 1차지지 30%, 강한지지 30%)
- [x] 프론트엔드 표시

---

## Phase 3 의존성

```
Task 1 (Gemini 연동) ──► Task 2 (자가검증) ──► Task 3 (모달)
                                            │
Task 4 (분할매수) ─────────────────────────────┘
```

---

## 환경 변수

```bash
# .env에 추가 필요
GEMINI_API_KEY=xxx
```

---

## Gemini 프롬프트 설계

### 추천 이유 생성
```python
RECOMMENDATION_REASON_PROMPT = """
너는 주식 추천 이유를 한글로 작성하는 분석가야.

[규칙]
1. 아래 데이터만 사용해. 추측/예측 금지.
2. "~일 것이다", "~할 것으로 보인다" 금지.
3. 팩트만 서술해.

[종목 데이터]
- 티커: {ticker}
- 현재가: ${current_price}
- RSI: {rsi}
- MACD: {macd_cross}
- 거래량 비율: {volume_ratio}x
- 뉴스 점수: {news_score}
- 뉴스 요약: {news_summary}

3줄 이내로 작성:
1. 기술적 분석 요약
2. 뉴스/이슈 요약
3. 종합 판단
"""
```

---

## 파일 변경 예정

| 파일 | 변경 |
|------|------|
| `scanners/full_market_scanner.py` | Gemini 연동, 이유 생성 |
| `api/main.py` | 추천 이유/등급 반환 |
| `ProfileRecommendations.svelte` | 이유/등급/분할매수 표시 |
| `RecommendationModal.svelte` | 신규 생성 |
