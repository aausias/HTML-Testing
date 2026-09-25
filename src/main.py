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
_LAST_SENT = os.path.join(os.path.dirname(__file__), "..", "data", "last_sent.txt")


def _guard_active():
    return os.getenv("SCHEDULE_GUARD", "").lower() in ("1", "true", "yes")


def _now_local():
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo(os.getenv("TARGET_TZ", "Europe/Madrid")))


def _should_skip_now():
    """En runs programados: envía UNA vez al día, a partir de la hora objetivo.

    El cron de GitHub es "best-effort" y puede llegar con horas de retraso, así
    que en vez de exigir una hora exacta, disparamos varias veces por la mañana
    y enviamos en cuanto sea >= TARGET_HOUR (hora local), evitando duplicados con
    un sello en data/last_sent.txt. SCHEDULE_GUARD lo activa solo el workflow.
    """
    if not _guard_active():
        return False
    try:
        hour = int(os.getenv("TARGET_HOUR", "10"))
        now = _now_local()
        today = now.date().isoformat()
        if os.path.exists(_LAST_SENT) and open(_LAST_SENT, encoding="utf-8").read().strip() == today:
            print(f"[schedule] ya enviado hoy ({today}); se omite.")
            return True
        if now.hour < hour:
            print(f"[schedule] {now:%H:%M} < {hour:02d}:00 objetivo; aún no toca.")
            return True
    except Exception as e:
        print(f"[schedule] guard no aplicable ({e}); se continúa.")
    return False


def _mark_sent_today():
    """Sella el envío del día (solo en modo programado) para no duplicar."""
    if not _guard_active():
        return
    try:
        with open(_LAST_SENT, "w", encoding="utf-8") as f:
            f.write(_now_local().date().isoformat() + "\n")
    except Exception:
        pass


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

    base = base_ccy.upper()
    sym = {"EUR": "€", "GBP": "£", "USD": "$"}.get(base, "")
    _fx_cache = {}

    def to_base(amount, ccy):
        """Convierte `amount` (en `ccy`) a la moneda base. None si no hay tasa."""
        if amount is None:
            return None
        ccy = (ccy or "USD").upper()
        if ccy not in _fx_cache:
            _fx_cache[ccy] = market_data.get_fx(ccy, base)
        r = _fx_cache[ccy]
        return amount * r if r is not None else None

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
        ai = None
        if use_llm:
            ai = insights.llm_analyze(ticker, quote, headlines, note, llm_model)
            if ai:
                if ai.get("summary"):
                    insight["llm_summary"] = ai["summary"]
                if ai.get("short_term"):
                    note["short_term"] = ai["short_term"]
                if ai.get("medium_term"):
                    note["medium_term"] = ai["medium_term"]

        ccy = (quote or {}).get("currency", "USD")
        last = (quote or {}).get("last")
        qty = item["quantity"]

        value_base = to_base(last * qty, ccy) if (quote and qty) else None

        # P&L vs precio medio de compra (con los lotes que tienen coste conocido)
        cost_qty = sum(l["quantity"] for l in item["lots"] if l.get("avg_price"))
        cost_native = sum(l["quantity"] * l["avg_price"] for l in item["lots"] if l.get("avg_price"))
        pos = {"quantity": qty, "sources": item["sources"], "value_base": value_base, "currency": ccy}
        if cost_qty > 0 and last:
            avg_cost = cost_native / cost_qty
            pos["avg_cost"] = round(avg_cost, 2)
            pos["pnl_pct"] = round((last / avg_cost - 1) * 100, 2)
            pos["pnl_base"] = to_base((last - avg_cost) * cost_qty, ccy)
            pos["pnl_partial"] = cost_qty < qty - 1e-6  # parte de la posición sin coste conocido

        # Plan de acción (niveles por reglas + acción/panorama de la IA si está)
        plan = insights.action_levels(quote, pos)
        if plan:
            if ai and ai.get("action"):
                plan["action"] = ai["action"]
            plan["outlook"] = (ai.get("outlook") if ai else None) or note.get("medium_term")
            plan["currency"] = ccy

        stocks.append(
            {
                "ticker": ticker,
                "name": name_for(ticker),
                "quote": dict(quote or {}, currency=ccy),
                "news": headlines,
                "insight": insight,
                "notes": note,
                "position": pos,
                "plan": plan,
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

    _mark_sent_today()


if __name__ == "__main__":
    main()
