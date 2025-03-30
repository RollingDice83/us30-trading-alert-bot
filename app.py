from flask import Flask, request, jsonify
import os, re, json, requests
from datetime import datetime, timedelta

app = Flask(__name__)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
active_trades = []
signal_store_path = "us30_memory.json"
version = "3.9.1"

# === Helper Functions ===

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

def save_signals(signals):
    with open(signal_store_path, "w") as f:
        json.dump(signals, f)

def load_signals():
    if not os.path.exists(signal_store_path):
        return []
    with open(signal_store_path, "r") as f:
        return json.load(f)

def reset_signals():
    save_signals([])

def score_signals():
    signals = load_signals()
    now = datetime.utcnow()
    active = [s for s in signals if datetime.strptime(s["time"], "%Y-%m-%dT%H:%M:%S") > now - timedelta(minutes=45)]
    tags = [s["text"] for s in active]
    score = 0
    reasons = []
    if any("RSI" in t and "<30" in t for t in tags):
        score += 20
        reasons.append("RSI < 30")
    if any("Momentum: Bullish" in t for t in tags):
        score += 25
        reasons.append("Momentum bullish")
    if any("MSS Bullish" in t for t in tags):
        score += 30
        reasons.append("MSS Bullish Break")
    if any("Zone -2%" in t for t in tags):
        score += 15
        reasons.append("STDV -2% Pullback")
    if any("crossing up" in t for t in tags):
        score += 10
        reasons.append("Preis Break")
    if len(reasons) >= 3:
        score += 10
    return score, reasons

# === Command Handlers ===

def handle_status(chat_id):
    if not active_trades:
        send_message(chat_id,
