import json
import re
from flask import Flask, request

app = Flask(__name__)

VERSION = "v4.1"

active_trades = []
signal_memory = []
open_price = None

def send_message(chat_id, text):
    print(f"SEND TO {chat_id}: {text}")
    # Placeholder – für echte Telegram-Integration hier HTTP-POST einbauen
    return json.dumps({"method": "sendMessage", "chat_id": chat_id, "text": text})

@app.route("/", methods=["GET"])
def home():
    return "US30 Bot Live"

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.json
    if not data or "message" not in data:
        return "ok"

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip().lower()

    if text.startswith("/help"):
        return send_message(chat_id, get_help())

    elif text.startswith("/status"):
        return send_message(chat_id, format_status())

    elif text.startswith("/trade"):
        return handle_trade(text, chat_id)

    elif text.startswith("/batch"):
        return handle_batch(text, chat_id)

    elif text.startswith("/openprice"):
        return handle_open_price(text, chat_id)

    elif text.startswith("/resetsignals"):
        signal_memory.clear()
        return send_message(chat_id, "♻️ Signal-Speicher geleert.")

    elif text.startswith("/signals"):
        return send_message(chat_id, format_signals())

    elif text.startswith("/close"):
        return send_message(chat_id, "🔐 Funktion '/close' wird demnächst aktiviert.")

    elif text.startswith("/update"):
        return send_message(chat_id, "🔄 STDV-Zonen Update folgt in Modul 4.")

    elif text.startswith("/zones"):
        return send_message(chat_id, "📊 Aktuelle STDV-Zonen: [Platzhalter]")

    return send_message(chat_id, "❌ Unbekannter Befehl. Nutze /help für alle Kommandos.")

def get_help():
    return f"""📘 Befehle ({VERSION}):
/status – offene Positionen
/trade – Setup senden
/close – Trade schließen
/update – STDV aktualisieren
/openprice – STDV Startpreis setzen
/zones – STDV Zonen anzeigen
/signals – aktuelle Signale
/resetsignals – Signal-Reset
/batch – mehrere Trades"""

def handle_trade(text, chat_id):
    try:
        pattern = r"/trade\s+(long|short)\s+(\d+(?:\.\d+)?)\s+sl=(\d+(?:\.\d+)?)\s+tp=(\d+(?:\.\d+)?)"
        match = re.search(pattern, text)
        if not match:
            return send_message(chat_id, "❌ Format: /trade long 42500 SL=42250 TP=43200")

        direction, entry, sl, tp = match.groups()
        trade = {
            "type": direction,
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

def handle_open_price(text, chat_id):
    global open_price
    try:
        match = re.search(r"/openprice (\d+(?:\.\d+)?)", text)
        if not match:
            return send_message(chat_id, "❌ Beispiel: /openprice 44100")
        open_price = float(match.group(1))
        return send_message(chat_id, f"📍 Opening Price gesetzt: {open_price}")
    except:
        return send_message(chat_id, "❌ Fehler beim Setzen des Opening Prices.")

def format_signals():
    if not signal_memory:
        return "ℹ️ Keine aktiven Signale."
    return "📡 Aktive Signale:\n" + "\n".join(signal_memory)

if __name__ == "__main__":
    app.run(debug=True)
