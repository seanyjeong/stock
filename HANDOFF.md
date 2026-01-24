# 숏스퀴즈 분석 v1.9.0 핸드오프

## 완료된 작업

### v1.9.0 주요 기능
1. **Positive News 감지** - SEC EDGAR에서 deal/partnership/contract/agreement 키워드 검색
2. **Negative News 감지** - lawsuit/bankruptcy/default/fraud/investigation/delisting 키워드
3. **스코어 보너스/페널티** - 호재 +10점, 악재 -15점
4. **프론트엔드 개선** - 종목명 제거, 티커 툴팁, 스코어 모달, PN/NN 뱃지 추가

### v1.8.0 주요 기능
1. **Zero Borrow 감지** - shortablestocks.com 스크래핑 (stealth 모드)
2. **SEC EDGAR Full-Text Search** - 워런트/희석/covenant 언급 횟수 분석
3. **v2 스코어 로직** - Base Score + Bonus 시스템
4. **프론트엔드 /squeeze 페이지** - 점수 순 정렬, 필터, 지표 표시

### BNAI 테스트 결과
- **v1 점수:** 7.7점 (COLD)
- **v2 점수:** 69.8점 (HOT!) 🔥

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

Urgency Bonus (0-15):
├─ BR > 300%: +10점
└─ SI > 40%: +5점
```

## 파일 변경

### Backend
- `stock_collector.py` - v2 로직 추가
  - `collect_borrow_rates()` - shortablestocks 스크래핑
  - `collect_sec_dilution_info()` - SEC Full-Text Search
  - `calculate_squeeze_score_v2()` - 새 스코어 계산
- `api/main.py` - /api/squeeze 엔드포인트 새 컬럼 추가

### Frontend
- `web/src/routes/squeeze/+page.svelte` - 신규 페이지
- `web/src/lib/components/BottomNav.svelte` - 스퀴즈 메뉴 추가
- `web/src/lib/components/Icons.svelte` - fire 아이콘 추가

### DB 스키마
```sql
-- squeeze_data 테이블 새 컬럼
available_shares BIGINT
float_shares BIGINT
dilution_protected BOOLEAN
```

## Cron 설정
```bash
# 매일 오전 9시 KST
0 9 * * * cd /home/sean/dailystockstory && /home/sean/.local/bin/uv run python stock_collector.py
```

## API 서버 재시작 필요
```bash
sudo systemctl restart [서비스명]
```

## 다음 작업 (TODO) - 우선순위 높음!
- [ ] **뉴스 호재 점수 추가** - SEC 8-K/PR Newswire에서 긍정 키워드 감지
  - 키워드: deal, partnership, contract, agreement, revenue, profit
  - 컬럼 추가: `has_positive_news`, `news_score`
  - 스코어에 +5~10점 보너스
- [ ] FTD 데이터 추가 (SEC에서 가져오기)
- [ ] Sentiment 분석 추가 (Stocktwits/ORTEX - 현재 차단됨)
- [ ] 알림 기능 (스코어 급등 시 푸시)

## 의존성
```
playwright-stealth>=2.0.1  # 봇 감지 우회
httpx>=0.28.1              # SEC API 호출
```

## 커밋 히스토리
- `6a80378` chore: bump version to v1.8.0
- `4b9a04e` feat: 숏스퀴즈 분석 페이지 추가 (프론트엔드)
- `5ab10f7` feat: 숏스퀴즈 v1.8.0 - SEC 워런트/희석 분석 완성
- `548f148` feat: 숏스퀴즈 v1.7.0 - Zero Borrow 감지
