import json
import re
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

VERSION = "v4.1.2"

active_trades = []
signal_memory = []
open_price = None

@app.route("/", methods=["GET"])
def home():
    return "US30 Bot Live"

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.json
    if not data or "message" not in data:
        return jsonify(ok=True)

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text.lower().startswith("/help"):
        return send_message(chat_id, get_help())

    elif text.lower().startswith("/status"):
        return send_message(chat_id, format_status())

    elif text.lower().startswith("/trade"):
        return handle_trade(text, chat_id)

    elif text.lower().startswith("/batch"):
        return handle_batch(text, chat_id)

    elif text.lower().startswith("/openprice"):
        return handle_open_price(text, chat_id)

    elif text.lower().startswith("/resetsignals"):
        signal_memory.clear()
        return send_message(chat_id, "♻️ Signal-Speicher geleert.")

    elif text.lower().startswith("/signals"):
        return send_message(chat_id, format_signals())

    elif text.lower().startswith("/zones"):
        return send_message(chat_id, format_zones())

    elif text.lower().startswith("/close"):
        return handle_close(text, chat_id)

    parsed = parse_signal(text)
    if parsed:
        signal_memory.append(parsed)
        return send_message(chat_id, f"✅ Signal gespeichert: {parsed}")

    return send_message(chat_id, "❌ Unbekannter Befehl. Nutze /help für alle Kommandos.")

def send_message(chat_id, text):
    print(f"SEND TO {chat_id}: {text}")
    return jsonify({
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": text
    })

def get_help():
    return f"""📘 Befehle ({VERSION}):
/status – offene Positionen
/trade – Setup senden
/close [Preis] – Trade schließen
/update – STDV aktualisieren
/openprice [Preis] – STDV Startpreis setzen
/zones – STDV Zonen anzeigen
/signals – aktuelle Signale
/resetsignals – Signal-Reset
/batch – mehrere Trades"""

def handle_trade(text, chat_id):
    try:
        pattern = r"/trade\s+(long|short)\s+(\d+(?:\.\d+)?)\s+SL=(\d+(?:\.\d+)?)\s+TP=(\d+(?:\.\d+)?)"
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return send_message(chat_id, "❌ Format: /trade long 42500 SL=42250 TP=43300")

        direction, entry, sl, tp = match.groups()
        trade = {
            "type": direction.lower(),
            "lot": 1,
            "entry": float(entry),
            "sl": float(sl),
            "tp": float(tp),
            "tag": "manual"
        }
        active_trades.append(trade)
        return send_message(chat_id, f"✅ {direction.upper()} @ {entry} gespeichert.")
    except Exception as e:
        return send_message(chat_id, f"❌ Fehler: {str(e)}")

def handle_batch(text, chat_id):
    lines = text.strip().split("\n")
    count = 0
    for line in lines:
        if "lot @" in line and "TP:" in line:
            try:
                type_match = re.search(r"(LONG|SHORT)", line.upper())
                lot_match = re.search(r"(\d+(\.\d+)?) lot", line)
                entry_match = re.search(r"@ (\d+(\.\d+)?)", line)
                tp_match = re.search(r"TP: (\d+(\.\d+)?|open)", line)
                sl_match = re.search(r"SL: (\d+(\.\d+)?|manual|none)", line)
                tag_match = re.search(r"Tag: (\w+)", line)

                trade = {
                    "type": type_match.group(1).lower(),
                    "lot": float(lot_match.group(1)),
                    "entry": float(entry_match.group(1)),
                    "tp": tp_match.group(1) if tp_match else "open",
                    "sl": sl_match.group(1) if sl_match else "manual",
                    "tag": tag_match.group(1) if tag_match else "none"
                }
                active_trades.append(trade)
                count += 1
            except:
                continue

    return send_message(chat_id, f"✅ {count} Trades gespeichert." if count > 0 else "⚠️ Keine gültigen Trades erkannt.")

def format_status():
    if not active_trades:
        return "ℹ️ Keine aktiven Positionen."

    longs = [t for t in active_trades if t["type"] == "long"]
    shorts = [t for t in active_trades if t["type"] == "short"]

    msg = "📈 Offene Positionen\n\n"
    if longs:
        msg += f"🟢 Longs ({len(longs)}):\n"
        for t in longs:
            msg += f"• {t['lot']} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']}\n"
    if shorts:
        msg += f"\n🔴 Shorts ({len(shorts)}):\n"
        for t in shorts:
            msg += f"• {t['lot']} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']}\n"
    return msg

def handle_close(text, chat_id):
    try:
        match = re.search(r"/close\s+(\d+(\.\d+)?)", text)
        if not match:
            return send_message(chat_id, "❌ Beispiel: /close 44500")

        price = float(match.group(1))
        removed = [t for t in active_trades if t["entry"] == price]
        if not removed:
            return send_message(chat_id, f"ℹ️ Keine Position bei {price} gefunden.")

        for t in removed:
            active_trades.remove(t)

        return send_message(chat_id, f"❌ Position @ {price} geschlossen.")
    except:
        return send_message(chat_id, "❌ Fehler beim Schließen der Position.")

def handle_open_price(text, chat_id):
    global open_price
    try:
        match = re.search(r"/openprice (\d+(\.\d+)?)", text)
        if not match:
            return send_message(chat_id, "❌ Beispiel: /openprice 44100")
        open_price = float(match.group(1))
        return send_message(chat_id, f"📍 Opening Price gesetzt: {open_price}")
    except:
        return send_message(chat_id, "❌ Fehler beim Setzen des Opening Prices.")

def format_zones():
    if open_price is None:
        return "❌ Bitte zuerst /openprice setzen."
    zones = []
    for i in range(-5, 6):
        level = round(open_price * (1 + i / 100), 1)
        color = "🟥" if i < 0 else ("🟩" if i > 0 else "🟩")
        zones.append(f"{color} {i:+}%: {level}")
    return "📊 STDV Zonen:\n" + "\n".join(zones)

def format_signals():
    if not signal_memory:
        return "ℹ️ Keine aktiven Signale."
    return "🛰 Aktive Signale:\n" + "\n".join(signal_memory)

def parse_signal(text):
    signal_patterns = [
        r"rsi.*?(\d+\.\d+)",
        r"momentum.*?(bullish|bearish)",
        r"mss.*?(bullish|bearish).*?break"
    ]
    for pattern in signal_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return f"{text} [{time.strftime('%H:%M:%S')}]"
    return None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
