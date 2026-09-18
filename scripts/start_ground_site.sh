#!/usr/bin/env bash
set -e
source "$(dirname "$0")/env.sh"
export ROS_LOCALHOST_ONLY=0
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROBOT_TEST_CONFIG_DIR="${ROBOT_TEST_CONFIG_DIR:-$PROJECT_ROOT/config/robot_a_site}"
exec ros2 run robot_test_ground ground_station
