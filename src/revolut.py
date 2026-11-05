"""Posiciones de Revolut.

Revolut no expone un API automatizable aquí, así que las posiciones se cargan:
  1) desde config/settings.yaml -> portfolio.revolut_holdings, o
  2) desde un CSV exportado en data/revolut_positions.csv
     (columnas: ticker,quantity[,avg_price])
"""
import csv
import os

_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "revolut_positions.csv")


def load_holdings(cfg):
    holdings = []

    # 1) Desde la config
    for h in cfg.get("portfolio", {}).get("revolut_holdings", []) or []:
        if not h.get("ticker"):
            continue
        holdings.append(
            {
                "ticker": str(h["ticker"]).upper(),
                "quantity": float(h.get("quantity") or 0),
                "avg_price": float(h["avg_price"]) if h.get("avg_price") else None,
                "currency": h.get("currency"),
                "source": "Revolut",
            }
        )

    # 2) Desde un CSV exportado (se acumula sobre lo anterior)
    if os.path.exists(_CSV_PATH):
        with open(_CSV_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                tkr = (row.get("ticker") or row.get("Ticker") or "").strip().upper()
                if not tkr:
                    continue
                qty = row.get("quantity") or row.get("Quantity") or 0
                avg = row.get("avg_price") or row.get("Avg_price") or row.get("avgPrice")
                holdings.append(
                    {
                        "ticker": tkr,
                        "quantity": float(qty or 0),
                        "avg_price": float(avg) if avg else None,
                        "currency": row.get("currency"),
                        "source": "Revolut",
                    }
                )

    return holdings
