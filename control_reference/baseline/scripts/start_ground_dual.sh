#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export ROBOT_TEST_CONFIG_DIR="${ROBOT_TEST_CONFIG_DIR:-$SCRIPT_DIR/../config/dual_robot_site}"
exec "$SCRIPT_DIR/start_ground_site.sh" "$@"
