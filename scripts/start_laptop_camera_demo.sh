#!/usr/bin/env bash
set -e
source "$(dirname "$0")/env.sh"
# Dedicated runtime config; source Mock YAML files are never modified.
export ROBOT_TEST_CONFIG_DIR
ROBOT_TEST_CONFIG_DIR="$(mktemp -d /tmp/robot-laptop-camera-XXXXXX)"
cleanup() { rm -f "$ROBOT_TEST_CONFIG_DIR/robot_a.yaml" "$ROBOT_TEST_CONFIG_DIR/robot_b.yaml"; rmdir "$ROBOT_TEST_CONFIG_DIR"; }
trap cleanup EXIT
export LAPTOP_CAMERA_DEVICE="${LAPTOP_CAMERA_DEVICE:-/dev/video0}"
python3 - <<'PY'
import os
from pathlib import Path
import yaml
from ament_index_python.packages import get_package_share_directory
source = Path(get_package_share_directory('robot_test_bringup')) / 'config'
for rid in ['robot_a', 'robot_b']:
    config = yaml.safe_load((source / f'{rid}.yaml').read_text())
    if rid == 'robot_a':
        config['cameras']['camera_1'].update(backend='uvc', device=os.environ['LAPTOP_CAMERA_DEVICE'], width=640, height=480, fps=5, reconnect_sec=2.0, label='LAPTOP CAMERA (LIVE)')
    (Path(os.environ['ROBOT_TEST_CONFIG_DIR']) / f'{rid}.yaml').write_text(yaml.safe_dump(config, sort_keys=False))
PY
"$PROJECT_ROOT/scripts/start_mock_demo.sh"
