# Daily Stock Story - Claude 설정

## 1. 코드 수정 시 필수!
**`ARCHITECTURE.md` 최신화 필수!**
- DB 스키마 변경 → 테이블 구조 수정
- API 추가/변경 → 엔드포인트 목록 수정
- 컴포넌트 추가 → 프론트 구조 수정
- 로직 변경 → 해당 섹션 수정

---

## 다음 작업 (TODO)
**플랜 문서:** `PLAN_v2_scanner.md`

### 종목 추천 시스템 v2
- 뉴스/호재/악재 종합 분석
- 스마트 매수가 계산 (지지선, 피보나치)
- 추천 이유 한글 상세 설명
- AI 자가 검증 로직
- 투자성향 프로파일링 (첫 로그인 설문)
- 내 정보에서 성향 다시하기

→ 완료 후 이 섹션 삭제

---

## 문서

| 문서 | 설명 |
|------|------|
| `ARCHITECTURE.md` | 전체 스택, DB 스키마, API, 인프라 |
| `HANDOFF.md` | 작업 인수인계, 완료/TODO |
| `PLAN_v2_scanner.md` | 추천 시스템 v2 개선 플랜 |

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

## 세션 시작 시 할 일

Claude Code 세션 시작하면 **DB에서 브리핑 읽기만 하면 됨!**

### 브리핑 출력 (한 줄)
```bash
uv run python ~/dailystockstory/read_briefing.py
```

이게 끝! 모든 데이터는 외부에서 자동 수집됨.

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

## 폴더 구조

```
~/dailystockstory/
├── CLAUDE.md            ← 설정
├── stock_collector.py   ← 데이터 수집 (cron)
├── read_briefing.py     ← 브리핑 읽기 (Claude용)
├── scrape_blog.py       ← 블로그 스크래핑 (collector에 통합됨)
├── portfolio.md         ← 포트폴리오 기록
├── pyproject.toml       ← Python 의존성
└── blog_posts/          ← 스크래핑된 블로그 글
```

**DB 테이블:**
- `stock_prices` - 주가
- `regSHO_list` - RegSHO 목록
- `exchange_rates` - 환율
- `blog_posts` - 블로그 포스트
- `stock_briefing` - 브리핑 캐시

---

## 브리핑 예시

`uv run python read_briefing.py` 실행 결과:

```
## 📊 Daily Stock Briefing
*데이터 수집: 2026-01-24 06:33 KST*

### 내 포트폴리오
| 종목 | 수량 | 평단 | 현재가 | 평가금 | 손익 |
| **BNAI** | 464주 | $9.55 | **$58.54** | $27,163 | +$22,731 (+513%) 🔥 |
| **GLSI** | 67주 | $25.22 | **$26.00** | $1,742 | +$52 (+3%) 📈 |

**총 평가금:** $28,905 (₩41,911,622)
**총 손익:** +$22,784 (+372%)

### 세금 계산 (실현 시)
| **예상 세금 (22%)** | **₩6,717,977** |
| **세후 순수익** | **₩26,318,282** |

### RegSHO Threshold
✅ **보유 종목 등재:** BNAI

### 블로거 인사이트 (까꿍토끼)
- 티커, 키워드 자동 추출
```

---

## 주의사항

- 투자 결정은 본인 책임
- 나노캡 변동성 주의
- 익절/손절 기준 미리 설정
