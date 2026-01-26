"""
lib/options.py - 옵션 체인 분석
콜/풋 OI, Max Pain, 감마 집중 구간
"""


def get_options_data(stock) -> dict:
    """옵션 체인 분석 (감마 스퀴즈 가능성)"""
    options_info = {
        "has_options": False,
        "nearest_expiry": None,
        "total_call_oi": 0,
        "total_put_oi": 0,
        "put_call_ratio": 0,
        "max_pain": 0,
        "gamma_exposure": [],
        "itm_calls": 0,
        "strikes_analysis": [],
    }

    try:
        expirations = stock.options
        if not expirations:
            return options_info

        options_info["has_options"] = True
        options_info["nearest_expiry"] = expirations[0]

        current_price = stock.info.get('regularMarketPrice', 0) or stock.info.get('currentPrice', 0)

        opt = stock.option_chain(expirations[0])
        calls = opt.calls
        puts = opt.puts

        if not calls.empty:
            options_info["total_call_oi"] = int(calls['openInterest'].sum())
            itm_calls = calls[calls['strike'] < current_price]
            options_info["itm_calls"] = int(itm_calls['openInterest'].sum()) if not itm_calls.empty else 0

            top_strikes = calls.nlargest(5, 'openInterest')[['strike', 'openInterest']]
            options_info["gamma_exposure"] = [
                {"strike": row['strike'], "oi": int(row['openInterest'])}
                for _, row in top_strikes.iterrows()
            ]

        if not puts.empty:
            options_info["total_put_oi"] = int(puts['openInterest'].sum())

        if options_info["total_call_oi"] > 0:
            options_info["put_call_ratio"] = round(
                options_info["total_put_oi"] / options_info["total_call_oi"], 2
            )

        # Max Pain 계산
        if not calls.empty and not puts.empty:
            all_strikes = sorted(set(calls['strike'].tolist() + puts['strike'].tolist()))
            min_pain = float('inf')
            max_pain_strike = 0

            for strike in all_strikes:
                call_pain = calls[calls['strike'] < strike]['openInterest'].sum() * (strike - calls[calls['strike'] < strike]['strike']).sum() if not calls[calls['strike'] < strike].empty else 0
                put_pain = puts[puts['strike'] > strike]['openInterest'].sum() * (puts[puts['strike'] > strike]['strike'] - strike).sum() if not puts[puts['strike'] > strike].empty else 0
                total_pain = call_pain + put_pain

                if total_pain < min_pain:
                    min_pain = total_pain
                    max_pain_strike = strike

            options_info["max_pain"] = max_pain_strike

    except Exception as e:
        print(f"    ⚠️ 옵션 분석 오류: {e}")

    return options_info
