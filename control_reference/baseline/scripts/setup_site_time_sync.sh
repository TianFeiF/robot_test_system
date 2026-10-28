#!/usr/bin/env bash
# Persistent LAN clock synchronization. Run once, with all test processes stopped.
set -euo pipefail
role="${1:-}"
if [[ "$role" != ground && "$role" != robot ]]; then
  echo "Usage: sudo $0 ground|robot" >&2
  exit 2
fi
if (( EUID != 0 )); then
  echo 'Run this setup with sudo; it writes system time-service configuration.' >&2
  exit 1
fi
if pgrep -f '[/]robot_test_agent/agent|[/]robot_test_ground/ground_station|[/]eyou_agent --run|[/]eyou_canopen_agent --run' >/dev/null; then
  echo 'Stop ground and robot test programs before changing system time.' >&2
  exit 1
fi
backup="/var/backups/robot-test-time-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$backup"
if [[ "$role" == ground ]]; then
  if ! command -v chronyd >/dev/null; then
    apt-get update
    apt-get install -y chrony
  fi
  cp -a /etc/chrony/chrony.conf "$backup/"
  # Keep existing upstream sources. Local reference also supports an isolated LAN.
  if ! grep -Fxq 'include /etc/chrony/robot-test-site.conf' /etc/chrony/chrony.conf; then
    echo 'include /etc/chrony/robot-test-site.conf' >> /etc/chrony/chrony.conf
  fi
  [[ ! -e /etc/chrony/robot-test-site.conf ]] || cp -a /etc/chrony/robot-test-site.conf "$backup/"
  cat > /etc/chrony/robot-test-site.conf <<'CONF'
allow 192.168.10.0/24
local stratum 10
CONF
  systemctl enable chrony
  systemctl restart chrony
  chronyc tracking
else
  # Robots use the existing Ubuntu timesyncd client, avoiding extra SDK dependencies.
  if systemctl is-active --quiet chrony; then
    echo 'chrony is already running on this robot; configure its source instead of starting a second clock service.' >&2
    exit 1
  fi
  mkdir -p /etc/systemd/timesyncd.conf.d
  target=/etc/systemd/timesyncd.conf.d/robot-test-site.conf
  [[ ! -e "$target" ]] || cp -a "$target" "$backup/"
  cat > "$target" <<'CONF'
[Time]
NTP=
NTP=192.168.10.4
FallbackNTP=
PollIntervalMinSec=16
PollIntervalMaxSec=32
CONF
  systemctl enable systemd-timesyncd
  systemctl restart systemd-timesyncd
  timedatectl timesync-status || true
fi
echo "Configuration saved; backup: $backup"
echo 'Ground must keep 192.168.10.4 and permit LAN UDP/123. Verify synchronization before starting control.'
