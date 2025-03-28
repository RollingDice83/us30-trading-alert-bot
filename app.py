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

active_trades = []
auto_check_thread = None
auto_check_interval = None
auto_check_active = False

# Telegram Nachricht senden
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

# RSI berechnen (1H, Yahoo)
def fetch_rsi(symbol="^DJI", interval="1h", period=14):
    data = yf.download(symbol, period="7d", interval=interval, progress=False)
    if data.empty or len(data["Close"]) < period:
        return None
    delta = data["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi.iloc[-1], 2)

# Analyze ausführen
def handle_analyze(chat_id):
    rsi = fetch_rsi()
    if rsi is None:
        send_message(chat_id, "⚠️ Konnte RSI nicht abrufen.")
        return
    if rsi < 30:
        send_message(chat_id, f"📉 RSI Alert US30 (1H): {rsi} < 30 – Watch für LONG-Möglichkeit")
    elif rsi > 70:
        send_message(chat_id, f"📈 RSI Alert US30 (1H): {rsi} > 70 – Watch für SHORT-Möglichkeit")
    else:
        send_message(chat_id, f"ℹ️ RSI US30 (1H): {rsi} – Kein Extremwert")

# Auto-Check als Thread
def auto_analyze_loop(interval):
    global auto_check_active
    while auto_check_active:
        handle_analyze(TELEGRAM_CHAT_ID)
        time.sleep(interval * 60)

# Analyze Trigger Handler
def handle_analyze_command(user_text, chat_id):
    global auto_check_active, auto_check_thread, auto_check_interval

    if user_text.strip() == "/analyze":
        handle_analyze(chat_id)
        return

    if user_text.startswith("/analyze on"):
        try:
            minutes = int(user_text.split()[2])
            auto_check_interval = minutes
            auto_check_active = True
            auto_check_thread = threading.Thread(target=auto_analyze_loop, args=(minutes,), daemon=True)
            auto_check_thread.start()
            send_message(chat_id, f"⏱️ Auto-Analyse aktiviert: alle {minutes} Minuten.")
        except:
            send_message(chat_id, "⚠️ Fehler beim Starten der Auto-Analyse. Nutze: /analyze on 30")
        return

    if user_text.startswith("/analyze off"):
        auto_check_active = False
        send_message(chat_id, "🛑 Auto-Analyse deaktiviert.")
        return

# Trade-Befehl parsen
def parse_trade_command(text):
    pattern = r"/trade(?=.*\b(?P<symbol>\w+)\b)(?=.*\b(?P<direction>long|short)\b)(?=.*\b(?P<entry>\d+(?:\.\d+)?)\b)(?:.*?SL=(?P<sl>\d+(?:\.\d+)?))?(?:.*?TP=(?P<tp>\d+(?:\.\d+)?))?(?:.*?score=(?P<score>\d+))?(?:.*?tag=(?P<tag>[^\n]+))?"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    data = match.groupdict()
    return {
        "symbol": data["symbol"].upper(),
        "direction": data["direction"].lower(),
        "entry": float(data["entry"]),
        "sl": float(data["sl"]) if data["sl"] else None,
        "tp": float(data["tp"]) if data["tp"] else None,
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

# Trade Command Handler
def handle_trade_command(user_text, chat_id):
    result = parse_trade_command(user_text)
    if not result:
        send_message(chat_id, "❌ Ungültiges Format. Beispiel: /trade US30 long 42650 SL=42500 TP=43000 score=80 tag=Breakout")
        return
    active_trades.append(result)
    msg = f"📥 Neuer Trade-Eingang\n🔹 Symbol: {result['symbol']}\n🔹 Richtung: {result['direction']}\n🔹 Entry: {result['entry']}"
    if result['sl']: msg += f"\n🔹 SL: {result['sl']}"
    if result['tp']: msg += f"\n🔹 TP: {result['tp']}"
    if result['score']: msg += f"\n🔹 Score: {result['score']}/100"
    if result['tag']: msg += f"\n🔹 Tag: {result['tag']}"
    send_message(chat_id, msg)

def handle_close_command(user_text, chat_id):
    symbol, entry, tag = parse_close_command(user_text)
    if not symbol:
        send_message(chat_id, "❌ Bitte gib die Position an, die du schließen willst. Beispiel: /close US30 42650 profit")
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
        send_message(chat_id, "📘 Befehle:\n/status\n/trade\n/close\n/analyze [on <min> | off]\n/help")
    elif user_text.startswith("/trade"):
        handle_trade_command(user_text, chat_id)
    elif user_text.startswith("/close"):
        handle_close_command(user_text, chat_id)
    elif user_text.startswith("/analyze"):
        handle_analyze_command(user_text, chat_id)
    else:
        send_message(chat_id, "❓ Unbekannter Befehl.")
    return jsonify({"status": "ok"}), 200
