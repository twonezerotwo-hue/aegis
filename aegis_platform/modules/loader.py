from __future__ import annotations

import importlib
from typing import Any


def lazy_import(import_path: str) -> tuple[bool, Any | None, str | None]:
    """Import a module lazily and return a structured result."""
    try:
        return True, importlib.import_module(import_path), None
    except Exception as exc:  # noqa: BLE001
        return False, None, str(exc)

