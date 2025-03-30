import json
import re
import requests
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

BOT_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

VERSION = "v4.0.2"
active_trades = []
signal_memory = []
open_price = None

# --- Hilfsfunktionen ---
def send_message(chat_id, text):
    requests.post(TELEGRAM_API_URL, json={"chat_id": chat_id, "text": text})

def parse_trade_command(text):
    match = re.search(r"/trade (long|short) (\d+(\.\d+)?) SL=(\d+(\.\d+)?) TP=(\d+(\.\d+)?)", text, re.IGNORECASE)
    if match:
        direction, entry, _, sl, _, tp, _ = match.groups()
        return {
            "direction": direction.lower(),
            "entry": float(entry),
            "sl": float(sl),
            "tp": float(tp),
            "tag": "manual"
        }
    return None

def format_trades():
    longs = [t for t in active_trades if t['direction'] == 'long']
    shorts = [t for t in active_trades if t['direction'] == 'short']
    
    text = "📈 Offene Positionen\n"
    total_longs = sum(t['lot'] for t in longs)
    total_shorts = sum(t['lot'] for t in shorts)

    if longs:
        text += f"\n🟢 Longs ({len(longs)} | {total_longs} lot):"
        for t in longs:
            text += f"\n• {t['lot']} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']}"

    if shorts:
        text += f"\n\n🔴 Shorts ({len(shorts)} | {total_shorts} lot):"
        for t in shorts:
            text += f"\n• {t['lot']} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']}"

    return text or "Keine offenen Positionen."

def parse_batch(text):
    trades = []
    for line in text.split('\n'):
        if 'lot' not in line:
            continue
        try:
            direction = 'long' if line.lower().startswith('long') else 'short'
            lot = float(re.search(r"(\d+(\.\d+)?) lot", line).group(1))
            entry = float(re.search(r"@ (\d+(\.\d+)?)", line).group(1))
            tp_match = re.search(r"TP: (\d+(\.\d+)?|open)", line)
            sl_match = re.search(r"SL: (\d+(\.\d+)?|manual)", line)
            tag_match = re.search(r"Tag: (\w+)", line)
            
            tp = tp_match.group(1) if tp_match else 'open'
            sl = sl_match.group(1) if sl_match else 'manual'
            tag = tag_match.group(1) if tag_match else 'manual'
            
            trade = {
                "direction": direction,
                "lot": lot,
                "entry": entry,
                "tp": float(tp) if tp != 'open' else 'open',
                "sl": float(sl) if sl != 'manual' else 'manual',
                "tag": tag
            }
            trades.append(trade)
        except Exception as e:
            print(f"Fehler beim Parsen einer Zeile: {line} Fehler: {e}")
    return trades

# --- Routen ---
@app.route("/")
def index():
    return "US30 Bot Online"

@app.route("/telegram", methods=['POST'])
def telegram():
    data = request.json
    chat_id = data['message']['chat']['id']
    text = data['message'].get('text', '').strip()

    if text.lower().startswith("/help"):
        help_text = f"📘 Befehle ({VERSION}):\n"
        help_text += "/status – offene Positionen\n"
        help_text += "/trade – Setup senden\n"
        help_text += "/close – Trade schließen\n"
        help_text += "/update – STDV aktualisieren\n"
        help_text += "/openprice – STDV Startpreis setzen\n"
        help_text += "/zones – STDV Zonen anzeigen\n"
        help_text += "/signals – aktuelle Signale\n"
        help_text += "/resetsignals – Signal-Reset\n"
        help_text += "/batch – mehrere Trades"
        send_message(chat_id, help_text)

    elif text.lower().startswith("/status"):
        send_message(chat_id, format_trades())

    elif text.lower().startswith("/trade"):
        trade = parse_trade_command(text)
        if trade:
            trade['lot'] = 1.0
            active_trades.append(trade)
            send_message(chat_id, f"✅ Trade gespeichert: {trade['direction'].upper()} @ {trade['entry']} TP {trade['tp']} SL {trade['sl']}")
        else:
            send_message(chat_id, "❌ Ungültiges Format. Beispiel: /trade long 42500 SL=42250 TP=43200")

    elif text.lower().startswith("/batch"):
        trades = parse_batch(text)
        if trades:
            active_trades.extend(trades)
            send_message(chat_id, f"✅ {len(trades)} Trades hinzugefügt.")
        else:
            send_message(chat_id, "⚠️ Keine gültigen Trades erkannt.")

    elif text.lower().startswith("/openprice"):
        match = re.search(r"/openprice (\d+(\.\d+)?)", text, re.IGNORECASE)
        if match:
            global open_price
            open_price = float(match.group(1))
            send_message(chat_id, f"📌 Opening Price gesetzt: {open_price}")
        else:
            send_message(chat_id, "❌ Bitte gib den Opening Preis an. Beispiel: /openprice 44100")

    elif text.lower().startswith("/resetsignals"):
        signal_memory.clear()
        send_message(chat_id, "🧹 Signal-Speicher wurde geleert.")

    elif text.lower().startswith("/signals"):
        if not signal_memory:
            send_message(chat_id, "ℹ️ Keine gespeicherten Signale.")
        else:
            message = "🧠 Gespeicherte Signale:\n" + "\n".join(signal_memory[-10:])
            send_message(chat_id, message)

    else:
        send_message(chat_id, "❓ Unbekannter Befehl. Nutze /help für alle Optionen.")

    return "ok"

if __name__ == "__main__":
    app.run(debug=True)
