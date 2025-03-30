from flask import Flask, request
import json
import re
import datetime

app = Flask(__name__)

active_trades = []
active_signals = []
open_price = None
version = "v4.0.1"

# Farben für STDV-Ausgabe
def colorize(value, base):
    if value == base:
        return f"\U0001F4C8 Opening: {value}"
    elif value > base:
        return f"\U0001F7E2 +{round((value-base)/base*100, 2)}%: {value}"
    else:
        return f"\U0001F534 {round((value-base)/base*100, 2)}%: {value}"

# STDV-Zonen berechnen
def get_zones():
    if not open_price:
        return "⚠️ Kein Opening Price gesetzt."
    base = float(open_price)
    zones = [colorize(round(base * (1 + i / 100), 2), base) for i in range(-5, 6)]
    return "\n".join(zones)

# Signal hinzufügen
def add_signal(text):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    active_signals.append(f"{timestamp} - {text}")

# /batch Parser
def handle_batch(text):
    lines = text.splitlines()
    parsed = []
    for line in lines:
        if line.strip().startswith("LONG") or line.strip().startswith("SHORT"):
            try:
                direction = "LONG" if "LONG" in line else "SHORT"
                lot = float(re.search(r"(\d+(\.\d+)?) lot", line).group(1))
                entry = float(re.search(r"@ (\d+(\.\d+)?)", line).group(1))
                tp_match = re.search(r"TP: ([\d\.]+)", line)
                tp = float(tp_match.group(1)) if tp_match else None
                sl_match = re.search(r"SL: ([\d\.]+)", line)
                sl = float(sl_match.group(1)) if sl_match else None
                tag_match = re.search(r"Tag: (\w+)", line)
                tag = tag_match.group(1) if tag_match else ""
                parsed.append({"dir": direction, "lot": lot, "entry": entry, "tp": tp, "sl": sl, "tag": tag})
            except Exception as e:
                print(f"Fehler beim Parsen einer Zeile: {line} Fehler: {e}")
    return parsed

@app.route("/", methods=["GET"])
def home():
    return "US30 Bot v4.0.1 running"

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json()
    if not data or "message" not in data:
        return "ok"

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "")
    response = ""

    # Normalisiere Text
    cmd = text.lower()

    # Signaleingang (z. B. Momentum: Bullish 1h)
    if any(x in text for x in ["Momentum:", "RSI", "MSS", "crossing"]):
        add_signal(text)
        return send(chat_id, f"✅ Signal empfangen: {text}")

    if cmd.startswith("/help"):
        response = f"📘 Befehle ({version}):\n"
        response += "/status – offene Positionen\n"
        response += "/trade – Setup senden\n"
        response += "/close – Trade schließen\n"
        response += "/update – STDV aktualisieren\n"
        response += "/openprice – STDV Startpreis setzen\n"
        response += "/zones – STDV Zonen anzeigen\n"
        response += "/signals – aktuelle Signale\n"
        response += "/resetsignals – Signal-Reset\n"
        response += "/batch – mehrere Trades"

    elif cmd.startswith("/openprice"):
        try:
            global open_price
            open_price = float(re.findall(r"\d+\.?\d*", text)[0])
            response = f"📈 Opening Price gesetzt: {open_price}\n\n{get_zones()}"
        except:
            response = "⚠️ Ungültiges Format. Beispiel: /openprice 44100"

    elif cmd.startswith("/zones"):
        response = get_zones()

    elif cmd.startswith("/signals"):
        if not active_signals:
            response = "⚠️ Keine aktiven Signale."
        else:
            response = "\n".join(active_signals[-10:])

    elif cmd.startswith("/resetsignals"):
        active_signals.clear()
        response = "♻️ Signal-Speicher geleert."

    elif cmd.startswith("/batch"):
        parsed = handle_batch(text)
        if parsed:
            active_trades.extend(parsed)
            response = f"✅ {len(parsed)} Trades übernommen."
        else:
            response = "⚠️ Keine gültigen Trades erkannt."

    elif cmd.startswith("/status"):
        if not active_trades:
            response = "📭 Keine aktiven Positionen."
        else:
            longs = [t for t in active_trades if t['dir'] == "LONG"]
            shorts = [t for t in active_trades if t['dir'] == "SHORT"]
            total_l = sum(t['lot'] for t in longs)
            total_s = sum(t['lot'] for t in shorts)
            response = f"📈 Offene Positionen\n\n🟢 Longs ({len(longs)} | {total_l} lot):"
            for t in longs:
                response += f"\n• {t['lot']} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']}"
            response += f"\n\n🔴 Shorts ({len(shorts)} | {total_s} lot):"
            for t in shorts:
                response += f"\n• {t['lot']} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']}"

    elif cmd.startswith("/trade"):
        try:
            dir_match = re.search(r"(long|short)", cmd)
            entry_match = re.search(r"(\d{4,6})", cmd)
            sl_match = re.search(r"sl=(\d+\.?\d*)", cmd)
            tp_match = re.search(r"tp=(\d+\.?\d*)", cmd)
            if dir_match and entry_match:
                trade = {
                    "dir": dir_match.group(1).upper(),
                    "entry": float(entry_match.group(1)),
                    "sl": float(sl_match.group(1)) if sl_match else None,
                    "tp": float(tp_match.group(1)) if tp_match else None,
                    "lot": 1.0,
                    "tag": "manual"
                }
                active_trades.append(trade)
                response = f"✅ Trade gespeichert: {trade['dir']} @ {trade['entry']}"
            else:
                response = "❌ Ungültiges Format. Beispiel: /trade long 42500 SL=42250 TP=43200"
        except:
            response = "⚠️ Fehler beim Speichern des Trades."

    elif cmd.startswith("/close"):
        entry = re.findall(r"\d+\.?\d*", cmd)
        if not entry:
            response = "❌ Bitte gib den Entry Preis an. Beispiel: /close 42500"
        else:
            e = float(entry[0])
            before = len(active_trades)
            active_trades[:] = [t for t in active_trades if t['entry'] != e]
            after = len(active_trades)
            if before == after:
                response = "⚠️ Keine Position mit diesem Entry gefunden."
            else:
                response = f"✅ Position @ {e} geschlossen."

    elif cmd.startswith("/update"):
        if open_price:
            response = f"♻️ STDV neu berechnet:\n{get_zones()}"
        else:
            response = "⚠️ Bitte zuerst /openprice setzen."

    else:
        response = "❓ Unbekannter Befehl. Nutze /help für alle Optionen."

    return send(chat_id, response)

# Antwort senden
import requests

def send(chat_id, msg):
    TOKEN = "<DEIN_BOT_TOKEN>"
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": msg}
    requests.post(url, json=data)
    return "ok"
