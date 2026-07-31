# Custom brand fonts

Drop a brand's TTF files here to override the report typography. They are loaded
by `reportkit.fonts.register_brand_fonts` when a branding config sets
`title_font` / `body_font`; `app/pdf_report.py` injects **this** directory as
`font_dir`, so the same bytes get embedded in the PDF.

**If a file is missing the report silently falls back to IBM Plex Sans** — no
error, no warning. That makes this directory optional, but it also means a
misspelled filename looks exactly like "the brand font isn't installed". Check
the rendered PDF, not the console.

## Naming convention

`<AlnumFontName>-<Style>.ttf`, where `<AlnumFontName>` is the `title_font` /
`body_font` value with spaces and punctuation removed, and `<Style>` is one of
`Regular`, `Bold`, `Italic`, `BoldItalic`.

## CADIEM (`branding/branding_cadiem.json`: `title_font: "Neulis Alt"`, `body_font: "Gantari"`)

Title font (headings — only Bold is used):
- `NeulisAlt-Bold.ttf`

Body font (regular text; add the weights you have, Regular is required):
- `Gantari-Regular.ttf`
- `Gantari-Bold.ttf`        (optional)
- `Gantari-Italic.ttf`      (optional)
- `Gantari-BoldItalic.ttf`  (optional)

These are licensed fonts and are intentionally **not** committed to the repo —
add the licensed `.ttf` files here and the CADIEM report will pick them up.
