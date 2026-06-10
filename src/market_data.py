"""Datos de mercado vía Stooq (CSV gratuito, sin API key).

Para la rutina headless (GitHub Actions) no podemos usar el MCP de IBKR,
así que usamos Stooq para precios e histórico. Stooq usa sufijos por bolsa;
los tickers US planos reciben ".us" automáticamente.
"""
import csv
import datetime as dt
import io

import requests


def get_fx(base_ccy):
    """USD -> base_ccy. Devuelve el multiplicador (p.ej. 0.87 para EUR) o None."""
    base = (base_ccy or "USD").upper()
    if base == "USD":
        return 1.0
    # 1) Stooq: eurusd = USD por 1 EUR -> USD->EUR = 1/eurusd
    try:
        url = f"https://stooq.com/q/l/?s={base.lower()}usd&f=sd2t2ohlcv&h&e=csv"
        rows = list(csv.DictReader(io.StringIO(requests.get(url, timeout=20).text)))
        px = float(rows[0]["Close"])
        if px > 0:
            return round(1.0 / px, 6)
    except Exception:
        pass
    # 2) Yahoo Finance fallback (EURUSD=X)
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{base}USD=X?range=5d&interval=1d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (StockDashboard)"}, timeout=20)
        px = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        if px and px > 0:
            return round(1.0 / px, 6)
    except Exception:
        pass
    return None


def _stooq_symbol(ticker, overrides):
    if ticker in overrides:
        return overrides[ticker]
    t = ticker.lower()
    return t if "." in t else f"{t}.us"


def _from_series(ticker, closes, dates, currency="USD", source="Stooq"):
    """Construye el dict de métricas a partir de series de cierres + fechas."""
    if len(closes) < 2:
        return None
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
    return _from_series(ticker, [float(x["Close"]) for x in rows], [x["Date"] for x in rows], source="Stooq")


def _yahoo_quote(ticker):
    """Fallback vía Yahoo Finance chart API (JSON, fiable en CI)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (StockDashboard)"}, timeout=20)
        res = r.json()["chart"]["result"][0]
        closes = res["indicators"]["quote"][0]["close"]
        ts = res["timestamp"]
        ccy = res.get("meta", {}).get("currency", "USD")
    except Exception:
        return None
    import datetime as _dt
    pairs = [(t, c) for t, c in zip(ts, closes) if c is not None]
    if len(pairs) < 2:
        return None
    dates = [_dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d") for t, _ in pairs]
    return _from_series(ticker, [c for _, c in pairs], dates, currency=ccy, source="Yahoo")


def get_quote(ticker, overrides=None):
    """Precio + métricas. Intenta Stooq y, si falla, Yahoo Finance."""
    overrides = overrides or {}
    return _stooq_quote(ticker, overrides) or _yahoo_quote(ticker)
