#!/usr/bin/env bash
set -euo pipefail
[[ "$EUID" == 0 ]] || { echo 'Run with sudo/root' >&2; exit 1; }
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
install -d -m 700 /etc/jastcraft
install -d -m 755 /usr/local/lib/jastcraft
install -m 755 "$root/backup.sh" "$root/backup-sqlite.py" "$root/check-host.sh" /usr/local/lib/jastcraft/
install -m 644 "$root"/jastcraft-*.service "$root"/jastcraft-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now jastcraft-health.timer
printf 'Health checks enabled. Configure /etc/jastcraft/backup.env, install the cloud CLI and test backup before enabling jastcraft-backup.timer.\n'
