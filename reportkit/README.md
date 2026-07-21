# reportkit

A small, reusable toolkit for **themed PDF reports** — decoupled from any one
project's domain. It grew out of the Structured Note Simulator's report
generator; this package is the part worth reusing.

## What's here

| Module | Responsibility |
| --- | --- |
| `reportkit.theme` | The visual-identity layer: `ReportTheme` (interface), the built-in `HexagonTheme` / `MercatorTheme`, palette-derived `ThemeTokens`, the shape + gradient primitives, and the theme registry (`resolve_theme` / `register_theme`). |
| `reportkit.images` | Dependency-light image helpers (aspect-correct `cover_crop`, …). |

Planned (in progress): a declarative **theme spec** so a theme is *data you
author* (shapes, fills, gradients, geometry) rather than code; a generic
`ReportDocument` (the themed FPDF builder, currently `app/pdf_report.py:_NotePDF`)
with imperative building blocks (`cover`, `section`, `table`, `metrics`,
`figure`, `callout`, `custom`); and `reportkit.branding` (palette / fonts / logos
/ images resolution).

## Design

- **Content is imperative, look is declarative.** A host app drives a themed
  document imperatively and feeds in its own content; the *theme* is swappable
  data. None of the report chrome knows anything about the host's domain.
- **Palette-driven.** Every identity colour is derived from the brand palette
  (`build_tokens`), so any brand inherits a theme in its own colours.
- **No heavy deps at import.** Core dependency is `fpdf2`. Pillow and Plotly are
  optional and imported lazily.

## Usage sketch

```python
from reportkit.theme import resolve_theme, build_tokens

theme = resolve_theme(branding.get("report_theme"))   # name or inline spec
# The host document sets its palette tokens from build_tokens(...) and delegates
# every chrome surface to `self.theme.<hook>(self, ...)`.
```

See `app/pdf_report.py` in this repo for a complete reference adapter (maps
structured-note data onto the themed document and registers domain-specific
blocks).

## Reusing in another project

`reportkit/` has no imports from `app/`, `core/`, or `data/`. Copy the package in
(or add this repo as a path dependency) and drive it from your own content
adapter. A `pyproject.toml` can be added if/when it graduates to its own repo.
