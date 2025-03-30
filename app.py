from flask import Flask, request, jsonify
import os, requests, re, json

app = Flask(__name__)

BOT_VERSION = "v3.6b"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

active_trades = []
signal_memory = {}
stdv_zones = {}
open_price = None

# ========== UTILITIES ==========

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    requests.post(url, json=payload)

# ========== HANDLERS ==========

def parse_trade_line(line):
    match = re.match(r"(LONG|SHORT)\s*\|\s*(\d+(?:\.\d+)?) lot @ (\d+(?:\.\d+)?)\s*\|\s*TP: ([\w\.]+)\s*\|\s*SL: ([\w\.]+)\s*\|\s*Tag: (.+)", line, re.IGNORECASE)
    if match:
        direction, lot, entry, tp, sl, tag = match.groups()
        return {
            "symbol": "US30",
            "direction": direction.lower(),
            "entry": float(entry),
            "tp": None if tp.lower() in ['open', 'none'] else float(tp),
            "sl": None if sl.lower() in ['manual', 'none'] else float(sl),
            "score": None,
            "tag": tag.strip(),
            "lot": float(lot)
        }
    return None

def handle_batch(text, chat_id):
    lines = text.split("\n")
    new_trades = []
    for line in lines:
        if "|" in line:
            parsed = parse_trade_line(line)
            if parsed:
                active_trades.append(parsed)
                new_trades.append(parsed)

    if not new_trades:
        send_message(chat_id, "⚠️ Keine gültigen Batch-Positionen erkannt.")
        return

    msg = f"✅ {len(new_trades)} Position(en) übernommen:\n"
    for t in new_trades:
        msg += f"• {t['direction'].upper()} {t['lot']} Lot @ {t['entry']} – {t['tag']}\n"
    send_message(chat_id, msg)

def handle_open_price_command(text, chat_id):
    global open_price, stdv_zones
    match = re.match(r"/openprice (\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if not match:
        send_message(chat_id, "❌ Bitte nutze: /OpenPrice 44100")
        return
    open_price = float(match.group(1))
    stdv_zones = {
        f"-{i}%": round(open_price * (1 - i / 100), 2) for i in range(1, 6)
    }
    stdv_zones.update({
        f"+{i}%": round(open_price * (1 + i / 100), 2) for i in range(1, 6)
    })
    send_message(chat_id, f"📈 Opening Preis gesetzt: {open_price}\nSTDV Zonen aktualisiert.")

def handle_zones(chat_id):
    if not open_price or not stdv_zones:
        send_message(chat_id, "⚠️ Kein Opening Preis gesetzt. Nutze /OpenPrice 44100")
        return
    msg = f"<b>📊 STDV Zonen (ab {open_price}):</b>\n"
    for key in sorted(stdv_zones.keys(), key=lambda x: int(x.replace('%', '').replace('+', '').replace('-', '-'))):
        val = stdv_zones[key]
        color = "🟥" if "-" in key else "🟩"
        msg += f"{color} {key}: <b>{val}</b>\n"
    send_message(chat_id, msg)

def handle_update(chat_id):
    if not open_price:
        send_message(chat_id, "⚠️ Kein Opening Preis gesetzt.")
        return
    handle_open_price_command(f"/OpenPrice {open_price}", chat_id)

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

# ========== ROUTING ==========

@app.route("/", methods=["GET"])
def home():
    return f"US30 Bot {BOT_VERSION} läuft ✅"

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json()
    msg = data.get("message", {})
    text = msg.get("text", "").strip()
    chat_id = msg.get("chat", {}).get("id", "")

    if not text:
        return jsonify({"status": "error"}), 400

    lowered = text.lower()
    if lowered.startswith("/batch"):
        handle_batch(text, chat_id)
    elif lowered.startswith("/openprice"):
        handle_open_price_command(text, chat_id)
    elif lowered.startswith("/zones"):
        handle_zones(chat_id)
    elif lowered.startswith("/update"):
        handle_update(chat_id)
    elif lowered.startswith("/help"):
        handle_help(chat_id)
    else:
        send_message(chat_id, "❓ Unbekannter Befehl. Nutze /help für alle Optionen.")

    return jsonify({"status": "ok"}), 200
