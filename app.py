from flask import Flask, request, jsonify
import os
import requests
import re
from datetime import datetime
import math

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Speicher
active_trades = []
open_price = None
stdv_zones = []

# Telegram
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

# /trade parsing
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

# /close parsing
def parse_close_command(text):
    if "/close all" in text:
        return "ALL", None, text.split()[-1] if len(text.split()) > 2 else ""
    pattern = r"/close (?P<symbol>\w+) (?P<entry>\d+(?:\.\d+)?)(?: (?P<tag>\w+))?"
    match = re.match(pattern, text, re.IGNORECASE)
    if not match:
        return None, None, None
    data = match.groupdict()
    return data["symbol"].upper(), float(data["entry"]), data["tag"] or ""

# /batch parsing
def parse_batch_trades(text):
    lines = text.splitlines()
    parsed = []
    for line in lines:
        match = re.match(r"(LONG|SHORT)\s*\|\s*(\d+(\.\d+)?) lot @ (\d+(?:\.\d+)?)(?: \| TP: ([\w.]+))?(?: \| SL: ([\w.]+))?(?: \| Tag: (.+))?", line.strip(), re.IGNORECASE)
        if match:
            direction, size, _, entry, tp, sl, tag = match.groups()
            parsed.append({
                "symbol": "US30",
                "direction": direction.lower(),
                "entry": float(entry),
                "size": float(size),
                "tp": float(tp) if tp and tp.lower() != "open" else None,
                "sl": float(sl) if sl and sl.lower() not in ["none", "manual"] else None,
                "score": None,
                "tag": tag.strip() if tag else ""
            })
    return parsed

# STDV
def set_stdv_zones(base_price):
    global stdv_zones
    stdv_zones = []
    for i in range(1, 6):
        stdv_zones.append(round(base_price * (1 + i / 100), 2))
        stdv_zones.append(round(base_price * (1 - i / 100), 2))

def handle_open_price(text, chat_id):
    global open_price
    try:
        value = float(text.split(" ")[1])
        open_price = value
        set_stdv_zones(open_price)
        send_message(chat_id, f"✅ Opening Price gesetzt auf {open_price}. STDV-Zonen berechnet.")
    except:
        send_message(chat_id, "⚠️ Ungültiger Befehl. Beispiel: /OpenPrice 44100")

def handle_zones(chat_id):
    if not open_price:
        send_message(chat_id, "ℹ️ Kein Opening Price gesetzt.")
        return
    zones = "\n".join([f"{'-' if z < open_price else '+'}{round(abs(z - open_price) / open_price * 100)}% → {z}" for z in sorted(stdv_zones)])
    send_message(chat_id, f"📈 Aktive STDV-Zonen (Basis {open_price}):\n{zones}")

# Commands
def handle_trade_command(user_text, chat_id):
    result = parse_trade_command(user_text)
    if not result:
        send_message(chat_id, "❌ Ungültiges Format. Beispiel: /trade US30 long 42650 SL=42500 TP=43000 score=80 tag=Breakout")
        return
    active_trades.append(result)
    msg = f"📥 Neuer Trade\n{result['symbol']} {result['direction'].upper()} @ {result['entry']}"
    if result['sl']: msg += f" | SL: {result['sl']}"
    if result['tp']: msg += f" | TP: {result['tp']}"
    if result['score']: msg += f" | Score: {result['score']}"
    if result['tag']: msg += f" | Tag: {result['tag']}"
    send_message(chat_id, msg)

def handle_close_command(user_text, chat_id):
    symbol, entry, tag = parse_close_command(user_text)
    if not symbol:
        send_message(chat_id, "❌ Beispiel: /close US30 42650 oder /close all")
        return
    global active_trades
    if symbol == "ALL":
        if entry and entry.lower() in ["long", "short"]:
            filtered = [t for t in active_trades if t['direction'] == entry.lower()]
            active_trades = [t for t in active_trades if t['direction'] != entry.lower()]
            send_message(chat_id, f"🚫 {len(filtered)} {entry}-Positionen geschlossen.")
        else:
            count = len(active_trades)
            active_trades = []
            send_message(chat_id, f"🚫 Alle {count} Positionen geschlossen.")
        return
    original_len = len(active_trades)
    active_trades = [t for t in active_trades if not (t['symbol'] == symbol and t['entry'] == entry)]
    if len(active_trades) < original_len:
        send_message(chat_id, f"💼 Position {symbol} @ {entry} geschlossen. Tag: {tag}")
    else:
        send_message(chat_id, f"⚠️ Keine Position {symbol} @ {entry} gefunden.")

def handle_status(chat_id):
    if not active_trades:
        send_message(chat_id, "📊 Keine offenen Positionen.")
        return
    msg = "📈 Offene Positionen:\n"
    for t in active_trades:
        msg += f"• {t['symbol']} {t['direction'].upper()} @ {t['entry']}"
        if t.get("tp"): msg += f" → TP {t['tp']}"
        if t.get("sl"): msg += f", SL {t['sl']}"
        if t.get("score"): msg += f" (Score {t['score']})"
        if t.get("tag"): msg += f" – {t['tag']}"
        msg += "\n"
    send_message(chat_id, msg)

def handle_update_command(text, chat_id):
    pattern = r"/update (?P<entry>\d+(?:\.\d+)?)(?:.*?SL=(?P<sl>\d+(?:\.\d+)?))?(?:.*?TP=(?P<tp>\d+(?:\.\d+)?))?(?:.*?tag=(?P<tag>[^\n]+))?"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        send_message(chat_id, "❌ Beispiel: /update 42600 SL=42400 TP=43000 tag=Breakout")
        return
    data = match.groupdict()
    entry = float(data["entry"])
    updated = False
    for trade in active_trades:
        if trade["entry"] == entry:
            if data["sl"]: trade["sl"] = float(data["sl"])
            if data["tp"]: trade["tp"] = float(data["tp"])
            if data["tag"]: trade["tag"] = data["tag"]
            updated = True
            break
    if updated:
        send_message(chat_id, f"🔄 Trade @ {entry} aktualisiert.")
    else:
        send_message(chat_id, f"⚠️ Kein Trade bei {entry} gefunden.")

def handle_batch_command(text, chat_id):
    parsed = parse_batch_trades(text)
    if not parsed:
        send_message(chat_id, "⚠️ Keine gültigen Batch-Positionen erkannt.")
        return
    active_trades.extend(parsed)
    send_message(chat_id, f"📦 {len(parsed)} Batch-Trades gespeichert.")

# Webhook
@app.route("/")
def index():
    return "US30Bot läuft ✅"

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
    if user_text.startswith("/status"): handle_status(chat_id)
    elif user_text.startswith("/trade"): handle_trade_command(user_text, chat_id)
    elif user_text.startswith("/close"): handle_close_command(user_text, chat_id)
    elif user_text.startswith("/update"): handle_update_command(user_text, chat_id)
    elif user_text.startswith("/OpenPrice"): handle_open_price(user_text, chat_id)
    elif user_text.startswith("/zones"): handle_zones(chat_id)
    elif user_text.startswith("/batch"): handle_batch_command(user_text, chat_id)
    elif user_text.startswith("/help"):
        send_message(chat_id, "📘 Befehle:\n/status\n/trade\n/close\n/update\n/batch\n/OpenPrice\n/zones\n/help\n\n🧠 Version: Modul 3.3")
    else:
        send_message(chat_id, "❓ Unbekannter Befehl.")
    return jsonify({"status": "ok"}), 200
