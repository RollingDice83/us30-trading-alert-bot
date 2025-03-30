from flask import Flask, request, jsonify
import os
import requests
import re
import threading
import time

app = Flask(__name__)

# ENV
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === STATE ===
active_trades = []
signal_context = {
    "momentum_1h": None,
    "momentum_4h": None,
    "rsi": None,
    "mss": None
}
auto_check_interval = 30  # in Minuten
auto_check_active = False
VERSION = "v3.2"

# === UTILS ===
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

def build_score():
    score = 0
    if signal_context["momentum_1h"] == "bullish": score += 25
    if signal_context["momentum_4h"] == "bullish": score += 25
    if signal_context["rsi"] in ["below30", "crossup30"]: score += 25
    if signal_context["mss"] == "bullish": score += 25
    return score

def build_signal_text():
    score = build_score()
    text = f"📊 Neues Long-Setup erkannt\nScore: {score}/100\n"
    if score >= 70:
        text += "✅ High-Quality Signal!\n"
        text += "/trade US30 long 42500 SL=42250 TP=43200 score=85 tag=AutoSignal"
    else:
        text += "⚠️ Frühindikator erkannt, noch kein vollständiges Setup."
    return text

# === COMMAND PARSING ===
def parse_trade_command(text):
    pattern = r"/trade(?=.*\b(?P<symbol>\w+)\b)(?=.*\b(?P<direction>long|short)\b)(?=.*\b(?P<entry>\d+(?:\.\d+)?)\b)(?:.*?SL=(?P<sl>\d+(?:\.\d+)?))?(?:.*?TP=(?P<tp>\d+(?:\.\d+)?))?(?:.*?score=(?P<score>\d+))?(?:.*?tag=(?P<tag>[^\n]+))?"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    data = match.groupdict()
    return {
        "symbol": data["symbol"].upper(),
        "direction": data["direction"].lower(),
        "entry": float(data["entry"]),
        "sl": float(data["sl"]) if data["sl"] else None,
        "tp": float(data["tp"]) if data["tp"] else None,
        "score": int(data["score"]) if data["score
