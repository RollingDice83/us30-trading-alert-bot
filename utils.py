def parse_trade_command(text):
    parts = text.split()
    if len(parts) < 4:
        return None
    try:
        entry = float(parts[1].replace(',', '.'))
        sl = float(parts[2].replace(',', '.'))
        tp = float(parts[3].replace(',', '.'))
        return entry, sl, tp
    except ValueError:
        return None

def evaluate_trade_score(entry, sl, tp):
    try:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk == 0:
            return 0, "Ungültiges Setup – SL ist gleich Entry."
        crv = reward / risk
        score = 50
        if crv > 2: score += 30
        elif crv > 1.5: score += 15
        elif crv < 1: score -= 15
        if reward > 100: score += 10
        elif reward > 50: score += 5
        if risk > 150: score -= 10
        elif risk < 20: score += 5
        reason = f"CRV: {crv:.2f}, Risiko: {risk:.1f} Punkte, Ziel: {reward:.1f} Punkte"
        return max(0, min(100, score)), reason
    except Exception as e:
        return 0, f"Fehler bei der Bewertung: {str(e)}"

def parse_close_command(text):
    try:
        parts = text.split()
        entry = float(parts[1].replace(',', '.'))
        percent = float(parts[2]) if len(parts) > 2 else 100
        return entry, percent
    except:
        return None, None
