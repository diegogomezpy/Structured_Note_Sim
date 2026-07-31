// heston_kernel.cpp
// ----------------------------------------------------------------------------
// Optional C++ engine for the multi-asset Heston simulator (pybind11 module
// `heston_cpp`). The numpy engine in core/simulator.py stays the reference;
// this is validated against it by convergence of statistics (see
// scripts/compare_engines.py), not bit-equality (different RNG stream).
//
// Boundary: same arrays-in / arrays-out contract as HestonMultiSimulator.run().
// simulate(...) returns (S, V) as (n_total, N+1, n); the Python wrapper reshapes
// them into the list-of-(n_total, N+1) form the rest of the app expects.
//
// PERFORMANCE STRUCTURE — this is the key to beating numpy. A scalar one-path-at-
// a-time loop loses to numpy's vectorized SIMD libm (that was the lesson from the
// numba experiment). Instead we process a contiguous BLOCK of paths per step, in
// PATH-CONTIGUOUS layout (asset-major, paths inner), so the per-step variance and
// price updates auto-vectorise across paths: `sqrt`/`exp` run on whole SIMD
// registers (a vector libm via -fveclib: Accelerate vvexp on macOS, libmvec on
// Linux). std::thread then parallelises ACROSS path-blocks for the multicore
// factor (one thread per contiguous chunk of blocks).
//
//   SIMD over paths (within a step)  ×  std::thread over blocks (across cores)
//
// Why std::thread and not OpenMP: the block decomposition is embarrassingly
// parallel with a static partition, so OpenMP buys nothing over std::thread here,
// and dropping it removes the libomp/libgomp RUNTIME dependency on every platform
// (macOS ships no libomp; this keeps the wheels self-contained). The inner-loop
// SIMD is unaffected — `#pragma omp simd` is enabled by -fopenmp-simd at COMPILE
// time and needs no runtime. Per-block seeding (seed+blk) makes the output
// independent of the thread count: an N-thread run is bit-identical to serial.
//
// Build flags that matter: -O3 -march=native -fopenmp-simd -fveclib=Accelerate.
// See cpp/CMakeLists.txt.
// ----------------------------------------------------------------------------

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <cmath>
#include <random>
#include <vector>
#include <cstdint>
#include <cstdlib>
#include <algorithm>
#include <thread>
#include <utility>
#include <fstream>
#include <string>
#ifdef __linux__
// CPU_COUNT is a GNU extension; g++ defines _GNU_SOURCE for libstdc++ anyway,
// but clang-on-Linux does not, and a missing macro here is a build break rather
// than a warning.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include <sched.h>          // sched_getaffinity / CPU_COUNT — see cpu_budget()
#endif

namespace py = pybind11;

// Paths processed together per step. Multiple of the widest SIMD register (AVX2
// = 4 doubles, AVX-512 = 8); 64 amortises loop overhead while staying in L1.
static constexpr int BLK = 64;

// ── RNG ─────────────────────────────────────────────────────────────────────
// xoshiro256++ — a very fast, high-quality PRNG (passes BigCrush). One stream per
// path-block, seeded via splitmix64. We draw a contiguous buffer of uniforms,
// then convert to normals with a branch-free Box–Muller that VECTORISES (the
// log/sqrt/sin/cos run on whole SIMD registers via the vector libm). This
// replaced std::normal_distribution, whose rejection-based polar method has data-
// dependent branches and cannot vectorise — the RNG was the bottleneck once exp
// was vectorised.
static inline std::uint64_t splitmix64(std::uint64_t& s) {
    std::uint64_t z = (s += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}
static inline std::uint64_t rotl64(std::uint64_t x, int k) {
    return (x << k) | (x >> (64 - k));
}
struct Xoshiro256pp {
    std::uint64_t s[4];
    using result_type = std::uint64_t;            // UniformRandomBitGenerator
    static constexpr std::uint64_t min() { return 0; }
    static constexpr std::uint64_t max() { return ~std::uint64_t(0); }
    void seed(std::uint64_t sd) { std::uint64_t z = sd; for (int i = 0; i < 4; ++i) s[i] = splitmix64(z); }
    std::uint64_t operator()() {
        const std::uint64_t r = rotl64(s[0] + s[3], 23) + s[0];
        const std::uint64_t t = s[1] << 17;
        s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3]; s[2] ^= t; s[3] = rotl64(s[3], 45);
        return r;
    }
    // Uniform in (0,1) — 53-bit mantissa, offset by 0.5 ULP so it is never 0/1
    // (the Box–Muller log needs a strictly positive argument).
    double uniform() { return ((operator()() >> 11) + 0.5) * (1.0 / 9007199254740992.0); }
};

// How many CPUs this process may actually use, as opposed to how many the
// machine has. In a container these are different numbers and only the first one
// is useful: `hardware_concurrency()` reports the HOST's logical cores, so a
// 2-vCPU Cloud Run instance on a 64-core host span 64 worker threads to share
// two of them — pure context-switch thrash, slower than running single-threaded,
// and nothing in the deploy set HESTON_NUM_THREADS to prevent it.
//
// Two sources, both cheap and both read once:
//   * the CPU affinity mask (a cpuset limit, and the honest count when there is
//     no quota), and
//   * the cgroup CPU quota — v2 `cpu.max` ("<quota> <period>" or "max ..."),
//     v1 `cpu.cfs_quota_us` / `cpu.cfs_period_us` (quota -1 = unlimited).
// Non-Linux hosts have neither and fall through to hardware_concurrency.
static int cpu_budget() {
    int n = 0;
#ifdef __linux__
    cpu_set_t set;
    if (sched_getaffinity(0, sizeof(set), &set) == 0) n = CPU_COUNT(&set);

    auto quota_from = [](const char* path, const char* period_path) -> int {
        std::ifstream f(path);
        if (!f) return 0;
        double quota = 0, period = 0;
        if (period_path) {                       // cgroup v1: two files
            std::string q; f >> q;
            if (q == "max" || q == "-1") return 0;
            quota = std::atof(q.c_str());
            std::ifstream p(period_path);
            if (!p) return 0;
            p >> period;
        } else {                                 // cgroup v2: "<quota> <period>"
            std::string q; f >> q;
            if (q == "max") return 0;
            quota = std::atof(q.c_str());
            f >> period;
        }
        if (quota <= 0 || period <= 0) return 0;
        // Round up: 1.5 vCPU should use 2 threads, not 1.
        const int c = static_cast<int>(std::ceil(quota / period));
        return c > 0 ? c : 1;
    };
    int q = quota_from("/sys/fs/cgroup/cpu.max", nullptr);
    if (q == 0) q = quota_from("/sys/fs/cgroup/cpu/cpu.cfs_quota_us",
                               "/sys/fs/cgroup/cpu/cpu.cfs_period_us");
    if (q > 0) n = (n > 0) ? std::min(n, q) : q;
#endif
    if (n <= 0) {
        const unsigned h = std::thread::hardware_concurrency();
        n = h ? static_cast<int>(h) : 1;
    }
    return n;
}

// Worker thread count: explicit request wins; else HESTON_NUM_THREADS /
// OMP_NUM_THREADS env vars; else the process's real CPU budget (see cpu_budget).
// Capped to n_blocks by caller.
static int resolve_threads(int requested) {
    if (requested > 0) return requested;
    for (const char* var : {"HESTON_NUM_THREADS", "OMP_NUM_THREADS"}) {
        if (const char* e = std::getenv(var)) {
            const int t = std::atoi(e);
            if (t > 0) return t;
        }
    }
    // Computed once — the limit cannot change under a running process, and the
    // simulate() entry point is called per request.
    static const int budget = cpu_budget();
    return budget;
}

py::tuple simulate(
    py::array_t<double, py::array::c_style | py::array::forcecast> S0,
    py::array_t<double, py::array::c_style | py::array::forcecast> V0,
    py::array_t<double, py::array::c_style | py::array::forcecast> kappa,
    py::array_t<double, py::array::c_style | py::array::forcecast> theta,
    py::array_t<double, py::array::c_style | py::array::forcecast> xi,
    py::array_t<double, py::array::c_style | py::array::forcecast> mu,
    py::array_t<double, py::array::c_style | py::array::forcecast> L,    // (2n,2n)
    py::array_t<double, py::array::c_style | py::array::forcecast> dt,   // (N,)
    py::array_t<double, py::array::c_style | py::array::forcecast> sdt,  // (N,)
    py::array_t<double, py::array::c_style | py::array::forcecast> div,  // (n,N) or zeros
    double t_dof,                                                        // 0 => Gaussian
    std::uint64_t seed,
    int n_base,
    int nthreads_req) {                                                 // 0 => auto

    const int n   = static_cast<int>(S0.size());
    const int N   = static_cast<int>(dt.size());
    const int two = 2 * n;
    const int n_total = 2 * n_base;

    const double* pS0 = S0.data();   const double* pV0 = V0.data();
    const double* pk  = kappa.data(); const double* pth = theta.data();
    const double* pxi = xi.data();    const double* pmu = mu.data();
    const double* pL  = L.data();     const double* pdt = dt.data();
    const double* psdt = sdt.data();  const double* pdiv = div.data();

    std::vector<double> xi2(n);
    for (int a = 0; a < n; ++a) xi2[a] = pxi[a] * pxi[a];
    const double t_scale = (t_dof > 0.0) ? std::sqrt((t_dof - 2.0) / t_dof) : 0.0;

    auto S_out = py::array_t<double>({n_total, N + 1, n});
    auto V_out = py::array_t<double>({n_total, N + 1, n});
    double* oS = S_out.mutable_data();
    double* oV = V_out.mutable_data();
    const std::size_t row = static_cast<std::size_t>(N + 1) * n;  // per-path stride

    {
    py::gil_scoped_release nogil;   // re-acquired before make_tuple below
    const int n_blocks = (n_base + BLK - 1) / BLK;

    // Each worker owns a CONTIGUOUS range of path-blocks, its own scratch buffers
    // and its own RNG. Blocks are seeded independently (seed+blk) and chisq is
    // reset per block, so the output is independent of how blocks are split across
    // threads — an N-thread run is bit-identical to serial.
    auto worker = [&](int blk_begin, int blk_end) {
        // Per-thread, path-contiguous buffers ([k*BLK+p] / [a*BLK+p]).
        std::vector<double> z(static_cast<std::size_t>(two) * BLK);
        std::vector<double> w(static_cast<std::size_t>(two) * BLK);
        std::vector<double> Sb(static_cast<std::size_t>(n) * BLK), Vb(static_cast<std::size_t>(n) * BLK);
        std::vector<double> Sa(static_cast<std::size_t>(n) * BLK), Va(static_cast<std::size_t>(n) * BLK);
        std::vector<double> u(static_cast<std::size_t>(two) * BLK);
        std::vector<double> chi(BLK);
        Xoshiro256pp xo;
        std::chi_squared_distribution<double> chisq(t_dof > 0.0 ? t_dof : 1.0);

        for (int blk = blk_begin; blk < blk_end; ++blk) {
            const int b0 = blk * BLK;
            const int bs = std::min(BLK, n_base - b0);   // paths in this block
            xo.seed(seed + static_cast<std::uint64_t>(blk));    // per-block stream
            chisq.reset();                                      // drop any cached state

            for (int a = 0; a < n; ++a)
                for (int p = 0; p < bs; ++p) {
                    Sb[a * BLK + p] = Sa[a * BLK + p] = pS0[a];
                    Vb[a * BLK + p] = Va[a * BLK + p] = pV0[a];
                }
            for (int p = 0; p < bs; ++p) {
                const std::size_t base = static_cast<std::size_t>(b0 + p) * row;
                const std::size_t anti = static_cast<std::size_t>(b0 + p + n_base) * row;
                for (int a = 0; a < n; ++a) {
                    oS[base + a] = pS0[a]; oV[base + a] = pV0[a];
                    oS[anti + a] = pS0[a]; oV[anti + a] = pV0[a];
                }
            }

            for (int t = 0; t < N; ++t) {
                const double dtt = pdt[t], sdtt = psdt[t];

                // Draw N(0,1) into path-contiguous z[k*BLK + p]: fast xoshiro
                // uniforms + a branch-free, SIMD Box–Muller (split-half so each
                // R = sqrt(-2 ln u1) and the sin/cos run on whole registers). The
                // full BLK width is filled; tail slots beyond `bs` go unused.
                const int M = two * BLK;
                for (int i = 0; i < M; ++i) u[i] = xo.uniform();
                const int half = M / 2;
                #pragma omp simd
                for (int j = 0; j < half; ++j) {
                    const double R  = std::sqrt(-2.0 * std::log(u[j]));
                    const double th = 6.283185307179586476 * u[j + half];
                    z[j]        = R * std::cos(th);
                    z[j + half] = R * std::sin(th);
                }
                if (t_dof > 0.0) {                         // Student-t copula
                    for (int p = 0; p < bs; ++p)
                        chi[p] = t_scale / std::sqrt(chisq(xo) / t_dof);
                    for (int k = 0; k < two; ++k) {
                        double* __restrict zk = &z[k * BLK];
                        #pragma omp simd
                        for (int p = 0; p < bs; ++p) zk[p] *= chi[p];
                    }
                }

                // Correlate: w[k] = sum_c L[k][c] z[c]  — SIMD over paths.
                for (int k = 0; k < two; ++k) {
                    double* __restrict wk = &w[k * BLK];
                    for (int p = 0; p < bs; ++p) wk[p] = 0.0;
                    const double* Lk = pL + static_cast<std::size_t>(k) * two;
                    for (int c = 0; c < two; ++c) {
                        const double Lkc = Lk[c];
                        const double* __restrict zc = &z[c * BLK];
                        #pragma omp simd
                        for (int p = 0; p < bs; ++p) wk[p] += Lkc * zc[p];
                    }
                }

                // Heston step, SIMD across the block's paths (this is the hot
                // loop the vector libm accelerates: sqrt + exp on whole registers).
                for (int a = 0; a < n; ++a) {
                    const double ka = pk[a], tha = pth[a], xa = pxi[a],
                                 x2 = xi2[a], ma = pmu[a];
                    const double drop = 1.0 - pdiv[static_cast<std::size_t>(a) * N + t];
                    const double* __restrict wS = &w[a * BLK];
                    const double* __restrict wV = &w[(n + a) * BLK];
                    double* __restrict Sbp = &Sb[a * BLK]; double* __restrict Vbp = &Vb[a * BLK];
                    double* __restrict Sap = &Sa[a * BLK]; double* __restrict Vap = &Va[a * BLK];
                    #pragma omp simd
                    for (int p = 0; p < bs; ++p) {        // base path (+dW)
                        const double dWv = wV[p] * sdtt, dWs = wS[p] * sdtt;
                        const double vp = Vbp[p] > 0.0 ? Vbp[p] : 0.0, sq = std::sqrt(vp);
                        const double vn = Vbp[p] + ka * (tha - Vbp[p]) * dtt
                                          + xa * sq * dWv + 0.25 * x2 * (dWv * dWv - dtt);
                        Vbp[p] = vn > 0.0 ? vn : 0.0;
                        Sbp[p] = Sbp[p] * std::exp(ma * dtt - 0.5 * vp * dtt + sq * dWs) * drop;
                    }
                    #pragma omp simd
                    for (int p = 0; p < bs; ++p) {        // antithetic twin (-dW)
                        const double dWv = wV[p] * sdtt, dWs = wS[p] * sdtt;
                        const double vp = Vap[p] > 0.0 ? Vap[p] : 0.0, sq = std::sqrt(vp);
                        const double vn = Vap[p] + ka * (tha - Vap[p]) * dtt
                                          - xa * sq * dWv + 0.25 * x2 * (dWv * dWv - dtt);
                        Vap[p] = vn > 0.0 ? vn : 0.0;
                        Sap[p] = Sap[p] * std::exp(ma * dtt - 0.5 * vp * dtt - sq * dWs) * drop;
                    }
                }

                // Scatter the step's columns into the (n_total, N+1, n) output.
                for (int p = 0; p < bs; ++p) {
                    const std::size_t off  = static_cast<std::size_t>(b0 + p) * row
                                             + static_cast<std::size_t>(t + 1) * n;
                    const std::size_t offA = static_cast<std::size_t>(b0 + p + n_base) * row
                                             + static_cast<std::size_t>(t + 1) * n;
                    for (int a = 0; a < n; ++a) {
                        oS[off  + a] = Sb[a * BLK + p]; oV[off  + a] = Vb[a * BLK + p];
                        oS[offA + a] = Sa[a * BLK + p]; oV[offA + a] = Va[a * BLK + p];
                    }
                }
            }
        }
    };   // worker

    // Static, contiguous partition of blocks across threads (each block ≈ equal
    // work). The calling thread runs chunk 0; the remaining chunks get one
    // std::thread each. A single chunk (nthr==1 or n_blocks==1) never spawns.
    int nthr = resolve_threads(nthreads_req);
    if (nthr > n_blocks) nthr = n_blocks;
    if (nthr < 1) nthr = 1;
    const int per = (n_blocks + nthr - 1) / nthr;
    std::vector<std::pair<int, int>> ranges;
    for (int b0 = 0; b0 < n_blocks; b0 += per)
        ranges.emplace_back(b0, std::min(n_blocks, b0 + per));
    std::vector<std::thread> pool;
    pool.reserve(ranges.size() - 1);
    for (std::size_t i = 1; i < ranges.size(); ++i)
        pool.emplace_back(worker, ranges[i].first, ranges[i].second);
    worker(ranges[0].first, ranges[0].second);          // chunk 0 on this thread
    for (auto& th : pool) th.join();
    }  // GIL re-acquired here
    return py::make_tuple(S_out, V_out);
}

PYBIND11_MODULE(heston_cpp, m) {
    m.doc() = "C++ Heston engine (block-SIMD + std::thread; validated vs numpy).";
    m.def("simulate", &simulate,
          py::arg("S0"), py::arg("V0"), py::arg("kappa"), py::arg("theta"),
          py::arg("xi"), py::arg("mu"), py::arg("L"), py::arg("dt"),
          py::arg("sdt"), py::arg("div"), py::arg("t_dof"),
          py::arg("seed"), py::arg("n_base"), py::arg("nthreads") = 0);
}
