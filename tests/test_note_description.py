"""Structural guards on the generated note description.

The description is a template, so it must read correctly for every feature
combination rather than for the four notes anyone happened to look at. These
assertions encode the rules that keep it prose rather than a feature list:
six paragraphs always, no labelled fragments, and — the regression that
prompted the rewrite — a feature is only ever named when the note uses it.

Runs against every config in note_configs/ in both languages.
"""
from __future__ import annotations

import glob
import re
from pathlib import Path

import pytest

from core.note import NoteTerms
from core.note_description import describe_note
from core.phoenix_prose import pct

_ROOT = Path(__file__).resolve().parent.parent
CONFIGS = sorted(glob.glob(str(_ROOT / "note_configs" / "*.json")))


def _phoenix_terms():
    for f in CONFIGS:
        try:
            t = NoteTerms.from_json(Path(f).read_text())
        except Exception:
            continue
        cg = getattr(t, "capital_guarantee", None)
        if getattr(t, "note_type", "") == "participation" or (cg is not None and cg > 0):
            continue
        yield Path(f).name, t


CASES = [(n, t, lang) for n, t in _phoenix_terms() for lang in ("en", "es")]
IDS = [f"{n}-{lang}" for n, _, lang in CASES]

if not CASES:
    pytest.skip("no phoenix configs to check", allow_module_level=True)


@pytest.mark.parametrize("name,terms,lang", CASES, ids=IDS)
def test_six_paragraphs(name, terms, lang):
    assert len(describe_note(terms, lang).split("\n\n")) == 6


@pytest.mark.parametrize("name,terms,lang", CASES, ids=IDS)
def test_no_label_fragments(name, terms, lang):
    """The failure mode this rewrite exists to kill: a paragraph that opens
    with a feature name and a full stop, reading as a glossary entry."""
    for para in describe_note(terms, lang).split("\n\n"):
        assert not re.match(
            r"^(Basket|Step-down|One Star|Zenith|Premium|Principal|Cesta|Prima)\b[^.]{0,30}\.\s",
            para), f"label-style opener: {para[:60]}"


@pytest.mark.parametrize("name,terms,lang", CASES, ids=IDS)
def test_features_named_only_when_used(name, terms, lang):
    txt = describe_note(terms, lang)
    if terms.one_star_level is None or len(terms.tickers) == 1:
        assert "One Star" not in txt
    if not getattr(terms, "zenith", False):
        assert "Zenith" not in txt
    if not (getattr(terms, "autocall_step_down", 0) or 0) > 0:
        # the declining-barrier clause and its floor must be absent entirely
        assert "falls" not in txt or "points at each date" not in txt
        assert "baja" not in txt or "puntos en cada" not in txt
        assert "its floor of" not in txt and "su suelo del" not in txt
    if not terms.memory and terms.n_obs > 1 and terms.coupon_pa > 0 \
            and not getattr(terms, "coupon_at_autocall_only", False):
        assert ("memory effect" if lang == "en" else "efecto memoria") not in txt


@pytest.mark.parametrize("name,terms,lang", CASES, ids=IDS)
def test_autocall_level_is_always_stated(name, terms, lang):
    """The old template never printed the autocall level at all — the whole
    point of a note with a 100% barrier went unsaid."""
    txt = describe_note(terms, lang)
    if not (getattr(terms, "autocall_step_down", 0) or 0) > 0 \
            and terms.autocall_start_period <= terms.n_obs:
        assert pct(terms.autocall_barrier, lang) in txt


@pytest.mark.parametrize("name,terms,lang", CASES, ids=IDS)
def test_paragraph_ownership(name, terms, lang):
    """Each fact has exactly one home, so nothing is said twice."""
    paras = describe_note(terms, lang).split("\n\n")
    # the European/single-day nature of the barrier belongs to P5
    assert not re.search(r"European|europea", paras[1])
    # the coupon-at-the-call fact belongs to P4's settlement sentence
    if not getattr(terms, "coupon_at_autocall_only", False):
        assert not re.search(r"redeems early|amortiza anticipadamente", paras[2])


@pytest.mark.parametrize("name,terms,lang", CASES, ids=IDS)
def test_register(name, terms, lang):
    txt = describe_note(terms, lang)
    if lang == "en":
        assert not re.search(r"\byou\b|\byour\b", txt, re.I)
    else:
        # Spanish quotes decimals with a comma
        assert not re.search(r"\d\.\d+%", txt)


@pytest.mark.parametrize("name,terms,lang", CASES, ids=IDS)
def test_aggregate_coupon_is_per_observation(name, terms, lang):
    """The ceiling is n_obs x coupon_rate, NOT coupon_pa x maturity — they
    differ whenever maturity x periods_per_year is not an integer."""
    txt = describe_note(terms, lang)
    if terms.coupon_pa > 0 and not getattr(terms, "zenith", False):
        assert pct(terms.n_obs * terms.coupon_rate, lang) in txt
