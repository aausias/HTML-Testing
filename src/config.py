"""Carga de configuración del dashboard."""
import os
import yaml

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")


def load_config(path: str = None) -> dict:
    path = path or _DEFAULT_PATH
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    # Defaults defensivos
    cfg.setdefault("portfolio", {})
    cfg.setdefault("market", {}).setdefault("symbol_overrides", {})
    cfg.setdefault("news", {"max_items_per_ticker": 4, "lookback_days": 5})
    cfg.setdefault("insights", {"use_llm": False, "llm_model": "claude-haiku-4-5-20251001"})
    cfg.setdefault("delivery", {})
    return cfg
