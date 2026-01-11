from __future__ import annotations

from threading import Lock
from typing import Any, Dict


_lock = Lock()
_cache_hits = 0
_cache_misses = 0


def record_cache_hit() -> None:
    global _cache_hits
    with _lock:
        _cache_hits += 1


def record_cache_miss() -> None:
    global _cache_misses
    with _lock:
        _cache_misses += 1


def get_cache_metrics() -> Dict[str, Any]:
    with _lock:
        hits = _cache_hits
        misses = _cache_misses

    total = hits + misses
    hit_rate_pct = (hits / total * 100.0) if total else 0.0

    return {
        "hits": hits,
        "misses": misses,
        "total": total,
        "hit_rate_pct": round(hit_rate_pct, 2),
    }


def log_cache_hit_rate(logger) -> None:
    metrics = get_cache_metrics()
    logger.info(
        "Cache hit rate: %.2f%% (hits=%d misses=%d total=%d)",
        metrics["hit_rate_pct"],
        metrics["hits"],
        metrics["misses"],
        metrics["total"],
    )
