#!/usr/bin/env bash
# Start both real robots in MONITOR mode, then the local dual-robot UI.
# Closing the UI / Ctrl+C stops the remote sessions started by this launcher.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
domain="${ROS_DOMAIN_ID:-30}"
if [[ ! "$domain" =~ ^[0-9]{1,3}$ ]] || (( 10#$domain > 232 )); then
  echo 'ROS_DOMAIN_ID must be an integer from 0 to 232.' >&2
  exit 1
fi
exec 9>"/tmp/robot-test-site-${UID}.lock"
flock -n 9 || { echo 'Another all-site launcher is already running.' >&2; exit 1; }
started_hosts=()
started_units=()
ground_pid=''
cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$ground_pid" ]] && kill -0 "$ground_pid" 2>/dev/null; then
    kill -TERM "$ground_pid" 2>/dev/null || true
    wait "$ground_pid" 2>/dev/null || true
  fi
  for i in "${!started_hosts[@]}"; do
    ssh -o BatchMode=yes -o ConnectTimeout=5 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 \
      "${started_hosts[$i]}" systemctl --user stop "${started_units[$i]}" \
      || echo "Could not stop ${started_units[$i]} on ${started_hosts[$i]}; check that robot." >&2
  done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
start_robot() {
  local host="$1" root="$2" rid="$3" unit="robot-$3-site-monitor"
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$host" bash -s -- "$root" "$rid" "$domain" <<'REMOTE'
set -e
root="$1"; rid="$2"; domain="$3"
if pgrep -f '[r]obot_test_agent/agent' >/dev/null; then
  echo 'A robot Agent is already running. Stop it before using this launcher.' >&2
  exit 1
fi
test -x "$root/scripts/start_robot_${rid}_site.sh"
systemd-run --user --unit="robot-${rid}-site-monitor" --collect \
  --property="WorkingDirectory=$root" \
  --setenv="ROS_DOMAIN_ID=$domain" \
  --setenv="ROBOT_TEST_CONFIG_DIR=$root/config/robot_${rid}_site" \
  "$root/scripts/start_robot_${rid}_site.sh"
REMOTE
  started_hosts+=("$host")
  started_units+=("$unit")
}
start_robot phi@192.168.10.3 /home/phi/robot_test_system a
start_robot phi@192.168.10.63 /home/phi/robot_test_system_git b
export ROS_DOMAIN_ID="$domain"
export ROBOT_TEST_CONFIG_DIR="$ROOT/config/dual_robot_site"
"$SCRIPT_DIR/start_ground_dual.sh" &
ground_pid=$!
wait "$ground_pid"
