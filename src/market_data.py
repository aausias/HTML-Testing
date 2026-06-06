"""Datos de mercado vía Stooq (CSV gratuito, sin API key).

Para la rutina headless (GitHub Actions) no podemos usar el MCP de IBKR,
así que usamos Stooq para precios e histórico. Stooq usa sufijos por bolsa;
los tickers US planos reciben ".us" automáticamente.
"""
import csv
import datetime as dt
import io

import requests


def _stooq_symbol(ticker, overrides):
    if ticker in overrides:
        return overrides[ticker]
    t = ticker.lower()
    return t if "." in t else f"{t}.us"


def get_quote(ticker, overrides=None):
    """Devuelve métricas de precio o None si no hay datos."""
    overrides = overrides or {}
    sym = _stooq_symbol(ticker, overrides)
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    try:
        r = requests.get(url, timeout=30)
        rows = list(csv.DictReader(io.StringIO(r.text)))
    except Exception:
        return None
    rows = [x for x in rows if x.get("Close") not in (None, "", "N/D")]
    if len(rows) < 2:
        return None

    closes = [float(x["Close"]) for x in rows]
    dates = [x["Date"] for x in rows]
    last, prev = closes[-1], closes[-2]

    def perf(n):
        return round((last / closes[-n] - 1) * 100, 2) if len(closes) >= n else None

    # YTD
    year = dates[-1][:4]
    ytd = None
    for px, d in zip(closes, dates):
        if d[:4] == year:
            ytd = round((last / px - 1) * 100, 2)
            break

    window = closes[-252:]
    return {
        "ticker": ticker,
        "last": round(last, 2),
        "prev_close": round(prev, 2),
        "change_pct": round((last / prev - 1) * 100, 2) if prev else 0.0,
        "perf_5d": perf(5),
        "perf_1m": perf(21),
        "perf_ytd": ytd,
        "high_52w": round(max(window), 2),
        "low_52w": round(min(window), 2),
        "as_of": dates[-1],
        "source": "Stooq",
    }
