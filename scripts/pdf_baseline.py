"""Whole-document PDF fingerprint — the safety net for refactors that must not
change output.

The golden test (`tests/test_golden_pdf.py`) pins per-page pixels for 4 brand
fixtures in English, phoenix only. That is the right guard for *drawing* changes.
It is not wide enough for a structural refactor — moving code between modules can
change a Spanish participation report while leaving every guarded page identical.

This widens the net to the full matrix (themes x note kinds x languages) and
fingerprints the PDF BYTES, not the rendered pixels, so it catches anything: a
reordered content stream, a dropped font subset, a changed metadata field.

    python3 scripts/pdf_baseline.py capture      # before the refactor
    python3 scripts/pdf_baseline.py check        # after every slice

`check` exits non-zero and names every cell that moved. Two document fields are
excluded because they legitimately vary run to run: the PDF CreationDate and the
document ID. Everything else must match byte for byte.

Baselines are written OUTSIDE the repo (see `_BASELINE`) — this is a transient
scaffold for one refactor, not something to version.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_ROOT), str(_ROOT / "app"), str(_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_BASELINE = Path(
    os.environ.get("SNSIM_PDF_BASELINE")
    or (Path.home() / ".cache" / "snsim" / "pdf_baseline.json")
)

THEMES = ["mercator", "hexagon", "custom", "hexcluster"]
KINDS = ["phoenix", "participation"]
LANGS = ["en", "es"]

# Three metadata fields change every run by design; nothing else may.
#   /CreationDate  — the generation timestamp, to the second
#   /ID            — fpdf2's per-file identifier
#   /Subject       — `_stamp_provenance` puts "Generated <UTC to the minute>" in
#                    it, so two runs a minute apart differ. Written as a hex
#                    UTF-16BE string (it contains "·"), hence the <...> form as
#                    well as the literal (...) one.
# Title/Author/Creator/Producer are deliberately NOT stripped — they carry the
# attribution watermark, and losing it silently is exactly the kind of thing
# this fingerprint exists to catch.
_VOLATILE = [
    re.compile(rb"/CreationDate\s*\([^)]*\)"),
    re.compile(rb"/ID\s*\[[^\]]*\]"),
    re.compile(rb"/Subject\s*(?:\([^)]*\)|<[0-9A-Fa-f\s]*>)"),
]


def _fingerprint(raw: bytes) -> str:
    for pat in _VOLATILE:
        raw = pat.sub(b"", raw)
    return hashlib.sha256(raw).hexdigest()


def _render_all() -> dict[str, str]:
    from golden_fixture import render_report

    out: dict[str, str] = {}
    for theme in THEMES:
        for kind in KINDS:
            for lang in LANGS:
                key = f"{theme}/{kind}/{lang}"
                try:
                    raw = render_report(theme=theme, kind=kind,
                                        real_figures=False, lang=lang)
                    out[key] = _fingerprint(raw)
                except Exception as exc:                  # a crash IS a regression
                    out[key] = f"ERROR: {type(exc).__name__}: {exc}"
                print(f"  {key:<34} {out[key][:16]}")
    return out


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    print(f"[pdf-baseline] {mode} — {len(THEMES) * len(KINDS) * len(LANGS)} documents")
    now = _render_all()

    if mode == "capture":
        _BASELINE.parent.mkdir(parents=True, exist_ok=True)
        _BASELINE.write_text(json.dumps(now, indent=1, sort_keys=True))
        bad = [k for k, v in now.items() if v.startswith("ERROR")]
        print(f"\n[pdf-baseline] wrote {_BASELINE}")
        if bad:
            print(f"[pdf-baseline] WARNING: captured {len(bad)} failing cell(s): {bad}")
        return 0

    if not _BASELINE.exists():
        print(f"[pdf-baseline] no baseline at {_BASELINE} — run `capture` first")
        return 2

    was = json.loads(_BASELINE.read_text())
    moved = sorted(k for k in set(was) | set(now) if was.get(k) != now.get(k))
    if not moved:
        print(f"\n[pdf-baseline] OK — all {len(now)} documents byte-identical")
        return 0

    print(f"\n[pdf-baseline] {len(moved)} document(s) CHANGED:")
    for k in moved:
        print(f"  {k}\n      was {was.get(k, '<absent>')}\n      now {now.get(k, '<absent>')}")
    print("\nA pure code move must not change these. Either the move altered "
          "behaviour, or the change was intentional — in which case re-capture "
          "deliberately and say so.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
