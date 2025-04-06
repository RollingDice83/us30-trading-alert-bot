# US30 Telegram Trading Bot – Version v6.9 ✅

from flask import Flask, request
import os
import json
import re
from datetime import datetime

app = Flask(__name__)

VERSION = "v6.9"

TRADES = []
SIGNALS = []
OPEN_PRICE = 44000  # Default – kann per /openprice angepasst werden
STDV_LEVELS = {}

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ------------------------- UTILITIES -------------------------

def send_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return "Missing token or chat_id"
    from urllib import request as urlrequest
    import urllib.parse
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }).encode()
    req = urlrequest.Request(url, data=data)
    urlrequest.urlopen(req)

# ------------------------- STDV ZONES -------------------------

def update_stdv_zones():
    global STDV_LEVELS
    base = OPEN_PRICE
    STDV_LEVELS = {
        f"+{i}%": round(base * (1 + i / 100), 2) for i in range(1, 6)
    }
    STDV_LEVELS.update({
        f"-{i}%": round(base * (1 - i / 100), 2) for i in range(1, 6)
    })

def format_zones():
    msg = f"📊 <b>STDV Zonen (Basis: {OPEN_PRICE})</b>\n"
    for key in sorted(STDV_LEVELS.keys(), key=lambda x: float(x.replace('%',''))):
        msg += f"{key}: {STDV_LEVELS[key]}\n"
    return msg

# ------------------------- SIGNAL ENGINE -------------------------

def parse_signal(text):
    score = 0
    tag = ""
    text_lower = text.lower()

    if "rsi below 30" in text_lower:
        score += 60
        tag = "RSI 30"
    elif "rsi crossing up 30" in text_lower:
        score += 60
        tag = "RSI 30"
    elif "momentum: bullish" in text_lower:
        score += 20
        tag = "Momentum Bullish"
    elif "mss bullish break" in text_lower:
        score += 15
        tag = "MSS Bullish"
    elif re.match(r"^\d{5,6}$", text.strip()):  # Preis z. B. 44300
        score += 10
        tag = f"Grid Signal: {text.strip()}"
    elif "vix crossing" in text_lower:
        num_match = re.search(r"vix crossing (\d+)", text_lower)
        if num_match:
            vix = int(num_match.group(1))
            if vix >= 40:
                score -= 10
            elif vix <= 20:
                score += 5
            tag = f"VIX {vix}"

    if score > 0:
        SIGNALS.append({
            "text": text,
            "score": score,
            "tag": tag,
            "timestamp": datetime.now().isoformat()
        })
        return tag, score
    return None, 0

# ------------------------- COMMAND HANDLERS -------------------------

def handle_status():
    if not TRADES:
        return "📭 Keine offenen Positionen."
    msg = "📈 <b>Offene Positionen</b>\n"
    for t in TRADES:
        msg += f"{t['type']} @ {t['entry']} – TP: {t['tp']} | SL: {t['sl']}\n"
    return msg

def handle_trade(text):
    parts = text.split()
    if len(parts) < 3:
        return "❌ Format: /trade [long|short] [price]"
    direction = parts[1].upper()
    entry = float(parts[2])
    tp = entry + 250 if direction == "LONG" else entry - 250
    sl = entry - 150 if direction == "LONG" else entry + 150
    TRADES.append({"type": direction, "entry": entry, "tp": tp, "sl": sl})
    return f"✅ Trade gespeichert: {direction} @ {entry} (TP: {tp}, SL: {sl})"

def handle_close(text):
    if "all" in text.lower():
        TRADES.clear()
        return "✅ Alle Trades wurden gelöscht."
    price_match = re.search(r"\d{4,6}", text)
    if not price_match:
        return "❌ Bitte gib den Entry-Preis an."
    entry = float(price_match.group())
    for t in TRADES:
        if t['entry'] == entry:
            TRADES.remove(t)
            return f"✅ Trade @ {entry} gelöscht."
    return "❌ Kein Trade mit diesem Preis gefunden."

def handle_signals():
    if not SIGNALS:
        return "ℹ️ Keine aktuellen Signale."
    msg = "📡 <b>Letzte Signale</b>\n"
    for s in SIGNALS[-5:]:
        msg += f"✅ {s['tag']} (Score {s['score']})\n"
    return msg

def handle_help():
    return f"📘 Befehle (v{VERSION}):\n/status – offene Positionen\n/trade – Setup senden\n/close [Preis] – Trade schließen\n/close all – Alle Trades löschen\n/update – STDV aktualisieren\n/openprice [Preis] – STDV Startpreis setzen\n/zones – STDV Zonen anzeigen\n/signals – aktuelle Signale\n/resetsignals – Signal-Reset\n/batch – mehrere Trades\n/stats – Lernstatistik"

def handle_open_price(text):
    global OPEN_PRICE
    price_match = re.search(r"\d{4,6}", text)
    if not price_match:
        return "❌ Ungültiger Preis."
    OPEN_PRICE = int(price_match.group())
    update_stdv_zones()
    return format_zones()

def handle_update():
    update_stdv_zones()
    return format_zones()

def handle_resetsignals():
    SIGNALS.clear()
    return "✅ Signal-Speicher wurde geleert."

def handle_batch(text):
    lines = text.strip().split("\n")
    added = 0
    for l in lines[1:]:
        match = re.match(r"(LONG|SHORT)\s*\|\s*(\d+(\.\d+)?) lot @ (\d+(\.\d+)?)", l.upper())
        if match:
            typ, lot, _, entry, _ = match.groups()
            tp = float(entry) + 250 if typ == "LONG" else float(entry) - 250
            sl = float(entry) - 150 if typ == "LONG" else float(entry) + 150
            TRADES.append({"type": typ, "entry": float(entry), "tp": tp, "sl": sl})
            added += 1
    return f"✅ {added} Trades gespeichert."

def handle_stats():
    count = len(SIGNALS)
    avg_score = round(sum(s['score'] for s in SIGNALS) / count, 2) if count else 0
    return f"📊 Lernstatistik:\nSignale gespeichert: {count}\n⏱ Durchschnittlicher Score: {avg_score}"

# ------------------------- MAIN ROUTES -------------------------

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json()
    if not data or "message" not in data:
        return "ok"

    text = data['message'].get('text', '').strip()
    chat_id = data['message']['chat']['id']

    if text.startswith("/status"):
        msg = handle_status()
    elif text.startswith("/trade"):
        msg = handle_trade(text)
    elif text.startswith("/close"):
        msg = handle_close(text)
    elif text.startswith("/signals"):
        msg = handle_signals()
    elif text.startswith("/help"):
        msg = handle_help()
    elif text.startswith("/zones"):
        msg = format_zones()
    elif text.startswith("/openprice"):
        msg = handle_open_price(text)
    elif text.startswith("/update"):
        msg = handle_update()
    elif text.startswith("/resetsignals"):
        msg = handle_resetsignals()
    elif text.startswith("/batch"):
        msg = handle_batch(text)
    elif text.startswith("/stats"):
        msg = handle_stats()
    else:
        tag, score = parse_signal(text)
        msg = f"✅ Signal erkannt: {tag} (Score {score})" if score > 0 else "❌ Unbekannter Befehl. Nutze /help für alle Kommandos."

    send_message(msg)
    return "ok"

@app.route("/")
def home():
    return f"US30 Bot v{VERSION} läuft."

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return "no data"
    text = data.get("text") or data.get("message")
    if text:
        tag, score = parse_signal(text)
        if score > 0:
            send_message(f"✅ Signal erkannt: {tag} (Score {score})")
    return "ok"

if __name__ == "__main__":
    update_stdv_zones()
    app.run(debug=True)
