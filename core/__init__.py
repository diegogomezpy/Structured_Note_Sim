"""
core — pure quantitative library for Multiasset_Heston_Sim.

No Streamlit, no Plotly, no file I/O.  Import freely in notebooks and tests.

Public API
----------
from core import HestonParams, HestonMultiSimulator
from core import HestonCalibrator, CalibrationResult
from core import NoteTerms, price_note
from core import run_backtest
"""

from core.simulator  import HestonParams, HestonMultiSimulator
from core.calibrator import HestonCalibrator, CalibrationResult
from core.note       import NoteTerms, price_note, replay_note
from core.backtest   import run_backtest

__all__ = [
    "HestonParams",
    "HestonMultiSimulator",
    "HestonCalibrator",
    "CalibrationResult",
    "NoteTerms",
    "price_note",
    "replay_note",
    "run_backtest",
]