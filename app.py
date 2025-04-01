import json
import re
import time
from flask import Flask, request, jsonify
import os
import sys
import requests

app = Flask(__name__)

VERSION = "v5.5.3"

active_trades = []
signal_memory = []
open_price = None
learned_results = []

def get_live_price():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/US30USD=X?interval=1m&range=1d"
        res = requests.get(url)
        data = res.json()
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return round(price, 2)
    except:
        return None

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
    elif text.lower().startswith("/update"):
        return send_message(chat_id, f"🔄 Update erhalten ({VERSION}) – alle Systeme aktiv.")
    elif text.lower().startswith("/stats"):
        return send_message(chat_id, format_stats())

    parsed, score, tag = parse_signal(text)
    if parsed:
        signal_memory.append(f"{parsed} [{time.strftime('%H:%M:%S')}] (Score {score}) | Tag: {tag}")
        if score >= 60:
            return send_message(chat_id, generate_trade_suggestion(parsed, score))
        else:
            return send_message(chat_id, f"✅ Signal erkannt: {parsed} (Score {score})")

    return send_message(chat_id, "❌ Unbekannter Befehl. Nutze /help für alle Kommandos.")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # Sicher per Render ENV setzen

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        res = requests.post(url, json=payload)
        print(f"SEND TO {chat_id}: {text}")
        return "ok"
    except Exception as e:
        print(f"❌ Fehler beim Senden: {e}")
        return "error"


def get_help():
    return f"📘 Befehle ({VERSION}):\n/status – offene Positionen\n/trade – Setup senden\n/close [Preis] – Trade schließen\n/close all – Alle Trades löschen\n/update – STDV aktualisieren\n/openprice [Preis] – STDV Startpreis setzen\n/zones – STDV Zonen anzeigen\n/signals – aktuelle Signale\n/resetsignals – Signal-Reset\n/batch – mehrere Trades\n/stats – Lernstatistik"

def format_status():
    if not active_trades:
        return "ℹ️ Keine aktiven Positionen."

    longs = [t for t in active_trades if t["type"] == "long"]
    shorts = [t for t in active_trades if t["type"] == "short"]

    msg = "📈 Offene Positionen\n\n"
    if longs:
        msg += f"🟢 Longs ({len(longs)}):\n"
        for t in longs:
            msg += f"• {t['lot']} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']} | Tag: {t['tag']}\n"
    if shorts:
        msg += f"\n🔴 Shorts ({len(shorts)}):\n"
        for t in shorts:
            msg += f"• {t['lot']} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']} | Tag: {t['tag']}\n"

    return msg

def handle_trade(text, chat_id):
    try:
        pattern_full = r"/trade\s+(long|short)\s+(\d+(?:\.\d+)?)\s+SL=(\d+(?:\.\d+)?)\s+TP=(\d+(?:\.\d+)?)"
        pattern_simple = r"/trade\s+(long|short)\s+(\d+(?:\.\d+)?)"

        match = re.search(pattern_full, text.lower())
        if match:
            direction, entry, sl, tp = match.groups()
        else:
            match = re.search(pattern_simple, text.lower())
            if not match:
                return send_message(chat_id, "❌ Ungültiges Format. Beispiel: /trade long 42500 oder /trade long 42500 SL=42250 TP=43200")
            direction, entry = match.groups()
            sl = "manual"
            tp = "open"

        active_trades.append({
            "type": direction,
            "entry": float(entry),
            "sl": sl,
            "tp": tp,
            "lot": 1.0,
            "tag": "manual"
        })
        return send_message(chat_id, f"✅ {direction.upper()} @ {entry} gespeichert.")
    except Exception as e:
        return send_message(chat_id, f"❌ Fehler: {str(e)}")

def format_signals():
    if not signal_memory:
        return "ℹ️ Keine aktiven Signale."
    return "📡 Aktive Signale:\n" + "\n".join(signal_memory)

def parse_signal(text):
    text = text.lower()
    if "rsi" in text:
        match = re.search(r"rsi.*?(\d+\.?\d*)", text)
        if match:
            value = float(match.group(1))
            score = max(0, min(100, 100 - abs(50 - value) * 2))
            tag = "RSI"
            return f"RSI {value}", score, tag
    if "rsi crossing up 30" in text:
        return "RSI Crossing Up 30", 80, "RSI"
    if "rsi crossing down 70" in text:
        return "RSI Crossing Down 70", 80, "RSI"
    if "rsi below 30" in text:
        return "RSI Below 30", 75, "RSI"
    if "rsi above 70" in text:
        return "RSI Above 70", 75, "RSI"
    if "momentum" in text:
        if "bullish" in text:
            return "Momentum Shift Bullish", 70, "Momentum"
        elif "bearish" in text:
            return "Momentum Shift Bearish", 70, "Momentum"
    if "mss" in text:
        if "bullish" in text:
            return "MSS Break Bullish", 65, "MSS"
        elif "bearish" in text:
            return "MSS Break Bearish", 65, "MSS"
    if re.fullmatch(r"\d{5,6}", text):
        return f"Grid Signal: {text}", 10, "Grid"
    return None, 0, "None"

def generate_trade_suggestion(signal, score):
    price = get_live_price()
    if not price:
        return f"📈 Signal-Auswertung:\n• {signal}\n• Score: {score}\n• Entry: N/A\n➡️ Kein Preis verfügbar."
    return f"📈 Signal-Auswertung:\n• {signal}\n• Score: {score}\n• Entry: {price}\n✅ Vorschlag: /trade long {price} SL={round(price - 100)} TP={round(price + 300)}"

def format_stats():
    if not learned_results:
        return "📊 Noch keine abgeschlossenen Trades."
    avg = round(sum(learned_results) / len(learned_results), 2)
    return f"📊 Gelernt aus {len(learned_results)} Trades.\nØ PnL: {avg} Punkte"

def handle_open_price(text, chat_id):
    global open_price
    try:
        match = re.search(r"/openprice (\d+(?:\.\d+)?)", text.lower())
        if not match:
            return send_message(chat_id, "❌ Bitte gib einen gültigen Preis an. Beispiel: /openprice 44100")
        open_price = float(match.group(1))
        return send_message(chat_id, f"📍 Opening Price gesetzt: {open_price}")
    except:
        return send_message(chat_id, "❌ Fehler beim Setzen des Opening Prices.")

def format_zones():
    if open_price is None:
        return "⚠️ Bitte setze zuerst den Opening Price mit /openprice [Preis]"

    msg = "📊 STDV-Zonen:\n"
    for i in range(-5, 6):
        if i == 0:
            emoji = "🟩"
        elif i < 0:
            emoji = "🟥"
        else:
            emoji = "🟩"
        price = round(open_price * (1 + i * 0.01), 2)
        msg += f"{emoji} {i:+}%: {price}\n"
    return msg

def handle_close(text, chat_id):
    if "all" in text.lower():
        active_trades.clear()
        return send_message(chat_id, "🔐 Alle Positionen wurden gelöscht.")

    match = re.search(r"/close(?:\s+(long|short))?\s+(\d+(\.\d+)?)(?:\s+at\s+(\d+(\.\d+)?))?", text.lower())
    if not match:
        return send_message(chat_id, "❌ Ungültiger Befehl. Beispiel: /close long 44500 at 44950")

    direction, price, _, exit_price, _ = match.groups()
    price = float(price)
    exit_price = float(exit_price) if exit_price else None

    for trade in active_trades:
        if trade["entry"] == price and (not direction or trade["type"] == direction):
            active_trades.remove(trade)
            result = None
            if exit_price:
                result = (exit_price - trade["entry"]) if trade["type"] == "long" else (trade["entry"] - exit_price)
                learned_results.append(result)
            return send_message(chat_id, f"❎ {trade['type'].upper()} @ {price} geschlossen." + (f" PnL: {result}" if result else ""))

    return send_message(chat_id, "⚠️ Keine passende Position gefunden.")
