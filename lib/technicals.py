"""
lib/technicals.py - 기술적 지표
RSI, MACD, 볼린저밴드, 피보나치, 볼륨프로파일
"""

import pandas as pd


def get_technicals(stock) -> dict:
    """기술적 지표 계산"""
    try:
        hist = stock.history(period="3mo")

        if hist.empty:
            return {}

        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]
        volume = hist["Volume"]

        # RSI (14일, Wilder EMA - 업계 표준)
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = (-delta.where(delta < 0, 0))
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - signal

        # 볼린저 밴드
        sma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        bb_upper = sma20 + (std20 * 2)
        bb_lower = sma20 - (std20 * 2)

        current = close.iloc[-1]
        bb_position = ((current - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1])) * 100 if bb_upper.iloc[-1] != bb_lower.iloc[-1] else 50

        # ATR
        tr = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()

        # 거래량 비율
        vol_ratio = volume.iloc[-1] / volume.rolling(window=20).mean().iloc[-1] if volume.rolling(window=20).mean().iloc[-1] > 0 else 1

        return {
            "rsi": rsi.iloc[-1],
            "macd": macd.iloc[-1],
            "macd_signal": signal.iloc[-1],
            "macd_hist": macd_hist.iloc[-1],
            "bb_upper": bb_upper.iloc[-1],
            "bb_middle": sma20.iloc[-1],
            "bb_lower": bb_lower.iloc[-1],
            "bb_position": bb_position,
            "atr": atr.iloc[-1],
            "atr_pct": (atr.iloc[-1] / current) * 100,
            "vol_ratio": vol_ratio,
            "sma_20": sma20.iloc[-1],
            "sma_50": close.rolling(window=50).mean().iloc[-1] if len(close) >= 50 else None,
            # 가격 변화
            "change_1d": ((close.iloc[-1] / close.iloc[-2]) - 1) * 100 if len(close) >= 2 else 0,
            "change_5d": ((close.iloc[-1] / close.iloc[-5]) - 1) * 100 if len(close) >= 5 else 0,
            "change_20d": ((close.iloc[-1] / close.iloc[-20]) - 1) * 100 if len(close) >= 20 else 0,
        }
    except Exception as e:
        print(f"  ⚠️ 기술적 분석 실패: {e}")
        return {}


def get_fibonacci_levels(stock) -> dict:
    """피보나치 되돌림 레벨 계산"""
    fib_info = {
        "levels": {},
        "current_zone": None,
        "support_levels": [],
        "resistance_levels": [],
        "gaps": [],
    }

    try:
        hist = stock.history(period="6mo")
        if hist.empty:
            return fib_info

        high = hist['High'].max()
        low = hist['Low'].min()
        current = hist['Close'].iloc[-1]
        diff = high - low

        fib_levels = {
            "0%": high,
            "23.6%": high - diff * 0.236,
            "38.2%": high - diff * 0.382,
            "50%": high - diff * 0.5,
            "61.8%": high - diff * 0.618,
            "78.6%": high - diff * 0.786,
            "100%": low,
        }
        fib_info["levels"] = {k: round(v, 2) for k, v in fib_levels.items()}

        for level_name, level_price in fib_levels.items():
            if current >= level_price:
                fib_info["current_zone"] = f"{level_name} 위"
                break

        for level_name, level_price in fib_levels.items():
            if level_price < current:
                fib_info["support_levels"].append({
                    "level": level_name,
                    "price": round(level_price, 2),
                    "distance": f"{((current - level_price) / current * 100):.1f}%"
                })
            elif level_price > current:
                fib_info["resistance_levels"].append({
                    "level": level_name,
                    "price": round(level_price, 2),
                    "distance": f"{((level_price - current) / current * 100):.1f}%"
                })

        # 갭 분석 (최근 20일)
        recent = hist.tail(20)
        for i in range(1, len(recent)):
            prev_close = recent['Close'].iloc[i-1]
            curr_open = recent['Open'].iloc[i]
            curr_high = recent['High'].iloc[i]
            curr_low = recent['Low'].iloc[i]

            if curr_open > prev_close * 1.02:
                gap_filled = curr_low <= prev_close
                fib_info["gaps"].append({
                    "type": "갭업",
                    "date": str(recent.index[i].date()),
                    "gap_start": round(prev_close, 2),
                    "gap_end": round(curr_open, 2),
                    "filled": "충전됨" if gap_filled else "미충전"
                })
            elif curr_open < prev_close * 0.98:
                gap_filled = curr_high >= prev_close
                fib_info["gaps"].append({
                    "type": "갭다운",
                    "date": str(recent.index[i].date()),
                    "gap_start": round(curr_open, 2),
                    "gap_end": round(prev_close, 2),
                    "filled": "충전됨" if gap_filled else "미충전"
                })

    except Exception as e:
        print(f"    ⚠️ 피보나치 오류: {e}")

    return fib_info


def get_volume_profile(stock) -> dict:
    """가격대별 거래량 분석"""
    vp_info = {
        "high_volume_zones": [],
        "poc": None,
        "value_area_high": None,
        "value_area_low": None,
    }

    try:
        hist = stock.history(period="3mo")
        if hist.empty or len(hist) < 20:
            return vp_info

        price_min = hist['Low'].min()
        price_max = hist['High'].max()
        num_bins = 20
        bin_size = (price_max - price_min) / num_bins

        volume_by_price = {}

        for i in range(len(hist)):
            avg_price = (hist['High'].iloc[i] + hist['Low'].iloc[i]) / 2
            volume = hist['Volume'].iloc[i]

            bin_idx = int((avg_price - price_min) / bin_size)
            bin_idx = min(bin_idx, num_bins - 1)
            bin_price = price_min + bin_idx * bin_size + bin_size / 2

            if bin_price not in volume_by_price:
                volume_by_price[bin_price] = 0
            volume_by_price[bin_price] += volume

        if volume_by_price:
            poc_price = max(volume_by_price, key=volume_by_price.get)
            vp_info["poc"] = round(poc_price, 2)

            sorted_zones = sorted(volume_by_price.items(), key=lambda x: x[1], reverse=True)
            vp_info["high_volume_zones"] = [
                {"price": round(price, 2), "volume": int(vol)}
                for price, vol in sorted_zones[:5]
            ]

            total_vol = sum(volume_by_price.values())
            target_vol = total_vol * 0.7
            cumulative = 0

            va_prices = [poc_price]
            remaining = {k: v for k, v in volume_by_price.items() if k != poc_price}
            cumulative = volume_by_price[poc_price]

            while cumulative < target_vol and remaining:
                next_price = max(remaining, key=remaining.get)
                va_prices.append(next_price)
                cumulative += remaining[next_price]
                del remaining[next_price]

            vp_info["value_area_high"] = round(max(va_prices), 2)
            vp_info["value_area_low"] = round(min(va_prices), 2)

    except Exception as e:
        print(f"    ⚠️ 볼륨 프로파일 오류: {e}")

    return vp_info
