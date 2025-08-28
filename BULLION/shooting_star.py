import os
import time
import datetime as dt
from flask import Flask, request, jsonify
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor, as_completed
import pyotp
from SmartApi import SmartConnect
import mysql.connector

# ---------------- CONFIG ----------------
DEFAULT_LIST_NAME = "bull"
LOOKBACK_DAYS = 30
ENTRY_BUFFER = 0.001
RISK_REWARD = 2.0
MAX_WORKERS = 3  # Reduce to avoid API rate limit

API_KEY = os.getenv("SMART_API_KEY")
CLIENT_ID = os.getenv("SMART_API_CLIENT_ID")
PIN = os.getenv("SMART_PIN")
TOTP_SECRET = os.getenv("SMART_TOTP_SECRET")

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

INTERVAL = "ONE_DAY"

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

smartApi = SmartConnect(API_KEY)

def ensure_session():
    """Check and create valid SmartAPI session."""
    try:
        totp = pyotp.TOTP(TOTP_SECRET).now()
        data = smartApi.generateSession(CLIENT_ID, PIN, totp)
        return bool(data and data.get("data", {}).get("jwtToken"))
    except Exception as e:
        print("Auth error:", e)
        return False

def get_watchlist(list_name=DEFAULT_LIST_NAME):
    """Fetch all stocks from DB for given list_name."""
    cnx = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )
    try:
        cur = cnx.cursor(dictionary=True)
        cur.execute(
            "SELECT exchange, trading_symbol, symbol_token FROM stocks WHERE list_name = %s",
            (list_name,)
        )
        return cur.fetchall()
    finally:
        cnx.close()

def is_uptrend(candles):
    """Check if last 5 closes show uptrend."""
    if len(candles) < 5:
        return False
    closes = [c["close"] for c in candles[-5:]]
    return all(closes[i] > closes[i-1] for i in range(1, 5))

def is_shooting_star(candle):
    """Check Shooting Star pattern."""
    o, h, l, c = candle["open"], candle["high"], candle["low"], candle["close"]
    body = abs(c - o)
    if body == 0:
        return False
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    return upper_shadow >= 2 * body and lower_shadow <= 0.1 * body and c < o

def compute_levels(low, high):
    entry = low * (1.0 - ENTRY_BUFFER)
    stop  = high
    risk  = stop - entry
    target = entry - RISK_REWARD * risk
    return round(entry, 2), round(stop, 2), round(target, 2)

def get_symboltoken(exchange, trading_symbol, token_from_db=None):
    if token_from_db:
        return token_from_db
    try:
        sr = smartApi.searchScrip(exchange, trading_symbol)
        data = (sr or {}).get("data") or []
        for s in data:
            if s.get("trading_symbol") == trading_symbol:
                return s.get("symboltoken")
    except Exception as e:
        print(f"Token fetch error for {trading_symbol}: {e}")
    return None

def get_daily_candles(exchange, token, days=LOOKBACK_DAYS):
    """Fetch historical daily candles with rate-limit handling."""
    try:
        to_dt = dt.datetime.now()
        from_dt = to_dt - dt.timedelta(days=days + 5)
        payload = {
            "exchange": exchange,
            "symboltoken": str(token),
            "interval": INTERVAL,
            "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
            "todate": to_dt.strftime("%Y-%m-%d %H:%M"),
        }
        time.sleep(0.5)
        candles = smartApi.getCandleData(payload)
        data = (candles or {}).get("data") or []
        return [{"time": r[0], "open": float(r[1]), "high": float(r[2]),
                 "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])} for r in data]
    except Exception as e:
        print(f"Candle fetch error for token {token}: {e}")
        return []

def scan_symbol(exchange, trading_symbol, token_from_db=None):
    token = get_symboltoken(exchange, trading_symbol, token_from_db)
    if not token:
        return {"symbol": trading_symbol, "eligible": False, "reason": "token_not_found"}
    
    candles = get_daily_candles(exchange, token)
    if len(candles) < 10:
        return {"symbol": trading_symbol, "eligible": False, "reason": "not_enough_candles"}

    last_candle = candles[-1]
    prev_candles = candles[:-1]

    if not is_uptrend(prev_candles[-6:]):
        return {"symbol": trading_symbol, "eligible": False, "reason": "no_uptrend"}

    if not is_shooting_star(last_candle):
        return {"symbol": trading_symbol, "eligible": False, "reason": "no_shooting_star"}

    entry, stop, target = compute_levels(last_candle["low"], last_candle["high"])
    return {
        "symbol": trading_symbol,
        "eligible": True,
        "pattern": "Shooting Star",
        "candle_time": last_candle["time"],
        "entry_sell": entry,
        "stop_loss": stop,
        "target": target
    }

@app.route("/api/shooting_star", methods=["POST"])
def api_shooting_star():
    data = request.get_json(force=True) or {}
    list_name = data.get("list") or DEFAULT_LIST_NAME

    if not ensure_session():
        return jsonify({"error": "Auth failed"}), 401

    symbols = get_watchlist(list_name)
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(scan_symbol, s["exchange"], s["trading_symbol"], s["symbol_token"]) for s in symbols]
        for fut in as_completed(futures):
            results.append(fut.result())

    eligible = [r for r in results if r.get("eligible")]
    rejected = [r for r in results if not r.get("eligible")]

    return jsonify({
        "eligible": eligible,
        "rejected": rejected,
        "count": {
            "eligible": len(eligible),
            "rejected": len(rejected),
            "total": len(results)
        }
    })

if __name__ == "__main__":
    app.run(debug=True, port=5005)
