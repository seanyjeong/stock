# 숏스퀴즈 분석 v1.9.0 핸드오프

## 완료된 작업

### v1.9.0 주요 기능
1. **Positive News 감지** - SEC EDGAR에서 deal/partnership/contract/agreement 키워드 검색
2. **Negative News 감지** - lawsuit/bankruptcy/default/fraud/investigation/delisting 키워드
3. **스코어 보너스/페널티** - 호재 +10점, 악재 -15점
4. **ETF 제외** - yfinance quoteType으로 필터링
5. **프론트엔드** - 스코어 모달, PN/NN 뱃지, 티커 툴팁
6. **로그인 연동** - squeeze API에서 user_holdings 조회
7. **가격 알림 비활성화** - 실시간 API 필요

### 스코어 구성
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

Urgency Bonus (0-15):
├─ BR > 300%: +10점
└─ SI > 40%: +5점
```

## 다음 작업 (TODO)

### 1. 홈페이지 RegSHO 섹션 개선 (우선순위 높음)
- [ ] RegSHO 카드에 상위 4~5개만 점수순으로 표시
- [ ] 연속등재일, 종목명 컬럼 제거
- [ ] 주요 지표 표시: SI%, BR%, DTC, Float
- [ ] 스코어 표시
- 파일: `web/src/routes/+page.svelte`

### 2. 거래 이력 페이지
- [ ] 포트폴리오에서 거래 기록 시 이력 표시
- API: `/api/trades/history` (이미 있음)
- 파일: `web/src/routes/portfolio/+page.svelte`

### 3. 모든 종목 Borrow Rate 수집 (중요!)
- 현재: shortablestocks.com → RegSHO 종목만 BR 있음
- 목표: 모든 종목 BR 수집
- 방안: Fintel API (유료) 또는 다른 무료 소스 조사

### 4. 실시간 가격 알림 (나중에)
- 유료 API 필요 (Polygon, Alpha Vantage)
- 현재는 cron 기반 (하루 1회)

## 커밋 히스토리
- `c9feaec` fix: squeeze API 호출 시 auth 토큰 전송
- `99d24b0` chore: 가격 알림 일시 비활성화
- `2932c87` chore: 프론트엔드 버전 1.9.0
- `85cf15f` fix: squeeze API에서 로그인 유저의 user_holdings 사용
- `444194a` fix: ETF 숏스퀴즈 분석에서 제외
- `4dbf312` feat: 숏스퀴즈 v1.9.0 - 호재/악재 공시 분석

## API 서버
```bash
sudo systemctl restart stock-api
```

## Cron
```bash
0 9 * * * cd /home/sean/dailystockstory && uv run python stock_collector.py
```
