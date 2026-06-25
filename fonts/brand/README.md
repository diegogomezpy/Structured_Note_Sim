# Custom brand fonts

Drop a brand's TTF files here to override the report typography. The PDF report
(`app/pdf_report.py → _register_brand_fonts`) loads them when a branding config
sets `title_font` / `body_font`. If a file is missing the report silently falls
back to IBM Plex Sans, so this directory is optional.

## Naming convention

`<AlnumFontName>-<Style>.ttf`, where `<AlnumFontName>` is the `title_font` /
`body_font` value with spaces and punctuation removed, and `<Style>` is one of
`Regular`, `Bold`, `Italic`, `BoldItalic`.

## CADIEM (`branding/branding_cadiem.json`: `title_font: "Neulis Alt"`, `body_font: "Galanti"`)

Title font (headings — only Bold is used):
- `NeulisAlt-Bold.ttf`

Body font (regular text; add the weights you have, Regular is required):
- `Galanti-Regular.ttf`
- `Galanti-Bold.ttf`        (optional)
- `Galanti-Italic.ttf`      (optional)
- `Galanti-BoldItalic.ttf`  (optional)

These are licensed fonts and are intentionally **not** committed to the repo —
add the licensed `.ttf` files here and the CADIEM report will pick them up.
