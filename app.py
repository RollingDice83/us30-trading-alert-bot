from flask import Flask, request
import os
from utils import parse_trade_command, evaluate_trade_score, parse_close_command

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

@app.route("/", methods=["GET"])
def index():
    return "US30TradeAlertsBot ist aktiv."

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message", {})
    text = message.get("text", "")

    if not text:
        return {"ok": True}

    if text.startswith("/status"):
        response = "✅ Der US30-Bot läuft und empfängt Signale."

    elif text.startswith("/help"):
        response = (
            "📘 Befehle:\n"
            "/status – zeigt den aktuellen Bot-Status\n"
            "/trade – sendet Trade-Setup\n"
            "/close – Position schließen\n"
            "/help – Hilfe anzeigen"
        )

    elif text.startswith("/trade"):
        parsed = parse_trade_command(text)
        if parsed:
            entry, sl, tp = parsed
            score, reason = evaluate_trade_score(entry, sl, tp)
            response = (
                f"📊 Setup erkannt:\n"
                f"Entry: {entry:.2f}\n"
                f"SL: {sl:.2f}\n"
                f"TP: {tp:.2f}\n"
                f"➕ {reason}\n"
                f"✅ Bewertung: {score}/100 Punkten"
            )
        else:
            response = "❌ Ungültiger Befehl. Format: /trade ENTRY SL TP"

    elif text.startswith("/close"):
        entry, percent = parse_close_command(text)
        if entry is not None:
            response = f"🔒 Position bei {entry:.2f} zu {percent:.0f}% schließen (Demo-Modus)"
        else:
            response = "❌ Bitte gib die Position an, die du schließen willst. Beispiel: /close 42,650"

    else:
        response = "❌ Unbekannter Befehl. Sende /help für eine Übersicht."

    return {"method": "sendMessage", "chat_id": TELEGRAM_CHAT_ID, "text": response}

if __name__ == "__main__":
    app.run(debug=True)
