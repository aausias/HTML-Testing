"""Orquestador de la rutina diaria del dashboard de acciones.

Flujo:
  1. Carga posiciones de IBKR (Flex Web Service) + Revolut (config/CSV)
  2. Consolida por ticker
  3. Descarga precios (Stooq) y noticias (RSS) por acción
  4. Genera insights ("qué podría pasar")
  5. Renderiza el HTML -> docs/index.html (web)
  6. Envía el email (si está habilitado)
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import ibkr_flex
import insights
import market_data
import news as news_mod
import portfolio
import render
import revolut
from config import load_config
from emailer import send_email
from names import name_for

_SNAPSHOT = os.path.join(os.path.dirname(__file__), "..", "data", "holdings_snapshot.json")


def _load_ibkr(cfg):
    """Intenta IBKR Flex; si no hay credenciales, usa el snapshot de respaldo."""
    if cfg.get("portfolio", {}).get("ibkr_enabled", True):
        try:
            pos = ibkr_flex.fetch_positions()
            if pos:
                return pos
        except Exception as e:
            print(f"[ibkr] Flex no disponible ({e}); usando snapshot de respaldo.")
    if os.path.exists(_SNAPSHOT):
        with open(_SNAPSHOT, encoding="utf-8") as f:
            return json.load(f).get("ibkr", [])
    return []


def main():
    cfg = load_config()
    overrides = cfg.get("market", {}).get("symbol_overrides", {})
    base_ccy = cfg.get("portfolio", {}).get("base_currency", "EUR")

    ibkr_pos = _load_ibkr(cfg)
    revolut_pos = revolut.load_holdings(cfg)
    watchlist = cfg.get("portfolio", {}).get("watchlist", [])

    consolidated = portfolio.consolidate(ibkr_pos, revolut_pos, watchlist)

    stocks = []
    total_value = 0.0
    for item in consolidated:
        ticker = item["ticker"]
        quote = market_data.get_quote(ticker, overrides)
        headlines = news_mod.get_news(ticker, cfg["news"].get("max_items_per_ticker", 4))
        insight = insights.build(ticker, quote, headlines, cfg)

        value_label = None
        if quote and item["quantity"]:
            val = quote["last"] * item["quantity"]
            total_value += val
            value_label = f"~{val:,.0f} {quote.get('currency', 'USD')}"

        stocks.append(
            {
                "ticker": ticker,
                "name": name_for(ticker),
                "quote": dict(quote or {}, currency=(quote or {}).get("currency", "USD")),
                "news": headlines,
                "insight": insight,
                "position": {
                    "quantity": item["quantity"],
                    "sources": item["sources"],
                    "value_label": value_label,
                },
            }
        )

    # Ordena: primero posiciones por valor, luego watchlist
    stocks.sort(key=lambda s: (s["position"]["quantity"] == 0, -(s["quote"].get("last") or 0) * s["position"]["quantity"]))

    totals = {
        "Posiciones": str(sum(1 for s in stocks if s["position"]["quantity"])),
        "Fuentes": "IBKR + Revolut",
    }

    htmlout = render.render(stocks, totals)
    out_path = cfg["delivery"].get("web_output", "docs/index.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(htmlout)
    print(f"[render] Dashboard escrito en {out_path}")

    if cfg["delivery"].get("email_enabled"):
        today = dt.date.today().isoformat()
        subject = f"{cfg['delivery'].get('email_subject_prefix', 'Dashboard')} — {today}"
        send_email(htmlout, subject, cfg["delivery"].get("email_to"))


if __name__ == "__main__":
    main()
