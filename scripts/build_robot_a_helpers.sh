#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
rm_sdk="${ROBOT_TEST_RM_SDK:-/home/phi/ros2_robot_ws/src/ros2_rm_robot-humble/rm_driver}"
livox_sdk="${ROBOT_TEST_LIVOX_SDK:-$root/.local-deps/Livox-SDK2}"
mkdir -p "$root/.local-deps/bin"
g++ -std=c++17 -O2 -Wall -Wextra -pthread "$root/native/ethercat_agent.cpp" \
  -I"${ROBOT_TEST_IGH_INCLUDE:-/home/phi/ethercat/include}" -L/usr/local/lib -Wl,-rpath,/usr/local/lib \
  -lethercat -o "$root/.local-deps/bin/ethercat_agent"
"$root/.local-deps/bin/ethercat_agent" --self-test
g++ -std=c++11 -O2 "$root/scripts/rm75_read_state.cpp" \
  -I"$rm_sdk/include/rm_driver" -L"$rm_sdk/lib/linux_x86_c++_v1.1.3" \
  -Wl,-rpath,"$rm_sdk/lib/linux_x86_c++_v1.1.3" -lapi_cpp \
  -o "$root/.local-deps/bin/rm75_read_state"
cmake -S "$livox_sdk" -B "$livox_sdk/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$livox_sdk/build" --target livox_lidar_sdk_static -j2
g++ -std=c++11 -O2 -pthread "$root/scripts/livox_monitor.cpp" \
  -I"$livox_sdk/include" "$livox_sdk/build/sdk_core/liblivox_lidar_sdk_static.a" \
  -o "$root/.local-deps/bin/livox_monitor"
read -r -a rs_flags <<< "$(pkg-config --cflags --libs realsense2)"
g++ -std=c++11 -O2 "$root/scripts/realsense_depth.cpp" "${rs_flags[@]}" \
  -Wl,-rpath,/usr/local/lib/x86_64-linux-gnu -o "$root/.local-deps/bin/realsense_depth"
