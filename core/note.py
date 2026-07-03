"""
core/note.py
------------
NoteTerms dataclass — full Phoenix/Autocallable structured note specification.
price_note()         — fully vectorized payoff engine (no Python loops).

Supports replication of:
  - HSBC XS3376563584: 24M monthly Phoenix Memory Worst-of, knock-in barrier,
                        separate coupon barrier, autocall starts at period 4
  - BBVA XS3378405743: 18M quarterly Phoenix Memory Worst-of, knock-in barrier,
                        One Star best-of FINAL-redemption rescue (the default)
  - BNP Paribas One Star: One Star best-of overlay additionally on coupon AND
                        autocall (opt-in via one_star_coupon / one_star_autocall)

Key features
------------
  - Worst-of / best-of / basket-average selectable per event type
    (coupon check, autocall check, final redemption check)
  - Memory coupon: missed coupons accumulate and are paid on next trigger
  - Separate coupon barrier, autocall barrier, knock-in barrier
  - Autocall start period: first N periods are coupon-only (no early redemption)
  - European knock-in: checked only at final valuation date
  - Cash-equivalent physical delivery at maturity if knock-in triggered
  - Configurable observation frequency (monthly, quarterly, etc.)
  - JSON-serialisable via NoteTerms.to_dict() / NoteTerms.from_dict()

Extensibility
-------------
  - BarrierCondition: dataclass describing a single trigger condition.
  - ConditionRegistry: maps condition names to BarrierCondition instances.
  - price_note() builds a ConditionRegistry from NoteTerms at entry and
    dispatches the payoff loop over registered conditions.  Adding a new
    barrier type only requires registering a new BarrierCondition — the
    existing payoff logic is unchanged.
"""

from __future__ import annotations

import json
import warnings
import numpy as np
from dataclasses import dataclass
from typing import Callable, Literal

BasketType = Literal["worst_of", "best_of", "average"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _basket(perf: np.ndarray, kind: BasketType) -> np.ndarray:
    """
    Reduce per-asset performance array to a scalar per path.

    perf : (n_paths, n_assets)
    returns : (n_paths,)
    """
    if kind == "worst_of":
        return perf.min(axis=1)
    elif kind == "best_of":
        return perf.max(axis=1)
    elif kind == "average":
        return perf.mean(axis=1)
    else:
        raise ValueError(f"Unknown basket type '{kind}'. Use 'worst_of', 'best_of', or 'average'.")


# ---------------------------------------------------------------------------
# BarrierCondition — describes a single trigger condition
# ---------------------------------------------------------------------------

@dataclass
class BarrierCondition:
    """
    Describes a single barrier/trigger condition for a structured note.

    Attributes
    ----------
    name : str
        Identifier, e.g. "autocall", "coupon", "knock_in", "protection".
    kind : Literal["autocall", "coupon", "protection", "custom"]
        Determines how price_note() processes this condition:
          "autocall"   — early redemption check; uses basket + level.
          "coupon"     — periodic income check; uses basket + level, supports memory.
          "protection" — final capital-loss guard (knock-in / rescue); uses basket + level.
          "custom"     — fully custom; evaluate() is called instead of basket+level logic.
    basket : BasketType
        Aggregation method across assets: "worst_of", "best_of", or "average".
    level : float
        Barrier level as a fraction of initial (e.g. 1.0 = 100%, 0.55 = 55%).
    start_period : int
        First observation period (1-indexed) where this condition is active.
    memory : bool
        For coupon conditions: accumulate missed coupons and pay on next trigger.
    evaluate : Callable[[np.ndarray], np.ndarray] | None
        Optional override for fully custom logic.
        Signature: fn(perf_slice: (n_paths, n_assets)) -> (n_paths,) float/bool.
        When None the standard basket+level comparison is used.
        Only consulted for kind="custom".
    """
    name:         str
    kind:         Literal["autocall", "coupon", "protection", "custom"]
    basket:       BasketType
    level:        float
    start_period: int                    = 1
    memory:       bool                   = False
    evaluate:     Callable | None        = None

    def apply(self, perf_slice: np.ndarray) -> np.ndarray:
        """
        Evaluate the condition against a per-observation performance slice.

        perf_slice : (n_paths, n_assets) — performance at one observation date.
        Returns    : (n_paths,) float — 1.0 where condition is met, else 0.0.
                     For "custom" kind, the evaluate callable may return any float.
        """
        if self.kind == "custom" and self.evaluate is not None:
            return self.evaluate(perf_slice)
        basket_vals = _basket(perf_slice, self.basket)
        return (basket_vals >= self.level).astype(float)


# ---------------------------------------------------------------------------
# ConditionRegistry
# ---------------------------------------------------------------------------

class ConditionRegistry:
    """
    Ordered registry mapping condition names to BarrierCondition instances.

    price_note() processes conditions in insertion order:
      autocall conditions are checked before coupon conditions, which are
      checked before protection conditions.  This mirrors the real waterfall
      on a structured-note term sheet.
    """

    def __init__(self) -> None:
        self._conditions: dict[str, BarrierCondition] = {}

    def register(self, condition: BarrierCondition) -> None:
        """Add or replace a condition by name."""
        self._conditions[condition.name] = condition

    def get(self, name: str) -> BarrierCondition | None:
        """Return the condition with the given name, or None."""
        return self._conditions.get(name)

    def all(self) -> list[BarrierCondition]:
        """Return all registered conditions in insertion order."""
        return list(self._conditions.values())

    def by_kind(self, kind: str) -> list[BarrierCondition]:
        """Return all conditions of a given kind, in insertion order."""
        return [c for c in self._conditions.values() if c.kind == kind]

    @classmethod
    def from_note_terms(cls, terms: "NoteTerms") -> "ConditionRegistry":
        """
        Build a ConditionRegistry from a NoteTerms instance.

        This is the canonical factory used by price_note().  It encodes the
        same barrier semantics as the pre-refactor monolithic payoff loop,
        ensuring full backward compatibility.

        Condition insertion order (= processing order in price_note()):
          1. "autocall"   — early redemption trigger
          2. "coupon"     — periodic coupon trigger (with optional memory)
          3. "knock_in"   — European KI protection barrier at maturity
          4. "protection" — One Star best-of overlay (final-redemption portion)
        """
        registry = cls()

        registry.register(BarrierCondition(
            name="autocall",
            kind="autocall",
            basket=terms.autocall_basket,
            level=terms.autocall_barrier,
            start_period=terms.autocall_start_period,
        ))

        registry.register(BarrierCondition(
            name="coupon",
            kind="coupon",
            basket=terms.coupon_basket,
            level=terms.coupon_barrier,
            start_period=1,
            memory=terms.memory,
        ))

        # knock_in uses worst_of unconditionally (per spec: always worst performer)
        registry.register(BarrierCondition(
            name="knock_in",
            kind="protection",
            basket="worst_of",
            level=terms.knock_in_barrier,
            start_period=1,
        ))

        # One Star best-of overlay (final-redemption portion). When
        # one_star_level is None the feature is off, encoded as a best-of level
        # of +inf so the rescue condition can never be met.
        registry.register(BarrierCondition(
            name="protection",
            kind="protection",
            basket="best_of",
            level=terms.one_star_level if terms.one_star_level is not None else float("inf"),
            start_period=1,
        ))

        return registry


# ---------------------------------------------------------------------------
# Product specification
# ---------------------------------------------------------------------------

# Frequency string → periods per year
_FREQ_TO_PERIODS: dict[str, int] = {
    "monthly":     12,
    "quarterly":    4,
    "semi-annual":  2,
    "annual":       1,
}


@dataclass
class NoteTerms:
    """
    Full specification of a Phoenix Memory Autocallable note.

    Human-readable fields (set these in JSON / UI):
      maturity        : tenor in years (e.g. 2.0)
      payment_freq    : "monthly" | "quarterly" | "semi-annual" | "annual"
      coupon_pa       : annualised coupon rate as a fraction (e.g. 0.10 = 10% p.a.)

    Derived (computed automatically):
      n_obs           : maturity * periods_per_year
      coupon_rate     : coupon_pa / periods_per_year  (per-period rate)
    """
    maturity:               float       = 1.0
    payment_freq:           str         = "quarterly"   # monthly/quarterly/semi-annual/annual
    coupon_pa:              float       = 0.10          # annualised coupon rate
    coupon_barrier:         float       = 0.55
    autocall_barrier:       float       = 1.00
    autocall_start_period:  int         = 1
    knock_in_barrier:       float       = 0.55
    principal_protection:   float       = 1.00
    memory:                 bool        = True
    coupon_basket:          BasketType  = "worst_of"
    autocall_basket:        BasketType  = "worst_of"
    one_star_level:         float | None = None   # 'One Star' best-of overlay level (see price_note); None = off
    # One Star scope. The best-of rescue ALWAYS applies to FINAL REDEMPTION when
    # one_star_level is set (a single underlying >= level redeems capital at par
    # even if the worst-of breached the knock-in — BBVA XS3378405743). These two
    # flags extend that same best-of overlay to the PERIODIC checks; both default
    # OFF (final-only rescue). Set both True for a BNP-style "One Star" note where
    # a single underlying >= level also pays the coupon and forces the autocall.
    one_star_coupon:        bool        = False  # best-of also satisfies the coupon barrier
    one_star_autocall:      bool        = False  # best-of also forces the autocall trigger
    call_steepness:         float | None = None   # None = hard trigger (default)
    # ── Classic / Growth Autocall extensions (default = no-op → plain Phoenix) ──
    autocall_step_down:      float       = 0.0    # per-period decrement of autocall barrier (0 = constant)
    autocall_floor:          float | None = None  # minimum autocall barrier when stepping down
    coupon_at_autocall_only: bool        = False  # True = no periodic coupon; accrued premium paid as a lump at autocall
    # ── Note structure type (explicit; drives the menu, payoff branch, diagram, prose) ──
    # phoenix | reverse_conv | growth_autocall | participation | custom. Inferred on
    # load for legacy configs that predate this field (see from_dict).
    note_type:              str          = "phoenix"
    # ── Participation Note (note_type == "participation") ─────────────────────
    # A single maturity-level payoff profile: choose ONE downside style and ONE
    # upside style; the whole Phoenix waterfall (coupons/autocall/knock-in) is
    # skipped. See _participation_redemption() for the exact per-style formulas.
    participation_downside: str          = "full"       # full | buffer | airbag | bear
    participation_upside:   str          = "linear"     # linear | shark_fin | digital
    participation_basket:   BasketType   = "worst_of"   # basket applied to the final level
    protection_level:       float        = 1.0          # capital floor / buffer level / airbag barrier (fraction of initial)
    participation_rate:     float        = 1.0          # upside (or downside, for bear) multiplier
    participation_strike:   float        = 1.0          # level from which participation is measured
    knockout_level:         float | None = None         # shark-fin: upside knocks out above this final level
    knockout_payout:        float        = 1.0          # shark-fin: redemption if knocked out (1.0 = par; the level it drops to)
    digital_payout:         float        = 0.0          # digital: fixed extra return if final >= strike (e.g. 0.10 = +10%)
    # Periodic / cliquet participation (a series of back-to-back protected participation
    # notes): reset the strike each observation date and pay rate·max(0, min(period
    # return, period_cap)) as income at each reset; capital protected at protection_level.
    participation_periodic: bool         = False        # turns on the cliquet mode
    period_cap:             float | None = None         # per-period cap on the participation (None = uncapped)
    # ── Capital Protected legacy fields (kept for back-compat; see from_dict) ──
    capital_guarantee:       float | None = None  # legacy CP guarantee → migrated to protection_level + note_type=participation
    upside_cap:              float | None = None  # maximum redemption above par; also the cap for linear/shark-fin upside
    name:                   str         = "Phoenix Memory Note"
    # Systematic, terms-driven prose blurb (core.note_description). "" = auto-generate;
    # a non-empty value is a user override, mirroring issuer/underlying descriptions.
    note_description:       str         = ""
    issuer:                 str         = ""      # display-only: e.g. "BBVA", "HSBC"
    # ── Issuer information (display-only; powers the PDF "Issuer Information" section) ──
    issuer_description:     str         = ""      # short prose blurb about the issuer
    issuer_rating_sp:       str         = ""      # S&P credit rating, e.g. "A+"
    issuer_rating_moody:    str         = ""      # Moody's credit rating, e.g. "A1"
    issuer_rating_fitch:    str         = ""      # Fitch credit rating, e.g. "AA-"
    tickers:                dict | None  = None
    issue_date:             str  | None = None   # "YYYY-MM-DD" — enables Current Performance tab
    # ── Per-underlying display info (powers the PDF "Underlying Breakdown") ──
    # Keyed by DISPLAY NAME: {"Microsoft": {"description": "...", "sector": "..."}}.
    # 'description' mirrors issuer_description — JSON-preloaded, editable in the UI.
    # Any metric key present (sector, type, market_cap, iv_3m, last_price, …)
    # OVERRIDES the live data pull; everything else is fetched programmatically.
    underlyings:            dict | None = None

    def __post_init__(self):
        if self.tickers is None:
            object.__setattr__(self, "tickers", {})
        if self.underlyings is None:
            object.__setattr__(self, "underlyings", {})
        if self.payment_freq not in _FREQ_TO_PERIODS:
            raise ValueError(
                f"payment_freq must be one of {list(_FREQ_TO_PERIODS)}; got '{self.payment_freq}'"
            )
        if self.autocall_start_period < 1:
            raise ValueError(
                f"autocall_start_period must be >= 1 (1-indexed); got {self.autocall_start_period}"
            )

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def periods_per_year(self) -> int:
        return _FREQ_TO_PERIODS[self.payment_freq]

    @property
    def n_obs(self) -> int:
        """Total observation periods = maturity × periods per year."""
        return round(self.maturity * self.periods_per_year)

    @property
    def coupon_rate(self) -> float:
        """Per-period coupon rate = coupon_pa / periods_per_year."""
        return self.coupon_pa / self.periods_per_year

    # ------------------------------------------------------------------
    # Schedule helpers
    # ------------------------------------------------------------------

    def obs_times(self) -> list[float]:
        """Observation times in years, evenly spaced."""
        return [self.maturity * i / self.n_obs for i in range(1, self.n_obs + 1)]

    def obs_steps(self, N: int) -> list[int]:
        """Map observation times to simulation step indices."""
        return [round(t / self.maturity * N) for t in self.obs_times()]

    def obs_calendar_dates(self, anchor) -> list:
        """
        Calendar observation dates: anchor + k × (12 / periods_per_year) months,
        k = 1..n_obs. This is what term sheets specify (the caller is
        responsible for snapping each date to the next trading day in a price
        index). The last date is the final valuation / maturity date.
        """
        import pandas as pd
        a = pd.Timestamp(anchor)
        step_months = 12 // self.periods_per_year
        return [a + pd.DateOffset(months=step_months * (k + 1)) for k in range(self.n_obs)]

    def autocall_barrier_schedule(self) -> np.ndarray:
        """
        Per-observation autocall barrier levels, shape (n_obs,).

        Constant at `autocall_barrier` unless `autocall_step_down > 0`, in which
        case the barrier declines by `autocall_step_down` each period from the
        first callable period (`autocall_start_period`), floored at
        `autocall_floor` if set. This models "step-down" / growth autocalls such
        as Citi XS3096699163 (100% declining 3% per period from obs 3, min 88%).
        """
        levels = np.full(self.n_obs, self.autocall_barrier, dtype=float)
        if self.autocall_step_down and self.autocall_step_down > 0:
            for j in range(self.autocall_start_period, self.n_obs + 1):
                lvl = self.autocall_barrier - self.autocall_step_down * (j - self.autocall_start_period)
                if self.autocall_floor is not None:
                    lvl = max(lvl, self.autocall_floor)
                levels[j - 1] = lvl
        return levels

    # ------------------------------------------------------------------
    # Serialisation — stores human-readable fields only
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "name":                   self.name,
            "issuer":                 self.issuer,
            "maturity":               self.maturity,
            "payment_freq":           self.payment_freq,
            "coupon_pa":              self.coupon_pa,
            "coupon_barrier":         self.coupon_barrier,
            "autocall_barrier":       self.autocall_barrier,
            "autocall_start_period":  self.autocall_start_period,
            "knock_in_barrier":       self.knock_in_barrier,
            "principal_protection":   self.principal_protection,
            "memory":                 self.memory,
            "coupon_basket":          self.coupon_basket,
            "autocall_basket":        self.autocall_basket,
            "one_star_level":         self.one_star_level,
            "one_star_coupon":        self.one_star_coupon,
            "one_star_autocall":      self.one_star_autocall,
            "call_steepness":         self.call_steepness,
            "autocall_step_down":     self.autocall_step_down,
            "autocall_floor":         self.autocall_floor,
            "coupon_at_autocall_only": self.coupon_at_autocall_only,
            "note_type":              self.note_type,
            "participation_downside": self.participation_downside,
            "participation_upside":   self.participation_upside,
            "participation_basket":   self.participation_basket,
            "protection_level":       self.protection_level,
            "participation_rate":     self.participation_rate,
            "participation_strike":   self.participation_strike,
            "knockout_level":         self.knockout_level,
            "knockout_payout":        self.knockout_payout,
            "digital_payout":         self.digital_payout,
            "participation_periodic": self.participation_periodic,
            "period_cap":             self.period_cap,
            "capital_guarantee":      self.capital_guarantee,
            "upside_cap":             self.upside_cap,
            "note_description":       self.note_description,
            "issuer_description":     self.issuer_description,
            "issuer_rating_sp":       self.issuer_rating_sp,
            "issuer_rating_moody":    self.issuer_rating_moody,
            "issuer_rating_fitch":    self.issuer_rating_fitch,
            "tickers":                self.tickers,
            "issue_date":             self.issue_date,
            "underlyings":            self.underlyings,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NoteTerms":
        """
        Load from dict. Accepts both new format (payment_freq + coupon_pa)
        and old format (n_obs + coupon_rate) for backwards compatibility.
        """
        d = dict(d)  # don't mutate caller's dict

        # ── Legacy hard-trigger migration ─────────────────────────────
        # Older configs stored call_steepness=100.0 under the (incorrect)
        # assumption that it behaved as a hard trigger. Map it to None
        # (true hard trigger) so legacy JSONs price as originally intended.
        # Any other explicit value is respected as a deliberate soft trigger.
        if d.get("call_steepness") == 100.0:
            d["call_steepness"] = None

        # ── note_type inference (configs predating the explicit field) ────
        # The old 'Capital Protected' note keyed on capital_guarantee>0; map it
        # to the generalised participation branch (full protection, 100% linear
        # participation — the closest equivalent). Otherwise label the phoenix /
        # reverse-convertible / growth-autocall family (menu label only; those
        # share the one waterfall). protection_level inherits capital_guarantee.
        if not d.get("note_type"):
            if (d.get("capital_guarantee") or 0) > 0:
                d["note_type"] = "participation"
                d.setdefault("protection_level", float(d["capital_guarantee"]))
                d.setdefault("participation_downside", "full")
                d.setdefault("participation_upside", "linear")
            elif d.get("coupon_at_autocall_only") or (d.get("autocall_step_down") or 0) > 0:
                d["note_type"] = "growth_autocall"
            elif d.get("coupon_barrier") == 0 and not d.get("memory", True):
                d["note_type"] = "reverse_conv"
            else:
                d["note_type"] = "phoenix"

        # Shark-fin drop level was briefly a rebate (extra above par); it is now an
        # absolute knock-out payout (the level it drops to).
        if "knockout_rebate" in d and "knockout_payout" not in d:
            d["knockout_payout"] = 1.0 + float(d.pop("knockout_rebate") or 0.0)

        # ── One Star migration ────────────────────────────────────────
        # The 'One Star' best-of overlay was previously encoded as a
        # final-redemption-only rescue via final_basket="best_of" +
        # final_redemption_barrier. Map those legacy fields onto one_star_level,
        # which defaults to that same FINAL-REDEMPTION-ONLY behaviour (the coupon
        # and autocall overlays are separate opt-in flags, both off here — exactly
        # the legacy semantics). final_basket in {"worst_of","average"} → no overlay.
        if "final_basket" in d or "final_redemption_barrier" in d:
            legacy_basket = d.pop("final_basket", "worst_of")
            legacy_level  = d.pop("final_redemption_barrier", 1.0)
            if "one_star_level" not in d:
                d["one_star_level"] = float(legacy_level) if legacy_basket == "best_of" else None

        # ── Old-format migration ──────────────────────────────────────
        if "n_obs" in d or "coupon_rate" in d:
            # Infer payment_freq from maturity and n_obs
            maturity = float(d.get("maturity", 1.0))
            n_obs    = int(d.pop("n_obs", 4))
            periods_py = round(n_obs / maturity)
            # Find closest known frequency
            freq = min(_FREQ_TO_PERIODS, key=lambda f: abs(_FREQ_TO_PERIODS[f] - periods_py))
            d["payment_freq"] = freq
            # Convert per-period rate to annualised
            coupon_rate = float(d.pop("coupon_rate", 0.025))
            d["coupon_pa"] = coupon_rate * _FREQ_TO_PERIODS[freq]

        known   = cls.__dataclass_fields__
        unknown = [k for k in d if k not in known]
        if unknown:
            warnings.warn(
                f"NoteTerms.from_dict: ignoring unrecognised keys {unknown}. "
                "Check for typos in your JSON config.",
                stacklevel=2,
            )
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def from_json(cls, json_str: str) -> "NoteTerms":
        return cls.from_dict(json.loads(json_str))

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)




# ---------------------------------------------------------------------------
# Participation Note payoff — a single maturity-level profile
# ---------------------------------------------------------------------------

def _participation_redemption(B: np.ndarray, terms: "NoteTerms") -> np.ndarray:
    """Maturity redemption (as a fraction of notional) for a Participation Note,
    as a PURE function of the final basket level ``B`` (n_paths,). One downside
    style is composed with one upside style around the participation strike:

        Upside  (B >= strike):
          linear     R = 1 + rate·(B − strike)                    [capped]
          shark_fin  R = 1 + rate·(B − strike) up to knockout_level, then it
                     drops to a flat knockout_payout above it        [capped]
          digital    R = 1 + digital_payout   (fixed, if B >= strike)

        Downside (B < strike), with prot = protection_level:
          full       R = min(prot, 1)          (flat floor; prot=1 → par)
          buffer     R = 1 down to prot, then 1:1 loss below prot
          airbag     R = 1 down to prot, then geared  R = B / prot below it

        bear (a downside style that also defines the upside): participate as B
          falls below the strike, floored at prot above it —
              R = clip(1 + rate·max(0, strike − B), prot, cap)

    ``upside_cap`` (→ cap = 1 + upside_cap) limits the upside only; None = uncapped.
    """
    B = np.asarray(B, dtype=float)
    strike = float(terms.participation_strike)
    rate   = float(terms.participation_rate)
    prot   = float(terms.protection_level) if terms.protection_level is not None else 0.0
    cap    = (1.0 + terms.upside_cap) if terms.upside_cap is not None else np.inf
    up_style, dn_style = terms.participation_upside, terms.participation_downside

    # Bear: reverse note — upside style does not apply.
    if dn_style == "bear":
        return np.clip(1.0 + rate * np.maximum(0.0, strike - B), prot, cap)

    # Upside leg (B >= strike)
    if up_style == "digital":
        R_up = np.full_like(B, min(1.0 + float(terms.digital_payout), cap))
    elif up_style == "shark_fin" and terms.knockout_level is not None:
        # Participate strike..knock-out; at/above the knock-out the note drops to a
        # fixed redemption (knockout_payout — the level it drops to).
        lin_R = np.minimum(1.0 + rate * (B - strike), cap)
        R_up = np.where(B >= float(terms.knockout_level), float(terms.knockout_payout), lin_R)
    else:  # linear (or shark_fin with no knock-out level set yet)
        R_up = np.minimum(1.0 + rate * (B - strike), cap)

    # Downside leg (B < strike)
    if dn_style == "buffer":
        R_dn = np.where(B >= prot, 1.0, 1.0 - (prot - B))
    elif dn_style == "airbag":
        R_dn = np.where(B >= prot, 1.0,
                        np.divide(B, prot, out=np.zeros_like(B), where=(prot > 0)))
    else:  # full — flat protection floor (par when prot >= 1)
        R_dn = np.full_like(B, min(prot, 1.0))

    R = np.where(B >= strike, R_up, R_dn)
    return np.maximum(R, 0.0)


def _participation_stats(R: np.ndarray, terms: "NoteTerms", B: np.ndarray | None = None) -> dict:
    """Redemption-distribution metrics for a Participation Note (used by the hero
    tiles + the report). R = per-path redemption; B = final basket (for the
    shark-fin knock-out probability)."""
    cap_lv = (1.0 + terms.upside_cap) if terms.upside_cap is not None else None
    ko = None
    if (B is not None and terms.participation_upside == "shark_fin"
            and terms.knockout_level is not None):
        ko = float((B >= float(terms.knockout_level)).mean())
    return {
        "prob_above_par":   float((R > 1.0 + 1e-9).mean()),
        "prob_at_cap":      float((R >= cap_lv - 1e-6).mean()) if cap_lv is not None else None,
        "prob_knocked_out": ko,
        "expected_gain":    float(np.maximum(R - 1.0, 0.0).mean()),
        "p5_redemption":    float(np.percentile(R, 5)),
    }


def _participation_periodic_payoff(perf_paths, terms, obs_steps, t_maturity, n_obs) -> dict:
    """Cliquet / ratchet participation: at each reset date pay
    rate·max(0, min(period return, period_cap)) as income (down periods pay 0);
    capital is protected at protection_level. The per-period income maps onto the
    coupon stream so the path explorer and coupon stats work unchanged."""
    n_paths = perf_paths.shape[0]
    rate = float(terms.participation_rate)
    cap  = float(terms.period_cap) if terms.period_cap is not None else np.inf
    prot = float(terms.protection_level) if terms.protection_level is not None else 1.0
    # Basket level at each reset date; B_0 = 1.0 at inception. Period return is the
    # basket's move over each reset interval (strike resets each period).
    B      = np.stack([_basket(perf_paths[:, s, :], terms.participation_basket) for s in obs_steps], axis=1)  # (n_paths, n_obs)
    B_prev = np.concatenate([np.ones((n_paths, 1)), B[:, :-1]], axis=1)
    r      = np.divide(B, B_prev, out=np.ones_like(B), where=(B_prev != 0)) - 1.0
    period_income = rate * np.clip(r, 0.0, cap)          # (n_paths, n_obs), floored at 0
    total_income  = period_income.sum(axis=1)
    principal     = np.full(n_paths, prot)               # capital protected (floored periods never erode it)
    nominal       = principal + total_income
    total_return  = nominal - 1.0
    irr           = total_return / max(t_maturity, 1.0 / 252.0)
    loss          = principal < 1.0
    return {
        "nominal_payoffs":      nominal,
        "coupon_payoffs":       total_income,
        "principal_payoffs":    principal,
        "autocall_period":      np.zeros(n_paths, dtype=int),
        "knock_in_triggered":   loss,
        "knock_in_mask":        loss,
        "annualized_returns":   irr,
        "total_returns":        total_return,
        "coupon_amounts":       period_income,
        "autocall_events":      np.zeros(n_paths, dtype=int),
        "expected_irr":             float(irr.mean()),
        "expected_total_return":    float(total_return.mean()),
        "expected_nominal_payout":  float(nominal.mean()),
        "expected_coupon":          float(total_income.mean()),
        "prob_autocall":            0.0,
        "prob_autocall_by_period":  [0.0] * n_obs,
        "prob_maturity":            1.0,
        "prob_knock_in":            float(loss.mean()),
        "prob_knock_in_total":      float(loss.mean()),
        "prob_barrier_event":       float(loss.mean()),
        "prob_rescued":             0.0,
        "loss_given_knock_in":      float(irr[loss].mean()) if loss.any() else float("nan"),
        "avg_time_to_autocall":     None,
        **_participation_stats(nominal, terms),
    }


def _participation_payoff(perf_paths, terms, obs_steps, t_maturity, n_obs) -> dict:
    """price_note() branch for note_type == 'participation'. A pure maturity payoff:
    no coupons, no autocall, no periodic knock-in. Returns the same result schema as
    the Phoenix path so everything downstream (stats, plots, path explorer) is
    unchanged; 'knock-in' here means redeemed below par (a capital loss)."""
    if getattr(terms, "participation_periodic", False):
        return _participation_periodic_payoff(perf_paths, terms, obs_steps, t_maturity, n_obs)
    n_paths    = perf_paths.shape[0]
    final_step = obs_steps[-1]
    B          = _basket(perf_paths[:, final_step, :], terms.participation_basket)  # (n_paths,)
    R          = _participation_redemption(B, terms)
    total_return = R - 1.0
    irr        = total_return / max(t_maturity, 1.0 / 252.0)
    loss       = R < 1.0                                    # redeemed below par
    zeros      = np.zeros(n_paths)
    return {
        "nominal_payoffs":      R,
        "coupon_payoffs":       zeros,
        "principal_payoffs":    R,
        "autocall_period":      zeros.astype(int),
        "knock_in_triggered":   loss,
        "knock_in_mask":        loss,
        "annualized_returns":   irr,
        "total_returns":        total_return,
        "coupon_amounts":       np.zeros((n_paths, n_obs)),
        "autocall_events":      zeros.astype(int),
        "expected_irr":             float(irr.mean()),
        "expected_total_return":    float(total_return.mean()),
        "expected_nominal_payout":  float(R.mean()),
        "expected_coupon":          0.0,
        "prob_autocall":            0.0,
        "prob_autocall_by_period":  [0.0] * n_obs,
        "prob_maturity":            1.0,
        "prob_knock_in":            float(loss.mean()),
        "prob_knock_in_total":      float(loss.mean()),
        "prob_barrier_event":       float(loss.mean()),
        "prob_rescued":             0.0,
        "loss_given_knock_in":      float(irr[loss].mean()) if loss.any() else float("nan"),
        "avg_time_to_autocall":     None,
        **_participation_stats(R, terms, B),
    }


# ---------------------------------------------------------------------------
# Vectorized payoff engine
# ---------------------------------------------------------------------------

def price_note(
    perf_paths: np.ndarray,
    terms:      NoteTerms,
    seed:       int | None = 42,
    obs_steps:  list[int]   | None = None,
    obs_times:  list[float] | None = None,
) -> dict:
    """
    Evaluate Phoenix Memory Autocallable payoffs across all simulated paths.

    Fully vectorized — no Python loop over paths.

    Parameters
    ----------
    perf_paths : np.ndarray  shape (n_paths, N+1, n_assets)
        Per-asset performance paths (price / initial price).
        Produced by stacking sim_prices / S0_vector.
        perf_paths[:, 0, :] should be all 1.0 (initial level).

    terms : NoteTerms
        Product specification.

    seed : int or None
        RNG seed for autocall probability draws.

    obs_steps : list[int] or None
        Explicit grid indices of the observation dates (length n_obs, last
        entry should be N). Used when the simulation grid is a real
        trading-day calendar and observation dates were snapped to it. None
        (default) = uniform mapping via terms.obs_steps(N).

    obs_times : list[float] or None
        Explicit observation times in year fractions from the anchor date
        (length n_obs), used for holding-period / IRR computation. When given,
        the maturity holding time is obs_times[-1] instead of terms.maturity.
        None (default) = terms.obs_times().

    Returns
    -------
    dict with keys:
        nominal_payoffs      : (n_paths,)
        coupon_payoffs       : (n_paths,)   total coupons received
        autocall_period      : (n_paths,)   0 = maturity, 1..n_obs = period called
        knock_in_triggered   : (n_paths,)   bool, only meaningful for maturity paths
        expected_irr         : float        simple annualised IRR (not compound)
        expected_total_return: float
        expected_coupon      : float
        prob_autocall        : float
        prob_autocall_by_period : list[float]
        prob_maturity        : float
        prob_knock_in        : float        P(knock-in at maturity | reaches maturity)
        prob_knock_in_total  : float        P(knock-in) across all paths

    Note on IRR convention
    ----------------------
    IRR is computed as simple annualisation: total_return / t_held.
    This is consistent with the structured note market convention where
    coupons are quoted as simple p.a. rates.  For long-dated paths (2Y+)
    the simple IRR will exceed a compound (XIRR-style) IRR by a small amount.
    """
    n_paths, N_plus1, n_assets = perf_paths.shape
    N = N_plus1 - 1
    n_obs = terms.n_obs
    if obs_steps is None:
        obs_steps = terms.obs_steps(N)
    if obs_times is None:
        obs_times = terms.obs_times()
    if len(obs_steps) != n_obs or len(obs_times) != n_obs:
        raise ValueError(
            f"obs_steps/obs_times must have length n_obs={n_obs}; "
            f"got {len(obs_steps)}/{len(obs_times)}"
        )
    t_maturity = float(obs_times[-1])   # = terms.maturity unless overridden
    rng = np.random.default_rng(seed)

    # ------------------------------------------------------------------
    # Participation Note branch — a single maturity-level payoff profile
    # ------------------------------------------------------------------
    # Chosen downside × upside styles evaluated on the final basket level; the
    # entire Phoenix waterfall (coupons / autocall / knock-in) is skipped. Routed
    # by the explicit note_type, or (legacy) by a positive capital_guarantee —
    # which from_dict already maps to note_type="participation" + protection_level.
    if (getattr(terms, "note_type", "") == "participation"
            or (terms.capital_guarantee is not None and terms.capital_guarantee > 0)):
        return _participation_payoff(perf_paths, terms, obs_steps, t_maturity, n_obs)

    # ------------------------------------------------------------------
    # Build ConditionRegistry from NoteTerms (backward-compatible factory)
    # ------------------------------------------------------------------
    registry = ConditionRegistry.from_note_terms(terms)

    autocall_cond   = registry.get("autocall")    # BarrierCondition, kind="autocall"
    coupon_cond     = registry.get("coupon")      # BarrierCondition, kind="coupon"
    knock_in_cond   = registry.get("knock_in")    # BarrierCondition, kind="protection"
    protection_cond = registry.get("protection")  # BarrierCondition, kind="protection" (rescue)

    # Draw autocall decisions: (n_paths, n_obs)
    call_draws = rng.random((n_paths, n_obs))

    # ------------------------------------------------------------------
    # Per-observation basket values
    # ------------------------------------------------------------------
    coupon_basket_vals = np.stack(
        [_basket(perf_paths[:, s, :], coupon_cond.basket) for s in obs_steps], axis=1
    )  # (n_paths, n_obs)

    autocall_basket_vals = np.stack(
        [_basket(perf_paths[:, s, :], autocall_cond.basket) for s in obs_steps], axis=1
    )  # (n_paths, n_obs)

    # ------------------------------------------------------------------
    # One Star best-of overlay (BNP-style "Nivel de One Star")
    # ------------------------------------------------------------------
    # When one_star_level is set, a single underlying at or above that level
    # rescues FINAL REDEMPTION to par even if the worst-of breached the knock-in
    # (see the redemption block below — this is the default, BBVA-style).
    # Extending that best-of overlay to the PERIODIC coupon and autocall checks is
    # opt-in via one_star_coupon / one_star_autocall (BNP-style One Star). When
    # one_star_level is None the overlay is all-False and the note is plain
    # worst-of throughout.
    if terms.one_star_level is not None:
        best_of_vals = np.stack(
            [_basket(perf_paths[:, s, :], "best_of") for s in obs_steps], axis=1
        )  # (n_paths, n_obs)
        one_star_met = best_of_vals >= terms.one_star_level   # (n_paths, n_obs) bool
    else:
        one_star_met = np.zeros((n_paths, n_obs), dtype=bool)
    # Periodic overlays are gated by their flags; final redemption always uses the
    # full one_star_met (via protection_cond) regardless of these.
    _zero_overlay = np.zeros((n_paths, n_obs), dtype=bool)
    one_star_coupon_met   = one_star_met if terms.one_star_coupon   else _zero_overlay
    one_star_autocall_met = one_star_met if terms.one_star_autocall else _zero_overlay

    # ------------------------------------------------------------------
    # Autocall trigger
    # ------------------------------------------------------------------
    # Autocall mask: only eligible from autocall_start_period onward
    autocall_eligible = np.zeros(n_obs, dtype=bool)
    autocall_eligible[autocall_cond.start_period - 1:] = True  # 1-indexed → 0-indexed

    # Autocall probabilities per period, using a (possibly step-down) per-period
    # barrier schedule. For the common constant-barrier case this reduces exactly
    # to a scalar comparison against autocall_barrier; the schedule generalises
    # it to growth autocalls.
    autocall_levels = terms.autocall_barrier_schedule()          # (n_obs,)
    if terms.call_steepness is None:
        autocall_probs = (autocall_basket_vals >= autocall_levels[np.newaxis, :]).astype(float)
    else:
        x = np.clip(-terms.call_steepness * (autocall_basket_vals - autocall_levels[np.newaxis, :]),
                    -500.0, 500.0)
        autocall_probs = 1.0 / (1.0 + np.exp(x))
    # One Star overlay (opt-in via one_star_autocall): any underlying >=
    # one_star_level forces a (deterministic) autocall, regardless of the
    # worst-of/soft-trigger probability. Off by default → no effect.
    autocall_probs = np.maximum(autocall_probs, one_star_autocall_met.astype(float))
    autocall_probs[:, ~autocall_eligible] = 0.0

    autocall_triggered = call_draws < autocall_probs             # (n_paths, n_obs)

    # First autocall period per path (0 = none)
    any_autocalled   = autocall_triggered.any(axis=1)            # (n_paths,)
    first_call_idx   = np.argmax(autocall_triggered, axis=1)     # (n_paths,) 0-indexed

    autocall_period  = np.where(any_autocalled, first_call_idx + 1, 0).astype(int)

    # ------------------------------------------------------------------
    # Coupon calculation — dispatched via coupon_cond
    # ------------------------------------------------------------------
    # One Star overlay (opt-in via one_star_coupon): any underlying >=
    # one_star_level pays the coupon even if the worst-of is below the coupon
    # barrier. Off by default → coupon uses the plain (worst-of) basket only.
    coupon_barrier_met = (coupon_basket_vals >= coupon_cond.level) | one_star_coupon_met   # (n_paths, n_obs)

    # For each path, coupons are paid up to and including the autocall period
    # (or all periods if reaching maturity)
    active_until = np.where(any_autocalled, autocall_period, n_obs)  # last active period (inclusive, 1-indexed)

    # Build active mask: period j is active if j <= active_until (1-indexed)
    period_idx   = np.arange(1, n_obs + 1)[np.newaxis, :]            # (1, n_obs)
    active_mask  = period_idx <= active_until[:, np.newaxis]          # (n_paths, n_obs)

    if coupon_cond.memory:
        # Memory coupon — fully vectorized via cumulative sum trick.
        #
        # Key insight: the memory coupon paid at period j (when barrier is met)
        # equals rate * (1 + number of consecutive missed periods immediately
        # preceding j).  We can compute "periods since last payment" for every
        # (path, period) cell without a Python loop as follows:
        #
        # 1. Define paid[i,j] = 1 if the barrier was met AND the period is active.
        # 2. Build a "payment group" index via cumsum of paid shifted by one period:
        #    group[i,j] = number of payments made before period j on path i.
        # 3. Within each group the running count of active non-payment periods
        #    gives the accumulated pending count.
        #
        # This is equivalent to the sequential loop but executes in C via numpy.

        paid_mask = coupon_barrier_met & active_mask          # (n_paths, n_obs)

        # group[i,j] = how many payments have been made strictly before period j
        group = np.cumsum(paid_mask, axis=1)                  # (n_paths, n_obs)
        group_shifted = np.concatenate(
            [np.zeros((n_paths, 1), dtype=group.dtype), group[:, :-1]], axis=1
        )                                                      # (n_paths, n_obs)

        # Within each group, count consecutive active periods seen so far
        # (including the current one).  A payment resets this to 0.
        # active_count[i,j] = cumsum of active_mask within the current group.
        # We subtract the cumsum at the last payment in the same group.
        active_cumsum = np.cumsum(active_mask, axis=1)        # (n_paths, n_obs)

        # Last payment position per (path, period): the cumsum of active cells
        # up to and including the most recent paid cell in the same group.
        # We compute this by masking active_cumsum at paid cells and forward-filling.
        last_paid_active_cumsum = np.where(paid_mask, active_cumsum, 0)
        # Forward-fill within each row (axis=1) using np.maximum.accumulate
        last_paid_cumsum_ff = np.maximum.accumulate(last_paid_active_cumsum, axis=1)

        # pending[i,j] = number of active missed periods strictly before j
        # in the current payment group = (active cells up to j-1) - (active cells
        # up to the last payment before j).
        active_cumsum_shifted = np.concatenate(
            [np.zeros((n_paths, 1), dtype=active_cumsum.dtype), active_cumsum[:, :-1]], axis=1
        )
        last_paid_cumsum_shifted = np.concatenate(
            [np.zeros((n_paths, 1), dtype=last_paid_cumsum_ff.dtype),
             last_paid_cumsum_ff[:, :-1]], axis=1
        )
        pending_before = active_cumsum_shifted - last_paid_cumsum_shifted  # (n_paths, n_obs)
        pending_before = np.maximum(pending_before, 0)  # guard against rounding

        coupon_amounts = np.where(
            paid_mask,
            terms.coupon_rate * (pending_before + 1),
            0.0,
        )  # (n_paths, n_obs)
    else:
        # No memory: pay rate if barrier met, nothing otherwise
        coupon_amounts = np.where(
            coupon_barrier_met & active_mask,
            terms.coupon_rate,
            0.0,
        )

    total_coupons = coupon_amounts.sum(axis=1)   # (n_paths,)

    # ------------------------------------------------------------------
    # Classic / Growth Autocall premium
    # ------------------------------------------------------------------
    # For a growth autocall (e.g. Citi XS3096699163) there is NO periodic coupon.
    # Instead an accrued premium is paid as a lump ONLY when the note autocalls:
    # at observation j the redemption is principal + coupon_rate * j (the premium
    # accrues from inception at coupon_rate per period). Paths that reach maturity
    # without autocalling receive no premium.
    if terms.coupon_at_autocall_only:
        total_coupons = np.where(
            any_autocalled,
            terms.coupon_rate * autocall_period.astype(float),
            0.0,
        )
        # Keep the per-period coupon matrix consistent with the actual payoff:
        # a growth autocall pays NO periodic coupons — the accrued premium is a
        # single lump at the call period. Without this the matrix still held the
        # periodic barrier-met amounts (computed above), so the path-explorer
        # "coupon paid at period t" filter saw coupons the note never paid and
        # disagreed with the chart's replay_note flags. Lump goes at the call.
        coupon_amounts = np.zeros((n_paths, n_obs))
        _call_col = np.clip(autocall_period - 1, 0, n_obs - 1)
        _rows = np.nonzero(any_autocalled)[0]
        coupon_amounts[_rows, _call_col[_rows]] = total_coupons[_rows]

    # ------------------------------------------------------------------
    # Principal redemption — dispatched via knock_in_cond + protection_cond
    # ------------------------------------------------------------------
    # Autocalled paths: receive 100% principal back
    autocall_principal = np.ones(n_paths)

    # Maturity paths: check knock-in + final redemption condition
    # (final valuation = last observation step; equals N unless obs_steps override)
    final_step = obs_steps[-1]
    # One Star rescue uses best-of at maturity (protection_cond.basket = "best_of")
    final_basket_val = _basket(perf_paths[:, final_step, :], protection_cond.basket)  # (n_paths,)
    # knock-in always checks worst-of (per knock_in_cond.basket = "worst_of")
    worst_final      = _basket(perf_paths[:, final_step, :], knock_in_cond.basket)    # (n_paths,)

    # Barrier (knock-in) event: knock-in basket below the KI level at final valuation
    barrier_event = worst_final < knock_in_cond.level   # (n_paths,)

    # One Star final-redemption rescue: if the best performer is at or above
    # one_star_level, the note redeems at par EVEN IF the knock-in barrier was
    # breached.
    #
    # This implements term sheets like BBVA XS3378405743 (Final Payout xi —
    # Barrier and Knock-in) and the BNP One Star notes:
    #   (A) Best Value >= one_star_level           -> 100%
    #   (B) Best Value <  level and no Knock-in     -> 100%
    #   (C) Best Value <  level AND Knock-in        -> physical delivery of worst
    # i.e. capital loss requires BOTH worst < KI AND best < one_star_level.
    #
    # For notes without the One Star feature (one_star_level=None) the protection
    # level is +inf, so the rescue can never trigger and this reduces to the
    # standard worst-of payoff unchanged.
    rescued      = final_basket_val >= protection_cond.level
    capital_loss = barrier_event & ~rescued

    # Capital loss: cash-equivalent physical delivery = worst-of final performance.
    # Otherwise: principal_protection (100%) regardless of basket level (no upside
    # participation in a Phoenix). When KI is breached (capital_loss), standard
    # 1:1 downside applies regardless.
    protected_redemption = np.full(n_paths, terms.principal_protection)

    maturity_principal = np.where(
        capital_loss,
        worst_final,                       # cash equiv. of physical delivery
        protected_redemption,              # par redemption
    )

    # Combine
    principal = np.where(any_autocalled, autocall_principal, maturity_principal)

    # ------------------------------------------------------------------
    # Total payoff and IRR
    # ------------------------------------------------------------------
    nominal_payoffs = principal + total_coupons

    t_held_arr = np.where(
        any_autocalled,
        np.array(obs_times)[np.clip(first_call_idx, 0, n_obs - 1)],
        t_maturity,
    )

    # IRR: simple annualisation — total_return / t_held.
    # Structured note convention: coupon is quoted as p.a. simple rate,
    # so annualised return must use the same basis.
    # e.g. autocalled at 3M (t=0.25) with 2.5% coupon → IRR = 2.5%/0.25 = 10% p.a. ✓
    # Compound annualisation ((1+r)^(1/t)-1) overstates IRR for short tenors.
    total_return   = nominal_payoffs - 1.0
    # Guard against a degenerate near-zero holding time (QW5).
    annualized_irr = total_return / np.maximum(t_held_arr, 1.0 / 252.0)

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------
    maturity_mask = ~any_autocalled
    # 'Knock-in' in all reported stats means CAPITAL LOSS: barrier breached AND
    # final redemption condition not met (the 'rescue'). For worst-of final
    # baskets the two are identical; for best-of (BBVA) they differ.
    ki_total      = capital_loss & maturity_mask
    be_total      = barrier_event & maturity_mask   # barrier breached (incl. rescued paths)
    # A 'knock-in' here means a breach that ACTUALLY costs capital — barrier
    # breached AND not rescued by the final (best-of) redemption clause. Paths
    # rescued to par are NOT counted as knock-ins. (For worst-of notes there is
    # no rescue, so this equals the raw barrier-breach rate.) Loss given knock-in
    # is the mean annualised IRR over exactly those unrescued breach paths.
    lgki = float(annualized_irr[ki_total].mean()) if ki_total.any() else float("nan")

    return {
        # Per-path arrays (for Streamlit plots)
        "nominal_payoffs":      nominal_payoffs,
        "coupon_payoffs":       total_coupons,
        "principal_payoffs":    principal,
        "autocall_period":      autocall_period,
        "knock_in_triggered":   ki_total,
        "knock_in_mask":        ki_total,   # breached AND not rescued (a real knock-in)
        "annualized_returns":   annualized_irr,
        "total_returns":        total_return,
        # Per-path × per-period coupon amounts (n_paths, n_obs). Cells > 0 are
        # the periods that actually paid a coupon — powers the path-explorer
        # "coupon paid at period t" filter. Same engine, so it matches the
        # per-path coupon_payoffs total exactly: coupon_amounts.sum(1) == coupon_payoffs.
        "coupon_amounts":       coupon_amounts,

        # Legacy alias (app.py uses this key)
        "autocall_events":      autocall_period,

        # Scalars
        "expected_irr":             float(annualized_irr.mean()),
        "expected_total_return":    float(total_return.mean()),
        "expected_nominal_payout":  float(nominal_payoffs.mean()),
        "expected_coupon":          float(total_coupons.mean()),
        "prob_autocall":            float(any_autocalled.mean()),
        "prob_autocall_by_period":  [float((autocall_period == j).mean()) for j in range(1, n_obs + 1)],
        "prob_maturity":            float(maturity_mask.mean()),
        "prob_knock_in":            float(capital_loss[maturity_mask].mean()) if maturity_mask.any() else 0.0,
        "prob_knock_in_total":      float(ki_total.mean()),
        "prob_barrier_event":       float(be_total.mean()),   # incl. paths rescued by final condition
        "prob_rescued":             float((be_total & ~ki_total).mean()),
        "loss_given_knock_in":      lgki,
        # Average time (years) to early redemption, over the paths that actually
        # autocalled (None when none do). Uses the real observation times.
        "avg_time_to_autocall": (
            float(np.asarray(obs_times, dtype=float)[autocall_period[any_autocalled] - 1].mean())
            if bool(any_autocalled.any()) else None
        ),
    }


# ---------------------------------------------------------------------------
# Observation replay for partially-elapsed (live) notes
# ---------------------------------------------------------------------------

def replay_note(perf_obs: np.ndarray, terms: NoteTerms) -> dict:
    """
    Replay the first k observation dates of a single note life.

    This is the single source of truth for "what happened so far" on a live
    note (Current Performance tab). It applies the same semantics as
    price_note(): basket types per event, memory coupons, the (possibly
    step-down) autocall barrier schedule, autocall_start_period, and
    coupon_at_autocall_only. price_note() evaluates complete paths; this
    handles the partially-elapsed case — do NOT reimplement this logic in the
    app layer.

    Parameters
    ----------
    perf_obs : np.ndarray, shape (k, n_assets)
        Per-asset performance (price / initial fixing) at the first k
        observation dates that have already occurred, in order.

    terms : NoteTerms

    Returns
    -------
    dict with keys:
        rows            : list of per-period dicts with keys
                          period (1-indexed), coupon_met (bool),
                          coupon_amount (float), pending_after (int),
                          autocalled (bool), autocall_level (float)
        total_coupons   : float  total paid so far (incl. autocall premium for
                          coupon_at_autocall_only notes)
        pending_coupons : int    memory coupons accrued and unpaid
        autocall_period : int    0 = still alive, j = called at period j
    """
    perf_obs = np.atleast_2d(np.asarray(perf_obs, dtype=float))
    k = perf_obs.shape[0]
    if k > terms.n_obs:
        raise ValueError(f"perf_obs has {k} rows but the note has only {terms.n_obs} observations.")

    schedule = terms.autocall_barrier_schedule()
    rows: list[dict] = []
    pending = 0
    total   = 0.0
    called  = 0

    for j in range(k):
        slice_j   = perf_obs[j:j + 1, :]
        coupon_b  = float(_basket(slice_j, terms.coupon_basket)[0])
        ac_b      = float(_basket(slice_j, terms.autocall_basket)[0])
        # One Star overlay: any underlying >= one_star_level. Applies to the
        # periodic coupon / autocall checks ONLY when the respective opt-in flag
        # is set (see price_note); the final-redemption rescue is not evaluated
        # here (this replay covers observations that have already happened).
        one_star  = (terms.one_star_level is not None
                     and float(_basket(slice_j, "best_of")[0]) >= terms.one_star_level)
        one_star_ac  = one_star and terms.one_star_autocall
        one_star_cpn = one_star and terms.one_star_coupon
        eligible  = (j + 1) >= terms.autocall_start_period
        autocalled = bool(eligible and (ac_b >= schedule[j] or one_star_ac))

        if terms.coupon_at_autocall_only:
            # No periodic coupon — accrued premium paid as a lump only at call.
            coupon_met = False
            amount = terms.coupon_rate * (j + 1) if autocalled else 0.0
        else:
            coupon_met = (coupon_b >= terms.coupon_barrier) or one_star_cpn
            if coupon_met:
                amount  = terms.coupon_rate * (pending + 1) if terms.memory else terms.coupon_rate
                pending = 0
            else:
                amount = 0.0
                if terms.memory:
                    pending += 1

        total += amount
        rows.append({
            "period":         j + 1,
            "coupon_met":     coupon_met,
            "coupon_amount":  amount,
            "pending_after":  pending,
            "autocalled":     autocalled,
            "autocall_level": float(schedule[j]),
        })
        if autocalled:
            called = j + 1
            break

    return {
        "rows":            rows,
        "total_coupons":   total,
        "pending_coupons": pending,
        "autocall_period": called,
    }
