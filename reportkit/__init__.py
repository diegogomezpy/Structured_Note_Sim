"""
reportkit — a reusable, domain-agnostic toolkit for themed PDF reports.

This package is intentionally free of any Structured-Note-Simulator (or other
project) domain concepts. It provides:

  - reportkit.theme   — the visual-identity layer: ReportTheme + the declarative
                        SpecTheme, palette-derived tokens, shape/gradient
                        primitives, built-in theme specs, and the theme registry.
  - reportkit.images  — small image helpers (aspect-correct cover-crop, …).

A host application builds a report imperatively on a themed document and feeds
its own content in; the *look* is a swappable theme (data), and none of the
report's chrome knows anything about the host's domain. See app/pdf_report.py in
the Structured Note Simulator for a reference adapter.
"""
from __future__ import annotations

# Public API re-exports (kept small; import the submodules for the rest).
from reportkit.theme import (  # noqa: F401
    ReportTheme,
    ThemeTokens,
    build_tokens,
    resolve_theme,
    register_theme,
    known_themes,
    DEFAULT_THEME,
)

__all__ = [
    "ReportTheme",
    "ThemeTokens",
    "build_tokens",
    "resolve_theme",
    "register_theme",
    "known_themes",
    "DEFAULT_THEME",
]
