from flask import Flask, request, jsonify
import os
import requests
import re
import threading
import time

app = Flask(__name__)

# ENV
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === STATE ===
active_trades = []
signal_context = {
    "momentum_1h": None,
    "momentum_4h": None,
    "rsi": None,
    "mss": None
}
auto_check_interval = 30  # in Minuten
auto_check_active = False
VERSION = "v3.2"

# === UTILS ===
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

def build_score():
    score = 0
    if signal_context["momentum_1h"] == "bullish": score += 25
    if signal_context["momentum_4h"] == "bullish": score += 25
    if signal_context["rsi"] in ["below30", "crossup30"]: score += 25
    if signal_context["mss"] == "bullish": score += 25
    return score

def build_signal_text():
    score = build_score()
    text = f"📊 Neues Long-Setup erkannt\nScore: {score}/100\n"
    if score >= 70:
        text += "✅ High-Quality Signal!\n"
        text += "/trade US30 long 42500 SL=42250 TP=43200 score=85 tag=AutoSignal"
    else:
        text += "⚠️ Frühindikator erkannt, noch kein vollständiges Setup."
    return text

# === COMMAND PARSING ===
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

# === HANDLERS ===
def handle_trade_command(user_text, chat_id):
    result = parse_trade_command(user_text)
    if not result:
        send_message(chat_id, "❌ Ungültiges Format. Beispiel: /trade US30 long 42650 SL=42500 TP=43000 score=80 tag=Breakout")
        return
    active_trades.append(result)
    msg = f"📥 Neuer Trade\n{result['symbol']} {result['direction']} @ {result['entry']}"
    if result['sl']: msg += f" | SL: {result['sl']}"
    if result['tp']: msg += f" | TP: {result['tp']}"
    if result['score']: msg += f" | Score: {result['score']}"
    if result['tag']: msg += f"\n🔖 {result['tag']}"
    send_message(chat_id, msg)

def handle_close_command(user_text, chat_id):
    symbol, entry, tag = parse_close_command(user_text)
    global active_trades
    if symbol == "ALL":
        active_trades.clear()
        send_message(chat_id, "🚫 Alle Positionen wurden geschlossen.")
        return
    original_len = len(active_trades)
    active_trades = [t for t in active_trades if not (t['symbol'] == symbol and t['entry'] == entry)]
    if len(active_trades) < original_len:
        send_message(chat_id, f"✅ {symbol} {entry} geschlossen. Tag: {tag}")
    else:
        send_message(chat_id, f"⚠️ Keine Position gefunden für {symbol} @ {entry}")

def handle_status(chat_id):
    if not active_trades:
        send_message(chat_id, "📊 Keine offenen Positionen.")
        return
    msg = "📈 Aktive Positionen:\n"
    for t in active_trades:
        line = f"{t['symbol']} {t['direction']} @ {t['entry']}"
        if t['tp']: line += f" → TP {t['tp']}"
        if t['sl']: line += f", SL {t['sl']}"
        if t['score']: line += f" (Score {t['score']})"
        if t['tag']: line += f" – {t['tag']}"
        msg += f"• {line}\n"
    send_message(chat_id, msg)

def handle_batch(text, chat_id):
    lines = text.splitlines()
    count = 0
    for line in lines:
        if "|" not in line or line.startswith("/"): continue
        match = re.match(r"(LONG|SHORT)\s*\|\s*(\d+\.?\d*) lot @ (\d+\.?\d*)\s*\|\s*TP: ([\w\.]+)\s*\|\s*SL: ([\w\.]+)\s*\|\s*Tag: (.+)", line, re.IGNORECASE)
        if match:
            direction, lot, entry, tp, sl, tag = match.groups()
            active_trades.append({
                "symbol": "US30",
                "direction": direction.lower(),
                "entry": float(entry),
                "tp": None if tp.lower() in ["none", "open", "manual"] else float(tp),
                "sl": None if sl.lower() in ["none", "manual"] else float(sl),
                "score": None,
                "tag": tag.strip()
            })
            count += 1
    send_message(chat_id, f"✅ {count} Positionen gespeichert.")

# === ANALYZE ===
def handle_analyze(chat_id):
    score = build_score()
    send_message(chat_id, build_signal_text())

def start_auto_check():
    def loop():
        global auto_check_active
        while auto_check_active:
            print("[Auto-Check] Scanning context...")
            if TELEGRAM_CHAT_ID:
                send_message(TELEGRAM_CHAT_ID, "🤖 Auto-Analyse:\n" + build_signal_text())
            time.sleep(auto_check_interval * 60)
    thread = threading.Thread(target=loop)
    thread.daemon = True
    thread.start()

# === ROUTES ===
@app.route("/")
def index():
    return f"US30 Bot {VERSION} ✅"

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json()
    message = data.get("message", {})
    if not message: return jsonify({"status": "ok"}), 200

    text = message.get("text", "")
    chat_id = message["chat"]["id"]

    if text.startswith("/help"):
        send_message(chat_id, f"📘 Hilfe – Version {VERSION}\n/status\n/trade\n/close\n/batch\n/analyze\n/startauto\n/stopauto")
    elif text.startswith("/status"):
        handle_status(chat_id)
    elif text.startswith("/trade"):
        handle_trade_command(text, chat_id)
    elif text.startswith("/close"):
        handle_close_command(text, chat_id)
    elif text.startswith("/batch"):
        handle_batch(text, chat_id)
    elif text.startswith("/analyze"):
        handle_analyze(chat_id)
    elif text.startswith("/startauto"):
        global auto_check_active
        auto_check_active = True
        start_auto_check()
        send_message(chat_id, f"⏱️ Auto-Analyse aktiviert: alle {auto_check_interval} Minuten.")
    elif text.startswith("/stopauto"):
        auto_check_active = False
        send_message(chat_id, "⛔ Auto-Analyse gestoppt.")
    else:
        send_message(chat_id, "❓ Unbekannter Befehl.")

    return jsonify({"status": "ok"}), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_data(as_text=True).lower()

    if "bullish 1h" in data: signal_context["momentum_1h"] = "bullish"
    elif "bearish 1h" in data: signal_context["momentum_1h"] = "bearish"

    if "bullish 4h" in data: signal_context["momentum_4h"] = "bullish"
    elif "bearish 4h" in data: signal_context["momentum_4h"] = "bearish"

    if "crossing up 30" in data: signal_context["rsi"] = "crossup30"
    elif "below 30" in data: signal_context["rsi"] = "below30"
    elif "above 70" in data: signal_context["rsi"] = "above70"
    elif "crossing down 70" in data: signal_context["rsi"] = "crossdown70"

    if "mss bullish" in data: signal_context["mss"] = "bullish"
    elif "mss bearish" in data: signal_context["mss"] = "bearish"

    return jsonify({"status": "signal received"}), 200

@app.route("/signalstatus")
def signalstatus():
    return jsonify(signal_context)
