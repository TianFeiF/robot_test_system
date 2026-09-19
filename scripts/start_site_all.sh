#!/usr/bin/env bash
# Start Robot A in MONITOR mode and Robot B in CONTROL mode (still DISARMED),
# then start the local dual-robot ground UI.
# Closing the UI / Ctrl+C stops only remote sessions started by this launcher.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
domain="${ROS_DOMAIN_ID:-30}"

ROBOT_A_HOST="${ROBOT_A_HOST:-phi@192.168.10.3}"
ROBOT_A_ROOT="${ROBOT_A_ROOT:-/home/phi/robot_test_system}"
ROBOT_B_HOST="${ROBOT_B_HOST:-phi@192.168.10.63}"
ROBOT_B_ROOT="${ROBOT_B_ROOT:-/home/phi/robot_test_system_git}"

if [[ ! "$domain" =~ ^[0-9]{1,3}$ ]] || (( 10#$domain > 232 )); then
  echo 'ROS_DOMAIN_ID must be an integer from 0 to 232.' >&2
  exit 1
fi

exec 9>"/tmp/robot-test-site-${UID}.lock"
flock -n 9 || { echo 'Another all-site launcher is already running.' >&2; exit 1; }

SSH_OPTS=(
  -o BatchMode=yes
  -o ConnectTimeout=5
  -o ServerAliveInterval=5
  -o ServerAliveCountMax=2
)

started_hosts=()
started_units=()
ground_pid=''

cleanup() {
  trap - EXIT INT TERM

  if [[ -n "$ground_pid" ]] && kill -0 "$ground_pid" 2>/dev/null; then
    kill -TERM "$ground_pid" 2>/dev/null || true
    wait "$ground_pid" 2>/dev/null || true
  fi

  for ((i=${#started_hosts[@]} - 1; i >= 0; i--)); do
    ssh "${SSH_OPTS[@]}" "${started_hosts[$i]}" \
      systemctl --user stop "${started_units[$i]}" \
      || echo "Could not stop ${started_units[$i]} on ${started_hosts[$i]}; check that robot." >&2
  done
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

start_robot() {
  local host="$1"
  local root="$2"
  local rid="$3"
  local profile="$4"
  local unit

  case "$profile" in
    monitor) unit="robot-${rid}-site-monitor" ;;
    control) unit="robot-${rid}-site-control" ;;
    *)
      echo "Unsupported profile: $profile" >&2
      return 2
      ;;
  esac

  echo "[site] Starting Robot ${rid^^} on $host: $profile"

  ssh "${SSH_OPTS[@]}" "$host" bash -s -- \
    "$root" "$rid" "$domain" "$profile" "$unit" <<'REMOTE'
set -euo pipefail

root="$1"
rid="$2"
domain="$3"
profile="$4"
unit="$5"

case "$profile" in
  monitor)
    launcher="$root/scripts/start_robot_${rid}_site.sh"
    config_dir="$root/config/robot_${rid}_site"
    ;;
  control)
    launcher="$root/scripts/start_robot_${rid}_control.sh"
    config_dir="$root/config/robot_${rid}_control"
    ;;
  *)
    echo "Unsupported profile: $profile" >&2
    exit 2
    ;;
esac

test -d "$root"
test -x "$launcher"
test -f "$config_dir/robot_${rid}.yaml"

if pgrep -f '[r]obot_test_agent/agent' >/dev/null; then
  echo 'A robot Agent is already running. Stop it before using this launcher.' >&2
  exit 1
fi

if [[ "$rid" == 'b' && "$profile" == 'control' ]]; then
  test -x "$root/.local-deps/bin/eyou_canopen_agent"
  test -r "$root/.local-deps/eyou_canopen_sdk/lib/libeu_canopen.so"
  if ! sudo -n /usr/sbin/ip link show can0 >/dev/null 2>&1; then
    echo 'Robot B CANopen preflight failed: can0 or passwordless sudo for /usr/sbin/ip is unavailable.' >&2
    exit 1
  fi
fi

systemctl --user reset-failed "$unit" >/dev/null 2>&1 || true
systemd-run --user --unit="$unit" --collect \
  --property="WorkingDirectory=$root" \
  --setenv="ROS_DOMAIN_ID=$domain" \
  --setenv="ROBOT_TEST_CONFIG_DIR=$config_dir" \
  "$launcher"

sleep 2
if ! systemctl --user is-active --quiet "$unit"; then
  echo "Remote unit $unit failed to stay active." >&2
  journalctl --user -u "$unit" -n 40 --no-pager >&2 || true
  exit 1
fi
REMOTE

  started_hosts+=("$host")
  started_units+=("$unit")
}

echo "[site] ROS_DOMAIN_ID=$domain"
echo '[site] Robot A: MONITOR only'
echo '[site] Robot B: CONTROL backend, starts DISARMED; no motor is armed by this launcher'

start_robot "$ROBOT_A_HOST" "$ROBOT_A_ROOT" a monitor
start_robot "$ROBOT_B_HOST" "$ROBOT_B_ROOT" b control

export ROS_DOMAIN_ID="$domain"
export ROBOT_TEST_CONFIG_DIR="$ROOT/config/dual_robot_site"

"$SCRIPT_DIR/start_ground_dual.sh" &
ground_pid=$!
wait "$ground_pid"
