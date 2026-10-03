"""Generación de insights ("qué podría pasar") por acción.

Por defecto usa un motor basado en reglas (momentum, posición en rango 52s,
sentimiento de titulares). Si insights.use_llm=true y existe ANTHROPIC_API_KEY,
enriquece la redacción con la API de Claude.
"""
import json
import os

import requests


def rule_based(ticker, quote, news):
    signals = []
    bias = 0

    if quote:
        last = quote.get("last")
        hi, lo = quote.get("high_52w"), quote.get("low_52w")
        if last and hi and lo and hi > lo:
            pos = (last - lo) / (hi - lo)
            if pos >= 0.9:
                signals.append("Cotiza muy cerca de máximos de 52 semanas (zona de fuerza, pero con riesgo de toma de beneficios).")
                bias += 1
            elif pos <= 0.2:
                signals.append("Cotiza cerca de mínimos de 52 semanas (posible suelo o debilidad estructural).")
                bias -= 1

        ytd = quote.get("perf_ytd")
        if ytd is not None:
            if ytd >= 15:
                signals.append(f"Fuerte momentum en el año (YTD {ytd:+.1f}%).")
                bias += 1
            elif ytd <= -15:
                signals.append(f"Año difícil (YTD {ytd:+.1f}%); vigilar si hay cambio de tendencia.")
                bias -= 1

        m1 = quote.get("perf_1m")
        if m1 is not None and abs(m1) >= 8:
            signals.append(f"Movimiento relevante el último mes ({m1:+.1f}%).")

    # Sentimiento de noticias
    pos = sum(1 for n in news if n.get("sentiment") == "pos")
    neg = sum(1 for n in news if n.get("sentiment") == "neg")
    if pos or neg:
        if pos > neg:
            signals.append(f"Titulares recientes con tono mayoritariamente positivo ({pos} vs {neg}).")
            bias += 1
        elif neg > pos:
            signals.append(f"Titulares recientes con tono mayoritariamente negativo ({neg} vs {pos}).")
            bias -= 1

    if bias >= 2:
        outlook = "Sesgo alcista de corto plazo"
    elif bias <= -2:
        outlook = "Sesgo bajista / cautela"
    else:
        outlook = "Sesgo mixto / lateral"

    if not signals:
        signals.append("Sin señales claras con los datos disponibles; vigilar próximos catalizadores (resultados, guidance).")

    return {"outlook": outlook, "bias": bias, "signals": signals}


def llm_analyze(ticker, quote, news, notes, model, today=None):
    """Pide a Claude un JSON con resumen, corto/mediano plazo, acción y panorama.

    Recibe la fecha de hoy y la evolución reciente para que el texto refleje lo
    que cambió (y no repita eventos ya pasados). Devuelve el dict o None.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    q = quote or {}
    notes = notes or {}
    headlines = "\n".join(
        f"- {n['title']}" + (f" ({n['pub'][:16]})" if n.get("pub") else "") for n in news[:6]
    ) or "- (sin titulares)"
    earnings = (
        f"Próximos resultados: {notes['earnings_date']}. Estimado: {notes.get('estimate', 'n/d')}."
        if notes.get("earnings_iso") else
        "No hay fecha de resultados confirmada: NO inventes ni menciones una fecha."
    )
    prompt = (
        f"Hoy es {today or 'n/d'}. Eres analista financiero. Responde SOLO con un objeto JSON válido "
        f"(sin texto extra) con las claves \"summary\", \"short_term\", \"medium_term\", \"action\" y "
        f"\"outlook\", en español y objetivo.\n"
        f"- summary: 2 frases sobre qué está pasando HOY con {ticker} y qué podría pasar.\n"
        f"- short_term: 1-2 frases (próximas semanas). Debe apoyarse en el dato más reciente "
        f"(movimiento de hoy/semana o el último titular), no en generalidades.\n"
        f"- medium_term: 1-2 frases (6-18 meses): tesis y principal riesgo.\n"
        f"- action: UNA de estas etiquetas exactas: \"MANTENER\", \"TOMAR BENEFICIOS\" o \"VIGILAR / STOP\".\n"
        f"- outlook: 1-2 frases con los próximos catalizadores y riesgos.\n"
        f"Reglas: nunca describas como futuro algo cuya fecha ya pasó respecto de hoy; "
        f"no repitas frases genéricas.\n\n"
        f"Datos de {ticker} (moneda {q.get('currency')}): último {q.get('last')}, hoy {q.get('change_pct')}%, "
        f"5 días {q.get('perf_5d')}%, 1 mes {q.get('perf_1m')}%, YTD {q.get('perf_ytd')}%, "
        f"tendencia {q.get('trend')}, media 50d {q.get('sma50')}, volatilidad diaria (ATR) {q.get('atr_pct')}%, "
        f"rango 52s {q.get('low_52w')}-{q.get('high_52w')}.\n"
        f"{earnings}\n"
        f"Titulares recientes (más nuevos primero):\n{headlines}\n"
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            data=json.dumps(
                {"model": model, "max_tokens": 800, "messages": [{"role": "user", "content": prompt}]}
            ),
            timeout=45,
        )
        body = r.json()
        if "content" not in body:
            print(f"[ia] {ticker}: respuesta sin contenido ({str(body)[:200]})")
            return None
        txt = body["content"][0]["text"].strip()
        data = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        print(f"[ia] {ticker}: análisis generado")
        return {
            "summary": data.get("summary"),
            "short_term": data.get("short_term"),
            "medium_term": data.get("medium_term"),
            "action": data.get("action"),
            "outlook": data.get("outlook"),
        }
    except Exception as e:
        print(f"[ia] {ticker}: falló ({e})")
        return None


def action_levels(quote, pos):
    """Niveles ILUSTRATIVOS de stop/profit según la estructura y volatilidad de CADA acción.

    - Volatilidad: ATR(14) = cuánto se mueve la acción en un día normal.
    - Stop: debajo del soporte más cercano (mínimo de 20d, media de 50d o mínimo de 60d)
      con medio ATR de margen, siempre a 1.5-4 ATR del precio (ni tan pegado que lo
      salte el ruido diario, ni tan lejos que el riesgo sea enorme). Sin soporte útil:
      2.5 ATR.
    - Profit: la resistencia más cercana (máximo de 60d o de 52 semanas) si paga al
      menos 1.5 veces el riesgo; si no hay, 2 veces el riesgo (R:R 2:1).
    No hay porcentajes fijos: una acción tranquila (ETF) tiene niveles cercanos y una
    volátil, lejanos. No es asesoramiento.
    """
    q = quote or {}
    last = q.get("last")
    if not last:
        return None
    hi, lo = q.get("high_52w"), q.get("low_52w")
    posr = (last - lo) / (hi - lo) if (hi and lo and hi > lo) else 0.5
    atr = q.get("atr") or last * (q.get("atr_pct") or 2.5) / 100

    # --- STOP: soporte más cercano por debajo, a 1.5-4 ATR del precio ---
    supports = [(q.get("low_20"), "mínimo de 20 días"), (q.get("sma50"), "media de 50 días"),
                (q.get("low_60"), "mínimo de 60 días")]
    supports = sorted([s for s in supports if s[0] and s[0] < last], key=lambda s: -s[0])
    stop, basis = None, None
    for lvl, name in supports:
        cand = lvl - 0.5 * atr
        if last - cand < 1.5 * atr:      # demasiado pegado: probar el siguiente soporte
            continue
        if last - cand <= 4 * atr:
            stop, basis = cand, f"bajo el {name} ({lvl:.2f})"
        break
    if stop is None:
        stop, basis = last - 2.5 * atr, "2,5 veces su volatilidad diaria (sin soporte cercano claro)"
    stop = min(max(stop, last * 0.70), last * 0.99)
    risk = last - stop

    # --- PROFIT: resistencia más cercana que pague >= 1.5x el riesgo; si no, 2R ---
    resist = [(q.get("high_60"), "máximo de 60 días"), (q.get("high_52w"), "máximo de 52 semanas")]
    resist = sorted([r for r in resist if r[0] and r[0] > last], key=lambda r: r[0])
    target, target_basis = None, None
    for lvl, name in resist:
        if lvl - last >= 1.5 * risk:
            target, target_basis = lvl, f"resistencia en el {name} ({lvl:.2f})"
            break
    if target is None:
        target, target_basis = last + 2 * risk, "2 veces el riesgo (sin resistencia útil por encima)"

    pnl = (pos or {}).get("pnl_pct")
    trend = q.get("trend", "lateral")
    if pnl is not None and pnl >= 25 and posr >= 0.8:
        action = "TOMAR BENEFICIOS"
    elif (pnl is not None and pnl <= -15) or posr <= 0.2 or (trend == "bajista" and not q.get("above_sma50", True)):
        action = "VIGILAR / STOP"
    else:
        action = "MANTENER"

    return {
        "action": action,
        "stop": round(stop, 2),
        "stop_pct": round((1 - stop / last) * 100, 1),
        "target": round(target, 2),
        "target_pct": round((target / last - 1) * 100, 1),
        "basis": basis,
        "target_basis": target_basis,
        "atr_pct": round(atr / last * 100, 1),
        "rr": round((target - last) / risk, 1) if risk else None,
    }


def build(ticker, quote, news, cfg):
    """Insight base por reglas (la parte LLM se aplica en main para enriquecer notas)."""
    return rule_based(ticker, quote, news)
