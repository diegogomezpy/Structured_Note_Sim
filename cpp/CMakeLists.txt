cmake_minimum_required(VERSION 3.18)
project(heston_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(pybind11 CONFIG REQUIRED)
find_package(OpenMP)   # optional — without it the kernel still runs, serially

pybind11_add_module(heston_cpp heston_kernel.cpp)

# -fopenmp-simd enables the `#pragma omp simd` vectorisation of the inner path
# loops even without the OpenMP runtime, so the kernel is SIMD-fast serially; if
# libomp is found below, OpenMP also parallelises across path-blocks (multicore).
# -fno-math-errno lets the vectoriser use the vector sqrt/exp (which don't set
# errno) — needed for libmvec on Linux to kick in; harmless for our inputs.
target_compile_options(heston_cpp PRIVATE -O3 -funroll-loops -fopenmp-simd -fno-math-errno)

# Vector libm so the inner sqrt/exp vectorise (the decisive win): Accelerate's
# vForce on macOS, glibc libmvec on Linux.
if(APPLE)
  target_compile_options(heston_cpp PRIVATE -fveclib=Accelerate)
  target_link_libraries(heston_cpp PRIVATE "-framework Accelerate")
elseif(UNIX)
  target_compile_options(heston_cpp PRIVATE -fveclib=libmvec)
endif()

# -march=native gives the best auto-vectorisation for a LOCAL build, but bakes in
# the build host's ISA — never use it for portable/cibuildwheel wheels. Default ON
# for local dev; CI sets -DHESTON_NATIVE=OFF and a portable baseline instead.
option(HESTON_NATIVE "Tune for the build host (non-portable)" ON)
if(HESTON_NATIVE)
  target_compile_options(heston_cpp PRIVATE -march=native)
endif()

if(OpenMP_CXX_FOUND)
  target_link_libraries(heston_cpp PRIVATE OpenMP::OpenMP_CXX)
endif()

install(TARGETS heston_cpp DESTINATION .)
