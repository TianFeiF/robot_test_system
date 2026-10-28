#!/usr/bin/env bash
# Activate the prebuilt signed-torque helper and persistent clock sync after shutdown.
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
rid="${1:-}"
[[ "$rid" == a || "$rid" == b ]] || { echo "Usage: sudo $0 a|b" >&2; exit 2; }
(( EUID == 0 )) || { echo 'Run with sudo.' >&2; exit 1; }
candidate="$root/.local-deps/bin/eyou_agent.control-fix"
test -x "$candidate"
target="$(python3 - "$root/config/robot_${rid}_control/robot_${rid}.yaml" <<'PY'
import sys, yaml
print(yaml.safe_load(open(sys.argv[1]))['hardware']['ethercat']['executable'])
PY
)"
[[ "$target" == /* && -f "$target" ]] || { echo 'Invalid configured EtherCAT executable.' >&2; exit 1; }
"$root/scripts/setup_site_time_sync.sh" robot
backup="${target}.before-control-fix-$(date +%Y%m%dT%H%M%S)"
cp --preserve=all "$target" "$backup"
install -m 755 "$candidate" "${target}.new"
setcap cap_net_raw=ep "${target}.new"
mv -f "${target}.new" "$target"
echo "Installed $target; previous executable: $backup"
getcap "$target"
echo 'Wait for timedatectl to report synchronized before restarting control.'
