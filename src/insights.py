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


def llm_analyze(ticker, quote, news, notes, model):
    """Pide a Claude un JSON con {summary, short_term, medium_term} en español.

    Devuelve el dict o None si no hay API key o falla. Es objetivo y no da
    recomendaciones de compra/venta.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    q = quote or {}
    notes = notes or {}
    headlines = "\n".join(f"- {n['title']}" for n in news[:6]) or "- (sin titulares)"
    prompt = (
        f"Eres analista financiero. Responde SOLO con un objeto JSON válido (sin texto extra) "
        f"con las claves \"summary\", \"short_term\" y \"medium_term\", en español, objetivo y "
        f"SIN recomendar comprar/vender.\n"
        f"- summary: 2 frases sobre qué podría pasar con {ticker}.\n"
        f"- short_term: 1-2 frases de perspectiva a corto plazo (semanas).\n"
        f"- medium_term: 1-2 frases de perspectiva a mediano plazo (6-18 meses).\n\n"
        f"Datos de {ticker}: último {q.get('last')}, YTD {q.get('perf_ytd')}%, "
        f"1m {q.get('perf_1m')}%, rango 52s {q.get('low_52w')}-{q.get('high_52w')}.\n"
        f"Próximos resultados: {notes.get('earnings_date', 'n/d')}. "
        f"Estimado: {notes.get('estimate', 'n/d')}.\n"
        f"Titulares recientes:\n{headlines}\n"
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
                {"model": model, "max_tokens": 600, "messages": [{"role": "user", "content": prompt}]}
            ),
            timeout=45,
        )
        txt = r.json()["content"][0]["text"].strip()
        if txt.startswith("```"):
            txt = txt.strip("`")
            txt = txt[txt.find("{"):]
        data = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        return {
            "summary": data.get("summary"),
            "short_term": data.get("short_term"),
            "medium_term": data.get("medium_term"),
        }
    except Exception:
        return None


def build(ticker, quote, news, cfg):
    """Insight base por reglas (la parte LLM se aplica en main para enriquecer notas)."""
    return rule_based(ticker, quote, news)
