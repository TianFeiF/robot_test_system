#!/usr/bin/env bash
# Real Robot A control profile; ARM remains an explicit operator action.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export ROBOT_TEST_CONFIG_DIR="${ROBOT_TEST_CONFIG_DIR:-$SCRIPT_DIR/../config/robot_a_control}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
exec "$SCRIPT_DIR/start_robot_a_site.sh" "$@"
