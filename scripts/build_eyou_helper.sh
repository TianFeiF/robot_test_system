#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
sdk="${ROBOT_TEST_EYOU_SDK:-$root/.local-deps/eyou_ethercat_sdk_x86_64_linux_gnu_20260109}"
if [[ -z "${ROBOT_TEST_EYOU_SDK:-}" && ! -f "$sdk/include/eu_ethercat.h" ]]; then
  sdk="$HOME/下载/eyou_ethercat_sdk_x86_64_linux_gnu_20260109"
fi
mkdir -p "$root/.local-deps/bin"
g++ -std=c++17 -O2 -Wall -Wextra -pthread "$root/native/eyou_agent.cpp" \
  -I"$sdk/include" -L"$sdk/lib" -Wl,--disable-new-dtags,-rpath,"$sdk/lib" \
  -leu_ethercat -o "$root/.local-deps/bin/eyou_agent"
"$root/.local-deps/bin/eyou_agent" --self-test
