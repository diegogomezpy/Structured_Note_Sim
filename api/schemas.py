"""Pydantic request models for the API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SimRequest(BaseModel):
    # `terms` is a NoteTerms config dict — the same JSON shape as note_configs/*.
    terms: dict
    n_paths: int = Field(10000, ge=100, le=50000)
    seed: int = 42
    calib_years: float = Field(5.0, gt=0, le=20)
    history_years: float | None = None   # None → maximum available history
    lang: str = "en"


class PdfRequest(SimRequest):
    # Per-item include keys (see pdf_report.generate_pdf_report); None → all.
    include_sections: list[str] | None = None
    branding: dict | None = None
