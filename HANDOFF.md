# 달러농장 핸드오프

**작성일**: 2026-01-25
**버전**: v1.6.0

---

## 바로 할 일 (다음 세션)

### 종합 스퀴즈 스코어 v2 구현

**목표:** 블로거 스타일의 정확한 분석

**필요한 데이터:**
| 데이터 | 소스 | 방법 |
|--------|------|------|
| Borrow Rate | Fintel 무료 부분 확인 | 스크래핑 |
| 워런트 정보 | SEC EDGAR 8-K | API/스크래핑 |
| 부채/재무상황 | SEC 10-Q | API |
| 주식발행 제한 | SEC 공시 | 파싱 |

**BNAI 예시:**
- 워런트 $15 있지만 행사 불가 (회사 부채 때문)
- 주식 발행 제한 = 공매도자 청산 압박 증가
- 현재 스코어 35.7 (DTC 낮아서) → 워런트/부채 반영하면 더 높아야 함

### 구현 순서

```bash
1. SEC EDGAR API 연동
   - https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=BNAI&type=8-K
   - 8-K (중요 공시) 수집
   - 10-Q (분기 재무제표) 파싱

2. Fintel 무료 데이터 확인
   - https://fintel.io/ss/us/bnai
   - Borrow Rate 스크래핑 가능한지 테스트

3. 종합 스코어 계산 로직
   score = (
     short_interest * 0.25 +
     days_to_cover * 0.15 +
     regsho_days * 0.15 +
     borrow_rate * 0.25 +
     warrant_pressure * 0.20  # 워런트/부채 상황
   )

4. 프론트 UI 개선
   - 각 지표별 상세 표시
   - 왜 스퀴즈 확률이 높은지 설명
```

---

## 이번 세션 완료 (v1.6.0)

### 숏스퀴즈 분석 v1
- `squeeze_data` 테이블 생성
- yfinance에서 Short Interest, Days to Cover 수집
- `/api/squeeze` API 엔드포인트
- 포트폴리오 카드에 숏 지표 표시 (SI%, RegSHO일, 스퀴즈 점수)
- RegSHO 연속등재일 추적 개선 (등재 빠지면 리셋)
- RegSHO 설명 추가: "5일 연속 결제 실패 종목"

### 파일 변경
- `stock_collector.py` - collect_squeeze_data(), RegSHO first_seen_date 로직
- `api/main.py` - /api/squeeze 엔드포인트
- `web/src/routes/+page.svelte` - 숏스퀴즈 UI
- `web/src/lib/types.ts` - SqueezeResponse 타입
- `web/src/routes/+page.server.ts` - squeeze 데이터 fetch

---

## 테스트 명령어

```bash
# 수집기 실행
cd ~/dailystockstory && uv run python stock_collector.py

# squeeze 데이터 확인
docker exec continuous-claude-postgres psql -U claude -d continuous_claude -c \
  "SELECT * FROM squeeze_data ORDER BY squeeze_score DESC LIMIT 10;"

# RegSHO 연속등재일 확인
docker exec continuous-claude-postgres psql -U claude -d continuous_claude -c \
  "SELECT ticker, first_seen_date, (CURRENT_DATE - first_seen_date) as days
   FROM regsho_list WHERE collected_date = (SELECT MAX(collected_date) FROM regsho_list)
   ORDER BY days DESC LIMIT 10;"

# 빌드
cd ~/dailystockstory/web && npm run build
```

---

## 현재 DB squeeze_data

| 티커 | SI | DTC | Score | 비고 |
|------|-----|-----|-------|------|
| HIMS | 36.5% | 5.4일 | 65.4 | 높음 |
| GLSI | 24.3% | 2.4일 | 38.9 | |
| BNAI | 29.2% | 0.16일 | 35.7 | DTC 낮아서 점수 낮음 |

**BNAI 문제:** DTC 0.16일 = 거래량 많아서 점수 낮음
→ 워런트/부채 상황 반영해야 정확한 스코어 나옴

---

## 배포 현황

| 항목 | URL |
|------|-----|
| GitHub | https://github.com/seanyjeong/stock |
| Vercel | https://stock-six-phi.vercel.app |
| API | https://stock-api.sean8320.dedyn.io |

---

*Handoff: 2026-01-25*
