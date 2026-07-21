"""
reportkit.images — small, dependency-light image helpers for PDF layout.

Domain-agnostic; the only third-party dependency is Pillow, imported lazily so
importing this module is cheap and never fails when Pillow is absent (the
helpers degrade to returning their input unchanged).
"""
from __future__ import annotations

import io


def cover_crop(raw: bytes | None, aspect: float,
               bias_x: float = 0.0, bias_y: float = 0.0) -> bytes | None:
    """Crop an image to `aspect` (= width / height) so a full-bleed placement
    fills the box without stretching (CSS object-fit: cover). `bias_x`/`bias_y`
    in [-1, 1] shift the crop window off-centre (0 = centred, -1 = left/top,
    +1 = right/bottom) — used to show different regions of the same source on
    successive pages so a repeated filler photo doesn't read as identical.
    Returns PNG bytes; on any failure returns the input unchanged."""
    if not raw:
        return raw
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = im.size
        cur = w / h
        if abs(cur - aspect) < 1e-3 and not (bias_x or bias_y):
            return raw
        if cur > aspect:                       # too wide → crop the sides
            nw = int(round(h * aspect))
            x0 = int(round((w - nw) * (0.5 + 0.5 * max(-1.0, min(1.0, bias_x)))))
            x0 = max(0, min(w - nw, x0))
            im = im.crop((x0, 0, x0 + nw, h))
        else:                                  # too tall → crop top/bottom
            nh = int(round(w / aspect))
            y0 = int(round((h - nh) * (0.5 + 0.5 * max(-1.0, min(1.0, bias_y)))))
            y0 = max(0, min(h - nh, y0))
            im = im.crop((0, y0, w, y0 + nh))
        buf = io.BytesIO(); im.save(buf, "PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"[reportkit.images] crop skipped: {e}")
        return raw


# Back-compat alias for the original private name used across the codebase.
_cover_crop = cover_crop
