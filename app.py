from flask import Flask, request
import re, time, os

app = Flask(__name__)

VERSION = "v5.8"

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
from flask import make_response

def send_message(chat_id, text):
    print(f"SEND TO {chat_id}: {text}")
    return make_response("ok", 200)

def get_help():
    return f"📘 Befehle (v{VERSION}):\n/status – offene Positionen\n/trade – Setup senden\n/close [Preis] – Trade schließen\n/close all – Alle Trades löschen\n/update – STDV aktualisieren\n/openprice [Preis] – STDV Startpreis setzen\n/zones – STDV Zonen anzeigen\n/signals – aktuelle Signale\n/resetsignals – Signal-Reset\n/batch – mehrere Trades\n/stats – Lernstatistik"

def handle_trade(text, chat_id):
    parts = text.split()
    if len(parts) < 3:
        return send_message(chat_id, "⚠️ Ungültiges Format. Nutze /trade long|short preis")
    direction = parts[1].lower()
    try:
        entry = float(parts[2])
    except ValueError:
        return send_message(chat_id, "❌ Ungültiger Entry-Preis")
    sl = entry - 200 if direction == "long" else entry + 200
    tp = entry + 500 if direction == "long" else entry - 500
    trade = {"type": direction, "entry": entry, "sl": sl, "tp": tp}
    active_trades.append(trade)
    return send_message(chat_id, f"💼 Trade gespeichert: {direction.upper()} @ {entry} (SL {sl}, TP {tp})")

def handle_batch(text, chat_id):
    trades = re.findall(r"(LONG|SHORT) \| ([\d.]+) lot @ ([\d.]+)(?: \| TP: ([\d.]+))?(?: \| SL: ([\w.]+))?(?: \| Tag: (\w+))?", text, re.IGNORECASE)
    if not trades:
        return send_message(chat_id, "⚠️ Kein gültiges Batch-Format erkannt.")
    for t in trades:
        direction, lot, entry, tp, sl, tag = t
        trade = {
            "type": direction.lower(),
            "lot": float(lot),
            "entry": float(entry),
            "tp": float(tp) if tp else (float(entry) + 500 if direction.lower() == "long" else float(entry) - 500),
            "sl": float(sl) if sl and sl.replace('.', '', 1).isdigit() else "manual",
            "tag": tag if tag else ""
        }
        active_trades.append(trade)
    return send_message(chat_id, f"✅ {len(trades)} Trades gespeichert.")

def handle_open_price(text, chat_id):
    global open_price
    try:
        open_price = float(text.split()[1])
        return send_message(chat_id, f"📍 Opening Price gesetzt: {open_price}")
    except:
        return send_message(chat_id, "⚠️ Ungültiger Wert. Nutze: /openprice [Zahl]")

def handle_close(text, chat_id):
    global active_trades
    if "all" in text:
        active_trades.clear()
        return send_message(chat_id, "❌ Alle Positionen wurden gelöscht.")
    parts = text.split()
    try:
        entry_price = float(parts[1])
        active_trades = [t for t in active_trades if t.get("entry") != entry_price]
        return send_message(chat_id, f"❌ Trade @ {entry_price} wurde geschlossen.")
    except:
        return send_message(chat_id, "⚠️ Ungültiger Befehl. Nutze /close [Preis] oder /close all")

def format_status():
    if not active_trades:
        return "📊 Keine offenen Positionen."
    msg = "📈 Offene Positionen\n"
    longs = [t for t in active_trades if t["type"] == "long"]
    shorts = [t for t in active_trades if t["type"] == "short"]
    if longs:
        msg += "🟢 Longs:\n"
        for t in longs:
            msg += f"• {t['lot'] if 'lot' in t else 1.0} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']}\n"
    if shorts:
        msg += "🔴 Shorts:\n"
        for t in shorts:
            msg += f"• {t['lot'] if 'lot' in t else 1.0} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']}\n"
    return msg

def format_signals():
    if not signal_memory:
        return "📭 Keine Signale gespeichert."
    return "🧠 Aktive Signale:\n" + "\n".join(signal_memory[-10:])

def format_zones():
    if not open_price:
        return "⚠️ Kein Opening Price gesetzt. Nutze /openprice [Preis]"
    zones = "📊 STDV-Zonen:\n"
    for pct in range(-5, 6):
        level = open_price * (1 + pct / 100)
        emoji = "🟥" if pct < 0 else "🟩"
        zones += f"{emoji} {pct:+d}%: {level:.2f}\n"
    return zones

def parse_signal(text):
    patterns = [
        (r"RSI (Crossing Up|Below) 30.*", "rsi_cross_up_30"),
        (r"RSI (Above|Crossing Down) 70.*", "rsi_cross_down_70"),
        (r"Momentum: Bullish 1h", "momentum_bull_1h"),
        (r"Momentum: Bearish 1h", "momentum_bear_1h"),
        (r"Momentum: Bullish 4h", "momentum_bull_4h"),
        (r"Momentum: Bearish 4h", "momentum_bear_4h"),
        (r"MSS Bullish Break.*1h", "mss_bull_1h"),
        (r"MSS Bearish Break.*1h", "mss_bear_1h"),
        (r"MSS Bullish Break.*4h", "mss_bull_4h"),
        (r"MSS Bearish Break.*4h", "mss_bear_4h"),
        (r"^\d{5}$", "grid_price")
    ]
    for pattern, sig in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return sig.replace("_", " ").title(), score_weights.get(sig, 0)
    return None, 0

def generate_trade_suggestion(signal, score):
    base_price = 44000  # placeholder
    if "Bullish" in signal or "Crossing Up" in signal:
        return {"type": "long", "entry": base_price, "sl": base_price - 200, "tp": base_price + 500}
    else:
        return {"type": "short", "entry": base_price, "sl": base_price + 200, "tp": base_price - 500}

def format_stats():
    return f"📊 Signal-Speicher: {len(signal_memory)} Einträge\n📈 Aktive Trades: {len(active_trades)}\n🧠 Letzter Auto-Trade: {time.strftime('%H:%M:%S', time.localtime(last_autotrade_time)) if last_autotrade_time else '–'}"

if __name__ == "__main__":
    app.run(debug=True)
