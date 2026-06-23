# C++ engine (Phase 1) — optional fast path for the Heston simulator

A pybind11 module (`heston_cpp`) that runs the same multi-asset Heston model as
[`core/simulator.py`](../core/simulator.py), parallelised across cores with
`std::thread` (SIMD within a step × threads across path-blocks). It is an
**optional** alternative to the default numpy engine — the app runs with **no
build step** and `engine="numpy"` never imports this.

It is a *validated reference*, not a drop-in: a different RNG stream means it is
**not** bit-identical to numpy, so it is checked by **convergence of statistics**
(see [`scripts/compare_engines.py`](../scripts/compare_engines.py)), keeping the
numpy engine as the source of truth. It keeps **full daily paths** (this is a
visualization tool — the fans and path explorer need them).

## Build

Needs only a C++17 compiler — **no libomp/OpenMP runtime**. The multicore fan-out
is `std::thread`; the inner-loop SIMD is `-fopenmp-simd` (compile-time only, no
runtime).

```bash
pip install ./cpp          # builds heston_cpp via scikit-build-core + CMake
```

- **macOS (AppleClang):** builds and runs **multi-threaded out of the box** — no
  `brew install libomp` needed.
- **Linux:** GCC/Clang, no extra step.
- **Deploy:** don't compile on the server — build portable wheels in CI
  (`.github/workflows/wheels.yml`, cibuildwheel) and `pip install` the wheel.
  With no OpenMP runtime the wheels are self-contained (nothing to bundle/repair).

### Threads

Auto-detects all logical cores. Override with the `nthreads=` argument (0 = auto)
or the `HESTON_NUM_THREADS` / `OMP_NUM_THREADS` env vars. The output is **identical
for any thread count** (per-block RNG seeding), so this is purely a speed knob.

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

**Validated, SIMD-optimized, and multi-threaded.** Matches the numpy engine
within Monte-Carlo error (terminal moments, correlation, priced-note stats all
Δ < 0.011) and on this host (8-core Apple Silicon: 4 performance + 4 efficiency)
runs **3.6–3.7× faster** than numpy at 60k paths:

| engine            | time   | vs numpy | vs cpp-serial |
|-------------------|--------|----------|---------------|
| numpy (reference) | 4.91 s | 1.00×    | —             |
| cpp, 1 thread     | 2.50 s | 1.96×    | 1.00×         |
| cpp, 4 threads    | 1.42 s | 3.45×    | 1.76×         |
| cpp, 6 threads    | 1.33 s | 3.68×    | 1.88×         |

(min of 6 interleaved runs, N=378, 3 assets.) Three things got it there:

- **Block-SIMD + vectorized `sqrt`/`exp`** — the per-step update runs across a
  contiguous block of paths so the vector libm (`-fveclib`) does the transcendentals
  on whole SIMD registers. (1.26× scalar → 2.24×.)
- **xoshiro256++ + branch-free Box–Muller RNG** — replaced `std::mt19937_64` +
  `std::normal_distribution` (whose rejection-based polar method can't vectorise),
  measured **~19% faster** in a fair interleaved A/B.
- **std::thread across path-blocks** — ~1.9× on top of the SIMD serial kernel
  here. Scaling is sublinear because (a) the cores are heterogeneous (4 fast P +
  4 slow E, so threads 5–8 add little) and (b) materializing full daily paths
  (~1 GB of writes at 60k×378×3) makes it partly memory-bound. On homogeneous
  Linux CI boxes with more bandwidth it scales further.

The block decomposition is embarrassingly parallel with a static partition, so
`std::thread` is as good as OpenMP here and drops the libomp runtime dependency on
every platform. Output is **bit-identical for any thread count** (verified: 1 vs
3 vs 8 threads, Gaussian and Student-t, maxΔ = 0).

## Optimization roadmap

Done: block-SIMD restructure, vectorized `sqrt`/`exp`/`sin`/`cos`/`log`, the SIMD
RNG, and **`std::thread` multicore** across path-blocks. Remaining levers:

1. **Memory at scale.** For ≫100k paths, store only the observation columns on the
   C++ side (the payoff needs ~K columns, not all N) — the trick the backtest uses
   — so 1M paths fits in RAM. This also lifts the bandwidth ceiling that currently
   caps multicore scaling. (This engine keeps full paths because the app's fans and
   explorer need them; a pricing-only mode would drop them.)
2. **Tune `BLK`** (currently 64) per target ISA; try one-stream-per-SIMD-lane
   xoshiro to vectorise the uniform fill too (now scalar).
3. **Pin to performance cores** on heterogeneous CPUs — here, threads past the 4
   P-cores barely help. The `nthreads`/env knob already lets you cap the count; a
   thread-affinity hint could squeeze a little more.

Phase 2 (GPU / CUDA) is the higher ceiling (~50–300×) but needs GPU hardware; see
`docs/architecture_review.md`.
