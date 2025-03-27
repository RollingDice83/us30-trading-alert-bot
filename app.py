from flask import Flask, request, jsonify
import os
import requests
import re
import threading
import time

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

active_trades = []
auto_analysis_interval = 30  # in Minuten
analysis_thread_active = False

# --- Hilfsfunktionen ---
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

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

def parse_modify_command(text):
    pattern = r"/modify\s+(?P<symbol>\w+)\s+(?P<entry>\d+(?:\.\d+)?)(?:.*?SL=(?P<sl>\d+(?:\.\d+)?))?(?:.*?TP=(?P<tp>\d+(?:\.\d+)?))?"
    match = re.search(pattern, text, re.IGNORECASE)
    return match.groupdict() if match else None

def parse_close_command(text):
    if "/close all" in text:
        return "ALL", None, text.split()[-1] if len(text.split()) > 2 else ""
    pattern = r"/close (?P<symbol>\w+) (?P<entry>\d+(?:\.\d+)?)(?: (?P<tag>\w+))?"
    match = re.match(pattern, text, re.IGNORECASE)
    if not match:
        return None, None, None
    data = match.groupdict()
    return data["symbol"].upper(), float(data["entry"]), data["tag"] or ""

def parse_analyze_command(text):
    match = re.match(r"/analyze(?:\s+(?P<interval>\d+))?", text)
    return int(match.group("interval")) if match and match.group("interval") else None

# --- Hauptfunktionen ---
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

def handle_modify_command(user_text, chat_id):
    params = parse_modify_command(user_text)
    if not params or not params["symbol"] or not params["entry"]:
        send_message(chat_id, "❌ Beispiel: /modify US30 42650 SL=42500 TP=43000")
        return

    symbol = params["symbol"].upper()
    entry = float(params["entry"])
    modified = False

    for trade in active_trades:
        if trade["symbol"] == symbol and trade["entry"] == entry:
            if params["sl"]:
                trade["sl"] = float(params["sl"])
                modified = True
            if params["tp"]:
                trade["tp"] = float(params["tp"])
                modified = True

    if modified:
        send_message(chat_id, f"🔧 Trade {symbol} bei {entry} angepasst.")
    else:
        send_message(chat_id, f"⚠️ Keine passende Position gefunden.")

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

# --- Analysefunktionen (MOCK) ---
def get_mock_rsi():
    return 28

def check_mock_structure():
    return True

def perform_analysis():
    rsi = get_mock_rsi()
    mss_break = check_mock_structure()

    if rsi < 30 and mss_break:
        send_message(TELEGRAM_CHAT_ID, "📊 SIGNAL: RSI < 30 + MSS Break erkannt!\n✅ Score: 80")

# --- Auto-Analyse Scheduler ---
def analysis_scheduler():
    global analysis_thread_active
    analysis_thread_active = True
    while analysis_thread_active:
        perform_analysis()
        time.sleep(auto_analysis_interval * 60)

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
        send_message(chat_id, "📘 Befehle:\n/status – zeigt offenen Trades\n/trade – sendet Trade-Setup\n/close – Position schließen (/close all, /close all long, etc.)\n/modify – SL/TP anpassen\n/analyze [optional: Intervall in Minuten] – Marktanalyse starten\n/help – Hilfe anzeigen")
    elif user_text.startswith("/trade"):
        handle_trade_command(user_text, chat_id)
    elif user_text.startswith("/close"):
        handle_close_command(user_text, chat_id)
    elif user_text.startswith("/modify"):
        handle_modify_command(user_text, chat_id)
    elif user_text.startswith("/analyze"):
        global auto_analysis_interval, analysis_thread_active
        interval = parse_analyze_command(user_text)
        if interval:
            auto_analysis_interval = interval
            send_message(chat_id, f"🔁 Analyse-Intervall auf {interval} Minuten gesetzt.")
        if not analysis_thread_active:
            threading.Thread(target=analysis_scheduler, daemon=True).start()
            send_message(chat_id, "📊 Automatische Marktanalyse gestartet.")
        else:
            perform_analysis()
    else:
        send_message(chat_id, "❓ Unbekannter Befehl.")

    return jsonify({"status": "ok"}), 200
