import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
from SmartApi import SmartConnect
from dotenv import load_dotenv
import pyotp
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from flask_cors import CORS
from shooting_star import scan_symbol, get_watchlist, MAX_WORKERS, DEFAULT_LIST_NAME
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['CORS_HEADERS'] = 'application/json'

API_KEY = os.getenv("SMART_API_KEY")
CLIENT_ID = os.getenv("SMART_API_CLIENT_ID")
PIN = os.getenv("SMART_PIN")
TOTP_SECRET = os.getenv("SMART_TOTP_SECRET")

smartApi = SmartConnect(API_KEY)

def ensure_session() -> bool:
    """Login using ClientID + PIN + TOTP. Returns True if session is valid."""
    try:
        totp = pyotp.TOTP(TOTP_SECRET).now()
        data = smartApi.generateSession(CLIENT_ID, PIN, totp)
        return bool(data and data.get("data", {}).get("jwtToken"))
    except Exception as e:
        print("Session error:", e)
        return False

@app.route("/search", methods=["POST"])
def search_stock():
    """Search all stocks by name and return trading symbols."""
    try:
        body = request.get_json(force=True) or {}
        name_query = (body.get("name") or "").strip()
        exchange = (body.get("exchange") or "NSE").strip().upper()

        if not name_query:
            return jsonify({"error": "Please provide a stock name"}), 400

        if not ensure_session():
            return jsonify({"error": "Authentication failed"}), 401

        sr = smartApi.searchScrip(exchange, name_query)
        data = (sr or {}).get("data") or []

        if not data:
            return jsonify({"error": "No matching stocks found"}), 404

        results = []
        for s in data:
            results.append({
                "name": s.get("name") or s.get("tradingsymbol"),
                "tradingsymbol": s.get("tradingsymbol"),
                "symboltoken": s.get("symboltoken")
            })

        return jsonify({"results": results})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/ltp", methods=["POST"])
def get_ltp():
    """Fetch stock name, symbol, last traded price, and last closed price."""
    try:
        body = request.get_json(force=True) or {}
        tradingsymbol = (body.get("tradingsymbol") or "").strip()
        exchange = (body.get("exchange") or "NSE").strip().upper()

        if not tradingsymbol:
            return jsonify({"error": "Please provide tradingsymbol"}), 400

        if not ensure_session():
            return jsonify({"error": "Authentication failed"}), 401

        sr = smartApi.searchScrip(exchange, tradingsymbol)
        data = (sr or {}).get("data") or []

        picked = next((s for s in data if s.get("tradingsymbol") == tradingsymbol), None)
        if not picked:
            return jsonify({"error": "Symbol not found"}), 404

        symboltoken = picked.get("symboltoken")

        # Fetch LTP data
        ltp_resp = smartApi.ltpData(exchange=exchange, tradingsymbol=tradingsymbol, symboltoken=symboltoken)
        ltp_data = ltp_resp.get("data")

        if not ltp_data:
            print("LTP response for debugging:", ltp_resp)
            return jsonify({"error": "Unable to fetch LTP"}), 502

        return jsonify({
            "name": tradingsymbol,
            "symbol": tradingsymbol,
            "price": ltp_data.get("ltp"),
            "last_close": ltp_data.get("close")
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:pass123@localhost/bullion'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

@app.route('/check_name', methods=['POST'])
def check_name():
    try:
        data = request.get_json(force=True)
        name = data.get('name')

        if not name:
            return jsonify({'status': 'error', 'message': 'Name is required'}), 400

        sql = text("SELECT * FROM lists WHERE list_name = :name")
        result = db.session.execute(sql, {'name': name}).fetchone()

        if result:
            return jsonify({'status': 'exists'})
        else:
            stock = 0
            insert_sql = text("INSERT INTO lists (list_name, stocks) VALUES (:name, :stock)")
            db.session.execute(insert_sql, {'name': name, 'stock': stock})
            db.session.commit()
            db.session.execute(text("TRUNCATE TABLE curr_list"))
            db.session.commit()
            insert_sql = text("INSERT INTO curr_list (list_name) VALUES (:name)")
            db.session.execute(insert_sql, {'name': name})
            db.session.commit() 
            return jsonify({'status': 'not_found', 'redirect_url': 'http://127.0.0.1:3000/frontend/createlist.html'})

    except Exception as e:
        print("Error:", str(e))
        return jsonify({'status': 'error', 'message': 'Server error'}), 500


# @app.route('/api/stocks')
# def api_stocks(list_name):  # Problem: Flask won't pass list_name automatically here!
#     sql = text("SELECT list_name FROM curr_list LIMIT 1")
#     list_name = db.session.execute(sql).fetchone()  # This returns a Row, not a string!

#     sql = text("SELECT stock_name, tradingsymbol FROM stocks WHERE list_name = :list_name")
#     result = db.session.execute(sql, {'list_name': list_name}).fetchall()  # Problem: list_name is a Row object
#     stocks = [{'stock_name': r.stock_name, 'tradingsymbol': r.tradingsymbol} for r in result]
#     return jsonify(stocks)

@app.route("/api/lists", methods=["GET"])
def get_lists():
    try:
        sql = text("SELECT list_name, stocks FROM lists")
        result = db.session.execute(sql).fetchall()
        if not result:
            return jsonify([])  # No lists found
        lists = [{"list_name": r.list_name, "stocks": r.stocks} for r in result]
        return jsonify(lists)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/api/list/<list_name>/stocks", methods=["GET"])
def get_list_stocks(list_name):
    try:
        sql = text("SELECT stock_name, exchange, trading_symbol, symbol_token FROM stocks WHERE list_name = :ln")
        result = db.session.execute(sql, {"ln": list_name}).fetchall()
        if not result:
            return jsonify([])
        return jsonify([{"stock_name": r.stock_name, "exchange": r.exchange, "trading_symbol": r.trading_symbol, "symbol_token": r.symbol_token} for r in result])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@app.route("/api/candles/<exchange>/<trading_symbol>", methods=["GET"])
def get_candles(exchange, trading_symbol):
    try:
        # --- Step 1: Check cached candles in DB (last 30 days) ---
        from_ts = int((datetime.datetime.now() - datetime.timedelta(days=30)).timestamp() * 1000)
        cached_sql = text("""
            SELECT candle_time, open_price, high_price, low_price, close_price
            FROM candles
            WHERE trading_symbol = :ts AND exchange = :ex AND candle_time >= :from_ts
            ORDER BY candle_time ASC
        """)
        cached_data = db.session.execute(cached_sql, {"ts": trading_symbol, "ex": exchange, "from_ts": from_ts}).fetchall()

        if cached_data:
            # Return cached data immediately
            candles = [
                {"time": r.candle_time, "open": float(r.open_price), "high": float(r.high_price),
                 "low": float(r.low_price), "close": float(r.close_price)} 
                for r in cached_data
            ]
            return jsonify(candles)

        # --- Step 2: Fetch symbol_token from MySQL ---
        sql = text("""
            SELECT symbol_token 
            FROM stocks 
            WHERE trading_symbol = :ts AND exchange = :ex
            LIMIT 1
        """)
        result = db.session.execute(sql, {"ts": trading_symbol, "ex": exchange}).fetchone()
        if not result:
            return jsonify({"error": "Symbol not found in database"}), 404

        symbol_token = result.symbol_token

        # --- Step 3: Authenticate SmartAPI session ---
        totp = pyotp.TOTP(TOTP_SECRET).now()
        session_data = smartApi.generateSession(CLIENT_ID, PIN, totp)
        if not session_data or not session_data.get("data") or not session_data["data"].get("jwtToken"):
            return jsonify({"error": "Failed to authenticate Smart API session"}), 401

        # --- Step 4: Fetch historical candles from SmartAPI ---
        candle_response = smartApi.getCandleData(symbol_token, "1day")
        candles_raw = candle_response.get("data", {}).get("candle", [])
        if not candles_raw:
            return jsonify({"error": "No candle data found"}), 404

        # --- Step 5: Insert fetched candles into MySQL ---
        for candle in candles_raw:
            # Convert date string to timestamp in ms
            timestamp = int(datetime.datetime.strptime(candle[0], "%Y-%m-%d").timestamp()) * 1000
            db.session.execute(text("""
                INSERT IGNORE INTO candles (trading_symbol, exchange, symbol_token, candle_time, open_price, high_price, low_price, close_price)
                VALUES (:ts, :ex, :token, :time, :open, :high, :low, :close)
            """), {
                "ts": trading_symbol,
                "ex": exchange,
                "token": symbol_token,
                "time": timestamp,
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4])
            })
        db.session.commit()

        # --- Step 6: Return fetched candles ---
        candles = [
            {"time": int(datetime.datetime.strptime(c[0], "%Y-%m-%d").timestamp())*1000,
             "open": float(c[1]), "high": float(c[2]), "low": float(c[3]), "close": float(c[4])}
            for c in candles_raw
        ]
        return jsonify(candles)

    except Exception as e:
        print("Error in /api/candles:", str(e))
        return jsonify({"error": str(e)}), 500


    
# @app.route("/api/candles/<exchange>/<trading_symbol>", methods=["GET"])
# def get_candles(exchange, trading_symbol):
#     try:
#         # --- Fetch symbol_token from MySQL ---
#         sql = text("""
#             SELECT symbol_token 
#             FROM stocks 
#             WHERE trading_symbol = :ts AND exchange = :ex
#             LIMIT 1
#         """)
#         result = db.session.execute(sql, {"ts": trading_symbol, "ex": exchange}).fetchone()
#         if not result:
#             return jsonify({"error": "Symbol not found in database"}), 404

#         symbol_token = result.symbol_token

#         # --- Authenticate SmartAPI session ---
#         totp = pyotp.TOTP(TOTP_SECRET).now()
#         session_data = smartApi.generateSession(CLIENT_ID, PIN, totp)
#         if not session_data or not session_data.get("data") or not session_data["data"].get("jwtToken"):
#             return jsonify({"error": "Failed to authenticate Smart API session"}), 401

#         # --- Fetch candle data ---
#         from_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
#         to_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

#         candle_response = smartApi.getCandleData({
#             "exchange": exchange,
#             "symboltoken": symbol_token,
#             "interval": "ONE_DAY",
#             "fromdate": from_date,
#             "todate": to_date
#         })

#         if isinstance(candle_response, dict):
#             candles_raw = candle_response.get("data", {}).get("candle", [])
#         elif isinstance(candle_response, list):
#             candles_raw = candle_response
#         else:
#             return jsonify({"error": "Unexpected candle data format"}), 502

#         if not candles_raw:
#             return jsonify({"error": "No candle data found"}), 404

#         # --- Transform candles for frontend ---
#         candles = []
#         for candle in candles_raw:
#             try:
#                 timestamp = int(datetime.datetime.strptime(candle[0], "%Y-%m-%dT%H:%M:%S+05:30").timestamp()) * 1000
#             except Exception:
#                 timestamp = int(datetime.datetime.strptime(candle[0], "%Y-%m-%d").timestamp()) * 1000
#             candles.append({
#                 "time": timestamp,
#                 "open": float(candle[1]),
#                 "high": float(candle[2]),
#                 "low": float(candle[3]),
#                 "close": float(candle[4])
#             })

#         return jsonify(candles)

#     except Exception as e:
#         print("Error in /api/candles:", str(e))
#         return jsonify({"error": str(e)}), 500



    
# @app.route("/chart", methods=["POST"])
# def chart():
#     stock_name = request.form.get("stock_name")
#     trading_symbol = request.form.get("trading_symbol")
#     exchange = request.form.get("exchange")
#     symbol_token = request.form.get("symbol_token")

#     if not trading_symbol or not exchange or not symbol_token:
#         return "Stock info missing", 400

#     try:
#         from_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
#         to_date = datetime.datetime.now().strftime("%Y-%m-%d")

#         # Positional arguments
#         historical_data = smartApi.getCandleData(
#             exchange,
#             symbol_token,
#             "1day",
#             from_date,
#             to_date
#         )

#         chart_data = []
#         for candle in historical_data['data']['candle']:
#             timestamp = int(datetime.datetime.strptime(candle[0], "%Y-%m-%d").timestamp())
#             open_, high, low, close = float(candle[1]), float(candle[2]), float(candle[3]), float(candle[4])
#             chart_data.append({
#                 "time": timestamp,
#                 "open": open_,
#                 "high": high,
#                 "low": low,
#                 "close": close
#             })

#         last_close = chart_data[-1]["close"] if chart_data else None
#         ltp_data = smartApi.ltpData(exchange, trading_symbol)
#         current_price = ltp_data.get(trading_symbol, {}).get("ltp", last_close)

#         return render_template(
#             "chart.html",
#             stock_name=stock_name,
#             trading_symbol=trading_symbol,
#             exchange=exchange,
#             symbol_token=symbol_token,
#             chart_data=chart_data,
#             last_close=last_close,
#             current_price=current_price
#         )

#     except Exception as e:
#         return f"Error fetching stock data: {str(e)}", 500



if __name__ == "__main__":
    app.run(debug=True)
