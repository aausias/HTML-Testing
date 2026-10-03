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


def _true_atr(closes, highs, lows, n=14):
    """ATR clásico (media del 'true range' de n días). None si faltan máximos/mínimos."""
    if not highs or not lows:
        return None
    trs = []
    for i in range(max(1, len(closes) - n), len(closes)):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        if h is None or l is None or pc is None:
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if len(trs) >= max(5, n // 2) else None


def _from_series(ticker, closes, dates, opens=None, currency="USD", source="Stooq", highs=None, lows=None):
    """Construye el dict de métricas a partir de series diarias (cierre, apertura, máx, mín)."""
    if len(closes) < 2:
        return None
    last, prev = closes[-1], closes[-2]
    today_open = opens[-1] if opens and opens[-1] else None
    # Sin máximos/mínimos diarios usamos el cierre como aproximación
    highs = [h if h is not None else c for h, c in zip(highs, closes)] if highs else list(closes)
    lows = [l if l is not None else c for l, c in zip(lows, closes)] if lows else list(closes)

    # Tendencia: serie reciente (~3 meses) + medias móviles 20/50
    spark = _spark(closes[-63:])
    sma20 = sum(closes[-20:]) / len(closes[-20:]) if len(closes) >= 5 else None
    sma50 = sum(closes[-50:]) / len(closes[-50:]) if len(closes) >= 10 else None
    if sma20 and sma50:
        trend = "alcista" if last > sma20 > sma50 else "bajista" if last < sma20 < sma50 else "lateral"
    else:
        trend = "lateral"

    # Soportes (mínimos) / resistencias (máximos) recientes con los extremos intradía
    def _mm(n):
        return round(min(lows[-n:]), 2), round(max(highs[-n:]), 2)

    low20, high20 = _mm(20)
    low60, high60 = _mm(60)

    # Volatilidad: ATR(14) verdadero; si no hay datos, aproximación por cierres
    atr = _true_atr(closes, highs, lows)
    if atr is None:
        rets = [abs(closes[i] - closes[i - 1]) for i in range(max(1, len(closes) - 14), len(closes))]
        atr = sum(rets) / len(rets) if rets else None
    atr_pct = round(atr / last * 100, 2) if atr else None

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
        "high_52w": round(max(max(highs[-252:]), max(window)), 2),
        "low_52w": round(min(min(lows[-252:]), min(window)), 2),
        "low_20": low20,
        "high_20": high20,
        "low_60": low60,
        "high_60": high60,
        "sma20": round(sma20, 2) if sma20 else None,
        "sma50": round(sma50, 2) if sma50 else None,
        "atr": round(atr, 4) if atr else None,
        "atr_pct": atr_pct,
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

    def col(name):
        return [float(x[name]) if x.get(name) not in (None, "", "N/D") else None for x in rows]

    return _from_series(
        ticker, [float(x["Close"]) for x in rows], [x["Date"] for x in rows],
        opens=col("Open"), highs=col("High"), lows=col("Low"), source="Stooq",
    )


def _yahoo_quote(ticker, overrides):
    """Fallback vía Yahoo Finance chart API (JSON, fiable y con tickers internacionales)."""
    import datetime as _dt
    sym = overrides.get(ticker, ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d"
    try:
        res = requests.get(url, headers=_UA, timeout=20).json()["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        closes, ts = q["close"], res["timestamp"]
        n = len(closes)
        opens = q.get("open") or [None] * n
        highs = q.get("high") or [None] * n
        lows = q.get("low") or [None] * n
        ccy = res.get("meta", {}).get("currency", "USD")
    except Exception:
        return None
    rows = [r for r in zip(ts, opens, highs, lows, closes) if r[4] is not None]
    if len(rows) < 2:
        return None
    dates = [_dt.datetime.utcfromtimestamp(r[0]).strftime("%Y-%m-%d") for r in rows]
    return _from_series(
        ticker, [r[4] for r in rows], dates,
        opens=[r[1] for r in rows], highs=[r[2] for r in rows], lows=[r[3] for r in rows],
        currency=ccy, source="Yahoo",
    )


def get_quote(ticker, overrides=None):
    """Precio + métricas. Intenta Stooq y, si falla, Yahoo Finance."""
    overrides = overrides or {}
    return _stooq_quote(ticker, overrides) or _yahoo_quote(ticker, overrides)


_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def get_next_earnings(ticker):
    """Próxima fecha de resultados + BPA de consenso (Nasdaq). None si no hay dato.

    Devuelve {"date": "YYYY-MM-DD", "eps": float|None, "when": "tras cierre"|"antes de apertura"|None}.
    """
    import re
    url = f"https://api.nasdaq.com/api/analyst/{ticker}/earnings-date"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    try:
        d = requests.get(url, headers=headers, timeout=15).json().get("data") or {}
    except Exception:
        return None
    txt = f"{d.get('reportText') or ''} {d.get('announcement') or ''}"
    iso = None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", txt)
    if m:
        iso = f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    else:
        m = re.search(r"\b([A-Z][a-z]{2})[a-z]*\.? (\d{1,2}), (\d{4})", txt)
        if m and m.group(1) in _MONTHS:
            iso = f"{m.group(3)}-{_MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
    if not iso:
        return None
    eps = re.search(r"consensus EPS forecast for the quarter is \$?(-?[\d.]+)", txt)
    low = txt.lower()
    when = "tras cierre" if "after market close" in low else "antes de apertura" if "before market open" in low else None
    return {"date": iso, "eps": float(eps.group(1).rstrip(".")) if eps else None, "when": when}
