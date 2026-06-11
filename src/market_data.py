"""Datos de mercado vía Stooq (CSV gratuito) con fallback a Yahoo Finance.

Stooq usa sufijos por bolsa; los tickers US planos reciben ".us". Para tickers
no-US (p.ej. ETFs europeos) define un override en config -> market.symbol_overrides
con el símbolo de Yahoo (ej. VWCE: VWCE.DE); Stooq usa la versión en minúsculas.
"""
import csv
import io

import requests

_UA = {"User-Agent": "Mozilla/5.0 (StockDashboard)"}


def get_fx(from_ccy, to_ccy):
    """Multiplicador para convertir de `from_ccy` a `to_ccy` (p.ej. USD->EUR ≈ 0.87)."""
    f = (from_ccy or "USD").upper()
    t = (to_ccy or "USD").upper()
    if f == t:
        return 1.0
    # 1) Stooq: 'usdeur' = cuántos EUR por 1 USD
    try:
        url = f"https://stooq.com/q/l/?s={f.lower()}{t.lower()}&f=sd2t2ohlcv&h&e=csv"
        rows = list(csv.DictReader(io.StringIO(requests.get(url, timeout=20).text)))
        px = float(rows[0]["Close"])
        if px > 0:
            return round(px, 6)
    except Exception:
        pass
    # 2) Yahoo: USDEUR=X
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{f}{t}=X?range=5d&interval=1d"
        px = requests.get(url, headers=_UA, timeout=20).json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        if px and px > 0:
            return round(px, 6)
    except Exception:
        pass
    return None


def _stooq_symbol(ticker, overrides):
    if ticker in overrides:
        return str(overrides[ticker]).lower()
    t = ticker.lower()
    return t if "." in t else f"{t}.us"


def _spark(values, n=24):
    """Submuestrea una serie a ~n puntos para el mini-gráfico de tendencia."""
    if len(values) <= n:
        return [round(v, 2) for v in values]
    step = len(values) / n
    return [round(values[int(i * step)], 2) for i in range(n)]


def _from_series(ticker, closes, dates, opens=None, currency="USD", source="Stooq"):
    """Construye el dict de métricas a partir de series de cierres (+ aperturas)."""
    if len(closes) < 2:
        return None
    last, prev = closes[-1], closes[-2]
    today_open = opens[-1] if opens and opens[-1] else None

    # Tendencia: serie reciente (~3 meses) + medias móviles 20/50
    spark = _spark(closes[-63:])
    sma20 = sum(closes[-20:]) / len(closes[-20:]) if len(closes) >= 5 else None
    sma50 = sum(closes[-50:]) / len(closes[-50:]) if len(closes) >= 10 else None
    if sma20 and sma50:
        trend = "alcista" if last > sma20 > sma50 else "bajista" if last < sma20 < sma50 else "lateral"
    else:
        trend = "lateral"

    def perf(n):
        return round((last / closes[-n] - 1) * 100, 2) if len(closes) >= n else None

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
        "open": round(today_open, 2) if today_open else None,
        "prev_close": round(prev, 2),
        "change_abs": round(last - prev, 2) if prev else 0.0,
        "change_pct": round((last / prev - 1) * 100, 2) if prev else 0.0,
        "perf_5d": perf(5),
        "perf_1m": perf(21),
        "perf_ytd": ytd,
        "high_52w": round(max(window), 2),
        "low_52w": round(min(window), 2),
        "spark": spark,
        "trend": trend,
        "above_sma50": bool(sma50 and last >= sma50),
        "as_of": dates[-1],
        "currency": currency,
        "source": source,
    }


def _stooq_quote(ticker, overrides):
    sym = _stooq_symbol(ticker, overrides)
    try:
        r = requests.get(f"https://stooq.com/q/d/l/?s={sym}&i=d", timeout=30)
        rows = [x for x in csv.DictReader(io.StringIO(r.text)) if x.get("Close") not in (None, "", "N/D")]
    except Exception:
        return None
    if len(rows) < 2:
        return None
    opens = [float(x["Open"]) if x.get("Open") not in (None, "", "N/D") else None for x in rows]
    return _from_series(ticker, [float(x["Close"]) for x in rows], [x["Date"] for x in rows], opens=opens, source="Stooq")


def _yahoo_quote(ticker, overrides):
    """Fallback vía Yahoo Finance chart API (JSON, fiable y con tickers internacionales)."""
    import datetime as _dt
    sym = overrides.get(ticker, ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d"
    try:
        res = requests.get(url, headers=_UA, timeout=20).json()["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        closes, opens, ts = q["close"], q.get("open") or [], res["timestamp"]
        ccy = res.get("meta", {}).get("currency", "USD")
    except Exception:
        return None
    opens = opens or [None] * len(closes)
    triples = [(t, o, c) for t, o, c in zip(ts, opens, closes) if c is not None]
    if len(triples) < 2:
        return None
    dates = [_dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d") for t, _, _ in triples]
    return _from_series(
        ticker, [c for _, _, c in triples], dates, opens=[o for _, o, _ in triples], currency=ccy, source="Yahoo"
    )


def get_quote(ticker, overrides=None):
    """Precio + métricas. Intenta Stooq y, si falla, Yahoo Finance."""
    overrides = overrides or {}
    return _stooq_quote(ticker, overrides) or _yahoo_quote(ticker, overrides)
