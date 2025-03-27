# app.py
import os
from flask import Flask, request
import json
from utils import evaluate_entry_score, parse_trade_command

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

from telegram import Bot
bot = Bot(token=TELEGRAM_TOKEN)

positions = {}  # Dict: {tag/entry: {"type": ..., "sl": ..., "tp": ..., "score": ...}}

def send_message(text):
    if TELEGRAM_CHAT_ID:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.json
    message = data.get("message", {}).get("text", "")

    if message.startswith("/trade"):
        trade_info = parse_trade_command(message)
        if trade_info:
            score, reasons = evaluate_entry_score(trade_info)
            tag = trade_info.get("entry")
            trade_info["score"] = score
            trade_info["reasons"] = reasons
            positions[tag] = trade_info

            msg = f"📊 Entry Score für {tag} ({trade_info['type'].upper()}): {score}/100\n"
            for reason in reasons:
                msg += f"- {reason}\n"
            msg += f"\nVorschlag: SL {trade_info['sl']} | TP {trade_info['tp']}"
            send_message(msg)
        else:
            send_message("❌ Ungültiges Format. Beispiel: /trade 42650 long SL:42500 TP:42800")

    elif message.startswith("/close"):
        parts = message.split()
        if len(parts) >= 2:
            tag = parts[1]
            percent = 100
            if len(parts) == 3 and "%" in parts[2]:
                percent = int(parts[2].replace("%", ""))

            if tag in positions:
                pos = positions[tag]
                send_message(f"📉 {percent}% von {tag} ({pos['type'].upper()}) geschlossen.")
                if percent == 100:
                    del positions[tag]
            else:
                send_message(f"⚠️ Keine offene Position mit Tag {tag} gefunden.")
        else:
            send_message("❌ Bitte gib die Position an, die du schließen willst. Beispiel: /close 42650 50%")

    elif message.startswith("/status"):
        send_message("✅ Der US30-Bot läuft und empfängt Signale.")

    elif message.startswith("/help"):
        send_message("""📘 Befehle:
/status – zeigt den aktuellen Bot-Status
/trade – sendet Trade-Setup (inkl. Score)
/close – Position (teilweise) schließen
/help – Hilfe anzeigen""")

    return "ok"

@app.route("/")
def index():
    return "US30 Trading Bot läuft."
