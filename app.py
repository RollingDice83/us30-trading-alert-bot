# US30 TradingBot – Modul 3.6

from flask import Flask, request, jsonify
import os, requests, re, json, datetime

app = Flask(__name__)

BOT_VERSION = "v3.6"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
active_trades = []
signal_memory = {}
stdv_zones = {}
open_price = None

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    requests.post(url, json=payload)

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
        "tag": data["tag"].strip() if data["tag"] else "",
        "lot": 1.0
    }

def parse_close_command(text):
    if "/close all" in text:
        return "ALL", None, text.split()[-1] if len(text.split()) > 2 else ""
    match = re.match(r"/close (?P<symbol>\w+) (?P<entry>\d+(?:\.\d+)?)(?: (?P<tag>\w+))?", text, re.IGNORECASE)
    if not match:
        return None, None, None
    data = match.groupdict()
    return data["symbol"].upper(), float(data["entry"]), data["tag"] or ""

def handle_trade_command(user_text, chat_id):
    trade = parse_trade_command(user_text)
    if not trade:
        send_message(chat_id, "❌ Ungültiges Format. Beispiel: /trade US30 long 42650 SL=42500 TP=43000 score=80 tag=Breakout")
        return
    active_trades.append(trade)
    msg = f"📥 Neuer Trade\n<b>{trade['symbol']} {trade['direction'].upper()}</b> @ {trade['entry']:.2f} ({trade['lot']} Lot)"
    if trade['sl']: msg += f"\n🔻 SL: {trade['sl']}"
    if trade['tp']: msg += f"\n🎯 TP: {trade['tp']}"
    if trade['score'] is not None: msg += f"\n📊 Score: {trade['score']}/100"
    if trade['tag']: msg += f"\n🏷️ Tag: {trade['tag']}"
    send_message(chat_id, msg)

def handle_close_command(user_text, chat_id):
    global active_trades
    symbol, entry, tag = parse_close_command(user_text)
    if not symbol:
        send_message(chat_id, "❌ Bitte gib die Position an, z.B. /close US30 42650")
        return
    if symbol == "ALL":
        count = len(active_trades)
        active_trades = []
        send_message(chat_id, f"🛑 Alle {count} offenen Positionen geschlossen.")
        return
    original = len(active_trades)
    active_trades = [t for t in active_trades if not (t['symbol'] == symbol and t['entry'] == entry)]
    closed = original - len(active_trades)
    msg = f"✅ {closed}x Position {symbol} @ {entry} geschlossen. Tag: {tag}" if closed else "⚠️ Keine passende Position gefunden."
    send_message(chat_id, msg)

def handle_status(chat_id):
    if not active_trades:
        send_message(chat_id, "📊 Keine offenen Positionen.")
        return
    longs = [t for t in active_trades if t['direction'] == "long"]
    shorts = [t for t in active_trades if t['direction'] == "short"]
    msg = f"<b>📈 Offene Positionen ({len(active_trades)}):</b>\n"
    if longs:
        msg += "\n<b>🟢 LONGS:</b>\n"
        for t in longs:
            msg += f"• {t['lot']} Lot @ {t['entry']}"
            if t['tp']: msg += f" → TP {t['tp']}"
            if t['sl']: msg += f", SL {t['sl']}"
            if t['tag']: msg += f" – {t['tag']}"
            msg += "\n"
    if shorts:
        msg += "\n<b>🔴 SHORTS:</b>\n"
        for t in shorts:
            msg += f"• {t['lot']} Lot @ {t['entry']}"
            if t['tp']: msg += f" → TP {t['tp']}"
            if t['sl']: msg += f", SL {t['sl']}"
            if t['tag']: msg += f" – {t['tag']}"
            msg += "\n"
    send_message(chat_id, msg)

def handle_help(chat_id):
    msg = f"<b>🤖 US30 Trading Bot – {BOT_VERSION}</b>\n\n"
    msg += "📘 <b>Befehle:</b>\n"
    msg += "/status – offene Positionen\n"
    msg += "/trade – Trade-Setup senden\n"
    msg += "/close – Position schließen\n"
    msg += "/batch – Mehrere Positionen senden\n"
    msg += "/OpenPrice [Preis] – Opening-Preis setzen\n"
    msg += "/zones – STDV Zonen anzeigen\n"
    msg += "/update – STDV Zonen aktualisieren\n"
    msg += "/signals – aktive Signale anzeigen\n"
    msg += "/resetsignals – Signal-Speicher löschen\n"
    msg += "/help – Hilfe anzeigen"
    send_message(chat_id, msg)

def handle_signals(chat_id):
    if not signal_memory:
        send_message(chat_id, "📡 Kein aktives Signal im Speicher.")
        return
    msg = "<b>🧠 Aktive Signale:</b>\n"
    for key, val in signal_memory.items():
        ts = val.get("time", "–")
        score = val.get("score", "–")
        msg += f"• <b>{key}</b>: Score {score} @ {ts}\n"
    send_message(chat_id, msg)

@app.route("/")
def home():
    return f"US30 Bot {BOT_VERSION} läuft ✅"

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json()
    if not data: return jsonify({"status": "error"}), 400
    msg = data.get("message", {})
    text = msg.get("text", "")
    chat_id = msg.get("chat", {}).get("id", "")
    
    if text.lower().startswith("/status"):
        handle_status(chat_id)
    elif text.lower().startswith("/trade"):
        handle_trade_command(text, chat_id)
    elif text.lower().startswith("/close"):
        handle_close_command(text, chat_id)
    elif text.lower().startswith("/signals"):
        handle_signals(chat_id)
    elif text.lower().startswith("/resetsignals"):
        signal_memory.clear()
        send_message(chat_id, "♻️ Alle aktiven Signale wurden gelöscht.")
    elif text.lower().startswith("/help"):
        handle_help(chat_id)
    else:
        send_message(chat_id, "❓ Unbekannter Befehl. Nutze /help für alle Optionen.")

    return jsonify({"status": "ok"}), 200
