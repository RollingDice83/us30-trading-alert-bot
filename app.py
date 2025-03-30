from flask import Flask, request, jsonify
import os, json, requests, re
from datetime import datetime

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
STDV_FILE = "stdv_zones.json"
SIGNAL_FILE = "us30_memory.json"

# 🔹 Speicher für aktive Trades
active_trades = []

# 🔹 Initial STDV Speicher
stdv_zones = {
    "open": None,
    "zones": [],
    "timestamp": None
}

# 🔹 Signal Memory
signals = []

# 🔹 Lot-Größen Detection
def detect_lot_size(tag):
    match = re.search(r"(\d+(\.\d+)?)\s*lot", tag.lower())
    if match:
        return float(match.group(1))
    return 1.0

# 🔹 Telegram Messaging
def send_message(chat_id, text, parse_mode=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    requests.post(url, json=payload)

# 🔹 STDV Zones
def calculate_stdv_zones(opening_price):
    try:
        base = float(opening_price)
    except:
        return None
    stdv = {
        "open": base,
        "zones": [
            {"label": "-5%", "value": round(base * 0.95, 2)},
            {"label": "-4%", "value": round(base * 0.96, 2)},
            {"label": "-3%", "value": round(base * 0.97, 2)},
            {"label": "-2%", "value": round(base * 0.98, 2)},
            {"label": "-1%", "value": round(base * 0.99, 2)},
            {"label": "+1%", "value": round(base * 1.01, 2)},
            {"label": "+2%", "value": round(base * 1.02, 2)},
            {"label": "+3%", "value": round(base * 1.03, 2)},
            {"label": "+4%", "value": round(base * 1.04, 2)},
            {"label": "+5%", "value": round(base * 1.05, 2)}
        ],
        "timestamp": datetime.utcnow().isoformat()
    }
    with open(STDV_FILE, "w") as f:
        json.dump(stdv, f)
    return stdv

# 🔹 Webhook Signal Processing
def process_signal(text):
    text = text.strip()
    signal = {
        "text": text,
        "timestamp": datetime.utcnow().isoformat()
    }
    signals.append(signal)
    with open(SIGNAL_FILE, "w") as f:
        json.dump(signals, f)

# 🔹 /trade parser
def parse_trade(text):
    pattern = r"/trade.*?(?P<symbol>US30).*?(?P<dir>long|short).*?(?P<entry>\d+(?:\.\d+)?)(?:.*?SL[:= ](?P<sl>\d+(?:\.\d+)?))?(?:.*?TP[:= ](?P<tp>\d+(?:\.\d+)?))?(?:.*?score[:= ](?P<score>\d+))?(?:.*?tag[:= ](?P<tag>.+))?"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    d = match.groupdict()
    return {
        "symbol": d["symbol"].upper(),
        "direction": d["dir"].lower(),
        "entry": float(d["entry"]),
        "sl": float(d["sl"]) if d["sl"] else None,
        "tp": float(d["tp"]) if d["tp"] else None,
        "score": int(d["score"]) if d["score"] else None,
        "tag": d["tag"].strip() if d["tag"] else "",
        "lot": detect_lot_size(d["tag"] or "")
    }

# 🔹 Trade Handler
def handle_trade(cmd, chat_id):
    result = parse_trade(cmd)
    if not result:
        send_message(chat_id, "❌ Ungültiges Format. Beispiel:\n/trade US30 long 42650 SL=42500 TP=43000 score=80 tag=Breakout 2 lot")
        return
    active_trades.append(result)
    msg = f"📥 Trade gespeichert: {result['symbol']} {result['direction']} {result['entry']}"
    if result["sl"]: msg += f" | SL: {result['sl']}"
    if result["tp"]: msg += f" | TP: {result['tp']}"
    if result["score"]: msg += f" | Score: {result['score']}/100"
    if result["tag"]: msg += f" | Tag: {result['tag']}"
    send_message(chat_id, msg)

# 🔹 /close Handler
def handle_close(text, chat_id):
    global active_trades
    pattern = r"/close\s+(?P<symbol>\w+)\s+(?P<entry>\d+(?:\.\d+)?)(?:\s+(?P<tag>.*))?"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        send_message(chat_id, "❌ Beispiel: /close US30 42650")
        return
    d = match.groupdict()
    entry = float(d["entry"])
    before = len(active_trades)
    active_trades = [t for t in active_trades if not (t["symbol"] == d["symbol"].upper() and t["entry"] == entry)]
    after = len(active_trades)
    if before > after:
        send_message(chat_id, f"✅ Position {d['symbol']} @ {entry} geschlossen. {d['tag'] or ''}")
    else:
        send_message(chat_id, "⚠️ Keine passende Position gefunden.")

# 🔹 /status Handler
def handle_status(chat_id):
    if not active_trades:
        send_message(chat_id, "📊 Keine offenen Positionen.")
        return

    longs = [t for t in active_trades if t["direction"] == "long"]
    shorts = [t for t in active_trades if t["direction"] == "short"]

    msg = "📈 *Offene Positionen*\n\n"

    # Longs (grün)
    if longs:
        msg += f"🟢 *Longs* ({len(longs)}):\n"
        for t in longs:
            msg += f"• {t['lot']} lot @ {t['entry']}"
            if t['tp']: msg += f" → TP {t['tp']}"
            if t['sl']: msg += f", SL {t['sl']}"
            if t['tag']: msg += f" – _{t['tag']}_"
            msg += "\n"
        msg += "\n"

    # Shorts (rot)
    if shorts:
        msg += f"🔴 *Shorts* ({len(shorts)}):\n"
        for t in shorts:
            msg += f"• {t['lot']} lot @ {t['entry']}"
            if t['tp']: msg += f" → TP {t['tp']}"
            if t['sl']: msg += f", SL {t['sl']}"
            if t['tag']: msg += f" – _{t['tag']}_"
            msg += "\n"

    send_message(chat_id, msg, parse_mode="Markdown")

# 🔹 /zones Handler
def handle_zones(chat_id):
    try:
        with open(STDV_FILE) as f:
            z = json.load(f)
    except:
        send_message(chat_id, "⚠️ Keine STDV-Zonen gespeichert.")
        return
    msg = f"📊 STDV Zonen (Basis: {z['open']})\n🔵 Opening: {z['open']}\n"
    for zone in z["zones"]:
        color = "🟥" if "-" in zone["label"] else "🟩"
        msg += f"{color} {zone['label']}: {zone['value']}\n"
    send_message(chat_id, msg)

# 🔹 /batch Handler
def handle_batch(text, chat_id):
    global active_trades
    lines = text.split("\n")
    count = 0
    for line in lines:
        line = line.strip()
        if not line or "|" not in line:
            continue
        try:
            direction, rest = line.split("|", 1)
            direction = direction.strip().upper()
            parts = [p.strip() for p in rest.split("|")]
            lot = float(re.search(r"([\d.]+)", parts[0]).group(1))
            entry = float(re.search(r"@ ([\d.]+)", parts[0]).group(1))
            tp_match = re.search(r"TP: ([\d.]+)", parts[1]) if len(parts) > 1 else None
            tp = float(tp_match.group(1)) if tp_match else None
            sl_match = re.search(r"SL: ([\d.]+)", parts[1]) if len(parts) > 1 else None
            sl = float(sl_match.group(1)) if sl_match else None
            tag = parts[2].replace("Tag:", "").strip() if len(parts) > 2 else ""
            symbol = "US30"

            active_trades.append({
                "symbol": symbol,
                "direction": direction.lower(),
                "entry": entry,
                "tp": tp,
                "sl": sl,
                "lot": lot,
                "tag": tag,
                "score": None
            })
            count += 1
        except Exception as e:
            print(f"⚠️ Fehler beim Parsen der Zeile: {line} – {e}")
            continue

    send_message(chat_id, f"📥 {count} Trades hinzugefügt über /batch.")


# 🔹 Webhook Endpoint
@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"ok": True}), 200
    text = data["message"].get("text", "").strip()
    chat_id = data["message"]["chat"]["id"]

    if text.lower().startswith("/status"):
        handle_status(chat_id)
    elif text.lower().startswith("/trade"):
        handle_trade(text, chat_id)
    elif text.lower().startswith("/close"):
        handle_close(text, chat_id)
    elif text.lower().startswith("/zones"):
        handle_zones(chat_id)
    elif text.lower().startswith("/openprice"):
        price = re.findall(r"\d+(?:\.\d+)?", text)
        if price:
            zone = calculate_stdv_zones(price[0])
            if zone:
                send_message(chat_id, f"📌 Opening Price gesetzt: {zone['open']}")
            else:
                send_message(chat_id, "⚠️ Fehler beim Setzen des Preises.")
    elif text.lower().startswith("/update"):
        handle_zones(chat_id)
    elif text.lower().startswith("/resetsignals"):
        global signals
        signals = []
        with open(SIGNAL_FILE, "w") as f:
            json.dump(signals, f)
        send_message(chat_id, "🧹 Signal-Speicher wurde gelöscht.")
    elif text.lower().startswith("/batch"):
        handle_batch(text, chat_id)
    elif text.lower().startswith("/help"):
        send_message(chat_id, "📘 Befehle:\n/status – offene Positionen\n/trade – Trade-Setup senden\n/close – Position schließen\n/update – STDV Zones aktualisieren\n/OpenPrice 44100 – STDV Startpreis setzen\n/zones – STDV Zonen anzeigen\n/resetsignals – Signal-Speicher leeren\n/batch – Mehrere Trades senden\n/help – Hilfe anzeigen")
    else:
        process_signal(text)
        send_message(chat_id, f"📩 Signal empfangen: {text}")

    return jsonify({"ok": True})
