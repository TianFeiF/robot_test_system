#!/usr/bin/env bash
set -e
source "$(dirname "$0")/env.sh"
setsid ros2 launch robot_test_bringup mock_full_system.launch.py &
AGENT_PID=$!
cleanup() { kill -TERM -- "-$AGENT_PID" 2>/dev/null || true; wait "$AGENT_PID" 2>/dev/null || true; }
trap cleanup EXIT
trap 'exit 130' INT TERM
ros2 run robot_test_ground ground_station
