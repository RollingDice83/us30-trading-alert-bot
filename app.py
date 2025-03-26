from flask import Flask, request
import requests
import os

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

@app.route("/")
def home():
    return "Telegram Alert Bot is running."

@app.route("/webhook", methods=["POST"])
def webhook():
    # Versuche, JSON zu parsen
    data = request.get_json(silent=True)
    message = ""

    if data and "message" in data:
        message = data["message"]
    else:
        # Falls kein JSON oder kein "message"-Key vorhanden:
        try:
            message = request.data.decode("utf-8")
        except:
            message = "🚨 Alarm empfangen (aber kein lesbarer Inhalt)."

    send_telegram_message(message)
    return "OK", 200

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=payload)
