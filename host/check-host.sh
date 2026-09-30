#!/usr/bin/env bash
set -euo pipefail
docker info >/dev/null
usage=$(df -P /opt | awk 'NR==2 {gsub(/%/, "", $5); print $5}')
(( usage < 85 )) || { echo "Disk usage is ${usage}%" >&2; exit 1; }
failed=$(docker ps --filter health=unhealthy --format '{{.Names}}')
[[ -z "$failed" ]] || { printf 'Unhealthy containers:\n%s\n' "$failed" >&2; exit 1; }
