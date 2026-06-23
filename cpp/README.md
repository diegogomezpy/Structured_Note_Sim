# C++ engine (Phase 1) — optional fast path for the Heston simulator

A pybind11 module (`heston_cpp`) that runs the same multi-asset Heston model as
[`core/simulator.py`](../core/simulator.py), parallelised across cores with
OpenMP. It is an **optional** alternative to the default numpy engine — the app
runs with **no build step** and `engine="numpy"` never imports this.

It is a *validated reference*, not a drop-in: a different RNG stream means it is
**not** bit-identical to numpy, so it is checked by **convergence of statistics**
(see [`scripts/compare_engines.py`](../scripts/compare_engines.py)), keeping the
numpy engine as the source of truth. It keeps **full daily paths** (this is a
visualization tool — the fans and path explorer need them).

## Build

Needs a C++17 compiler. OpenMP is optional (without it the kernel still runs,
serially and correctly).

```bash
pip install ./cpp          # builds heston_cpp via scikit-build-core + CMake
```

- **macOS (AppleClang):** OpenMP needs libomp — `brew install libomp` and rebuild.
  Without it the module still imports and runs (single-threaded).
- **Linux:** GCC/Clang ship OpenMP; no extra step.
- **Deploy:** don't compile on the server — build portable wheels in CI
  (`.github/workflows/wheels.yml`, cibuildwheel) and `pip install` the wheel.

## Validate

```bash
python scripts/compare_engines.py 25000
```

Confirms the terminal moments, cross-asset correlation, and a priced note's
payoff stats match numpy to Monte-Carlo error, and reports the speedup.

## Using it

It is wired into the simulator behind a flag (the numpy engine stays the default
and the reference for posterity):

```python
sim.run()                 # numpy reference (default) — what the app uses
sim.run(engine="cpp")     # compiled engine; raises ImportError if not built
```

Both return the identical results dict (`S_paths`, `V_paths`, `realized_corr`, …),
so everything downstream (`price_note`, charts, backtest) is unchanged — the
boundary is `arrays in → arrays out`. The app calls `run()` with no argument, so
it is unaffected unless you opt in. To offer it as a user choice, pass the flag
through from a Streamlit toggle to the cached `sim.run(...)` call.

## Status

**Validated and SIMD-optimized.** Matches the numpy engine within Monte-Carlo
error (terminal moments, correlation, priced-note stats all Δ < 0.005) and runs
**~2.5× faster SINGLE-THREADED** on this host (an Apple-Silicon Mac *without*
OpenMP, so it is the SIMD win alone — the multicore factor stacks on top wherever
libomp is present: Linux CI wheels, or `brew install libomp` locally). Two things
got it there:

- **Block-SIMD + vectorized `sqrt`/`exp`** — the per-step update runs across a
  contiguous block of paths so the vector libm (`-fveclib`) does the transcendentals
  on whole SIMD registers. (1.26× scalar → 2.24×.)
- **xoshiro256++ + branch-free Box–Muller RNG** — replaced `std::mt19937_64` +
  `std::normal_distribution` (whose rejection-based polar method can't vectorise),
  measured **~19% faster** in a fair interleaved A/B. Even more on wider SIMD
  (this host is 2-wide NEON; AVX2/AVX-512 gain more from the vectorised sin/cos).

## Optimization roadmap

Done: block-SIMD restructure, vectorized `sqrt`/`exp`/`sin`/`cos`/`log`, and the
SIMD RNG. OpenMP across path-blocks is wired (`#pragma omp parallel for`) and
multiplies by core count wherever the runtime is linked — the **biggest remaining
win** (≈ N_cores). Other levers:

1. **Memory at scale.** For ≫100k paths, store only the observation columns on the
   C++ side (the payoff needs ~K columns, not all N) — the trick the backtest uses
   — so 1M paths fits in RAM. (This engine keeps full paths because the app's fans
   and explorer need them; a pricing-only mode would drop them.)
2. **Tune `BLK`** (currently 64) per target ISA; try one-stream-per-SIMD-lane
   xoshiro to vectorise the uniform fill too (now scalar).

Phase 2 (GPU / CUDA) is the higher ceiling (~50–300×) but needs GPU hardware; see
`docs/architecture_review.md`.
