#!/usr/bin/env bash
# Remove only the old launch service; preserve its workspace and EtherCAT SDKs.
set -euo pipefail
if (( EUID != 0 )); then
  exec sudo -- bash "$(realpath -- "${BASH_SOURCE[0]}")"
fi
unit=/etc/systemd/system/ros2_robot.service
if [[ ! -f "$unit" ]]; then
  echo "ros2_robot.service unit file is already absent."
  systemctl daemon-reload
  exit 0
fi
if ! grep -Eq '^ExecStart=/bin/bash /home/phi/ros2_robot_ws/start_robot\.sh[[:space:]]*$' "$unit"; then
  echo "Service differs from the reviewed legacy unit; leaving it unchanged." >&2
  exit 1
fi
backup_dir="/var/backups/robot-test-system/legacy-service-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$backup_dir"
cp -a -- "$unit" "$backup_dir/"
if [[ -d "$unit.d" ]]; then
  cp -a -- "$unit.d" "$backup_dir/"
fi
systemctl disable --now ros2_robot.service
rm -- "$unit"
systemctl daemon-reload
systemctl reset-failed ros2_robot.service 2>/dev/null || true
if systemctl is-enabled --quiet ros2_robot.service || systemctl is-active --quiet ros2_robot.service; then
  echo "Service still enabled or active; inspect systemctl status ros2_robot.service." >&2
  exit 1
fi
echo "Removed ros2_robot.service. Backup: $backup_dir"
