# Daily Stock Story - Claude 설정

## 세션 시작 시 필수!

Claude Code 세션 시작하면:

1. **ARCHITECTURE.md 먼저 읽기** - 전체 구조 파악
2. **DB 메모리 조회** - 과거 작업 내역 확인:
   ```bash
   /recall dailystockstory
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

## 데이터 수집 & 스케줄

**v3 Lite - 간소화된 수집:**
- 주가 수집 제거 (yfinance 실시간 사용)
- 숏스퀴즈 수집 제거 (deep_analyzer가 실시간 분석)

**cron 스케줄:**
```bash
# 데이터 수집 (하루 1번) - 09:00 KST 화-토
0 9 * * 2-6 stock_collector.py  # RegSHO + 환율 + 블로그

# 스캐너 시스템
0 17 * * 1-5 news_collector.py      # 뉴스 수집 (프리마켓 1시간 전)
30 17 * * 1-5 scanner --type day    # 단타 추천 + 알림
0 9 * * 2-6 scanner --type swing    # 스윙 추천 + 알림
5 9 * * 2-6 scanner --type long     # 장기 추천 + 알림
```

---

## 세금 계산

**해외주식 양도소득세:**
| 항목 | 내용 |
|------|------|
| 기본공제 | **250만원** (연간) |
| 세율 | **22%** (양도세 20% + 지방세 2%) |
| 신고 | 다음해 5월 (홈택스) |

> 250만원 이하면 세금 없음!

---

## 검색 소스 (우선순위)

| 순위 | 사이트 | 용도 |
|------|--------|------|
| 1 | [NASDAQ Trader](https://www.nasdaqtrader.com/trader.aspx?id=regshothreshold) | RegSHO Threshold List |
| 2 | [Chartexchange](https://chartexchange.com/) | 대차이자, Short Interest |
| 3 | [Stocktwits](https://stocktwits.com/symbol/) | 커뮤니티 반응, 센티먼트 |
| 4 | [Finviz](https://finviz.com/quote.ashx?t=) | 기본 정보, 뉴스 |

---

## 미국주식 분석 (deep_analyzer.py v4)

**사용자가 미국주식 관련 질문하면 이거 써!**

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
| "BNAI 분석해줘" | `deep_analyzer.py BNAI` |
| "이 종목 숏스퀴즈 가능해?" | `deep_analyzer.py {ticker}` |
| "Zero Borrow야?" | `deep_analyzer.py {ticker} --no-ai` |
| "SEC 공시 뭐 있어?" | `deep_analyzer.py {ticker} --no-ai` |
| "락업 언제 풀려?" | `deep_analyzer.py {ticker}` |
| "FDA 승인났어?" | `deep_analyzer.py {ticker}` (바이오텍 자동 감지) |

**분석 항목:**
- 기본정보, 가격, Float
- 숏 데이터 (Zero Borrow, SI%, Borrow Rate, DTC)
- 기술적 (RSI, MACD, 볼린저)
- SEC 키워드 (워런트/희석/빚/락업)
- FTD, 옵션체인, 소셜센티먼트
- 피보나치, 볼륨프로파일
- 섹터별 뉴스/촉매 (9개 섹터)
- 8-K 이벤트, 바이오텍 촉매
- Gemini AI 종합 분석

---

## 데일리 리포트 생성 규칙

### "분석해줘" 요청 시 필수 수행

사용자가 **"{티커} 분석해줘"** 라고 하면:

1. **deep_analyzer 실행** (AI 포함)
   ```bash
   uv run python deep_analyzer.py {TICKER}
   ```

2. **리포트 저장** → `daily/{TICKER}_{YYYY-MM-DD}.md`
   ```
   daily/
   ├── GRRR_2026-01-25.md
   ├── BNAI_2026-01-25.md
   └── ...
   ```

3. **리포트 형식** (필수 섹션)
   - 회사 개요 (테이블)
   - 가격 정보
   - 숏 포지션 분석
   - 기술적 분석
   - 피보나치 레벨
   - SEC 공시 리스크
   - 기관 보유
   - 최근 뉴스
   - 숏스퀴즈 점수
   - AI 종합 분석 (강점/약점/전략)
   - 결론 + 최종 등급

### 할루시네이션 절대 금지

> **중요: 모든 데이터는 deep_analyzer 실행 결과에서만 가져올 것!**

- 숫자, 가격, 퍼센트 → deep_analyzer 출력값 그대로 사용
- 뉴스, SEC 공시 → deep_analyzer가 수집한 것만 인용
- 없는 정보 지어내기 ❌
- 추측으로 수치 만들기 ❌
- "아마도", "추정" 같은 불확실한 정보 → 명시적으로 표기

**위반 시 Claude 구독 취소됨**

---

## 프로젝트 구조

> **상세 구조는 `ARCHITECTURE.md` 참조**

**핵심 파일:**
| 파일 | 역할 |
|------|------|
| `deep_analyzer.py` | 초정밀 주식 분석기 (v4) |
| `stock_collector.py` | 데이터 수집 v3 Lite (RegSHO, 환율, 블로그) |
| `scanners/runner.py` | 스캐너 오케스트레이터 (v3) |
| `api/realtime.py` | 실시간 가격 (yfinance) |
| `api/notifications.py` | 푸시 알림 (추천/RegSHO) |

---

## 주의사항

- 투자 결정은 본인 책임
- 나노캡 변동성 주의
- 익절/손절 기준 미리 설정
