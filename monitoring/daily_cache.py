"""
monitoring/daily_cache.py — Same-day result caching.

Caches processed ASIN results for the current calendar date.
On a new day, all previous cache files are auto-deleted.
"""

import json
from datetime import date
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


def _cache_file() -> Path:
    """Get today's cache file path."""
    return CACHE_DIR / f"results_{date.today().isoformat()}.json"


def _purge_old_caches():
    """Delete all cache files except today's."""
    today = date.today().isoformat()
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("results_*.json"):
            if today not in f.name:
                f.unlink()
                print(f"[Cache] Purged old cache: {f.name}")


def _load_cache() -> dict:
    """Load today's cache from disk."""
    path = _cache_file()
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict):
    """Save cache to disk."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_cache_file(), "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def get_cached_result(asin: str, marketplace: str) -> dict | None:
    """Get a cached result for an ASIN if it was processed today."""
    _purge_old_caches()
    cache = _load_cache()
    key = f"{asin}_{marketplace}"
    return cache.get(key)


def save_result(asin: str, marketplace: str, result: dict):
    """Save a processed result to today's cache."""
    cache = _load_cache()
    key = f"{asin}_{marketplace}"
    cache[key] = result
    _save_cache(cache)
