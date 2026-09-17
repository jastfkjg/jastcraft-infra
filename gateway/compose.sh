#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec docker compose --project-name jastcraft-gateway --env-file /opt/gateway/gateway.env -f "$root/compose.yaml" "$@"
