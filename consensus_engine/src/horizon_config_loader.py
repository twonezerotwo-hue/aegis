"""
AEGIS v7.2 — Horizon config hot-reload loader.

consensus_engine/src/horizon_config_loader.py
AEGIS v7.2 — Hot-reload YAML loader for horizon_configs.yaml.

Reads the config at most once per TTL_SECONDS, then caches it.
On every access, mtime is checked; if the file changed the cache is
invalidated and the new config is returned immediately.
On any parse / IO error the last valid config is returned and a
WARNING is logged — the service never crashes due to a bad edit.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


def _resolve_config_path() -> str:
    """Resolve horizon config path for local dev and container runtime."""
    candidates = [
        Path(__file__).resolve().parent.parent / "config" / "horizon_configs.yaml",
        Path("/app/consensus_engine/config/horizon_configs.yaml"),
        Path("consensus_engine/config/horizon_configs.yaml"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    # Keep first candidate so warnings show a meaningful expected location.
    return str(candidates[0])


_DEFAULT_CONFIG_PATH = _resolve_config_path()

# Fallback spec — used when the file cannot be read on first access
_BUILTIN_FALLBACK: dict[str, Any] = {
    "short": {
        "primary_tf": "4h",
        "active_tfs": ["4h", "1d"],
        "window_days": 7,
        "kelly_fraction": 0.15,
        "volatility_lookback_days": 14,
        "cbr_window_days": 90,
        "source_priority": "breaking",
        "bias_mode": "momentum",
        "tf_label": "4H",
        "window_label": "7g",
        "kelly_label": "Kelly×0.15",
        "module_weights": {
            "touche": 0.40,
            "fundamental": 0.25,
            "news": 0.15,
            "sentinel": 0.12,
            "quantum": 0.08,
        },
    },
    "medium": {
        "primary_tf": "1d",
        "active_tfs": ["1d", "4h"],
        "window_days": 30,
        "kelly_fraction": 0.25,
        "volatility_lookback_days": 30,
        "cbr_window_days": 180,
        "source_priority": "trend",
        "bias_mode": "balanced",
        "tf_label": "1D",
        "window_label": "30g",
        "kelly_label": "Kelly×0.25",
        "module_weights": {
            "touche": 0.35,
            "fundamental": 0.30,
            "news": 0.20,
            "sentinel": 0.10,
            "quantum": 0.05,
        },
    },
    "long": {
        "primary_tf": "1w",
        "active_tfs": ["1w", "1d"],
        "window_days": 90,
        "kelly_fraction": 0.40,
        "volatility_lookback_days": 90,
        "cbr_window_days": 730,
        "source_priority": "macro",
        "bias_mode": "cycle",
        "tf_label": "1W",
        "window_label": "90g",
        "kelly_label": "Kelly×0.40",
        "module_weights": {
            "touche": 0.25,
            "fundamental": 0.40,
            "news": 0.10,
            "sentinel": 0.15,
            "quantum": 0.10,
        },
    },
}

TTL_SECONDS: float = 60.0  # Re-check mtime at most this often


class _ConfigCache:
    """Thread-safe (GIL-protected) horizon config cache."""

    def __init__(self, path: str) -> None:
        self._path = os.path.abspath(path)
        self._config: dict[str, Any] = {}
        self._mtime: float = -1.0
        self._checked_at: float = 0.0
        self._loaded_at: str = ""

    # ------------------------------------------------------------------ #
    def get(self) -> dict[str, Any]:
        """Return the current config, reloading if needed."""
        now = time.monotonic()
        if now - self._checked_at < TTL_SECONDS and self._config:
            return self._config

        self._checked_at = now
        try:
            current_mtime = os.path.getmtime(self._path)
        except OSError as exc:
            logger.warning("HORIZON_CONFIG: cannot stat %s — %s", self._path, exc)
            return self._config or dict(_BUILTIN_FALLBACK)

        if current_mtime == self._mtime and self._config:
            return self._config

        # File changed (or first load) — reload
        try:
            with open(self._path, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
            if not isinstance(raw, dict):
                raise ValueError("Top-level YAML value must be a mapping")
            self._config = raw
            self._mtime = current_mtime
            self._loaded_at = datetime.now(timezone.utc).isoformat()
            logger.info(
                "HORIZON_CONFIG: reloaded %s (mtime=%.3f) at %s",
                self._path,
                current_mtime,
                self._loaded_at,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "HORIZON_CONFIG: parse error in %s — %s — using last valid config",
                self._path,
                exc,
            )
            if not self._config:
                self._config = dict(_BUILTIN_FALLBACK)

        return self._config

    def loaded_at(self) -> str:
        return self._loaded_at or "never"

    def config_path(self) -> str:
        return self._path


# ── Module-level singleton ──────────────────────────────────────────────────
_cache = _ConfigCache(_DEFAULT_CONFIG_PATH)
_observer: Observer | None = None


class HorizonConfigWatcher(FileSystemEventHandler):
    """AEGIS v7.2 — Dosya degisiminde cache'i zorla yeniler."""

    def on_modified(self, event):  # type: ignore[override]
        src_path = getattr(event, "src_path", "")
        if isinstance(src_path, str) and src_path.endswith("horizon_configs.yaml"):
            logger.info("[HorizonConfig] Reloading %s", src_path)
            _cache._checked_at = 0.0
            _cache.get()


def init_hot_reload(config_path: str) -> Observer:
    """AEGIS v7.2 — Watchdog observer baslatir ve global olarak saklar."""
    global _observer
    if _observer is not None:
        return _observer

    observer = Observer()
    watcher = HorizonConfigWatcher()
    observer.schedule(watcher, path=str(Path(config_path).resolve().parent), recursive=False)
    observer.daemon = True
    observer.start()
    _observer = observer
    return observer


def get_horizon_config(horizon: str = "medium") -> dict[str, Any]:
    """
    Return the config dict for the requested horizon.

    Falls back to ``medium`` if the horizon key is missing, then to the
    built-in fallback dict if the file cannot be read at all.
    """
    valid = {"short", "medium", "long"}
    if horizon not in valid:
        horizon = "medium"

    all_cfg = _cache.get()
    if horizon in all_cfg:
        return all_cfg[horizon]

    # Key missing in file — return built-in
    logger.warning(
        "HORIZON_CONFIG: key '%s' not found — returning builtin fallback",
        horizon,
    )
    return dict(_BUILTIN_FALLBACK.get(horizon, _BUILTIN_FALLBACK["medium"]))


def get_all_horizon_configs() -> dict[str, Any]:
    """Return the full raw config dict (all horizons)."""
    return _cache.get()


def cache_status() -> dict[str, Any]:
    """Diagnostic info for /health endpoints."""
    return {
        "config_path": _cache.config_path(),
        "loaded_at": _cache.loaded_at(),
        "horizons": list(_cache.get().keys()),
        "ttl_seconds": TTL_SECONDS,
    }


try:
    init_hot_reload(_DEFAULT_CONFIG_PATH)
except Exception as exc:  # noqa: BLE001
    logger.warning("HORIZON_CONFIG: watchdog init failed — %s", exc)
