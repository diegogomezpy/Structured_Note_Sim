cmake_minimum_required(VERSION 3.18)
project(heston_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(pybind11 CONFIG REQUIRED)
find_package(OpenMP)   # optional — without it the kernel still runs, serially

pybind11_add_module(heston_cpp heston_kernel.cpp)

target_compile_options(heston_cpp PRIVATE -O3 -funroll-loops)

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
