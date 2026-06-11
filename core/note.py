"""
core/note.py
------------
NoteTerms dataclass — full Phoenix/Autocallable structured note specification.
price_note()         — fully vectorized payoff engine (no Python loops).

Supports replication of:
  - HSBC XS3376563584: 24M monthly Phoenix Memory Worst-of, knock-in barrier,
                        separate coupon barrier, autocall starts at period 4
  - BBVA XS3378405743: 18M quarterly Phoenix Memory Worst-of, knock-in barrier,
                        best-of final redemption condition

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
from dataclasses import dataclass, field
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
          4. "protection" — final-basket rescue condition (e.g. BBVA best-of)
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

        # final redemption rescue (e.g. BBVA best-of condition)
        registry.register(BarrierCondition(
            name="protection",
            kind="protection",
            basket=terms.final_basket,
            level=terms.final_redemption_barrier,
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
    final_basket:           BasketType  = "worst_of"
    final_redemption_barrier: float     = 1.00   # 'rescue' level for the final basket (see price_note)
    call_steepness:         float | None = None   # None = hard trigger (default)
    # ── Classic / Growth Autocall extensions (default = no-op → plain Phoenix) ──
    autocall_step_down:      float       = 0.0    # per-period decrement of autocall barrier (0 = constant)
    autocall_floor:          float | None = None  # minimum autocall barrier when stepping down
    coupon_at_autocall_only: bool        = False  # True = no periodic coupon; accrued premium paid as a lump at autocall
    name:                   str         = "Phoenix Memory Note"
    issuer:                 str         = ""      # display-only: e.g. "BBVA", "HSBC"
    tickers:                dict | None  = None
    issue_date:             str  | None = None   # "YYYY-MM-DD" — enables Current Performance tab

    def __post_init__(self):
        if self.tickers is None:
            object.__setattr__(self, "tickers", {})
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

    def autocall_prob(self, basket_val: np.ndarray) -> np.ndarray:
        """
        Autocall trigger probability at the observation date.

        call_steepness = None (default) — HARD TRIGGER:
            Returns exactly 1.0 where basket >= autocall_barrier, else 0.0.
            This is how real autocallables work: the call is a deterministic
            function of the observed level, not a coin flip. Because the
            downstream check is `uniform_draw < prob` with draws in [0, 1),
            probabilities of exactly 0/1 make the trigger fully deterministic
            (independent of the RNG seed) in both price_note() and the
            historical backtest.

        call_steepness = float — SOFT TRIGGER (sigmoid):
            Smooth sigmoid centred at the barrier, useful for sensitivity /
            "fuzzy barrier" analysis. Note that moderate steepness values are
            NOT effectively hard: at steepness=100, a basket sitting 1% below
            the barrier still autocalls with probability ≈ 27%, and 1% above
            only ≈ 73%. Use steepness >= ~2000 if you want a near-hard sigmoid
            (P ≈ 1e-9 at ±1%).
        """
        if self.call_steepness is None:
            return (basket_val >= self.autocall_barrier).astype(float)
        x = np.clip(-self.call_steepness * (basket_val - self.autocall_barrier), -500.0, 500.0)
        return 1.0 / (1.0 + np.exp(x))

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
            "final_basket":           self.final_basket,
            "final_redemption_barrier": self.final_redemption_barrier,
            "call_steepness":         self.call_steepness,
            "autocall_step_down":     self.autocall_step_down,
            "autocall_floor":         self.autocall_floor,
            "coupon_at_autocall_only": self.coupon_at_autocall_only,
            "tickers":                self.tickers,
            "issue_date":             self.issue_date,
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
    # Autocall trigger
    # ------------------------------------------------------------------
    # Autocall mask: only eligible from autocall_start_period onward
    autocall_eligible = np.zeros(n_obs, dtype=bool)
    autocall_eligible[autocall_cond.start_period - 1:] = True  # 1-indexed → 0-indexed

    # Autocall probabilities per period, using a (possibly step-down) per-period
    # barrier schedule. For the common constant-barrier case this reduces exactly
    # to NoteTerms.autocall_prob(); the schedule generalises it to growth autocalls.
    autocall_levels = terms.autocall_barrier_schedule()          # (n_obs,)
    if terms.call_steepness is None:
        autocall_probs = (autocall_basket_vals >= autocall_levels[np.newaxis, :]).astype(float)
    else:
        x = np.clip(-terms.call_steepness * (autocall_basket_vals - autocall_levels[np.newaxis, :]),
                    -500.0, 500.0)
        autocall_probs = 1.0 / (1.0 + np.exp(x))
    autocall_probs[:, ~autocall_eligible] = 0.0

    autocall_triggered = call_draws < autocall_probs             # (n_paths, n_obs)

    # First autocall period per path (0 = none)
    any_autocalled   = autocall_triggered.any(axis=1)            # (n_paths,)
    first_call_idx   = np.argmax(autocall_triggered, axis=1)     # (n_paths,) 0-indexed

    autocall_period  = np.where(any_autocalled, first_call_idx + 1, 0).astype(int)

    # ------------------------------------------------------------------
    # Coupon calculation — dispatched via coupon_cond
    # ------------------------------------------------------------------
    coupon_barrier_met = coupon_basket_vals >= coupon_cond.level   # (n_paths, n_obs)

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

    # ------------------------------------------------------------------
    # Principal redemption — dispatched via knock_in_cond + protection_cond
    # ------------------------------------------------------------------
    # Autocalled paths: receive 100% principal back
    autocall_principal = np.ones(n_paths)

    # Maturity paths: check knock-in + final redemption condition
    # (final valuation = last observation step; equals N unless obs_steps override)
    final_step = obs_steps[-1]
    # final_basket uses the protection_cond basket (e.g. best_of for BBVA)
    final_basket_val = _basket(perf_paths[:, final_step, :], protection_cond.basket)  # (n_paths,)
    # knock-in always checks worst-of (per knock_in_cond.basket = "worst_of")
    worst_final      = _basket(perf_paths[:, final_step, :], knock_in_cond.basket)    # (n_paths,)

    # Barrier (knock-in) event: knock-in basket below the KI level at final valuation
    barrier_event = worst_final < knock_in_cond.level   # (n_paths,)

    # Final redemption condition ('rescue'): if the final basket value is at or
    # above final_redemption_barrier, the note redeems at par EVEN IF the
    # knock-in barrier was breached.
    #
    # This implements term sheets like BBVA XS3378405743 (Final Payout xi —
    # Barrier and Knock-in):
    #   (A) Best Value >= 100%                     -> 100%
    #   (B) Best Value < 100% and no Knock-in      -> 100%
    #   (C) Best Value < 100% AND Knock-in         -> physical delivery of worst
    # i.e. capital loss requires BOTH worst < KI AND best < 100%. With
    # final_basket="best_of" and final_redemption_barrier=1.0 the logic below
    # reproduces (A)/(B)/(C) exactly.
    #
    # For plain worst-of notes (e.g. HSBC XS3376563584, final_basket="worst_of")
    # the rescue condition (worst >= 100%) can never coincide with a barrier
    # event (worst < 55%), so this reduces to the standard payoff unchanged.
    rescued      = final_basket_val >= protection_cond.level
    capital_loss = barrier_event & ~rescued

    # Capital loss: cash-equivalent physical delivery = worst-of final performance.
    # Otherwise: principal_protection (100%) regardless of basket level (no upside
    # participation in a Phoenix).
    maturity_principal = np.where(
        capital_loss,
        worst_final,                       # cash equiv. of physical delivery
        terms.principal_protection,        # par redemption
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
    annualized_irr = total_return / t_held_arr

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------
    maturity_mask = ~any_autocalled
    # 'Knock-in' in all reported stats means CAPITAL LOSS: barrier breached AND
    # final redemption condition not met (the 'rescue'). For worst-of final
    # baskets the two are identical; for best-of (BBVA) they differ.
    ki_total      = capital_loss & maturity_mask
    be_total      = barrier_event & maturity_mask   # barrier breached (incl. rescued paths)

    return {
        # Per-path arrays (for Streamlit plots)
        "nominal_payoffs":      nominal_payoffs,
        "coupon_payoffs":       total_coupons,
        "principal_payoffs":    principal,
        "autocall_period":      autocall_period,
        "knock_in_triggered":   ki_total,
        "annualized_returns":   annualized_irr,

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

        # Legacy alias
        "prob_floor":               float(ki_total.mean()),
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
        eligible  = (j + 1) >= terms.autocall_start_period
        autocalled = bool(eligible and ac_b >= schedule[j])

        if terms.coupon_at_autocall_only:
            # No periodic coupon — accrued premium paid as a lump only at call.
            coupon_met = False
            amount = terms.coupon_rate * (j + 1) if autocalled else 0.0
        else:
            coupon_met = coupon_b >= terms.coupon_barrier
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
