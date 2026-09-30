#!/usr/bin/env bash
# Shared gateway only; never starts, stops or migrates any business container.
set -euo pipefail
umask 077
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
target=${1:?Usage: deploy.sh HOST_TARGET CADDY_IMAGE_DIGEST}
image=${2:?Set immutable Caddy image}
gateway_root=${GATEWAY_ROOT:-/opt/gateway}
[[ -r "$gateway_root/deployment-target" && "$(cat "$gateway_root/deployment-target")" == "$target" ]] || { echo 'This host does not match the selected gateway target.' >&2; exit 1; }
python3 "$root/scripts/validate_image.py" "$image"
[[ -d "$gateway_root/config" && -d "$gateway_root/releases" && -r "$gateway_root/gateway.env" ]]
python3 - "$gateway_root/gateway.env" <<'CHECK'
import os, stat, sys
info = os.stat(sys.argv[1])
if stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.getuid():
    sys.exit('gateway.env must be owned by the deployment user, mode 600')
CHECK
exec 9>"$gateway_root/deploy.lock"
flock -w 120 9
candidate=$(mktemp -d "$gateway_root/releases/gateway.XXXXXXXX")
python3 "$root/scripts/render_host.py" "$target" "$candidate" --gateway-root "$gateway_root"
printf 'CADDY_IMAGE=%s\n' "$image" > "$candidate/image.env"
compose() { docker compose --project-name jastcraft-gateway --env-file "$gateway_root/gateway.env" --env-file "$candidate/image.env" -f "$candidate/compose.yaml" "$@"; }
config=$(compose config --format json)
printf '%s' "$config" | python3 "$root/scripts/check_gateway_config.py"
# External networks/volumes are local to this host. Retain existing volume names in gateway.env.
while IFS= read -r network; do
    docker network inspect "$network" >/dev/null 2>&1 || docker network create "$network" >/dev/null
done < <(printf '%s' "$config" | python3 -c 'import json,sys; print("\n".join(n["name"] for n in json.load(sys.stdin)["networks"].values()))')
while IFS= read -r volume; do
    docker volume inspect "$volume" >/dev/null 2>&1 || docker volume create "$volume" >/dev/null
done < <(printf '%s' "$config" | python3 -c 'import json,sys; print("\n".join(v["name"] for v in json.load(sys.stdin)["volumes"].values()))')
compose pull
compose run --rm --no-deps -T -v "$candidate/Caddyfile:/tmp/Caddyfile.candidate:ro" caddy caddy validate --config /tmp/Caddyfile.candidate --adapter caddyfile
previous=""
[[ ! -L "$gateway_root/current" ]] || previous=$(readlink -f "$gateway_root/current")
old_running=$(docker ps -q --filter label=com.docker.compose.project=jastcraft-gateway --filter label=com.docker.compose.service=caddy)
mkdir "$candidate/previous-config"
for file in Caddyfile compose.yaml image.env host; do
    [[ ! -f "$gateway_root/config/$file" ]] || cp "$gateway_root/config/$file" "$candidate/previous-config/$file"
done
switched=false
rollback() {
    status=$?
    trap - EXIT
    if [[ "$status" != 0 && "$switched" == true ]]; then
        compose stop caddy || true
        for file in Caddyfile compose.yaml image.env host; do
            if [[ -f "$candidate/previous-config/$file" ]]; then
                cp "$candidate/previous-config/$file" "$gateway_root/config/$file.next"
                mv "$gateway_root/config/$file.next" "$gateway_root/config/$file"
            else
                rm -f "$gateway_root/config/$file"
            fi
        done
        if [[ -n "$old_running" ]]; then
            GATEWAY_ROOT="$gateway_root" bash "$root/gateway/compose.sh" up -d --wait --wait-timeout 120 caddy || echo 'Gateway rollback failed; inspect logs.' >&2
        fi
    fi
    exit "$status"
}
trap rollback EXIT
switched=true
for file in Caddyfile compose.yaml image.env host; do
    cp "$candidate/$file" "$gateway_root/config/$file.next"
    mv "$gateway_root/config/$file.next" "$gateway_root/config/$file"
done
GATEWAY_ROOT="$gateway_root" bash "$root/gateway/compose.sh" up -d --wait --wait-timeout 120 caddy
[[ -z "$previous" ]] || ln -sfn "$previous" "$gateway_root/previous"
ln -sfn "$candidate" "$gateway_root/current"
switched=false
printf 'Gateway target: %s\nImage: %s\n' "$target" "$image"
