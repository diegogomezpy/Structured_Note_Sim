"""Pytest bootstrap: put the repo root (and app/) on sys.path so `from core.note
import ...` and the app/ helpers resolve when pytest runs from anywhere."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for p in (str(_ROOT), str(_ROOT / "app")):
    if p not in sys.path:
        sys.path.insert(0, p)
