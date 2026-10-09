"""Nombres legibles de compañías (fallback al ticker si no está)."""
NAMES = {
    "NVDA": "Nvidia",
    "CLS": "Celestica",
    "MELI": "MercadoLibre",
    "FNV": "Franco-Nevada",
    "META": "Meta Platforms",
    "VWCE": "Vanguard FTSE All-World (acc)",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "TSLA": "Tesla",
}


def name_for(ticker):
    return NAMES.get(ticker.upper(), ticker.upper())
