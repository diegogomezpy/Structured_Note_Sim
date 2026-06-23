// heston_kernel.cpp
// ----------------------------------------------------------------------------
// Phase-1 C++ engine for the multi-asset Heston simulator (pybind11 module
// `heston_cpp`). This is the OPTIONAL fast path; the numpy engine in
// core/simulator.py remains the reference. It is validated against numpy by
// convergence of statistics (see scripts/compare_engines.py), not bit-equality.
//
// Boundary: same arrays-in / arrays-out contract as HestonMultiSimulator.run().
// simulate(...) returns (S, V) as (n_total, N+1, n) arrays; the Python wrapper
// reshapes them into the list-of-(n_total, N+1) form the rest of the app expects.
//
// Status: CORRECT + parallel (OpenMP across base paths), but the inner per-asset
// update is still SCALAR. That alone (no interpreter, -O3, multicore) should beat
// single-threaded numpy modestly. The decisive win — beating numpy's vectorized
// SIMD `exp` — needs the inner loop restructured over a BLOCK of contiguous paths
// so it auto-vectorises, plus a vectorised exp (SLEEF/libmvec) and a faster RNG
// (PCG / MKL VSL). Those are the next iteration; see cpp/README.md. The point of
// this scaffold is the build + binding + correctness foundation to optimise from.
// ----------------------------------------------------------------------------

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <cmath>
#include <random>
#include <vector>
#include <cstdint>

namespace py = pybind11;

// One Heston step for a single (path, asset). Mirrors core/simulator.py's
// _heston_step exactly: Milstein variance + full truncation, log-Euler price.
// The Milstein dW^2 term and the dividend factor are sign-independent, so the
// antithetic twin reuses them and only flips the linear dW terms.
static inline void heston_step(double& S, double& V,
                               double dWs, double dWv, double dt,
                               double kappa, double theta, double xi,
                               double xi2, double mu, double drop) {
    double vpos = V > 0.0 ? V : 0.0;
    double sq   = std::sqrt(vpos);
    double vn   = V + kappa * (theta - V) * dt + xi * sq * dWv
                  + 0.5 * xi2 * (dWv * dWv - dt);
    V = vn > 0.0 ? vn : 0.0;
    S = S * std::exp(mu * dt - 0.5 * vpos * dt + sq * dWs) * drop;
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
    int n_base) {

    const int n  = static_cast<int>(S0.size());
    const int N  = static_cast<int>(dt.size());
    const int n_total = 2 * n_base;
    const int two = 2 * n;

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

    // Release the GIL for the compute only — it must be re-acquired before the
    // py::make_tuple below (that touches Python refcounts), so scope it tightly.
    {
    py::gil_scoped_release nogil;
    #pragma omp parallel
    {
        std::mt19937_64 gen(seed);
        std::normal_distribution<double> norm(0.0, 1.0);
        std::chi_squared_distribution<double> chi(t_dof > 0.0 ? t_dof : 1.0);
        std::vector<double> z(two), w(two);
        std::vector<double> Sb(n), Vb(n), Sa(n), Va(n);

        #pragma omp for schedule(static)
        for (int b = 0; b < n_base; ++b) {
            gen.seed(seed + static_cast<std::uint64_t>(b));  // per-path stream
            const std::size_t base = static_cast<std::size_t>(b) * row;
            const std::size_t anti = static_cast<std::size_t>(b + n_base) * row;
            for (int a = 0; a < n; ++a) {
                Sb[a] = Sa[a] = pS0[a];
                Vb[a] = Va[a] = pV0[a];
                oS[base + a] = pS0[a]; oV[base + a] = pV0[a];
                oS[anti + a] = pS0[a]; oV[anti + a] = pV0[a];
            }

            for (int t = 0; t < N; ++t) {
                const double dtt = pdt[t], sdtt = psdt[t];
                for (int k = 0; k < two; ++k) z[k] = norm(gen);
                if (t_dof > 0.0) {                       // Student-t copula
                    const double sc = t_scale / std::sqrt(chi(gen) / t_dof);
                    for (int k = 0; k < two; ++k) z[k] *= sc;
                }
                // Correlate: w = L @ z  (small 2n x 2n; not the bottleneck).
                for (int r = 0; r < two; ++r) {
                    double acc = 0.0;
                    const double* Lr = pL + static_cast<std::size_t>(r) * two;
                    for (int c = 0; c < two; ++c) acc += Lr[c] * z[c];
                    w[r] = acc;
                }
                const std::size_t off = base + static_cast<std::size_t>(t + 1) * n;
                const std::size_t offA = anti + static_cast<std::size_t>(t + 1) * n;
                for (int a = 0; a < n; ++a) {
                    const double dWs = w[a] * sdtt, dWv = w[n + a] * sdtt;
                    const double drop = 1.0 - pdiv[static_cast<std::size_t>(a) * N + t];
                    heston_step(Sb[a], Vb[a],  dWs,  dWv, dtt,
                                pk[a], pth[a], pxi[a], xi2[a], pmu[a], drop);
                    heston_step(Sa[a], Va[a], -dWs, -dWv, dtt,
                                pk[a], pth[a], pxi[a], xi2[a], pmu[a], drop);
                    oS[off + a]  = Sb[a]; oV[off + a]  = Vb[a];
                    oS[offA + a] = Sa[a]; oV[offA + a] = Va[a];
                }
            }
        }
    }  // end #pragma omp parallel
    }  // GIL re-acquired here
    return py::make_tuple(S_out, V_out);
}

PYBIND11_MODULE(heston_cpp, m) {
    m.doc() = "Phase-1 C++ Heston engine (validated reference alternative to numpy).";
    m.def("simulate", &simulate,
          py::arg("S0"), py::arg("V0"), py::arg("kappa"), py::arg("theta"),
          py::arg("xi"), py::arg("mu"), py::arg("L"), py::arg("dt"),
          py::arg("sdt"), py::arg("div"), py::arg("t_dof"),
          py::arg("seed"), py::arg("n_base"));
}
