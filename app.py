# /close command vollständig und flexibel
elif cmd.startswith("/close"):
    try:
        parts = user_text.split()
        if len(parts) == 2 and parts[1].lower() == "all":
            count = len(active_trades)
            active_trades.clear()
            send_message(chat_id, f"🚫 Alle {count} Positionen wurden geschlossen.")
        else:
            direction = parts[1].lower()
            entry_price = float(parts[2])
            removed = [t for t in active_trades if t['entry'] == entry_price and t['direction'] == direction]
            active_trades[:] = [t for t in active_trades if t not in removed]
            send_message(chat_id, f"❌ Position bei {entry_price} ({direction}) geschlossen.")
    except:
        send_message(chat_id, "❌ Ungültiger Befehl. Beispiel: /close long 42500 oder /close all")

# RSI explizit per Text speichern: z.B. "RSI 1h 13.82"
elif re.match(r"RSI\s+\d+h?\s+\d+(\.\d+)?", user_text, re.IGNORECASE):
    value = float(re.findall(r"\d+(\.\d+)?", user_text)[-1])
    add_signal(f"RSI_1h_Value: {value}")
    send_message(chat_id, f"📩 RSI-Wert gespeichert: {value}")
    evaluate_score()

# Verbesserte STDV-Anzeige mit Farbcodes
elif cmd.startswith("/update") or cmd.startswith("/zones"):
    zones = load_stdv_zones()
    if zones:
        msg = f"📊 Aktuelle STDV-Zonen:\n🔹 Opening: {zones['open']}\n"
        for k, v in zones["zones"].items():
            if "-" in k: msg += f"🔻 {k}: {v}\n"
            elif "+" in k: msg += f"🟢 {k}: {v}\n"
        send_message(chat_id, msg)
    else:
        send_message(chat_id, "⚠️ Noch keine STDV-Zonen gespeichert.")

# Verbesserter /status mit Lot Size & Gesamtanzahl
def handle_status(chat_id):
    if not active_trades:
        send_message(chat_id, "📊 Keine offenen Positionen.")
        return

    msg = "📈 Offene Positionen:\n"
    total_long = total_short = 0

    for trade in active_trades:
        lot = trade.get("lot", 1)
        msg += f"• {trade['symbol']} {trade['direction']} {lot} lot @ {trade['entry']}"
        if trade.get("tp"): msg += f" → TP {trade['tp']}"
        if trade.get("sl"): msg += f", SL {trade['sl']}"
        if trade.get("score"): msg += f" (Score {trade['score']})"
        if trade.get("tag"): msg += f" – {trade['tag']}"
        msg += "\n"

        if trade['direction'] == "long":
            total_long += lot
        elif trade['direction'] == "short":
            total_short += lot

    msg += f"\n📊 Gesamt: {total_long} Long | {total_short} Short"
    send_message(chat_id, msg)
