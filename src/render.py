"""Render del dashboard a HTML **email-safe** (layout con tablas + barras CSS).

Gmail y la mayoría de clientes no soportan flexbox ni SVG, así que todo se
construye con <table> e inline-styles, y los "gráficos" son celdas de color
(barra de asignación y barra de rango de 52 semanas). Sin imágenes externas
(que los clientes bloquean por defecto).
"""
import datetime as dt
import html

_PALETTE = ["#8b5cf6", "#22c55e", "#f59e0b", "#14b8a6", "#3b82f6", "#ec4899", "#06b6d4", "#a3a3a3"]


def _fmt(n, dec=2):
    return "—" if n is None else f"{n:,.{dec}f}"


def _pct(p):
    if p is None:
        return '<span style="color:#94a3b8">—</span>'
    c = "#16a34a" if p >= 0 else "#dc2626"
    a = "▲" if p >= 0 else "▼"
    return f'<span style="color:{c};font-weight:700">{a} {p:+.1f}%</span>'


def _range_bar(quote):
    """Barra de posición del precio en su rango de 52 semanas."""
    last, hi, lo = quote.get("last"), quote.get("high_52w"), quote.get("low_52w")
    if not (last and hi and lo and hi > lo):
        return ""
    pct = max(2, min(98, round((last - lo) / (hi - lo) * 100)))
    color = "#16a34a" if (quote.get("perf_ytd") or 0) >= 0 else "#dc2626"
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding-top:12px"><tr>
      <td width="16%" style="font-size:11px;color:#94a3b8">{_fmt(lo, 0)}</td>
      <td><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-radius:5px;overflow:hidden"><tr>
        <td height="8" width="{pct}%" style="background:{color}"></td><td height="8" style="background:#e5e7eb"></td>
      </tr></table></td>
      <td width="16%" align="right" style="font-size:11px;color:#94a3b8">{_fmt(hi, 0)}</td>
    </tr></table>"""


def _alloc_bar(stocks, total):
    if not total:
        return ""
    segs, legend = "", ""
    for i, s in enumerate(stocks):
        val = s.get("_value") or 0
        if val <= 0:
            continue
        w = round(val / total * 100, 1)
        c = _PALETTE[i % len(_PALETTE)]
        segs += f'<td height="16" width="{w}%" style="background:{c}"></td>'
        legend += f'<td style="white-space:nowrap;padding-right:10px"><span style="color:{c}">■</span> {html.escape(s["ticker"])} {w:.0f}%</td>'
    return f"""
      <div style="font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#94a3b8;padding-bottom:6px">Asignación por acción</div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-radius:7px;overflow:hidden"><tr>{segs}</tr></table>
      <table role="presentation" cellpadding="0" cellspacing="0" style="padding-top:8px;font-size:12px;color:#cbd5e1"><tr>{legend}</tr></table>"""


def _badge(bias):
    bg = "#16a34a" if bias >= 2 else "#dc2626" if bias <= -2 else "#d97706"
    label = "Sesgo alcista" if bias >= 2 else "Sesgo bajista / cautela" if bias <= -2 else "Sesgo mixto / lateral"
    return f'<div style="display:inline-block;margin-top:10px;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700;color:#fff;background:{bg}">{label}</div>'


def render(stocks, totals, generated_at=None):
    generated_at = generated_at or dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # valor por acción para la barra de asignación
    total_val = 0.0
    for s in stocks:
        q = s.get("quote") or {}
        s["_value"] = (q.get("last") or 0) * (s.get("position") or {}).get("quantity", 0)
        total_val += s["_value"]

    cards = ""
    for s in stocks:
        q = s.get("quote") or {}
        ins = s.get("insight") or {}
        pos = s.get("position") or {}
        ccy = html.escape(q.get("currency", "USD"))

        pos_line = ""
        if pos.get("quantity"):
            vl = f' · {html.escape(pos["value_label"])}' if pos.get("value_label") else ""
            pos_line = (f'<div style="font-size:12px;color:#475569;padding-top:3px">'
                        f'{_fmt(pos["quantity"], 4)} acc. · {html.escape(", ".join(pos.get("sources", [])))}{vl}</div>')

        signals = "".join(f"<li style='margin:3px 0'>{html.escape(x)}</li>" for x in ins.get("signals", []))
        llm = ins.get("llm_summary")
        insight_block = (
            f'<div style="margin-top:10px;padding:10px 12px;background:#f1f5f9;border-radius:8px;font-size:14px;color:#334155;line-height:1.5">{html.escape(llm)}</div>'
            if llm else
            f'<ul style="margin:10px 0 0;padding-left:18px;font-size:14px;color:#334155;line-height:1.5">{signals}</ul>'
        )

        news_links = " &nbsp;·&nbsp; ".join(
            f'<a href="{html.escape(n.get("link") or "#")}" style="color:#1d4ed8;text-decoration:none">'
            f'{"🟢" if n.get("sentiment")=="pos" else "🔴" if n.get("sentiment")=="neg" else "⚪"} {html.escape(n["title"][:70])}</a>'
            for n in s.get("news", [])[:3]
        ) or '<span style="color:#94a3b8">Sin titulares recientes.</span>'

        cards += f"""
        <tr><td style="padding-bottom:14px">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fff;border:1px solid #e5e7eb;border-radius:14px"><tr><td style="padding:18px">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
              <td align="left" valign="top"><span style="font-size:19px;font-weight:800">{html.escape(s['ticker'])}</span>
                <span style="color:#64748b">{html.escape(s.get('name',''))}</span>{pos_line}</td>
              <td align="right" valign="top" style="white-space:nowrap"><span style="font-size:19px;font-weight:800">{_fmt(q.get('last'))} {ccy}</span>
                <div style="font-size:12px;padding-top:3px">YTD {_pct(q.get('perf_ytd'))}</div></td>
            </tr></table>
            {_range_bar(q)}
            {_badge(ins.get('bias', 0))}
            {insight_block}
            <div style="font-size:13px;padding-top:10px">{news_links}</div>
          </td></tr></table>
        </td></tr>"""

    totals_rows = "".join(
        f'<tr><td style="padding:3px 0;color:#cbd5e1">{html.escape(k)}</td>'
        f'<td style="padding:3px 0;text-align:right;font-weight:700;color:#fff">{html.escape(str(v))}</td></tr>'
        for k, v in (totals or {}).items()
    )

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tu Dashboard de Acciones</title></head>
<body style="margin:0;background:#f1f5f9;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0f172a">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:680px;width:100%">
  <tr><td style="padding-bottom:4px">
    <div style="font-size:24px;font-weight:800">📊 Tu Dashboard de Acciones</div>
    <div style="color:#64748b;font-size:13px;padding-top:4px">{html.escape(generated_at)} · IBKR + Revolut</div>
  </td></tr>
  <tr><td style="padding:16px 0">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;border-radius:14px"><tr><td style="padding:20px">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:14px">{totals_rows}</table>
      <div style="height:12px"></div>
      {_alloc_bar(stocks, total_val)}
    </td></tr></table>
  </td></tr>
  {cards}
  <tr><td style="padding:8px 8px 0;color:#94a3b8;font-size:11px;text-align:center;line-height:1.5">
    Las barras muestran la posición del precio en su rango de 52 semanas.<br>
    Información con fines informativos, <b>no es asesoramiento de inversión</b>.<br>
    Precios/posiciones: IBKR + Revolut · Datos de mercado: Stooq · Noticias: Yahoo Finance / Google News.
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
