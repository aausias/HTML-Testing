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


def enrich_with_llm(ticker, quote, news, base, model):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return base
    headlines = "\n".join(f"- {n['title']}" for n in news[:6])
    q = quote or {}
    prompt = (
        f"Eres analista de inversiones. En 2-3 frases en español, de forma objetiva y "
        f"sin recomendar comprar/vender, resume qué podría pasar con {ticker}.\n"
        f"Datos: último {q.get('last')}, YTD {q.get('perf_ytd')}%, 1m {q.get('perf_1m')}%, "
        f"rango 52s {q.get('low_52w')}-{q.get('high_52w')}.\n"
        f"Titulares:\n{headlines}\n"
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
                {
                    "model": model,
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ),
            timeout=40,
        )
        txt = r.json()["content"][0]["text"].strip()
        if txt:
            base = dict(base)
            base["llm_summary"] = txt
    except Exception:
        pass
    return base


def build(ticker, quote, news, cfg):
    base = rule_based(ticker, quote, news)
    if cfg.get("insights", {}).get("use_llm"):
        base = enrich_with_llm(
            ticker, quote, news, base, cfg["insights"].get("llm_model", "claude-haiku-4-5-20251001")
        )
    return base
