"""Consolidación del portafolio (IBKR + Revolut + watchlist)."""
from collections import defaultdict


def consolidate(ibkr_positions, revolut_holdings, watchlist=None):
    """Une posiciones de distintas fuentes por ticker.

    Devuelve una lista ordenada por valor de mercado (desc) con:
      {ticker, quantity, sources, lots: [...], is_watchlist}
    """
    watchlist = watchlist or []
    by_ticker = defaultdict(lambda: {"quantity": 0.0, "sources": set(), "lots": []})

    for p in list(ibkr_positions) + list(revolut_holdings):
        t = p["ticker"]
        entry = by_ticker[t]
        entry["quantity"] += float(p.get("quantity") or 0)
        entry["sources"].add(p.get("source", "?"))
        entry["lots"].append(p)

    result = []
    for ticker, entry in by_ticker.items():
        result.append(
            {
                "ticker": ticker,
                "quantity": round(entry["quantity"], 4),
                "sources": sorted(entry["sources"]),
                "lots": entry["lots"],
                "is_watchlist": False,
            }
        )

    held = {r["ticker"] for r in result}
    for t in watchlist:
        t = str(t).upper()
        if t not in held:
            result.append(
                {"ticker": t, "quantity": 0.0, "sources": ["watchlist"], "lots": [], "is_watchlist": True}
            )

    return result
