from flask import Flask, request, jsonify
import os
import requests
import re
import threading
import time
import yfinance as yf

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Speicher
active_trades = []
auto_check_interval = 30  # in Minuten

# Telegram senden
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

# Trade-Parsing
def parse_trade_command(text):
    pattern = r"/trade(?=.*\b(?P<symbol>\w+)\b)(?=.*\b(?P<direction>long|short)\b)(?=.*\b(?P<entry>\d+(?:\.\d+)?)\b)(?:.*?SL=(?P<sl>\d+(?:\.\d+)?|manual|none))?(?:.*?TP=(?P<tp>\d+(?:\.\d+)?|open|none))?(?:.*?score=(?P<score>\d+))?(?:.*?tag=(?P<tag>[^\n]+))?"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    data = match.groupdict()
    return {
        "symbol": data["symbol"].upper(),
        "direction": data["direction"].lower(),
        "entry": float(data["entry"]),
        "sl": data["sl"] if data["sl"] not in [None, ""] else None,
        "tp": data["tp"] if data["tp"] not in [None, ""] else None,
        "score": int(data["score"]) if data["score"] else None,
        "tag": data["tag"].strip() if data["tag"] else ""
    }

def parse_close_command(text):
    if "/close all" in text:
        return "ALL", None, text.split()[-1] if len(text.split()) > 2 else ""
    pattern = r"/close (?P<symbol>\w+) (?P<entry>\d+(?:\.\d+)?)(?: (?P<tag>\w+))?"
    match = re.match(pattern, text, re.IGNORECASE)
    if not match:
        return None, None, None
    data = match.groupdict()
    return data["symbol"].upper(), float(data["entry"]), data["tag"] or ""

# RSI-Abfrage
def get_rsi(ticker="^DJI", interval="60m", period="14"):
    df = yf.download(tickers=ticker, interval=interval, period="1d")
    if df.empty or len(df) < int(period):
        return None
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(window=int(period)).mean()
    loss = -delta.clip(upper=0).rolling(window=int(period)).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi.iloc[-1], 2)

# AUTO CHECK TASK
def auto_check_loop():
    while True:
        try:
            rsi = get_rsi()
            if rsi and rsi < 30:
                send_message(TELEGRAM_CHAT_ID, f"📉 RSI-Alarm US30: {rsi} (unter 30!) – Check auf Long-Setup!")
        except Exception as e:
            print("Auto-Check-Fehler:", e)
        time.sleep(auto_check_interval * 60)

threading.Thread(target=auto_check_loop, daemon=True).start()

# Handler
def handle_trade_command(user_text, chat_id):
    result = parse_trade_command(user_text)
    if not result:
        send_message(chat_id, "❌ Ungültiges Format. Beispiel: /trade US30 long 42650 SL=42500 TP=43000 score=80 tag=Breakout")
        return
    active_trades.append(result)
    msg = f"📥 Neuer Trade-Eingang\n🔹 Symbol: {result['symbol']}\n🔹 Richtung: {result['direction']}\n🔹 Entry: {result['entry']}"
    if result['sl']: msg += f"\n🔹 SL: {result['sl']}"
    if result['tp']: msg += f"\n🔹 TP: {result['tp']}"
    if result['score'] is not None: msg += f"\n🔹 Score: {result['score']}/100"
    if result['tag']: msg += f"\n🔹 Tag: {result['tag']}"
    send_message(chat_id, msg)

def handle_close_command(user_text, chat_id):
    symbol, entry, tag = parse_close_command(user_text)
    if not symbol:
        send_message(chat_id, "❌ Beispiel: /close US30 42650 profit oder /close all")
        return
    global active_trades
    if symbol == "ALL":
        if entry and entry.lower() in ["long", "short"]:
            filtered = [t for t in active_trades if t['direction'] == entry.lower()]
            active_trades = [t for t in active_trades if t['direction'] != entry.lower()]
            send_message(chat_id, f"🚫 Alle {entry}-Positionen ({len(filtered)}) geschlossen. Tag: {tag}")
        else:
            count = len(active_trades)
            active_trades = []
            send_message(chat_id, f"🚫 Alle {count} offenen Positionen wurden geschlossen.")
        return
    original_len = len(active_trades)
    active_trades = [t for t in active_trades if not (t['symbol'] == symbol and t['entry'] == entry)]
    if len(active_trades) < original_len:
        send_message(chat_id, f"💼 Position {symbol} bei {entry} wird geschlossen. Tag: {tag}")
    else:
        send_message(chat_id, f"⚠️ Keine Position gefunden mit {symbol} bei {entry}.")

def handle_status(chat_id):
    if not active_trades:
        send_message(chat_id, "📊 Keine offenen Positionen.")
        return
    msg = "📈 Offene Positionen:\n"
    for trade in active_trades:
        msg += f"• {trade['symbol']} {trade['direction']} @ {trade['entry']}"
        if trade['tp']: msg += f" → TP {trade['tp']}"
        if trade['sl']: msg += f", SL {trade['sl']}"
        if trade['score']: msg += f" (Score {trade['score']})"
        if trade['tag']: msg += f" – {trade['tag']}"
        msg += "\n"
    send_message(chat_id, msg)

def handle_batch(text, chat_id):
    lines = text.strip().split("\n")
    count = 0
    for line in lines:
        match = re.match(r"(LONG|SHORT)\s*\|\s*(\d(?:\.\d+)?)\s*lot\s*@\s*(\d+(?:\.\d+)?)\s*\|\s*TP:\s*(\w+)?\s*\|\s*SL:\s*(\w+)?\s*\|\s*Tag:\s*(.*)", line.strip(), re.IGNORECASE)
        if match:
            direction, lot, entry, tp, sl, tag = match.groups()
            active_trades.append({
                "symbol": "US30",
                "direction": direction.lower(),
                "entry": float(entry),
                "tp": tp if tp.lower() != "none" else None,
                "sl": sl if sl.lower() != "none" else None,
                "score": None,
                "tag": tag.strip()
            })
            count += 1
    send_message(chat_id, f"✅ {count} Batch-Trades gespeichert.")

@app.route("/")
def index():
    return "US30-Bot läuft ✅"

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Kein JSON erhalten"}), 400

    message = data.get("message", {})
    if not message:
        return jsonify({"status": "ok"}), 200

    user_text = message.get("text", "")
    chat_id = message["chat"]["id"]

    if user_text.startswith("/status"):
        handle_status(chat_id)
    elif user_text.startswith("/help"):
        send_message(chat_id, "📘 Befehle:\n/status\n/trade SYMBOL long 42500 SL=42250 TP=43000\n/close 42500 oder /close all\n/batch [mehrere Trades]\n/analyze\n/interval 15")
    elif user_text.startswith("/trade"):
        handle_trade_command(user_text, chat_id)
    elif user_text.startswith("/close"):
        handle_close_command(user_text, chat_id)
    elif user_text.startswith("/analyze"):
        rsi = get_rsi()
        if rsi:
            msg = f"📊 RSI US30 (1H): {rsi}"
            if rsi < 30:
                msg += " ⚠️ Unter 30 – Watch für Long!"
            send_message(chat_id, msg)
    elif user_text.startswith("/interval"):
        try:
            global auto_check_interval
            minutes = int(user_text.split()[1])
            auto_check_interval = minutes
            send_message(chat_id, f"⏱️ Intervall für Auto-Check gesetzt: alle {minutes} Minuten.")
        except:
            send_message(chat_id, "❌ Beispiel: /interval 30")
    elif user_text.startswith("/batch"):
        handle_batch(user_text.replace("/batch", "").strip(), chat_id)
    else:
        send_message(chat_id, "❓ Unbekannter Befehl.")

    return jsonify({"status": "ok"}), 200
