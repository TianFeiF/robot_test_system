#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SDK="$ROOT/.local-deps/eyou_canopen_sdk"

OUT="$ROOT/.local-deps/bin"

mkdir -p "$OUT"

if [[ ! -f "$SDK/include/eu_canopen.h" ]]; then
    echo "Missing SDK header: $SDK/include/eu_canopen.h" >&2
    exit 1
fi

if [[ ! -f "$SDK/lib/libeu_canopen.so" ]]; then
    echo "Missing SDK library: $SDK/lib/libeu_canopen.so" >&2
    exit 1
fi

g++ \
    -std=c++17 \
    -O2 \
    -Wall \
    -Wextra \
    -I"$SDK/include" \
    "$ROOT/native/eyou_canopen_agent.cpp" \
    "$SDK/lib/libeu_canopen.so" \
    -Wl,-rpath,"$SDK/lib" \
    -Wl,-rpath-link,"$SDK/lib" \
    -pthread \
    -o "$OUT/eyou_canopen_agent"

echo "Built CANopen helper:"
ls -lh "$OUT/eyou_canopen_agent"

echo
echo "Runtime dependencies:"

LD_LIBRARY_PATH="$SDK/lib:${LD_LIBRARY_PATH:-}" \
    ldd "$OUT/eyou_canopen_agent" \
    | grep -E 'libeu_|libnl|not found' \
    || true
