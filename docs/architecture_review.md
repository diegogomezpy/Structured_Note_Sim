# Architecture Review — toward a C++ simulator/backtester

_Context: evaluating whether the Monte-Carlo simulator and backtester can be
ported to C++ for speed, and whether the Python boundaries are clean enough to
make that a drop-in replacement rather than a rewrite._

## Verdict

The separation is clean and the C++ boundary is already well drawn. The app
**never recomputes payoffs** — it builds a `NoteTerms` from the UI and calls the
single `price_note` engine. The numeric core takes numpy arrays in and returns
numpy arrays out, so a compiled module can slot in behind the same contract.

## What's worth porting (and what isn't)

| Component | Hot loop? | C++ value |
|---|---|---|
| `HestonMultiSimulator.run` (`core/simulator.py`) | **Yes** — sequential `for t in range(N)` time loop | **Highest** |
| `price_note` (`core/note.py`) | No — fully vectorized (memory coupon via cumsum trick) | Low |
| `run_backtest` (`core/backtest.py`) | No — fancy-indexes the perf array, one `price_note` call | Low |
| `replay_note` (`core/note.py`) | Loops over **one** path's observations | None (single-path explainer) |

**The simulator's time loop is the one true bottleneck.** It integrates a Heston
SDE: `V[t+1]` depends on `V[t]`, `S[t+1]` on `S[t]` and `V[t]`. That recursion is
**irreducibly sequential** — it cannot be vectorized over time in numpy. The
inner *per-asset* loop **was** vectorizable and has been folded into array ops
(bit-identical results, ~1.1× at 4 assets, more with more), but that only trims
Python overhead. The remaining per-step cost is the RNG draw, the Cholesky
matmul, and `exp` — all already vectorized kernels. To go materially faster you
need to remove the per-step interpreter overhead across all `N` steps and use
faster RNG/`exp`, which is precisely what a compiled inner loop buys.

## Recommended C++ boundary

Keep the exact numpy contract so the port is a drop-in:

- `HestonMultiSimulator.run() -> {S_paths, V_paths, ...}` (list of `(n_total, N+1)` arrays)
- `price_note(perf_paths, terms) -> dict` of per-path arrays

A pybind11 (or Cython) module can replace `run()` first — the biggest win — and
later `price_note` if profiling justifies it. Because `price_note` is the
**single engine** shared by Monte-Carlo and backtest, porting it once covers
both paths with no risk of the two drifting apart.

Implementation note: the simulator already stores paths **time-first**
(`(N+1, n_total, n)`) during the loop for cache locality, then transposes to the
public `(n_total, N+1)` layout once at the end. A C++ inner loop should keep the
same time-first write pattern.

## Boundary leaks to clean up (before/with the port)

`CLAUDE.md` states `core/` does no I/O or presentation. Two violations exist:

1. **`core/calibrator.py` imports `yfinance`** to self-fetch prices. This bypasses
   `data/loader.py` ("the single source of truth for price data"). The Streamlit
   app doesn't hit this path (it passes loaded prices in), but if you're drawing a
   hard C++/Python line, this data fetch belongs in `data/`.
2. **`core/simulator.py` imports `matplotlib`** inside `.plot()` — a debug/notebook
   convenience the app never calls. Lazy-imported, so harmless, but technically
   presentation logic in `core/`.

Neither blocks the rewrite. The calibrator's data fetch is the one worth moving.

## App-tier helpers that are pure (could move to core if useful in C++)

- `app/app.py::_path_filter_matches` — selects paths by outcome/return/coupon over
  `price_note`'s output arrays. Pure and portable; currently a UI concern, but if
  the path-query ever needs to run server-side or in the compiled layer, it's a
  clean candidate to lift into `core/`.
