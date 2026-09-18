#!/usr/bin/env bash
set -e
source "$(dirname "$0")/env.sh"
export ROS_LOCALHOST_ONLY=0
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
exec ros2 run robot_test_agent agent --ros-args -r __ns:=/robot_a \
  -p config_file:="${ROBOT_TEST_CONFIG_DIR:-$PROJECT_ROOT/config/robot_a_site}/robot_a.yaml"
