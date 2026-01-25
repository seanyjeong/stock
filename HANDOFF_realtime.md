# 실시간 주가 구현 핸드오프

## 현재 상태: v2.0.0 완료

### 완료된 기능
- Phase 1: 투자성향 시스템 (설문, 프로필)
- Phase 2: 스캐너 시스템 (뉴스 수집, 시장 스캔)
- Phase 3: AI 추천 (Gemini 한글 이유, 등급, 분할매수, 모달)
- 포트폴리오 새로고침 버튼 추가
- 휴장일 체크, cron 정리

### 현재 한계
- 포트폴리오 주가: API 호출 시점 기준 (실시간 X)
- 수동 새로고침 필요

---

## 다음 작업: 실시간 주가

### 추천 방식: Alpaca WebSocket (무료)

**Alpaca Markets:**
- 미국 주식 실시간 무료 (IEX 데이터)
- WebSocket API 제공
- 가입: https://alpaca.markets (Paper Trading 계정 무료)

**Alpaca 무료 제한:**
- IEX 데이터 (전체 거래량의 ~2-3%)
- SIP (전체 거래소) 데이터는 유료 ($9/월)
- 동시 WebSocket 연결: 1개
- 우리 용도(포트폴리오 가격)엔 IEX로 충분

### 구현 계획

```
1. Alpaca 계정 생성 + API Key 발급
2. 백엔드: FastAPI WebSocket 엔드포인트
   - /ws/prices - 클라이언트 연결
   - Alpaca WebSocket 구독 → 클라이언트로 전달
3. 프론트: WebSocket 클라이언트
   - 포트폴리오 보유 종목 구독
   - 가격 업데이트 시 UI 반영
```

### 파일 변경 예정

| 파일 | 변경 |
|------|------|
| `api/websocket.py` | 신규 - WebSocket 핸들러 |
| `api/main.py` | WebSocket 라우터 등록 |
| `web/src/routes/+page.svelte` | WebSocket 연결, 실시간 업데이트 |
| `.env` | ALPACA_API_KEY, ALPACA_SECRET_KEY |

### 코드 예시

**백엔드 (api/websocket.py):**
```python
from fastapi import WebSocket
import websockets
import json

ALPACA_WS = "wss://stream.data.alpaca.markets/v2/iex"

async def alpaca_price_stream(websocket: WebSocket, tickers: list):
    await websocket.accept()

    async with websockets.connect(ALPACA_WS) as alpaca_ws:
        # 인증
        await alpaca_ws.send(json.dumps({
            "action": "auth",
            "key": ALPACA_API_KEY,
            "secret": ALPACA_SECRET_KEY
        }))

        # 구독
        await alpaca_ws.send(json.dumps({
            "action": "subscribe",
            "trades": tickers
        }))

        # 가격 전달
        async for msg in alpaca_ws:
            data = json.loads(msg)
            await websocket.send_json(data)
```

**프론트:**
```typescript
const ws = new WebSocket('wss://stock-api.../ws/prices');
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    // 포트폴리오 가격 업데이트
    updatePrice(data.ticker, data.price);
};
```

---

## 간단한 방식: Finnhub Polling (추천)

**Finnhub API:**
- 무료: 60콜/분 (2초에 1번)
- REST API로 간단
- WebSocket보다 구현 쉬움

**토큰:** `d5pp5j9r01qq2b68humgd5pp5j9r01qq2b68hun0`

### 구현 방식

```javascript
// 프론트에서 2초마다 폴링
setInterval(async () => {
    for (const ticker of portfolio.tickers) {
        const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${ticker}&token=xxx`);
        const data = await res.json();
        updatePrice(ticker, data.c); // c = current price
    }
}, 2000);
```

### UI 표시
- 가격 옆에 "참고용" 또는 "실시간 아님" 표시
- 예: `$58.54 (참고용)`

### 주의사항
- 보유 종목 5개면 = 5콜/2초 = 150콜/분 (제한 초과!)
- 해결: 종목별 순차 호출 (2초 간격)
- 또는 백엔드에서 캐싱 후 일괄 전달

---

### 대안 (유료)

| 서비스 | 가격 | 특징 |
|--------|------|------|
| Polygon.io | $29/월 | 안정적, 문서 좋음 |
| Finnhub | 무료(제한) | 분당 60콜 |
| IEX Cloud | $9/월 | 사용량 기반 |

### 국내 서비스 현황

| 서비스 | 미국 주식 | API |
|--------|----------|-----|
| 네이버 증권 | ❌ 한국만 | ❌ 스크래핑 |
| 카카오 | ❌ | ❌ |
| 한국투자증권 | ❌ 한국만 | ✅ 한국만 |
| 키움증권 | ❌ 한국만 | ✅ 한국만 |

**결론: 미국 주식 실시간은 Alpaca(무료) 또는 Polygon(유료) 사용**

---

## 환경 변수 추가 필요

```bash
# .env
ALPACA_API_KEY=xxx
ALPACA_SECRET_KEY=xxx
```

---

## 참고 링크

- Alpaca 가입: https://alpaca.markets
- Alpaca WebSocket 문서: https://docs.alpaca.markets/docs/real-time-stock-pricing-data
- FastAPI WebSocket: https://fastapi.tiangolo.com/advanced/websockets/
