from __future__ import annotations


class ModuleRegistryError(Exception):
    """Base exception for module registry validation errors."""


class ModuleManifestError(ModuleRegistryError):
    """Raised when a module manifest is structurally invalid."""

