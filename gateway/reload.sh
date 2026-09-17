#!/usr/bin/env bash
# Reload only Caddyfile changes. Environment/image/Compose changes require up -d.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec 9>/opt/gateway/deploy.lock
flock -n 9 || { echo 'Another gateway change is running.' >&2; exit 1; }
compose() { bash "$root/compose.sh" "$@"; }
# Validate against the running container's environment and Caddy version.
compose exec -T caddy sh -c 'cat > /tmp/Caddyfile.candidate' < "$root/Caddyfile"
compose exec -T caddy caddy validate --config /tmp/Caddyfile.candidate --adapter caddyfile
cp /opt/gateway/config/Caddyfile /opt/gateway/config/Caddyfile.previous
cp "$root/Caddyfile" /opt/gateway/config/Caddyfile.next
mv /opt/gateway/config/Caddyfile.next /opt/gateway/config/Caddyfile
if ! compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
    cp /opt/gateway/config/Caddyfile.previous /opt/gateway/config/Caddyfile.next
    mv /opt/gateway/config/Caddyfile.next /opt/gateway/config/Caddyfile
    compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
    exit 1
fi
