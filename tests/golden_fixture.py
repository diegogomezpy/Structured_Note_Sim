"""Brand fixtures for the PDF golden harness.

The analytics half of the fixture — the note, the results dict and the figure
stub — lives in ``api/preview_fixture.py``, because the proof endpoint renders
from exactly the same inputs. Sharing it is the point: the golden then guards
what the PDF Studio actually shows.

What stays here is the *branding* half, which is test-only. The real CADIEM
config and its brand fonts are gitignored licensed assets and must never enter
the repo, so these fixtures drive the same code paths — hexagon chamfers, hex
cluster, linear and radial gradients, watermark, cover art — using images
generated at test time.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np

from api.preview_fixture import (  # noqa: F401  (re-exported for the tests)
    SEED, N_PATHS, N_STEPS, note_terms, results, stub_png, figures,
)

FIXTURES = Path(__file__).resolve().parent / "golden"


def branding(theme: str) -> dict:
    """Load a committed brand fixture and attach generated imagery."""
    cfg = json.loads((FIXTURES / f"branding_{theme}.json").read_text())
    cfg["logo_base64"] = _swatch(320, 96, (18, 62, 64), "LOGO")
    cfg["cover_logo_base64"] = _swatch(560, 120, (255, 255, 255), "COVER")
    cfg["cover_image_base64"] = _noise(900, 600, 11)
    cfg["back_image_base64"] = _noise(900, 600, 29)
    cfg["filler_images_base64"] = [_noise(700, 460, 41), _noise(700, 460, 53)]
    cfg["watermark_base64"] = _swatch(300, 300, (255, 255, 255), "WM")
    return cfg


def _swatch(w: int, h: int, rgb: tuple, label: str) -> str:
    """A deterministic labelled block — stands in for a logo/wordmark."""
    import base64
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (w, h), rgb)
    d = ImageDraw.Draw(im)
    inv = tuple(255 - c for c in rgb)
    d.rectangle([2, 2, w - 3, h - 3], outline=inv, width=3)
    d.text((10, h // 2 - 6), label, fill=inv)
    buf = io.BytesIO(); im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _noise(w: int, h: int, seed: int) -> str:
    """A deterministic soft gradient — stands in for a cover photograph."""
    import base64
    from PIL import Image

    rng = np.random.default_rng(seed)
    base = np.linspace(0, 255, w, dtype=np.float64)[None, :, None] * np.ones((h, 1, 3))
    base += rng.normal(0, 6, (h, w, 3))
    im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
    buf = io.BytesIO(); im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()
