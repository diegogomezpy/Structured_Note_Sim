# Local ticker / underlying logos

Drop image files here to have the PDF report use **local** logos for the
underlyings instead of fetching them from the web (which is unreliable and can
leave broken-image boxes).

## How it works

When building the PDF, for each underlying the resolver looks for a file in this
folder before falling back to a URL fetch. It tries, in order:

1. `{TICKER}.png` / `{TICKER}.jpg` — the ticker symbol (e.g. `NVDA.png`, `C.png`)
2. `{DisplayName}.png` / `{DisplayName}.jpg` — the display name (e.g. `Citigroup.png`)

Matching is **case-insensitive** and tries `.png`, `.jpg`, `.jpeg`, `.svg` in
that order.

## Notes

- **PNG or JPG recommended.** fpdf2 cannot render SVG natively, so `.svg` files
  are skipped (the report falls back to the next source, or shows the name only).
- A missing or unreadable file never crashes the report — it simply omits the
  logo and prints a diagnostic to the console.
- The firm/issuer logo is configured separately in your `branding_*.json`, not
  here — via `logo_file`, `logo_base64` (embedded, self-contained, so no file is
  needed on disk), or `logo_url`. `branding_example.json` shows all the keys.
- Square images around 128×128 px look best in the small logo slots.

## Examples

```
branding/ticker_logos/NVDA.png        # by ticker symbol
branding/ticker_logos/Citigroup.png   # by display name
```
