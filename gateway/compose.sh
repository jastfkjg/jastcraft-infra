#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
gateway_root=${GATEWAY_ROOT:-/opt/gateway}
file="$gateway_root/config/compose.yaml"
[[ -f "$file" ]] || file="$root/compose.yaml" # Existing shared EC2 remains usable before migration.
args=(--project-name jastcraft-gateway --env-file "$gateway_root/gateway.env")
[[ ! -f "$gateway_root/config/image.env" ]] || args+=(--env-file "$gateway_root/config/image.env")
exec docker compose "${args[@]}" -f "$file" "$@"
