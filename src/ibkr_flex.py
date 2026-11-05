"""Cliente del IBKR Flex Web Service (solo lectura).

Permite descargar las posiciones de Interactive Brokers de forma headless
(para que la rutina diaria funcione en GitHub Actions sin sesión interactiva).

Configura un Flex Query de tipo "Positions" en Client Portal y exporta:
  IBKR_FLEX_TOKEN     -> token del Flex Web Service
  IBKR_FLEX_QUERY_ID  -> ID del query de posiciones

Es de SOLO LECTURA: no permite operar, solo leer reportes.
"""
import os
import time
import xml.etree.ElementTree as ET

import requests

FLEX_BASE = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"


def fetch_positions(token=None, query_id=None, timeout=120):
    """Devuelve una lista de posiciones de IBKR vía Flex Web Service.

    Cada item: {ticker, quantity, avg_price, currency, market_value, source}.
    Devuelve [] si no hay credenciales configuradas.
    """
    token = token or os.getenv("IBKR_FLEX_TOKEN")
    query_id = query_id or os.getenv("IBKR_FLEX_QUERY_ID")
    if not token or not query_id:
        return []

    # 1) Solicitar la generación del reporte
    r = requests.get(
        f"{FLEX_BASE}/SendRequest",
        params={"t": token, "q": query_id, "v": 3},
        timeout=30,
    )
    root = ET.fromstring(r.text)
    if (root.findtext("Status") or "").strip() != "Success":
        raise RuntimeError(f"IBKR Flex SendRequest falló: {r.text[:300]}")
    ref = root.findtext("ReferenceCode")
    url = root.findtext("Url")

    # 2) Descargar el statement (con reintentos: el reporte tarda en generarse)
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = requests.get(url, params={"t": token, "q": ref, "v": 3}, timeout=30)
        if "<FlexStatements" in s.text or "<OpenPosition" in s.text:
            return _parse_positions(s.text)
        if "ErrorCode" in s.text:
            # 1019 = statement aún generándose -> esperar y reintentar
            time.sleep(5)
            continue
        time.sleep(5)
    raise TimeoutError("IBKR Flex: el statement no estuvo listo a tiempo")


def _parse_positions(xml_text):
    root = ET.fromstring(xml_text)
    out = []
    for pos in root.iter("OpenPosition"):
        qty = float(pos.get("position") or 0)
        if qty == 0:
            continue
        out.append(
            {
                "ticker": (pos.get("symbol") or "").upper(),
                "quantity": qty,
                "avg_price": float(pos.get("costBasisPrice") or 0) or None,
                "currency": pos.get("currency"),
                "market_value": float(pos.get("positionValue") or 0) or None,
                "source": "IBKR",
            }
        )
    return out
