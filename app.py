from flask import Flask, request
import re, time, os, requests

app = Flask(__name__)

VERSION = "v5.8.1"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

active_trades = []
signal_memory = []
open_price = None
last_autotrade_time = 0
AUTO_TRADE_DELAY = 60  # in seconds

# --- Signal Scoring Rules ---
score_weights = {
    "rsi_cross_up_30": 80,
    "rsi_below_30": 60,
    "rsi_above_70": 60,
    "rsi_cross_down_70": 80,
    "momentum_bull_1h": 70,
    "momentum_bear_1h": 70,
    "momentum_bull_4h": 80,
    "momentum_bear_4h": 80,
    "mss_bull_1h": 70,
    "mss_bear_1h": 70,
    "mss_bull_4h": 80,
    "mss_bear_4h": 80,
    "grid_price": 10
}

@app.route("/")
def home():
    return f"US30 Bot v{VERSION} Live"

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.json
    if not data or "message" not in data:
        return "ok"

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text.startswith("/help"):
        return send_message(chat_id, get_help())
    if text.startswith("/status"):
        return send_message(chat_id, format_status())
    if text.startswith("/trade"):
        return handle_trade(text, chat_id)
    if text.startswith("/batch"):
        return handle_batch(text, chat_id)
    if text.startswith("/openprice"):
        return handle_open_price(text, chat_id)
    if text.startswith("/zones"):
        return send_message(chat_id, format_zones())
    if text.startswith("/update"):
        return send_message(chat_id, format_zones())
    if text.startswith("/signals"):
        return send_message(chat_id, format_signals())
    if text.startswith("/resetsignals"):
        signal_memory.clear()
        return send_message(chat_id, "♻️ Signal-Speicher wurde geleert.")
    if text.startswith("/close"):
        return handle_close(text, chat_id)
    if text.startswith("/stats"):
        return send_message(chat_id, format_stats())

    parsed, score = parse_signal(text)
    if parsed:
        signal_memory.append(parsed)
        send_message(chat_id, f"✅ Signal erkannt: {parsed} (Score {score})")
        if score >= 80:
            global last_autotrade_time
            if time.time() - last_autotrade_time > AUTO_TRADE_DELAY:
                trade = generate_trade_suggestion(parsed, score)
                active_trades.append(trade)
                last_autotrade_time = time.time()
                send_message(chat_id, f"🤖 Auto-Trade ausgeführt:\n{trade['type'].upper()} @ {trade['entry']} (SL {trade['sl']}, TP {trade['tp']})")
        return "ok"

    return send_message(chat_id, "❌ Unbekannter Befehl. Nutze /help für alle Kommandos.")

# --- Helper Functions ---
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        requests.post(url, json=payload)
    except:
        pass
    print(f"SEND TO {chat_id}: {text}")
    return "ok"

def get_help():
    return f"📘 Befehle (v{VERSION}):\n/status – offene Positionen\n/trade – Setup senden\n/close [Preis] – Trade schließen\n/close all – Alle Trades löschen\n/update – STDV aktualisieren\n/openprice [Preis] – STDV Startpreis setzen\n/zones – STDV Zonen anzeigen\n/signals – aktuelle Signale\n/resetsignals – Signal-Reset\n/batch – mehrere Trades\n/stats – Lernstatistik"

def format_status():
    if not active_trades:
        return "📭 Keine offenen Positionen"
    msg = "📈 Offene Positionen\n"
    longs = [t for t in active_trades if t['type'] == 'long']
    shorts = [t for t in active_trades if t['type'] == 'short']
    if longs:
        msg += "🟢 Longs:\n" + "\n".join([f"• {t['lot']} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']}" for t in longs]) + "\n"
    if shorts:
        msg += "🔴 Shorts:\n" + "\n".join([f"• {t['lot']} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']}" for t in shorts])
    return msg

def handle_trade(text, chat_id):
    match = re.search(r"(long|short)\s+(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if not match:
        return send_message(chat_id, "❌ Format: /trade long 44500")
    type_, entry = match.groups()
    trade = {
        "type": type_.lower(),
        "entry": float(entry),
        "tp": float(entry) + 250 if type_.lower() == "long" else float(entry) - 250,
        "sl": "manual",
        "lot": 1.0,
        "tag": "manual"
    }
    active_trades.append(trade)
    return send_message(chat_id, f"✅ Trade gespeichert: {type_.upper()} @ {entry}")

def handle_batch(text, chat_id):
    lines = text.split("\n")[1:]
    count = 0
    for line in lines:
        m = re.match(r"(LONG|SHORT)\s*\|\s*(\d+(?:\.\d+)?) lot @ ([\d\.]+).*", line)
        if m:
            ttype, lot, entry = m.groups()
            tp = float(entry) + 250 if ttype == "LONG" else float(entry) - 250
            sl = "manual"
            trade = {
                "type": ttype.lower(), "entry": float(entry), "tp": tp, "sl": sl, "lot": float(lot), "tag": "batch"
            }
            active_trades.append(trade)
            count += 1
    return send_message(chat_id, f"✅ {count} Trades gespeichert.")

def handle_open_price(text, chat_id):
    global open_price
    match = re.search(r"/openprice (\d+(?:\.\d+)?)", text)
    if match:
        open_price = float(match.group(1))
        return send_message(chat_id, f"📍 Opening Price gesetzt: {open_price}")
    return send_message(chat_id, "❌ Bitte Preis angeben: /openprice 44400")

def format_zones():
    if not open_price:
        return "ℹ️ Kein Opening Price gesetzt. Nutze /openprice [Preis]"
    msg = "📊 STDV-Zonen:\n"
    for pct in [-5, -3, -1, 1, 3, 5]:
        level = open_price * (1 + pct / 100)
        msg += f"{level:.0f} ({pct:+}%)\n"
    return msg

def format_signals():
    if not signal_memory:
        return "📭 Keine gespeicherten Signale."
    msg = "🧠 Signal-Speicher:\n"
    for sig in signal_memory[-10:]:
        msg += f"• {sig}\n"
    return msg

def handle_close(text, chat_id):
    if "all" in text:
        active_trades.clear()
        return send_message(chat_id, "🚫 Alle Trades gelöscht.")
    match = re.search(r"/close (\d+(?:\.\d+)?)", text)
    if match:
        entry = float(match.group(1))
        before = len(active_trades)
        active_trades[:] = [t for t in active_trades if t['entry'] != entry]
        after = len(active_trades)
        return send_message(chat_id, f"🔐 {before - after} Trade(s) bei {entry} geschlossen.")
    return send_message(chat_id, "❌ Bitte Entry-Preis angeben: /close 44500")

def format_stats():
    if not signal_memory:
        return "📊 Keine Daten verfügbar."
    rsi_signals = len([s for s in signal_memory if "RSI" in s])
    mom_signals = len([s for s in signal_memory if "Momentum" in s])
    mss_signals = len([s for s in signal_memory if "MSS" in s])
    return f"📈 Lernstatistik:\n• RSI: {rsi_signals}\n• Momentum: {mom_signals}\n• MSS: {mss_signals}\n• Gesamt: {len(signal_memory)}"

def parse_signal(text):
    text = text.lower()
    if "rsi crossing up 30" in text:
        return ("RSI 30.0", score_weights["rsi_cross_up_30"])
    if "rsi below 30" in text:
        return ("RSI 30.0", score_weights["rsi_below_30"])
    if "rsi above 70" in text:
        return ("RSI 70.0", score_weights["rsi_above_70"])
    if "rsi crossing down 70" in text:
        return ("RSI 70.0", score_weights["rsi_cross_down_70"])
    if "momentum: bullish 1h" in text:
        return ("Momentum Bullish 1h", score_weights["momentum_bull_1h"])
    if "momentum: bearish 1h" in text:
        return ("Momentum Bearish 1h", score_weights["momentum_bear_1h"])
    if "momentum: bullish 4h" in text:
        return ("Momentum Bullish 4h", score_weights["momentum_bull_4h"])
    if "momentum: bearish 4h" in text:
        return ("Momentum Bearish 4h", score_weights["momentum_bear_4h"])
    if "mss bullish break on us30, 1h" in text:
        return ("MSS Bullish Break 1h", score_weights["mss_bull_1h"])
    if "mss bearish break on us30, 1h" in text:
        return ("MSS Bearish Break 1h", score_weights["mss_bear_1h"])
    if "mss bullish break on us30, 4h" in text:
        return ("MSS Bullish Break 4h", score_weights["mss_bull_4h"])
    if "mss bearish break on us30, 4h" in text:
        return ("MSS Bearish Break 4h", score_weights["mss_bear_4h"])
    if re.match(r"^\d{5}$", text.strip()):
        return (f"Grid Signal: {text.strip()}", score_weights["grid_price"])
    return (None, 0)

def generate_trade_suggestion(parsed, score):
    direction = "long" if any(k in parsed.lower() for k in ["rsi", "bullish", "grid"]) else "short"
    entry = float(re.search(r"\d{5}", parsed).group()) if re.search(r"\d{5}", parsed) else 44000.0
    tp = entry + 250 if direction == "long" else entry - 250
    sl = entry - 150 if direction == "long" else entry + 150
    return {"type": direction, "entry": entry, "tp": tp, "sl": sl, "lot": 1.0, "tag": "auto"}
