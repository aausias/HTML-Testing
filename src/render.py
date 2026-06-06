"""Render del dashboard a HTML (sirve para web y para email)."""
import datetime as dt
import html


def _fmt(n, dec=2, suffix=""):
    if n is None:
        return "—"
    return f"{n:,.{dec}f}{suffix}"


def _pct_badge(p):
    if p is None:
        return '<span style="color:#888">—</span>'
    color = "#16a34a" if p >= 0 else "#dc2626"
    arrow = "▲" if p >= 0 else "▼"
    return f'<span style="color:{color};font-weight:600">{arrow} {p:+.2f}%</span>'


def _outlook_color(bias):
    if bias >= 2:
        return "#16a34a"
    if bias <= -2:
        return "#dc2626"
    return "#d97706"


def render(stocks, totals, generated_at=None):
    """stocks: lista de dicts {ticker, name, quote, news, insight, position}."""
    generated_at = generated_at or dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    cards = []
    for s in stocks:
        q = s.get("quote") or {}
        ins = s.get("insight") or {}
        pos = s.get("position") or {}

        news_html = ""
        for n in s.get("news", [])[:4]:
            dot = {"pos": "#16a34a", "neg": "#dc2626", "neu": "#9ca3af"}.get(n.get("sentiment"), "#9ca3af")
            title = html.escape(n["title"])
            link = html.escape(n.get("link") or "#")
            news_html += (
                f'<li style="margin:6px 0;list-style:none">'
                f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
                f'background:{dot};margin-right:8px"></span>'
                f'<a href="{link}" style="color:#1d4ed8;text-decoration:none">{title}</a></li>'
            )
        if not news_html:
            news_html = '<li style="color:#888;list-style:none">Sin titulares recientes.</li>'

        signals_html = "".join(f"<li style='margin:4px 0'>{html.escape(x)}</li>" for x in ins.get("signals", []))
        llm = ins.get("llm_summary")
        llm_html = (
            f'<p style="margin:10px 0 0;padding:10px;background:#f1f5f9;border-radius:8px;'
            f'font-style:italic;color:#334155">{html.escape(llm)}</p>' if llm else ""
        )

        pos_html = ""
        if pos.get("quantity"):
            pos_html = (
                f'<div style="font-size:13px;color:#475569;margin-top:4px">'
                f'{_fmt(pos["quantity"], 4)} acc. · {", ".join(pos.get("sources", []))}'
                f'{" · " + pos["value_label"] if pos.get("value_label") else ""}</div>'
            )

        cards.append(f"""
        <div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:18px;margin-bottom:16px">
          <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap">
            <div>
              <span style="font-size:20px;font-weight:700;color:#0f172a">{html.escape(s['ticker'])}</span>
              <span style="color:#64748b;margin-left:8px">{html.escape(s.get('name',''))}</span>
              {pos_html}
            </div>
            <div style="text-align:right">
              <div style="font-size:20px;font-weight:700;color:#0f172a">{_fmt(q.get('last'))} {html.escape(q.get('currency','USD'))}</div>
              <div>{_pct_badge(q.get('change_pct'))}</div>
            </div>
          </div>
          <div style="display:flex;gap:18px;flex-wrap:wrap;margin:12px 0;font-size:13px;color:#475569">
            <span>YTD {_pct_badge(q.get('perf_ytd'))}</span>
            <span>1M {_pct_badge(q.get('perf_1m'))}</span>
            <span>52s: {_fmt(q.get('low_52w'))} – {_fmt(q.get('high_52w'))}</span>
          </div>
          <div style="display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:600;
                      color:#fff;background:{_outlook_color(ins.get('bias',0))}">{html.escape(ins.get('outlook','—'))}</div>
          <ul style="margin:10px 0 0;padding-left:18px;color:#334155;font-size:14px">{signals_html}</ul>
          {llm_html}
          <div style="margin-top:12px;font-size:12px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.04em">Noticias clave</div>
          <ul style="margin:6px 0 0;padding:0;font-size:14px">{news_html}</ul>
        </div>""")

    totals_html = ""
    if totals:
        rows = "".join(
            f'<tr><td style="padding:4px 12px 4px 0">{html.escape(k)}</td>'
            f'<td style="padding:4px 0;text-align:right;font-weight:600">{v}</td></tr>'
            for k, v in totals.items()
        )
        totals_html = (
            f'<div style="background:#0f172a;color:#fff;border-radius:14px;padding:18px;margin-bottom:20px">'
            f'<div style="font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#94a3b8;margin-bottom:8px">Resumen del portafolio</div>'
            f'<table style="width:100%;font-size:15px">{rows}</table></div>'
        )

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard de Acciones</title></head>
<body style="margin:0;background:#f8fafc;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<div style="max-width:680px;margin:0 auto;padding:24px 16px">
  <h1 style="font-size:24px;color:#0f172a;margin:0 0 4px">📊 Tu Dashboard de Acciones</h1>
  <p style="color:#64748b;margin:0 0 20px;font-size:14px">Generado {html.escape(generated_at)} · IBKR + Revolut</p>
  {totals_html}
  {''.join(cards)}
  <p style="color:#94a3b8;font-size:12px;text-align:center;margin-top:24px">
    Información con fines informativos, no es asesoramiento de inversión.<br>
    Precios y métricas de IBKR/Stooq; noticias de Yahoo Finance / Google News.
  </p>
</div></body></html>"""
