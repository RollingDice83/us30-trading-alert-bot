import os
import re
import json
import time
from datetime import datetime, timedelta
from flask import Flask, request

app = Flask(__name__)

# === Konfiguration ===
VERSION = "v6.6"
TRADES = []
SIGNALS = []
SCORES = {}
OPEN_PRICE = None
SIGNAL_TIMESTAMPS = []

# === Telegram Setup ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === STDV Zonen Berechnung ===
def get_stdv_zones():
    if not OPEN_PRICE:
        return "⚠️ Kein Opening Price gesetzt. Nutze /openprice [Preis]"
    base = float(OPEN_PRICE)
    msg = "📊 STDV Zonen:\n"
    for i in range(-5, 6):
        val = base * (1 + (i / 100))
        if i == 0:
            msg += f"➡️  0% = {val:.2f}\n"
        else:
            msg += f"{i:+}% = {val:.2f}\n"
    return msg

# === Signal speichern ===
def save_signal(text, score):
    timestamp = datetime.utcnow().isoformat()
    SIGNALS.append({"text": text, "score": score, "timestamp": timestamp})
    SIGNAL_TIMESTAMPS.append(datetime.utcnow())

# === Score Engine ===
def score_signal(text):
    score = 0
    text_lower = text.lower()

    if "rsi below 30" in text_lower or "rsi 30" in text_lower:
        score += 60
    elif "rsi crossing up 30" in text_lower:
        score += 60
    elif "rsi crossing down 70" in text_lower or "rsi above 70" in text_lower:
        score += 40

    if "momentum: bullish" in text_lower:
        score += 20
    elif "momentum: bearish" in text_lower:
        score += 10

    if "mss bullish" in text_lower:
        score += 15
    elif "mss bearish" in text_lower:
        score += 15

    if "vix crossing" in text_lower:
        try:
            vix_value = int(re.search(r"vix crossing (\d+)", text_lower).group(1))
            if vix_value >= 40:
                score += 40
            elif vix_value >= 30:
                score += 25
            elif vix_value >= 20:
                score += 15
            elif vix_value < 20:
                score += 5
        except:
            pass

    if re.match(r"^(\d{4,6})(\.\d+)?$", text.strip()):
        score += 10  # Preislevel Grid Impuls

    return min(score, 100)

# === Signal Parsing ===
def parse_signal(text):
    score = score_signal(text)
    save_signal(text, score)
    return f"✅ Signal erkannt: {text} (Score {score})", score

# === Hedge AI Part 1 ===
def hedge_ai():
    return "🤖 Hedge AI Modul geladen. Nächster Schritt: Exit/TP Bewertung."

# === Signal-Dichte Analyse ===
def analyze_density():
    now = datetime.utcnow()
    recent = [t for t in SIGNAL_TIMESTAMPS if now - t <= timedelta(minutes=15)]
    count = len(recent)
    if count >= 3:
        return f"⚠️ Hohe Signal-Dichte: {count} Impulse in 15 Minuten."
    return None

# === Telegram Versand ===
def send_message(chat_id, text):
    print(f"SEND TO {chat_id}: {text}")

# === Telegram Handler ===
@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json()
    text = data.get("message", {}).get("text", "")
    chat_id = str(data.get("message", {}).get("chat", {}).get("id", ""))
    if not text:
        return "OK"

    global OPEN_PRICE

    if text.startswith("/help"):
        msg = f"📘 Befehle ({VERSION}):\n"
        msg += "/status – offene Positionen\n"
        msg += "/trade – Setup senden\n"
        msg += "/close [Preis] – Trade schließen\n"
        msg += "/close all – Alle Trades löschen\n"
        msg += "/update – STDV aktualisieren\n"
        msg += "/openprice [Preis] – STDV Startpreis setzen\n"
        msg += "/zones – STDV Zonen anzeigen\n"
        msg += "/signals – aktuelle Signale\n"
        msg += "/resetsignals – Signal-Reset\n"
        msg += "/batch – mehrere Trades\n"
        msg += "/stats – Lernstatistik\n"
        msg += "/hedgecheck – Hedge Status anzeigen\n"
        send_message(chat_id, msg)

    elif text.startswith("/zones") or text.startswith("/update"):
        msg = get_stdv_zones()
        send_message(chat_id, msg)

    elif text.startswith("/openprice"):
        parts = text.split()
        if len(parts) >= 2:
            try:
                OPEN_PRICE = float(parts[1])
                send_message(chat_id, f"✅ Opening Price gesetzt auf {OPEN_PRICE:.2f}")
            except:
                send_message(chat_id, "⚠️ Ungültiger Preis.")
        else:
            send_message(chat_id, "⚠️ Nutzung: /openprice [Preis]")

    elif text.startswith("/signals"):
        if not SIGNALS:
            send_message(chat_id, "📭 Keine Signale im Speicher.")
        else:
            msg = "🧠 Aktive Signale:\n"
            for s in SIGNALS[-5:]:
                msg += f"• {s['text']} (Score {s['score']})\n"
            send_message(chat_id, msg)

    elif text.startswith("/resetsignals"):
        SIGNALS.clear()
        SIGNAL_TIMESTAMPS.clear()
        send_message(chat_id, "🧹 Signal-Speicher gelöscht.")

    elif text.startswith("/hedgecheck"):
        recent_short_signals = [
            s for s in SIGNALS if "short" in s["text"].lower() or s["score"] >= 60
        ]
        count = len(recent_short_signals)
        if count >= 3:
            advice = "Hedge aktiv lassen und TP prüfen."
            level = "Hoch"
        elif count == 2:
            advice = "Hedge überwachen – mögliches TP-Fenster."
            level = "Mittel"
        else:
            advice = "TP in Sicht oder Hedge ggf. reduzieren."
            level = "Niedrig"
        msg = f"🛡️ Hedge-Status-Check:\n• Short-Signale erkannt: {count}\n• Risiko-Level: {level}\n• Empfehlung: {advice}"
        send_message(chat_id, msg)

    elif re.match(r"^\d{4,6}(\.\d+)?$", text.strip()):
        msg, score = parse_signal(text.strip())
        density_alert = analyze_density()
        send_message(chat_id, msg)
        if density_alert:
            send_message(chat_id, density_alert)

    elif any(keyword in text.lower() for keyword in ["rsi", "momentum", "mss", "vix"]):
        msg, score = parse_signal(text.strip())
        density_alert = analyze_density()
        send_message(chat_id, msg)
        if density_alert:
            send_message(chat_id, density_alert)

    elif text.startswith("/stats"):
        msg = f"📊 Stats:\nSignale: {len(SIGNALS)}\nLetzter Score: {SIGNALS[-1]['score'] if SIGNALS else '–'}\n"
        msg += hedge_ai()
        send_message(chat_id, msg)

    else:
        send_message(chat_id, "❌ Unbekannter Befehl. Nutze /help für alle Kommandos.")

    return "OK"

# === Webhook Endpoint für TradingView Signale ===
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_data(as_text=True)
    try:
        msg, score = parse_signal(data.strip())
        print(f"WEBHOOK SIGNAL: {msg}")
    except:
        print("Webhook-Fehler beim Verarbeiten.")
    return "OK"

# === Root Check ===
@app.route("/")
def home():
    return f"US30 Bot {VERSION} läuft."

if __name__ == "__main__":
    app.run(debug=True, port=5000)
