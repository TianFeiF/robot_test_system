#!/usr/bin/env bash
set -e
source "$(dirname "$0")/env.sh"
source "$PROJECT_ROOT/scripts/site_network.sh"
exec ros2 run robot_test_agent agent --ros-args -r __ns:=/robot_b \
  -p config_file:="${ROBOT_TEST_CONFIG_DIR:-$PROJECT_ROOT/config/robot_b_site}/robot_b.yaml"
