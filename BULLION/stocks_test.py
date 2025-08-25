from shooting_star import is_uptrend, is_shooting_star, compute_levels
import datetime as dt

# ---------------- Dummy candles ----------------
def get_dummy_candles_for_stock(stock_symbol):
    """Return dummy candles with clear patterns for testing."""

    # Uptrend + Shooting Star (eligible)
    if stock_symbol in ["ICICIBANK-EQ", "TCS-EQ"]:
        prev = [{"time": f"2025-08-1{i} 00:00", "open": 100+i, "high": 101+i, "low": 99+i, "close": 100+i, "volume": 1000+i} for i in range(6)]
        last = {"time": "2025-08-17 00:00", "open": 107, "high": 110, "low": 106.9, "close": 106.8, "volume": 1200}
        return prev + [last]

    # Uptrend but no Shooting Star
    if stock_symbol in ["RELIANCE-EQ", "INFY-EQ"]:
        prev = [{"time": f"2025-08-1{i} 00:00", "open": 100+i, "high": 101+i, "low": 99+i, "close": 100+i, "volume": 1000+i} for i in range(6)]
        last = {"time": "2025-08-17 00:00", "open": 107, "high": 108, "low": 106.5, "close": 107, "volume": 1200}
        return prev + [last]

    # No uptrend
    if stock_symbol in ["SBIN-EQ", "HDFCBANK-EQ"]:
        prev = [{"time": f"2025-08-1{i} 00:00", "open": 100-i, "high": 101-i, "low": 99-i, "close": 100-i, "volume": 1000+i} for i in range(6)]
        last = {"time": "2025-08-17 00:00", "open": 95, "high": 96, "low": 94, "close": 95, "volume": 1200}
        return prev + [last]

# ---------------- Test Function ----------------
def test_shooting_star():
    with open("BULLION\dummy_stocks.txt") as f:
        stocks = [line.strip().split(",") for line in f.readlines()]

    results = []

    for symbol, exchange, token in stocks:
        candles = get_dummy_candles_for_stock(symbol)
        last_candle = candles[-1]
        prev_candles = candles[:-1]

        eligible = False
        reason = ""

        if not is_uptrend(prev_candles):
            reason = "no_uptrend"
        elif not is_shooting_star(last_candle):
            reason = "no_shooting_star"
        else:
            eligible = True
            reason = "eligible"
            entry, stop, target = compute_levels(last_candle["low"], last_candle["high"])

        results.append({
            "symbol": symbol,
            "eligible": eligible,
            "reason": reason,
            **({"entry_sell": entry, "stop_loss": stop, "target": target} if eligible else {})
        })
        
    for r in results:
        print(r)

if __name__ == "__main__":
    test_shooting_star()
