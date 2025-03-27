from flask import Flask, request
import os
import requests

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

@app.route('/')
def home():
    return "US30 Telegram Bot is running."

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    if request.method == 'POST':
        data = request.get_json()

        if "message" in data:
            chat_id = data["message"]["chat"]["id"]
            message = data["message"].get("text", "")

            if message.lower() == "/start" or message.lower() == "/help":
                send_message(chat_id, "📘 Befehle:\n/status – zeigt den aktuellen Bot-Status\n/trade – sendet Trade-Setup\n/close – Position schließen\n/help – Hilfe anzeigen")
            elif message.lower() == "/status":
                send_message(chat_id, "✅ Der US30-Bot läuft und empfängt Signale.")
            elif message.lower() == "/close":
                send_message(chat_id, "❌ Bitte gib die Position an, die du schließen willst. Beispiel:\n/close 42,650")
            elif message.lower().startswith("/trade"):
                send_message(chat_id, "📈 Trade-Signal erkannt. Details werden analysiert... (Demo-Modus)")

        return {"status": "ok"}, 200

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    requests.post(url, json=payload)

if __name__ == '__main__':
    app.run(debug=True)
