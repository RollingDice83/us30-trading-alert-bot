from flask import Flask, request, jsonify
import datetime
import re
import requests

app = Flask(__name__)

# Speicher für aktive Setups
active_setups = []

# Telegram Bot Config
TELEGRAM_TOKEN = '7958399333:AAEGvMvyD_MhzDT47ZMHXGmJnJ0B_vh9KdU'
CHAT_ID = '805285674'


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'Markdown'}
    requests.post(url, json=payload)


def parse_signal(message):
    signal = {
        'direction': None,
        'entry': None,
        'tp': None,
        'sl': None,
        'type': None,
        'rsi': None,
        'momentum': None,
        'vwap': None,
        'volume': False,
        'liquidity': False,
        'bos': False,
        'fvg': False,
        'text': message,
        'time': datetime.datetime.utcnow().isoformat()
    }

    parts = re.split(r'[|\n ]', message.lower())
    for item in parts:
        item = item.strip()
        if '@' in item or 'bei' in item:
            digits = ''.join(filter(str.isdigit, item))
            if digits:
                signal['entry'] = int(digits)
        if 'long' in item:
            signal['direction'] = 'long'
        if 'short' in item:
            signal['direction'] = 'short'
        if 'tp:' in item:
            signal['tp'] = int(''.join(filter(str.isdigit, item)))
        if 'sl:' in item:
            signal['sl'] = int(''.join(filter(str.isdigit, item)))
        if 'scalp' in item:
            signal['type'] = 'scalp'
        if 'swing' in item:
            signal['type'] = 'swing'
        if 'smack' in item:
            signal['type'] = 'smack'
        if 'rsi:' in item:
            signal['rsi'] = int(''.join(filter(str.isdigit, item)))
        if 'momentum:' in item:
            if 'bullish' in item:
                signal['momentum'] = 'bullish'
            elif 'bearish' in item:
                signal['momentum'] = 'bearish'
        if 'vwap' in item:
            signal['vwap'] = item.strip()
        if 'volume spike' in item:
            signal['volume'] = True
        if 'liquidity' in item:
            signal['liquidity'] = True
        if 'bos' in item or 'break of structure' in item:
            signal['bos'] = True
        if 'fvg' in item:
            signal['fvg'] = True

    return signal


def calculate_signal_score(signal):
    score = 0
    if signal['rsi'] and signal['rsi'] < 30:
        score += 2
    if signal['momentum'] in ['bullish', 'bearish']:
        score += 2
    if signal['volume']:
        score += 1
    if signal['bos']:
        score += 1
    if signal['fvg']:
        score += 1
    if signal['vwap']:
        score += 1
    if signal['liquidity']:
        score += 1
    return score


def build_bot_response(signal, score):
    response = f"\n📌 *Neues US30 Setup erkannt*\n"
    response += f"➡️ Richtung: {signal['direction'].capitalize()}\n"
    response += f"🎯 Entry: {signal['entry']}\n"
    if signal['tp']:
        response += f"🎯 TP: {signal['tp']}\n"
    if signal['sl']:
        response += f"🛑 SL: {signal['sl']}\n"
    if signal['type']:
        response += f"🎯 Entry-Typ: {signal['type'].capitalize()}\n"
    if signal['rsi']:
        response += f"📊 RSI: {signal['rsi']}\n"
    if signal['momentum']:
        response += f"📈 Momentum: {signal['momentum']}\n"
    response += f"⚙️ Signalqualität: {score}/10\n"
    return response


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data:
        return 'Invalid payload', 400

    message = data.get('message')
    if not message:
        return 'Missing message', 400

    if message.lower().startswith('/status'):
        return status()
    elif message.lower().startswith('/help'):
        return help()
    elif message.lower().startswith('/reset'):
        active_setups.clear()
        send_telegram_message("♻️ Alle Setups wurden gelöscht.")
        return jsonify({'status': 'cleared'}), 200

    signal = parse_signal(message)
    score = calculate_signal_score(signal)

    if signal['entry'] and signal['direction']:
        active_setups.append(signal)
        response = build_bot_response(signal, score)
        send_telegram_message(response)
        return jsonify({'status': 'sent', 'score': score}), 200
    else:
        send_telegram_message(f"🟢 Nachricht erhalten: {message}")
        return jsonify({'status': 'echoed'}), 200


@app.route('/status', methods=['GET'])
def status():
    if not active_setups:
        send_telegram_message("📭 Keine aktiven Setups gefunden.")
        return jsonify({'status': 'no setups'}), 200

    text = "\n🗂 *Aktive US30 Setups:*\n"
    for idx, setup in enumerate(active_setups, start=1):
        text += f"#{idx} – {setup['direction'].capitalize()} @ {setup['entry']}"
        if setup['tp']:
            text += f" | TP: {setup['tp']}"
        if setup['sl']:
            text += f" | SL: {setup['sl']}"
        if setup['type']:
            text += f" | Typ: {setup['type'].capitalize()}"
        if setup['rsi']:
            text += f" | RSI: {setup['rsi']}"
        text += f"\n"
    send_telegram_message(text)
    return jsonify({'status': 'sent', 'setups': len(active_setups)}), 200


@app.route('/help', methods=['GET'])
def help():
    help_text = """
📘 *US30 TradingBot – Hilfe*:

✅ Unterstützte Keywords:
- Long, Short, @42100 / bei 42100
- TP: / SL:
- RSI: 30
- Momentum: Bullish / Bearish
- Scalp / Swing / Smack
- VWAP crossed / rejected
- Volume Spike
- Break of Structure / BOS
- FVG / Liquidity Zone

✏️ Beispiel:
US30 Long @42100 TP: 42800 SL: 41900 RSI: 29 Momentum: Bullish Smack

📌 Schließe Position mit:
US30 Long closed @42600 entry 42100
oder
US30 Long partial close @42600 (50%) entry 42100

🧠 Chat-Kommandos:
/status → Aktive Setups anzeigen
/help → Befehlsglossar anzeigen
/reset → Alle Setups löschen
"""
    send_telegram_message(help_text)
    return jsonify({'status': 'sent help'}), 200


if __name__ == '__main__':
    app.run(debug=True)
