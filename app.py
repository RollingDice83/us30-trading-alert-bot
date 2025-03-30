from flask import Flask, request, jsonify
import os, json, re, requests
from datetime import datetime

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BOT_VERSION = "v3.6"

active_trades = []
stdv_zones = {}
signal_memory = []

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def load_opening_price():
    try:
        with open("stdv_open.json", "r") as f:
            return float(json.load(f).get("open_price", 0))
    except:
        return 0

def save_opening_price(price):
    with open("stdv_open.json", "w") as f:
        json.dump({"open_price": price}, f)

def calculate_stdv(price):
    global stdv_zones
    stdv_zones = {
        "+1%": round(price * 1.01, 2),
        "+2%": round(price * 1.02, 2),
        "+3%": round(price * 1.03, 2),
        "+4%": round(price * 1.04, 2),
        "+5%": round(price * 1.05, 2),
        "-1%": round(price * 0.99, 2),
        "-2%": round(price * 0.98, 2),
        "-3%": round(price * 0.97, 2),
        "-4%": round(price * 0.96, 2),
        "-5%": round(price * 0.95, 2),
    }

@app.route("/")
def index():
    return "US30-Bot läuft ✅"

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"status": "ok"})

    msg = data["message"]
    text = msg.get("text", "")
    chat_id = msg["chat"]["id"]

    if text.startswith("/start") or text.startswith("/help"):
        send_message(chat_id, f"📘 Befehle (Version {BOT_VERSION}):\n"
                              "/status – offene Positionen\n"
                              "/trade – Trade-Setup senden\n"
                              "/close – Position schließen\n"
                              "/update – STDV Zonen aktualisieren\n"
                              "/OpenPrice [Preis] – Opening Preis setzen\n"
                              "/zones – STDV Zonen anzeigen\n"
                              "/resetsignals – Signal-Speicher leeren\n"
                              "/signals – aktuelle Signals anzeigen\n"
                              "/batch – mehrere Trades senden")
    elif text.startswith("/status"):
        handle_status(chat_id)
    elif text.startswith("/trade"):
        handle_trade(text, chat_id)
    elif text.startswith("/close"):
        handle_close(text, chat_id)
    elif text.startswith("/OpenPrice"):
        try:
            price = float(text.split()[1])
            save_opening_price(price)
            calculate_stdv(price)
            send_message(chat_id, f"📌 Opening Price gesetzt: <b>{price}</b>")
        except:
            send_message(chat_id, "⚠️ Formatfehler. Beispiel: /OpenPrice 44100")
    elif text.startswith("/update"):
        price = load_opening_price()
        if price:
            calculate_stdv(price)
            send_message(chat_id, f"🔄 STDV Zonen aktualisiert auf Basis von: {price}")
        else:
            send_message(chat_id, "⚠️ Kein Opening Price gesetzt.")
    elif text.startswith("/zones"):
        if not stdv_zones:
            send_message(chat_id, "⚠️ Keine Zonen berechnet. Nutze /OpenPrice zuerst.")
        else:
            msg = "<b>📊 Aktuelle STDV-Zonen</b>\n"
            msg += f"<i>Opening:</i> <b>{load_opening_price()}</b>\n\n"
            for k, v in sorted(stdv_zones.items(), reverse=True):
                color = "🟩" if "+" in k else "🟥"
                msg += f"{color} {k}: {v}\n"
            send_message(chat_id, msg)
    elif text.startswith("/resetsignals"):
        signal_memory.clear()
        send_message(chat_id, "🧠 Signal-Speicher wurde geleert.")
    elif text.startswith("/signals"):
        if not signal_memory:
            send_message(chat_id, "📭 Keine aktiven Signale gespeichert.")
        else:
            msg = "<b>🧠 Aktive Signale:</b>\n" + "\n".join([f"• {s}" for s in signal_memory[-20:]])
            send_message(chat_id, msg)
    elif text.startswith("/batch"):
        handle_batch(text, chat_id)
    else:
        # Optional: Signal-Impuls als Text (für Tests)
        signal_memory.append(text.strip())
        send_message(chat_id, f"📡 Signal gespeichert: {text.strip()}")

    return jsonify({"status": "ok"})

# ==== Handler ====

def handle_trade(text, chat_id):
    match = re.search(r"/trade\s+(\w+)\s+(long|short)\s+(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if not match:
        send_message(chat_id, "❌ Formatfehler. Beispiel: /trade US30 long 42500 SL=42250 TP=43200 score=85 tag=Breakout")
        return
    symbol, direction, entry = match.groups()
    sl = extract_value(text, "SL")
    tp = extract_value(text, "TP")
    score = extract_value(text, "score", as_int=True)
    tag = extract_tag(text)
    trade = {
        "symbol": symbol.upper(),
        "direction": direction.lower(),
        "entry": float(entry),
        "sl": sl,
        "tp": tp,
        "score": score,
        "tag": tag,
        "lot": 1
    }
    active_trades.append(trade)
    send_message(chat_id, f"✅ Trade gespeichert: {symbol.upper()} {direction} @ {entry}\n"
                          f"SL: {sl or '—'} | TP: {tp or '—'} | Score: {score or '—'} | Tag: {tag or '—'}")

def handle_status(chat_id):
    if not active_trades:
        send_message(chat_id, "📊 Keine offenen Positionen.")
        return
    msg = "📈 <b>Offene Positionen:</b>\n"
    longs = [t for t in active_trades if t["direction"] == "long"]
    shorts = [t for t in active_trades if t["direction"] == "short"]
    if longs:
        msg += "\n🟩 <b>Longs:</b>\n"
        for t in longs:
            msg += f"• {t['lot']} lot @ {t['entry']} | TP: {t['tp'] or '—'} | SL: {t['sl'] or '—'} | Tag: {t['tag']}\n"
    if shorts:
        msg += "\n🟥 <b>Shorts:</b>\n"
        for t in shorts:
            msg += f"• {t['lot']} lot @ {t['entry']} | TP: {t['tp'] or '—'} | SL: {t['sl'] or '—'} | Tag: {t['tag']}\n"
    send_message(chat_id, msg)

def handle_close(text, chat_id):
    send_message(chat_id, "🚧 /close wird im nächsten Modul erweitert.")

def handle_batch(text, chat_id):
    global active_trades
    entries = re.findall(r"(LONG|SHORT) \| (\d+(?:\.\d+)?) lot @ (\d+(?:\.\d+)) \| TP: (.+?) \| SL: (.+?) \| Tag: (.+)", text, re.IGNORECASE)
    if not entries:
        send_message(chat_id, "❌ Konnte keine gültigen Positionen erkennen.")
        return
    count = 0
    for e in entries:
        dir, lot, entry, tp, sl, tag = e
        active_trades.append({
            "symbol": "US30",
            "direction": dir.lower(),
            "lot": float(lot),
            "entry": float(entry),
            "tp": None if "open" in tp.lower() else float(tp),
            "sl": None if "manual" in sl.lower() else float(sl),
            "tag": tag.strip(),
        })
        count += 1
    send_message(chat_id, f"✅ {count} Positionen aus Batch übernommen.")

# ==== Hilfsfunktionen ====

def extract_value(text, key, as_int=False):
    match = re.search(rf"{key}=(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    return int(match.group(1)) if as_int else float(match.group(1))

def extract_tag(text):
    match = re.search(r"tag=([^\n]+)", text)
    return match.group(1).strip() if match else ""
