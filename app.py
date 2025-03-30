from flask import Flask, request, jsonify
import os, json, requests, re, datetime

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
active_trades = []
signal_memory_file = "us30_memory.json"
stdv_file = "stdv_zones.json"

# Telegram Nachricht senden
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

# STDV speichern + laden
def save_stdv_zones(open_price):
    zones = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "open": open_price,
        "zones": {f"{i:+d}%": round(open_price * (1 + i / 100), 2) for i in range(-5, 6)}
    }
    with open(stdv_file, "w") as f:
        json.dump(zones, f)

def load_stdv_zones():
    if not os.path.exists(stdv_file):
        return None
    with open(stdv_file, "r") as f:
        return json.load(f)

# Signals speichern + bewerten
def save_signals(signals):
    with open(signal_memory_file, "w") as f:
        json.dump(signals, f)

def load_signals():
    if not os.path.exists(signal_memory_file):
        return []
    with open(signal_memory_file, "r") as f:
        return json.load(f)

def add_signal(text):
    signals = load_signals()
    if text not in signals:
        signals.append(text)
        save_signals(signals)

def reset_signals():
    if os.path.exists(signal_memory_file):
        os.remove(signal_memory_file)

def evaluate_score():
    signals = load_signals()
    score = 0
    context = []

    if "Momentum: Bullish 1h" in signals: score += 30; context.append("📈 Bullish Momentum 1h")
    if "RSI Below 30 on US30, 1h" in signals: score += 30; context.append("🟢 RSI < 30")
    if "MSS Bullish Break on US30, 1h" in signals: score += 40; context.append("🚀 Strukturbruch 1h")

    if score >= 70:
        send_message(TELEGRAM_CHAT_ID, f"✅ High Quality Setup!\nScore: {score}/100\n" + "\n".join(context))
    elif score >= 40:
        send_message(TELEGRAM_CHAT_ID, f"⚠️ Frühwarnung\nScore: {score}/100\n" + "\n".join(context))

# TRADE Verarbeitung
def handle_trade(text, chat_id):
    pattern = r"/trade(?=.*\b(?P<symbol>\w+)\b)(?=.*\b(?P<direction>long|short)\b)(?=.*\b(?P<entry>\d+(?:\.\d+)?))(?=.*SL=(?P<sl>\d+(?:\.\d+)?))?(?=.*TP=(?P<tp>\d+(?:\.\d+)?))?(?=.*score=(?P<score>\d+))?(?=.*tag=(?P<tag>.+))?"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        send_message(chat_id, "❌ Ungültiges Format. Beispiel:\n/trade US30 long 42650 SL=42500 TP=43000 score=80 tag=Breakout")
        return
    data = match.groupdict()
    result = {
        "symbol": data["symbol"].upper(),
        "direction": data["direction"].lower(),
        "entry": float(data["entry"]),
        "sl": float(data["sl"]) if data["sl"] else None,
        "tp": float(data["tp"]) if data["tp"] else None,
        "score": int(data["score"]) if data["score"] else None,
        "tag": data["tag"].strip() if data["tag"] else ""
    }
    active_trades.append(result)
    msg = f"📥 Neuer Trade:\n{result['symbol']} {result['direction']} @ {result['entry']}"
    if result['sl']: msg += f" | SL: {result['sl']}"
    if result['tp']: msg += f" | TP: {result['tp']}"
    if result['score']: msg += f" | Score: {result['score']}"
    if result['tag']: msg += f"\n📝 {result['tag']}"
    send_message(chat_id, msg)

# BATCH Trades verarbeiten
def handle_batch(text, chat_id):
    lines = text.splitlines()
    count = 0
    for line in lines:
        if "|" in line and ("LONG" in line.upper() or "SHORT" in line.upper()):
            fake_cmd = "/trade " + line.replace("LONG", "US30 long").replace("SHORT", "US30 short")
            fake_cmd = fake_cmd.replace("lot", "").replace("@", "").replace("→", "").replace("|", "")
            handle_trade(fake_cmd, chat_id)
            count += 1
    send_message(chat_id, f"📦 Batch-Verarbeitung abgeschlossen. {count} Trades erkannt.")

# STATUS anzeigen
def handle_status(chat_id):
    if not active_trades:
        send_message(chat_id, "📊 Keine offenen Positionen.")
        return
    msg = "📈 Offene Positionen:\n"
    for t in active_trades:
        line = f"{t['symbol']} {t['direction']} @ {t['entry']}"
        if t['tp']: line += f" → TP {t['tp']}"
        if t['sl']: line += f", SL {t['sl']}"
        if t['score']: line += f" (Score {t['score']})"
        if t['tag']: line += f" – {t['tag']}"
        msg += f"• {line}\n"
    send_message(chat_id, msg)

# HILFE anzeigen
def handle_help(chat_id):
    send_message(chat_id, """📘 Befehle (v3.4):
/status – offene Positionen
/trade – Trade-Setup senden
/close – Position schließen
/update – STDV Zones anzeigen
/OpenPrice 44100 – Wochenstart setzen
/zones – STDV Zonen anzeigen
/resetsignals – Signal-Speicher leeren
/batch – Mehrere Trades senden
/help – Hilfe anzeigen""")

# /close command vollständig und flexibel
elif cmd.startswith("/close"):
    try:
        parts = user_text.split()
        if len(parts) == 2 and parts[1].lower() == "all":
            count = len(active_trades)
            active_trades.clear()
            send_message(chat_id, f"🚫 Alle {count} Positionen wurden geschlossen.")
        else:
            direction = parts[1].lower()
            entry_price = float(parts[2])
            removed = [t for t in active_trades if t['entry'] == entry_price and t['direction'] == direction]
            active_trades[:] = [t for t in active_trades if t not in removed]
            send_message(chat_id, f"❌ Position bei {entry_price} ({direction}) geschlossen.")
    except:
        send_message(chat_id, "❌ Ungültiger Befehl. Beispiel: /close long 42500 oder /close all")

# RSI explizit per Text speichern: z.B. "RSI 1h 13.82"
elif re.match(r"RSI\s+\d+h?\s+\d+(\.\d+)?", user_text, re.IGNORECASE):
    value = float(re.findall(r"\d+(\.\d+)?", user_text)[-1])
    add_signal(f"RSI_1h_Value: {value}")
    send_message(chat_id, f"📩 RSI-Wert gespeichert: {value}")
    evaluate_score()

# Verbesserte STDV-Anzeige mit Farbcodes
elif cmd.startswith("/update") or cmd.startswith("/zones"):
    zones = load_stdv_zones()
    if zones:
        msg = f"📊 Aktuelle STDV-Zonen:\n🔹 Opening: {zones['open']}\n"
        for k, v in zones["zones"].items():
            if "-" in k: msg += f"🔻 {k}: {v}\n"
            elif "+" in k: msg += f"🟢 {k}: {v}\n"
        send_message(chat_id, msg)
    else:
        send_message(chat_id, "⚠️ Noch keine STDV-Zonen gespeichert.")

# Verbesserter /status mit Lot Size & Gesamtanzahl
def handle_status(chat_id):
    if not active_trades:
        send_message(chat_id, "📊 Keine offenen Positionen.")
        return

    msg = "📈 Offene Positionen:\n"
    total_long = total_short = 0

    for trade in active_trades:
        lot = trade.get("lot", 1)
        msg += f"• {trade['symbol']} {trade['direction']} {lot} lot @ {trade['entry']}"
        if trade.get("tp"): msg += f" → TP {trade['tp']}"
        if trade.get("sl"): msg += f", SL {trade['sl']}"
        if trade.get("score"): msg += f" (Score {trade['score']})"
        if trade.get("tag"): msg += f" – {trade['tag']}"
        msg += "\n"

        if trade['direction'] == "long":
            total_long += lot
        elif trade['direction'] == "short":
            total_short += lot

    msg += f"\n📊 Gesamt: {total_long} Long | {total_short} Short"
    send_message(chat_id, msg)


# Webhook Endpoint
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    message = data.get("message", {})
    if not message: return jsonify({"status": "no message"}), 200

    user_text = message.get("text", "").strip()
    chat_id = message["chat"]["id"]
    cmd = user_text.lower()

    if cmd.startswith("/status"):
        handle_status(chat_id)
    elif cmd.startswith("/help"):
        handle_help(chat_id)
    elif cmd.startswith("/resetsignals"):
        reset_signals()
        send_message(chat_id, "🧹 Signal-Speicher wurde gelöscht.")
    elif cmd.startswith("/openprice"):
        try:
            value = float(user_text.split()[1])
            save_stdv_zones(value)
            send_message(chat_id, f"✅ STDV Startpreis gesetzt: {value}")
        except:
            send_message(chat_id, "❌ Beispiel: /OpenPrice 44100")
    elif cmd.startswith("/update") or cmd.startswith("/zones"):
        zones = load_stdv_zones()
        if zones:
            zone_text = "\n".join([f"{k}: {v}" for k, v in zones["zones"].items()])
            send_message(chat_id, f"📊 Aktuelle STDV-Zonen:\n{zone_text}")
        else:
            send_message(chat_id, "⚠️ Noch keine STDV-Zonen gespeichert.")
    elif cmd.startswith("/trade"):
        handle_trade(user_text, chat_id)
    elif cmd.startswith("/batch"):
        handle_batch(user_text, chat_id)
    elif any(key in user_text for key in ["Momentum", "RSI", "MSS"]):
        add_signal(user_text)
        evaluate_score()
    else:
        send_message(chat_id, "❓ Unbekannter Befehl.")

    return jsonify({"status": "ok"}), 200

@app.route("/")
def index():
    return "✅ US30 Trading Bot v3.4 aktiv"
