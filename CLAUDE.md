# Daily Stock Story - Claude 설정

## 세션 시작 시 필수!

Claude Code 세션 시작하면:

1. **ARCHITECTURE.md 먼저 읽기** - 전체 구조 파악
2. **DB 메모리 조회** - 과거 작업 내역 확인:
   ```bash
   /recall dailystockstory
   ```
3. **브리핑 출력** (선택):
   ```bash
   uv run python read_briefing.py
   ```

---

## 핵심 문서

| 문서 | 용도 | 내용 |
|------|------|------|
| **`ARCHITECTURE.md`** | 필독 | DB 스키마, API 목록, 인프라, 버전 이력 |
| `thoughts/shared/handoffs/` | 작업 인수 | 핸드오프 문서 (YAML) |

> **코드 수정 시 ARCHITECTURE.md도 반드시 업데이트!**

---

## 버전 관리

**버전 업데이트 시 수정해야 할 파일:**
1. `web/package.json` - `"version": "x.x.x"`
2. `web/src/routes/settings/+page.svelte` - 버전 표시
3. 커밋 메시지: `chore: vX.X.X`


**API 서버:**
- 포트: **8340**
- 재시작: `sudo systemctl restart stock-api`
- 상태 확인: `sudo systemctl status stock-api`

---

## 데이터 수집 (외부 자동화)

**수집 스크립트 (cron으로 자동 실행):**
```bash
uv run python ~/dailystockstory/stock_collector.py
```

**수집 항목:**
| 항목 | 소스 | 저장 위치 |
|------|------|-----------|
| 주가 | yfinance | PostgreSQL |
| RegSHO | NASDAQ | PostgreSQL |
| 환율 | x-rates | PostgreSQL |
| 블로그 | 까꿍토끼 | PostgreSQL |

**cron 설정 (매 시간):**
```bash
crontab -e
# 추가:
0 * * * * cd ~/dailystockstory && uv run python stock_collector.py >> /tmp/stock_collector.log 2>&1
```

---

## 세금 계산

**해외주식 양도소득세:**
| 항목 | 내용 |
|------|------|
| 기본공제 | **250만원** (연간) |
| 세율 | **22%** (양도세 20% + 지방세 2%) |
| 신고 | 다음해 5월 (홈택스) |

> ⚠️ 250만원 이하면 세금 없음!

---

## 검색 소스 (우선순위)

| 순위 | 사이트 | 용도 |
|------|--------|------|
| 1 | [Benzinga](https://www.benzinga.com/quote/) | 실시간 가격, 프리/애프터 |
| 2 | [NASDAQ Trader](https://www.nasdaqtrader.com/trader.aspx?id=regshothreshold) | RegSHO Threshold List |
| 3 | [Stocktwits](https://stocktwits.com/symbol/) | 커뮤니티 반응, 센티먼트 |
| 4 | [Chartexchange](https://chartexchange.com/) | 대차이자, Short Interest |

**야후/구글 파이낸스 사용 금지** - 프리마켓/애프터 데이터 부정확

---

## 세션 기록 저장

중요한 분석이나 결정은 메모리에 저장:

```bash
cd $CLAUDE_OPC_DIR && PYTHONPATH=. uv run python scripts/core/store_learning.py \
  --session-id "stock-YYYYMMDD" \
  --type WORKING_SOLUTION \
  --content "분석 내용" \
  --context "주식 분석" \
  --tags "stock,short-squeeze,종목명" \
  --confidence high
```

---

## 미국주식 분석 (deep_analyzer.py v4) 🔥

**사용자가 미국주식 관련 질문하면 이거 써! (나스닥의 신 에디션)**

```bash
# 종목 분석 (AI 포함)
uv run python deep_analyzer.py BNAI

# 빠른 분석 (AI 스킵)
uv run python deep_analyzer.py BNAI --no-ai

# 일반 분석 모드 강제 (숏스퀴즈 아닐 때)
uv run python deep_analyzer.py GLSI --normal
```

**언제 쓸까?**
| 질문 유형 | 사용 |
|----------|------|
| "BNAI 분석해줘" | ✅ `deep_analyzer.py BNAI` |
| "이 종목 숏스퀴즈 가능해?" | ✅ `deep_analyzer.py {ticker}` |
| "Zero Borrow야?" | ✅ `deep_analyzer.py {ticker} --no-ai` |
| "SEC 공시 뭐 있어?" | ✅ `deep_analyzer.py {ticker} --no-ai` |
| "락업 언제 풀려?" | ✅ `deep_analyzer.py {ticker}` |
| "SPAC이야?" | ✅ `deep_analyzer.py {ticker}` |
| "FDA 승인났어?" | ✅ `deep_analyzer.py {ticker}` (바이오텍 자동 감지) |
| "임상 몇상이야?" | ✅ `deep_analyzer.py {ticker}` (ClinicalTrials.gov 연동) |
| "AI 관련 뉴스 있어?" | ✅ `deep_analyzer.py {ticker}` (Tech/AI 자동 감지) |
| "내 포트폴리오 보여줘" | ❌ `read_briefing.py` 사용 |

**v4 신규 기능:**
- 섹터별 특화 뉴스 (바이오텍/AI·Tech/에너지/일반)
- 바이오텍 촉매 (FDA Fast Track, ClinicalTrials.gov)
- 8-K 이벤트 파싱 (FDA승인, 임상결과, 계약, 유증)
- 뉴스 60일 필터 + 구글뉴스 백업

**분석 항목:**
- 기본정보, 가격, Float
- 숏 데이터 (Zero Borrow, SI%, Borrow Rate, DTC)
- 기술적 (RSI, MACD, 볼린저)
- SEC 키워드 (워런트/희석/빚/락업)
- FTD, 옵션체인, 소셜센티먼트
- 피보나치, 볼륨프로파일, 다크풀
- SPAC/Earnout 조건
- **섹터별 뉴스** (Biotech FDA/AI Tech/Energy)
- **8-K 이벤트** (FDA승인, 임상, 계약, 유증 자동분류)
- **바이오텍 촉매** (ClinicalTrials.gov 임상정보)
- Gemini AI 종합 분석

---

## 프로젝트 구조

> **상세 구조는 `ARCHITECTURE.md` 참조** (DB 스키마, API 목록, 컴포넌트 구조 포함)

**핵심 파일:**
| 파일 | 역할 |
|------|------|
| `deep_analyzer.py` | 초정밀 주식 분석기 (v4) |
| `stock_collector.py` | 데이터 수집 (cron) |
| `read_briefing.py` | 브리핑 조회 |
| `api/realtime.py` | 실시간 가격 (Finnhub+yfinance 하이브리드) |
| `scanners/full_market_scanner.py` | 종목 스캔 + AI 추천 |

---

## 주의사항

- 투자 결정은 본인 책임
- 나노캡 변동성 주의
- 익절/손절 기준 미리 설정
