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
_NOTES = os.path.join(os.path.dirname(__file__), "..", "data", "notes.json")


def _should_skip_now():
    """En runs programados, solo continúa a la hora local objetivo.

    Permite un único envío diario a las TARGET_HOUR de TARGET_TZ aunque el cron
    de GitHub (UTC) dispare a varias horas para cubrir el cambio de hora (DST).
    SCHEDULE_GUARD lo activa solo el workflow en ejecuciones 'schedule'.
    """
    if os.getenv("SCHEDULE_GUARD", "").lower() not in ("1", "true", "yes"):
        return False
    try:
        from zoneinfo import ZoneInfo
        tz = os.getenv("TARGET_TZ", "Europe/Madrid")
        hour = int(os.getenv("TARGET_HOUR", "10"))
        now = dt.datetime.now(ZoneInfo(tz))
        if now.hour != hour:
            print(f"[schedule] {now:%H:%M} {tz} ≠ {hour:02d}:00 objetivo; se omite esta ejecución.")
            return True
    except Exception as e:
        print(f"[schedule] guard no aplicable ({e}); se continúa.")
    return False


def _load_notes():
    if os.path.exists(_NOTES):
        with open(_NOTES, encoding="utf-8") as f:
            return json.load(f)
    return {}


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
    if _should_skip_now():
        return
    cfg = load_config()
    overrides = cfg.get("market", {}).get("symbol_overrides", {})
    base_ccy = cfg.get("portfolio", {}).get("base_currency", "EUR")

    ibkr_pos = _load_ibkr(cfg)
    revolut_pos = revolut.load_holdings(cfg)
    watchlist = cfg.get("portfolio", {}).get("watchlist", [])
    notes = _load_notes()

    consolidated = portfolio.consolidate(ibkr_pos, revolut_pos, watchlist)

    # Tipo de cambio USD -> moneda base (para mostrar valor y %)
    fx = market_data.get_fx(base_ccy)
    sym = {"EUR": "€", "GBP": "£", "USD": "$"}.get(base_ccy.upper(), "")
    if not fx:  # sin FX -> mostramos en USD
        fx, sym = 1.0, "$"

    use_llm = cfg.get("insights", {}).get("use_llm")
    llm_model = cfg.get("insights", {}).get("llm_model", "claude-haiku-4-5-20251001")

    stocks = []
    for item in consolidated:
        ticker = item["ticker"]
        quote = market_data.get_quote(ticker, overrides)
        headlines = news_mod.get_news(ticker, cfg["news"].get("max_items_per_ticker", 4))
        insight = insights.build(ticker, quote, headlines, cfg)
        note = dict(notes.get(ticker) or {})

        # IA: regenera resumen + corto/mediano plazo (si está activado y hay API key)
        if use_llm:
            ai = insights.llm_analyze(ticker, quote, headlines, note, llm_model)
            if ai:
                if ai.get("summary"):
                    insight["llm_summary"] = ai["summary"]
                if ai.get("short_term"):
                    note["short_term"] = ai["short_term"]
                if ai.get("medium_term"):
                    note["medium_term"] = ai["medium_term"]

        value_base = None
        if quote and item["quantity"]:
            value_base = quote["last"] * item["quantity"] * fx

        stocks.append(
            {
                "ticker": ticker,
                "name": name_for(ticker),
                "quote": dict(quote or {}, currency=(quote or {}).get("currency", "USD")),
                "news": headlines,
                "insight": insight,
                "notes": note,
                "position": {
                    "quantity": item["quantity"],
                    "sources": item["sources"],
                    "value_base": value_base,
                },
            }
        )

    # Ordena por valor (desc); watchlist al final
    stocks.sort(key=lambda s: (s["position"]["quantity"] == 0, -(s["position"]["value_base"] or 0)))

    total_value = sum(s["position"]["value_base"] or 0 for s in stocks)
    totals = {
        "Patrimonio en acciones": (f"{sym}{total_value:,.0f}".replace(",", ".")) if total_value else "—",
        "Posiciones": str(sum(1 for s in stocks if s["position"]["quantity"])),
    }

    htmlout = render.render(stocks, totals, base_symbol=sym)
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
