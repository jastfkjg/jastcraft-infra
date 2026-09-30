#!/usr/bin/env bash
# Route-only reload. Network/environment/image changes use deploy.sh or Deploy gateway.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
gateway_root=${GATEWAY_ROOT:-/opt/gateway}
exec 9>"$gateway_root/deploy.lock"
flock -n 9 || { echo 'Another gateway change is running' >&2; exit 1; }
compose() { GATEWAY_ROOT="$gateway_root" bash "$root/gateway/compose.sh" "$@"; }
candidate=$(mktemp -d)
trap 'rm -rf "$candidate"' EXIT
if [[ -f "$gateway_root/config/host" ]]; then
    python3 "$root/scripts/render_host.py" "$(cat "$gateway_root/config/host")" "$candidate" --gateway-root "$gateway_root"
    cmp -s "$candidate/compose.yaml" "$gateway_root/config/compose.yaml" || { echo 'Host services changed; use Deploy gateway to recreate networks and environment.' >&2; exit 1; }
else
    cp "$root/gateway/Caddyfile" "$candidate/Caddyfile"
fi
compose exec -T caddy sh -c 'cat > /tmp/Caddyfile.candidate' < "$candidate/Caddyfile"
compose exec -T caddy caddy validate --config /tmp/Caddyfile.candidate --adapter caddyfile
cp "$gateway_root/config/Caddyfile" "$gateway_root/config/Caddyfile.previous"
cp "$candidate/Caddyfile" "$gateway_root/config/Caddyfile.next"
mv "$gateway_root/config/Caddyfile.next" "$gateway_root/config/Caddyfile"
if ! compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
    cp "$gateway_root/config/Caddyfile.previous" "$gateway_root/config/Caddyfile.next"
    mv "$gateway_root/config/Caddyfile.next" "$gateway_root/config/Caddyfile"
    compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
    exit 1
fi
