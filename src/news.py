"""Noticias por ticker vía RSS gratuito (Yahoo Finance -> Google News fallback)."""
import datetime as dt
import re
import xml.etree.ElementTree as ET

import requests

_POS = {"beat", "beats", "surge", "surges", "record", "soar", "soars", "rally", "upgrade",
        "raises", "raised", "growth", "strong", "buy", "jumps", "gain", "gains", "tops",
        "outperform", "bullish", "wins", "expands", "high", "highs"}
_NEG = {"miss", "misses", "fall", "falls", "drop", "drops", "plunge", "plunges", "cut",
        "cuts", "downgrade", "weak", "loss", "losses", "sell", "lawsuit", "probe", "warns",
        "warning", "slump", "sinks", "bearish", "concern", "concerns", "decline", "tumble",
        "tumbles", "low", "lows"}


def _sentiment(title):
    words = set(re.findall(r"[a-z]+", title.lower()))
    score = len(words & _POS) - len(words & _NEG)
    if score > 0:
        return "pos"
    if score < 0:
        return "neg"
    return "neu"


def _parse_rss(xml_text, limit):
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if not title:
            continue
        items.append({"title": title, "link": link, "pub": pub, "sentiment": _sentiment(title)})
        if len(items) >= limit:
            break
    return items


def get_news(ticker, limit=4):
    headers = {"User-Agent": "Mozilla/5.0 (StockDashboard)"}
    # 1) Yahoo Finance RSS
    try:
        u = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        r = requests.get(u, headers=headers, timeout=20)
        items = _parse_rss(r.text, limit)
        if items:
            return items
    except Exception:
        pass
    # 2) Google News RSS
    try:
        u = f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
        r = requests.get(u, headers=headers, timeout=20)
        return _parse_rss(r.text, limit)
    except Exception:
        return []
