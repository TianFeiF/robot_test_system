#!/usr/bin/env bash
# Source this helper from launcher scripts.
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source /opt/ros/humble/setup.bash
source "$PROJECT_ROOT/ros2_ws/install/setup.bash"
export PYTHONPATH="$PROJECT_ROOT/.venv/lib/python3.10/site-packages:${PYTHONPATH:-}"
export ROBOT_TEST_LOG_ROOT="$PROJECT_ROOT/logs"
export ROBOT_TEST_SESSION="${ROBOT_TEST_SESSION:-$(date -u +%Y%m%dT%H%M%SZ)}"
export LD_LIBRARY_PATH="$PROJECT_ROOT/.local-deps/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
# Keep ROS/system OpenCV on Ubuntu NumPy; ignore unrelated user-site NumPy 2.
export PYTHONNOUSERSITE=1
