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

**Validated.** It matches the numpy engine within Monte-Carlo error (terminal
moments, correlation, and priced-note stats all Δ < 0.002 at 16k paths) and is
already **~1.26× faster even SERIAL** — measured on a host with no OpenMP, so the
`omp` pragmas were ignored and it ran single-threaded scalar against single-
threaded numpy. With OpenMP across cores and the SIMD work below, that grows
substantially.

## Optimization roadmap

The inner per-asset update is still **scalar**. Serial, that already edges out
numpy (no interpreter, `-O3`); with OpenMP it gets the multicore factor on top.
The decisive win — beating numpy's vectorized SIMD `exp` — is the next iteration:

1. **SIMD over a block of paths.** Restructure the inner loop to update a
   contiguous *block* of paths per step (paths in the inner dimension) so `-O3
   -march=native` auto-vectorises it (4–8 paths per AVX instruction). This is the
   single biggest change and the reason a naive scalar kernel (CPU or numba) does
   *not* beat numpy at scale.
2. **Vectorized `exp`.** Swap scalar `std::exp` for a vector-math library
   (SLEEF, libmvec, or Eigen `array().exp()`) over the path block.
3. **Faster RNG.** Replace `std::mt19937_64` + `std::normal_distribution` with a
   SIMD PCG or Intel MKL VSL `vdRngGaussian` (itself vectorized).
4. **Memory at scale.** For ≫100k paths, store only the observation columns
   on the C++ side (the payoff needs ~K columns, not all N) — the same trick the
   backtest uses — so 1M paths fits in RAM.

Expected after (1)–(3): ~5–20× over numpy. Phase 2 (GPU / CUDA) is the higher
ceiling (~50–300×) but needs GPU hardware; see `docs/architecture_review.md`.
