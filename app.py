import json
import re
import time
from flask import Flask, request, jsonify
import os
import sys
import requests

app = Flask(__name__)

VERSION = "v5.5.1"

active_trades = []
signal_memory = []
open_price = None

learned_results = []

def get_live_price():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/US30USD=X?interval=1m&range=1d"
        res = requests.get(url)
        data = res.json()
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return round(price, 2)
    except:
        return None

@app.route("/", methods=["GET"])
def home():
    return "US30 Bot Live"

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.json
    if not data or "message" not in data:
        return jsonify(ok=True)

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text.lower().startswith("/help"):
        return send_message(chat_id, get_help())
    elif text.lower().startswith("/status"):
        return send_message(chat_id, format_status())
    elif text.lower().startswith("/trade"):
        return handle_trade(text, chat_id)
    elif text.lower().startswith("/batch"):
        return handle_batch(text, chat_id)
    elif text.lower().startswith("/openprice"):
        return handle_open_price(text, chat_id)
    elif text.lower().startswith("/resetsignals"):
        signal_memory.clear()
        return send_message(chat_id, "♻️ Signal-Speicher geleert.")
    elif text.lower().startswith("/signals"):
        return send_message(chat_id, format_signals())
    elif text.lower().startswith("/zones"):
        return send_message(chat_id, format_zones())
    elif text.lower().startswith("/close"):
        return handle_close(text, chat_id)
    elif text.lower().startswith("/update"):
        return send_message(chat_id, f"🔄 Update erhalten ({VERSION}) – alle Systeme aktiv.")

    parsed, score, tag = parse_signal(text)
    if parsed:
        signal_memory.append(f"{parsed} [{time.strftime('%H:%M:%S')}] (Score {score}) | Tag: {tag}")
        if score >= 60:
            return send_message(chat_id, generate_trade_suggestion(parsed, score))
        else:
            return send_message(chat_id, f"✅ Signal erkannt: {parsed} (Score {score})")

    return send_message(chat_id, "❌ Unbekannter Befehl. Nutze /help für alle Kommandos.")

def send_message(chat_id, text):
    print(f"SEND TO {chat_id}: {text}")
    return jsonify({"method": "sendMessage", "chat_id": chat_id, "text": text})

def get_help():
    return f"""📘 Befehle ({VERSION}):
/status – offene Positionen
/trade – Setup senden
/close [Preis] – Trade schließen
/close [long|short] [Entry] at [Exit] – Position bewerten
/close all – alle Trades löschen
/stats – Auswertung aller Trades nach Signal-Tag
/update – Check & Statusmeldung
/openprice [Preis] – STDV Startpreis setzen
/zones – STDV Zonen anzeigen
/signals – aktuelle Signale
/resetsignals – Signal-Reset
/batch – mehrere Trades"""

def format_stats():
    if not learned_results:
        return "📊 Keine abgeschlossenen Trades gespeichert."
    stats = {}
    for r in learned_results:
        tag = r.get("tag", r["type"])
        if tag not in stats:
            stats[tag] = {"total": 0, "wins": 0}
        stats[tag]["total"] += 1
        if r["pnl"] > 0:
            stats[tag]["wins"] += 1

    lines = ["📈 Signal-Auswertung:"]
    for tag, val in stats.items():
        winrate = round(100 * val["wins"] / val["total"], 1)
        lines.append(f"• {tag.upper()}: {val['total']} Trades → {val['wins']}x Gewinn → {winrate}%")
        return "
".join(lines)

@app.route("/stats", methods=["POST"])
def stats():
    data = request.json
    if not data or "message" not in data:
        return jsonify(ok=True)
    chat_id = data["message"]["chat"]["id"]
    return send_message(chat_id, format_stats())
    return f"""📘 Befehle ({VERSION}):
/status – offene Positionen
/trade – Setup senden
/close [Preis] – Trade schließen
/close [long|short] [Entry] at [Exit] – Position bewerten
/close all – alle Trades löschen
/update – Check & Statusmeldung
/openprice [Preis] – STDV Startpreis setzen
/zones – STDV Zonen anzeigen
/signals – aktuelle Signale
/resetsignals – Signal-Reset
/batch – mehrere Trades"""

def parse_signal(text):
    # Erweiterung zur Webhook-Verarbeitung von exakten Signaltexten
    signal_map = {
        "rsi crossing up 30.00": ("RSI Cross Up 30", 40, "rsi"),
        "rsi below 30": ("RSI < 30", 40, "rsi"),
        "rsi above 70": ("RSI > 70", 20, "rsi"),
        "rsi crossing down 70.00": ("RSI Cross Down 70", 20, "rsi"),
        "momentum: bullish": ("Momentum Bullish", 30, "momentum"),
        "momentum: bearish": ("Momentum Bearish", 30, "momentum"),
        "mss bullish break": ("MSS Bullish Break", 20, "mss"),
        "mss bearish break": ("MSS Bearish Break", 20, "mss")
    }

    text_lower = text.lower().strip()
    for keyword, (label, score, tag) in signal_map.items():
        if keyword in text_lower:
            return (label, score, tag)
    text_lower = text.lower()
    score = 0
    signals = []
    tag = "unknown"

    rsi_patterns = [
        r"rsi.*?(\d{1,2}\.\d+)",
        r"rsi[:=\s]+(\d{1,2}\.\d+)",
        r"us30.*?rsi.*?(\d{1,2}\.\d+)"
    ]

    for pattern in rsi_patterns:
        match = re.search(pattern, text_lower)
        if match:
            value = float(match.group(1))
            tag = "rsi"
            if value < 30:
                score += 40
                signals.append("RSI < 30")
            elif value > 70:
                score += 20
                signals.append("RSI > 70")
            break

    if "momentum: bullish" in text_lower:
        score += 30
        tag = "momentum"
        signals.append("Momentum Bullish")
    if "momentum: bearish" in text_lower:
        score += 30
        tag = "momentum"
        signals.append("Momentum Bearish")
    if "mss bullish break" in text_lower:
        score += 20
        tag = "mss"
        signals.append("MSS Bullish Break")
    if "mss bearish break" in text_lower:
        score += 20
        tag = "mss"
        signals.append("MSS Bearish Break")

    if re.fullmatch(r"\d{5}", text.strip()):
        score += 10
        tag = "grid"
        signals.append(f"Grid Signal: {text.strip()}")

    if score > 0:
        return (" + ".join(signals), score, tag)
    return (None, 0, tag)

def generate_trade_suggestion(reason, score):
    direction = "LONG" if "bullish" in reason.lower() or "rsi < 30" in reason.lower() else "SHORT"
    price = get_live_price()
    if not price:
        price = "(aktuell)"
    sl = round(40 + (100 - score) * 0.5)
    tp = round(100 + score)
    return f"🚀 Tradevorschlag (Score {score})\nTyp: {direction}\nEntry: {price}\nTrigger: {reason}\nSL: {sl} Punkte\nTP: {tp} Punkte\nTag: signal-auto\nNutze /trade um manuell zu speichern."

def handle_trade(text, chat_id):
    match = re.match(r'/trade (long|short) (\d+) SL=(\d+) TP=(\d+)', text, re.I)
    if not match:
        return send_message(chat_id, "❌ Ungültiges Format. Beispiel: /trade long 42500 SL=42250 TP=43200")
    direction, entry, sl, tp = match.groups()
    active_trades.append({"type": direction.lower(), "entry": float(entry), "sl": float(sl), "tp": float(tp), "tag": "manual"})
    return send_message(chat_id, f"✅ {direction.upper()} Trade @ {entry} gespeichert.")

def handle_batch(text, chat_id):
    lines = text.strip().split("\n")
    count = 0
    for line in lines:
        if "lot @" in line and "TP:" in line:
            try:
                type_match = re.search(r"(LONG|SHORT)", line)
                lot_match = re.search(r"(\d+(\.\d+)?) lot", line)
                entry_match = re.search(r"@ (\d+(\.\d+)?)", line)
                tp_match = re.search(r"TP: (\d+(\.\d+)?|open)", line)
                sl_match = re.search(r"SL: (\d+(\.\d+)?|manual|none)", line)
                tag_match = re.search(r"Tag: (\w+)", line)

                trade = {
                    "type": type_match.group(1).lower(),
                    "lot": float(lot_match.group(1)),
                    "entry": float(entry_match.group(1)),
                    "tp": tp_match.group(1) if tp_match else "open",
                    "sl": sl_match.group(1) if sl_match else "manual",
                    "tag": tag_match.group(1) if tag_match else "none"
                }
                active_trades.append(trade)
                count += 1
            except:
                continue
    if count == 0:
        return send_message(chat_id, "⚠️ Keine gültigen Trades erkannt.")
    else:
        return send_message(chat_id, f"✅ {count} Trades gespeichert.")

def handle_open_price(text, chat_id):
    global open_price
    match = re.match(r"/openprice (\d+(\.\d+)?)", text)
    if not match:
        return send_message(chat_id, "❌ Beispiel: /openprice 44100")
    open_price = float(match.group(1))
    return send_message(chat_id, f"📍 Opening Price gesetzt: {open_price}")

def format_zones():
    if open_price is None:
        return "📊 Keine Zonen verfügbar. Bitte /openprice setzen."
    zones = []
    for i in range(-5, 6):
        level = round(open_price * (1 + i / 100), 1)
        color = "🟥" if i < 0 else ("🟩" if i > 0 else "🟩")
        zones.append(f"{color} {i:+}%: {level}")
    return "📊 STDV Zonen:\n" + "\n".join(zones)

def format_signals():
    if not signal_memory:
        return "📡 Keine aktiven Signale."
    return "📡 Signale:\n" + "\n".join(signal_memory)

def format_status():
    if not active_trades:
        return "ℹ️ Keine aktiven Positionen."
    longs = [t for t in active_trades if t["type"] == "long"]
    shorts = [t for t in active_trades if t["type"] == "short"]
    msg = "📈 Offene Positionen\n\n"
    if longs:
        msg += f"🟢 Longs ({len(longs)}):\n"
        for t in longs:
            lot = t.get("lot", 1.0)
            msg += f"• {lot} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']}\n"
    if shorts:
        msg += f"\n🔴 Shorts ({len(shorts)}):\n"
        for t in shorts:
            lot = t.get("lot", 1.0)
            msg += f"• {lot} lot @ {t['entry']} → TP {t['tp']} – SL: {t['sl']}\n"
    return msg

def handle_close(text, chat_id):
    if text.strip().lower() == "/close all":
        active_trades.clear()
        return send_message(chat_id, "✅ Alle Positionen wurden gelöscht.")

    match_simple = re.match(r"/close (\d+(\.\d+)?)", text)
    match_advanced = re.match(r"/close\s*(long|short)?\s*(\d+(\.\d+)?)\s*at\s*(\d+(\.\d+)?)", text)

    if match_advanced:
        pos_type, entry, _, exit_price, _ = match_advanced.groups()
        entry = float(entry)
        exit_price = float(exit_price)
        trade = next((t for t in active_trades if abs(t["entry"] - entry) < 1), None)
        if not pos_type and trade:
            pos_type = trade["type"]
        if not pos_type:
            return send_message(chat_id, "❌ Positionstyp nicht erkannt.")
        profit = (exit_price - entry) if pos_type == "long" else (entry - exit_price)
        learned_results.append({"type": pos_type, "entry": entry, "exit": exit_price, "pnl": round(profit, 1)})
        active_trades[:] = [t for t in active_trades if abs(t["entry"] - entry) >= 1]
        return send_message(chat_id, f"📉 {pos_type.upper()} @ {entry} geschlossen bei {exit_price} → PnL: {profit:.1f}")

    elif match_simple:
        entry = float(match_simple.group(1))
        active_trades[:] = [t for t in active_trades if t["entry"] != entry]
        return send_message(chat_id, f"✅ Position bei {entry} gelöscht.")

    return send_message(chat_id, "❌ Ungültiger Close-Befehl. Beispiel: /close long 44500 at 44950")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
