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
        val = (s.get("position") or {}).get("value_base") or 0
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


def _notes_block(notes):
    """Bloque de próximos resultados + horizontes corto/mediano plazo."""
    if not notes:
        return ""
    ed = notes.get("earnings_date")
    est = notes.get("estimate")
    st = notes.get("short_term")
    mt = notes.get("medium_term")
    head = ""
    if ed:
        head += f'<div style="font-size:13px;color:#334155"><b>📅 Resultados:</b> {html.escape(ed)}</div>'
    if est:
        head += f'<div style="font-size:13px;color:#334155;padding-top:2px"><b>🎯 Estimado:</b> {html.escape(est)}</div>'
    horizons = ""
    if st or mt:
        horizons = (
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px"><tr>'
            f'<td valign="top" width="50%" style="padding-right:5px"><div style="background:#eff6ff;border-radius:8px;padding:9px 11px;font-size:13px;color:#1e3a8a;line-height:1.45"><b>⏱ Corto plazo</b><br>{html.escape(st or "—")}</div></td>'
            f'<td valign="top" width="50%" style="padding-left:5px"><div style="background:#ecfdf5;border-radius:8px;padding:9px 11px;font-size:13px;color:#065f46;line-height:1.45"><b>📈 Mediano plazo</b><br>{html.escape(mt or "—")}</div></td>'
            '</tr></table>'
        )
    if not head and not horizons:
        return ""
    return ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px;border-top:1px solid #eef2f7">'
            f'<tr><td style="padding-top:10px">{head}{horizons}</td></tr></table>')


def _badge(bias):
    bg = "#16a34a" if bias >= 2 else "#dc2626" if bias <= -2 else "#d97706"
    label = "Sesgo alcista" if bias >= 2 else "Sesgo bajista / cautela" if bias <= -2 else "Sesgo mixto / lateral"
    return f'<div style="display:inline-block;margin-top:10px;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700;color:#fff;background:{bg}">{label}</div>'


def _stats_row(q, pos, base_symbol):
    """Línea de mercado (apertura/último/cierre + var. día) y P&L de mi posición."""
    ccy = html.escape(q.get("currency", ""))
    out = ""

    mk = []
    if q.get("open") is not None:
        mk.append(f"Apertura {q['open']}")
    if q.get("last") is not None:
        mk.append(f"Último {q['last']}")
    if q.get("prev_close") is not None:
        mk.append(f"Cierre ant. {q['prev_close']}")
    if mk:
        chg = ""
        ca, cp = q.get("change_abs"), q.get("change_pct")
        if ca is not None and cp is not None:
            color = "#16a34a" if ca >= 0 else "#dc2626"
            sign = "+" if ca >= 0 else "−"
            chg = (f' · <span style="color:{color};font-weight:700">'
                   f'{sign}{abs(ca)} {ccy} ({cp:+.2f}%) hoy</span>')
        out += f'<div style="font-size:12px;color:#64748b;padding-top:10px">{" · ".join(mk)} {ccy}{chg}</div>'

    if pos.get("avg_cost") is not None:
        pp = pos.get("pnl_pct") or 0
        pb = pos.get("pnl_base")
        color = "#16a34a" if pp >= 0 else "#dc2626"
        money = ""
        if pb is not None:
            s = "+" if pb >= 0 else "−"
            money = (f"{s}{base_symbol}{abs(pb):,.0f}".replace(",", ".")) + " "
        partial = ' <span style="color:#94a3b8">· coste parcial</span>' if pos.get("pnl_partial") else ""
        out += (f'<div style="font-size:12px;color:#475569;padding-top:4px">'
                f'Mi posición · precio medio {pos["avg_cost"]} {ccy} · '
                f'<span style="color:{color};font-weight:700">{money}({pp:+.1f}%)</span>{partial}</div>')

    return out


def _sparkline(q, base_symbol=""):
    """Mini-gráfico de tendencia (~3 meses) con barras de color, email-safe."""
    spark = q.get("spark") or []
    if len(spark) < 3:
        return ""
    # Menos barras y más anchas para que no se vea apretado
    if len(spark) > 18:
        step = len(spark) / 18.0
        spark = [spark[int(i * step)] for i in range(18)]
    lo, hi = min(spark), max(spark)
    rng = (hi - lo) or 1
    trend = q.get("trend", "lateral")
    color = {"alcista": "#16a34a", "bajista": "#dc2626"}.get(trend, "#64748b")
    H = 64  # alto del gráfico (antes 34) -> más legible
    w = round(100.0 / len(spark), 3)
    bars = ""
    for v in spark:
        h = 10 + round((v - lo) / rng * (H - 12))
        # div con contenido (&nbsp;) y line-height: Gmail colapsa los divs vacíos
        bars += (
            f'<td valign="bottom" width="{w}%" style="padding:0 1px;font-size:0;line-height:0">'
            f'<div style="height:{h}px;line-height:{h}px;font-size:1px;background:{color};'
            f'border-radius:2px 2px 0 0">&nbsp;</div></td>'
        )
    ccy = html.escape(q.get("currency", ""))
    cap = f'Tendencia ~3m: <b style="color:{color}">{html.escape(trend)}</b>'
    if "above_sma50" in q:
        cap += f' · {"por encima" if q.get("above_sma50") else "por debajo"} de su media de 50 días'
    return (
        f'<div style="padding-top:14px;background:#fafafa;border-radius:8px;padding:12px 10px 6px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="height:{H}px;border-bottom:1px solid #e5e7eb"><tr>{bars}</tr></table>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding-top:4px"><tr>'
        f'<td style="font-size:10px;color:#94a3b8">{lo} {ccy}</td>'
        f'<td align="right" style="font-size:10px;color:#94a3b8">máx {hi} {ccy}</td></tr></table>'
        f'</div>'
        f'<div style="font-size:11px;color:#94a3b8;padding-top:6px">📈 {cap}</div>'
    )


def _levels_box(plan):
    """Cajas prominentes con Stop y Profit sugeridos (precio)."""
    if not plan or plan.get("stop") is None:
        return ""
    ccy = html.escape(plan.get("currency") or "")
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:10px"><tr>
      <td valign="top" width="50%" style="padding-right:5px"><div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:9px 11px">
        <div style="font-size:11px;color:#991b1b;font-weight:700;text-transform:uppercase;letter-spacing:.03em">🛑 Stop sugerido</div>
        <div style="font-size:17px;font-weight:800;color:#dc2626;padding-top:2px">{ccy} {plan.get('stop')}</div>
        <div style="font-size:11px;color:#b91c1c">−{plan.get('stop_pct')}% del precio actual</div></div></td>
      <td valign="top" width="50%" style="padding-left:5px"><div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:9px 11px">
        <div style="font-size:11px;color:#166534;font-weight:700;text-transform:uppercase;letter-spacing:.03em">🎯 Profit sugerido</div>
        <div style="font-size:17px;font-weight:800;color:#16a34a;padding-top:2px">{ccy} {plan.get('target')}</div>
        <div style="font-size:11px;color:#15803d">+{plan.get('target_pct')}% del precio actual</div></div></td>
    </tr></table>"""


def _plan_section(stocks):
    rows = ""
    for s in stocks:
        pl = s.get("plan")
        pos = s.get("position") or {}
        if not pl or not pos.get("quantity"):
            continue
        ccy = html.escape(pl.get("currency") or "")
        act = pl.get("action", "MANTENER")
        color = {"TOMAR BENEFICIOS": "#16a34a", "VIGILAR / STOP": "#dc2626"}.get(act, "#d97706")
        outlook = html.escape(pl.get("outlook") or "")
        rows += f"""
        <tr><td style="padding:12px 0;border-top:1px solid #1f2937">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
            <td align="left" valign="middle"><span style="font-size:15px;font-weight:800;color:#fff">{html.escape(s['ticker'])}</span>
              <span style="color:#94a3b8;font-size:12px"> {html.escape(s.get('name',''))}</span></td>
            <td align="right" valign="middle"><span style="display:inline-block;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:800;color:#fff;background:{color}">{html.escape(act)}</span></td>
          </tr></table>
          <div style="font-size:12px;color:#cbd5e1;padding-top:6px">🛑 Stop: {ccy} {pl.get('stop')} (−{pl.get('stop_pct')}%) &nbsp;·&nbsp; 🎯 Objetivo: {ccy} {pl.get('target')} (+{pl.get('target_pct')}%)</div>
          <div style="font-size:12px;color:#94a3b8;padding-top:4px">🔭 {outlook}</div>
        </td></tr>"""
    if not rows:
        return ""
    return f"""
    <tr><td style="padding:16px 0">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;border-radius:14px"><tr><td style="padding:20px">
        <div style="font-size:16px;font-weight:800;color:#fff">🎯 Plan de acción <span style="font-size:11px;color:#94a3b8;font-weight:600">· orientativo</span></div>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>
        <div style="font-size:11px;color:#64748b;padding-top:14px;line-height:1.5">⚠️ Etiquetas y niveles generados automáticamente (reglas + IA) a partir del rango de 52 semanas y tu P&amp;L. <b>No es asesoramiento financiero</b> ni una recomendación de compra/venta — son una guía para tu propia decisión.</div>
      </td></tr></table>
    </td></tr>"""


def render(stocks, totals, generated_at=None, base_symbol="$"):
    generated_at = generated_at or dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    total_val = sum((s.get("position") or {}).get("value_base") or 0 for s in stocks)

    cards = ""
    for s in stocks:
        q = s.get("quote") or {}
        ins = s.get("insight") or {}
        pos = s.get("position") or {}
        ccy = html.escape(q.get("currency", "USD"))

        # valor de la posición y % de la cartera
        vb = pos.get("value_base")
        value_html = ""
        if vb:
            weight = (vb / total_val * 100) if total_val else 0
            money = f"{base_symbol}{vb:,.0f}".replace(",", ".")
            value_html = (
                f'<div style="font-size:15px;font-weight:800;color:#0f172a;padding-top:5px">{money}</div>'
                f'<div style="font-size:12px;color:#64748b">{weight:.1f}% de la cartera</div>'
            )

        pos_line = ""
        if pos.get("quantity"):
            pos_line = (f'<div style="font-size:12px;color:#475569;padding-top:3px">'
                        f'{_fmt(pos["quantity"], 4)} acc. · {html.escape(", ".join(pos.get("sources", [])))}</div>')

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
                <div style="font-size:12px;padding-top:3px">Hoy {_pct(q.get('change_pct'))} · YTD {_pct(q.get('perf_ytd'))}</div>{value_html}</td>
            </tr></table>
            {_range_bar(q)}
            {_sparkline(q, base_symbol)}
            {_stats_row(q, pos, base_symbol)}
            {_levels_box(s.get('plan'))}
            {_badge(ins.get('bias', 0))}
            {insight_block}
            {_notes_block(s.get('notes'))}
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
  {_plan_section(stocks)}
  <tr><td style="padding:8px 8px 0;color:#94a3b8;font-size:11px;text-align:center;line-height:1.5">
    Las barras muestran la posición del precio en su rango de 52 semanas.<br>
    Información con fines informativos, <b>no es asesoramiento de inversión</b>.<br>
    Precios/posiciones: IBKR + Revolut · Datos de mercado: Stooq · Noticias: Yahoo Finance / Google News.
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
