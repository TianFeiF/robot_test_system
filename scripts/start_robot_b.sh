#!/usr/bin/env bash
set -e
source "$(dirname "$0")/env.sh"
exec ros2 run robot_test_agent agent --ros-args -r __ns:=/robot_b -p config_file:="$PROJECT_ROOT/ros2_ws/src/robot_test_bringup/config/robot_b.yaml"
