#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
sdk="${ROBOT_TEST_LIVOX_SDK:-$root/.local-deps/Livox-SDK2}"
mkdir -p "$root/.local-deps/bin"
cmake -S "$sdk" -B "$sdk/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$sdk/build" --target livox_lidar_sdk_static -j2
g++ -std=c++11 -O2 -pthread "$root/scripts/livox_monitor.cpp" \
  -I"$sdk/include" "$sdk/build/sdk_core/liblivox_lidar_sdk_static.a" \
  -o "$root/.local-deps/bin/livox_monitor"
