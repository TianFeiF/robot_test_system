#!/usr/bin/env bash
set -e
source "$(dirname "$0")/env.sh"
exec ros2 run robot_test_ground ground_station
