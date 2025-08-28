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

@app.route('/add_stock', methods=['POST'])
def add_stock():
    try:
        data = request.get_json(force=True)
        list_name = data.get('list_name')
        stock_name = data.get('stock_name')
        exchange = data.get('exchange')
        trading_symbol = data.get('trading_symbol')
        symbol_token = data.get('symbol_token')
        instrument_type = 'EQ'

        if not all([list_name, stock_name, exchange, trading_symbol, symbol_token]):
            return jsonify({'status': 'error', 'message': 'All fields are required'}), 400

        insert_sql = text("""
            INSERT INTO stocks (list_name, stock_name, exchange, trading_symbol, symbol_token, instrument_type)
            VALUES (:list_name, :stock_name, :exchange, :trading_symbol, :symbol_token, :instrument_type)
        """)
        db.session.execute(insert_sql, {
            'list_name': list_name,
            'stock_name': stock_name,
            'exchange': exchange,
            'trading_symbol': trading_symbol,
            'symbol_token': symbol_token,
            'instrument_type': instrument_type
        })

        update_sql = text("""
            UPDATE lists
            SET stocks = stocks + 1
            WHERE list_name = :list_name
        """)
        db.session.execute(update_sql, {'list_name': list_name})

        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Stock added successfully'})

    except Exception as e:
        db.session.rollback()
        print("Error:", str(e))
        return jsonify({'status': 'error', 'message': 'Server error'}), 500
    
@app.route('/delete_stock', methods=['POST'])
def delete_stock():
    try:
        data = request.get_json(force=True)
        list_name = data.get('list_name')
        trading_symbol = data.get('trading_symbol')

        if not all([list_name, trading_symbol]):
            return jsonify({'status': 'error', 'message': 'List name and trading symbol are required'}), 400

        delete_sql = text("""
            DELETE FROM stocks
            WHERE list_name = :list_name AND trading_symbol = :trading_symbol
        """)
        result = db.session.execute(delete_sql, {
            'list_name': list_name,
            'trading_symbol': trading_symbol
        })

        if result.rowcount == 0:
            return jsonify({'status': 'error', 'message': 'Stock not found in the specified list'}), 404

        update_sql = text("""
            UPDATE lists
            SET stocks = GREATEST(stocks - 1, 0)
            WHERE list_name = :list_name
        """)
        db.session.execute(update_sql, {'list_name': list_name})

        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Stock deleted successfully'})

    except Exception as e:
        db.session.rollback()
        print("Error:", str(e))
        return jsonify({'status': 'error', 'message': 'Server error'}), 500
    
@app.route('/delete_list', methods=['POST'])
def delete_list():
    try:
        data = request.get_json(force=True)
        list_name = data.get('list_name')

        if not list_name:
            return jsonify({'status': 'error', 'message': 'List name is required'}), 400

        delete_sql = text("""
            DELETE FROM lists
            WHERE list_name = :list_name
        """)
        result = db.session.execute(delete_sql, {'list_name': list_name})

        if result.rowcount == 0:
            return jsonify({'status': 'error', 'message': 'List not found'}), 404

        delete_stocks_sql = text("""
            DELETE FROM stocks
            WHERE list_name = :list_name
        """)
        db.session.execute(delete_stocks_sql, {'list_name': list_name})

        db.session.commit()
        return jsonify({'status': 'success', 'message': 'List and associated stocks deleted successfully'})

    except Exception as e:
        db.session.rollback()
        print("Error:", str(e))
        return jsonify({'status': 'error', 'message': 'Server error'}), 500

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
            insert_sql = text("INSERT INTO lists (list_name, stocks) VALUES (:name, :stock)")
            db.session.execute(insert_sql, {'name': name, 'stock': 0})
            db.session.commit()
            return jsonify({
                'status': 'not_found',
                'redirect_url': f"/modify_list.html?list={name}"
            })

    except Exception as e:
        print("Error:", str(e))
        return jsonify({'status': 'error', 'message': 'Server error'}), 500
    

@app.route("/api/lists", methods=["GET"])
def get_lists():
    try:
        sql = text("SELECT list_name, stocks FROM lists")
        result = db.session.execute(sql).fetchall()
        if not result:
            return jsonify([])
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
        from_ts = int((datetime.datetime.now() - datetime.timedelta(days=30)).timestamp() * 1000)
        cached_sql = text("""
            SELECT candle_time, open_price, high_price, low_price, close_price
            FROM candles
            WHERE trading_symbol = :ts AND exchange = :ex AND candle_time >= :from_ts
            ORDER BY candle_time ASC
        """)
        cached_data = db.session.execute(cached_sql, {"ts": trading_symbol, "ex": exchange, "from_ts": from_ts}).fetchall()

        if cached_data:
            candles = [
                {"time": r.candle_time, "open": float(r.open_price), "high": float(r.high_price),
                 "low": float(r.low_price), "close": float(r.close_price)} 
                for r in cached_data
            ]
            return jsonify(candles)

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
        totp = pyotp.TOTP(TOTP_SECRET).now()
        session_data = smartApi.generateSession(CLIENT_ID, PIN, totp)
        if not session_data or not session_data.get("data") or not session_data["data"].get("jwtToken"):
            return jsonify({"error": "Failed to authenticate Smart API session"}), 401

        candle_response = smartApi.getCandleData(symbol_token, "1day")
        candles_raw = candle_response.get("data", {}).get("candle", [])
        if not candles_raw:
            return jsonify({"error": "No candle data found"}), 404

        for candle in candles_raw:
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

        candles = [
            {"time": int(datetime.datetime.strptime(c[0], "%Y-%m-%d").timestamp())*1000,
             "open": float(c[1]), "high": float(c[2]), "low": float(c[3]), "close": float(c[4])}
            for c in candles_raw
        ]
        return jsonify(candles)

    except Exception as e:
        print("Error in /api/candles:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
