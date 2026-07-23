"""Pytest bootstrap: put the repo root (and app/) on sys.path so `from core.note
import ...` and the app/ helpers resolve when pytest runs from anywhere."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# tests/ itself too, so test modules can import shared fixtures (golden_fixture).
for p in (str(_ROOT), str(_ROOT / "app"), str(Path(__file__).resolve().parent)):
    if p not in sys.path:
        sys.path.insert(0, p)
