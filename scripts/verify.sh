#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$root"
for script in gateway/*.sh host/*.sh scripts/*.sh; do bash -n "$script"; done
python3 -m unittest discover -s tests
candidate=$(mktemp -d)
trap 'rm -rf "$candidate"' EXIT
bash scripts/retry_docker_build.sh build --progress=plain -t gateway-check gateway
docker compose --env-file gateway/gateway.env.example -f gateway/compose.yaml config --quiet
docker run --rm -e ECHOOO_ADDRESS=echooo.example.com -e SHADOWTABLE_DOMAIN=table.example.com -e WENLV_DOMAIN=wenlv.example.com -e ACME_EMAIL=admin@example.com -v "$root/gateway/Caddyfile:/etc/caddy/Caddyfile:ro" gateway-check caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
for manifest in hosts/*/*/*/host.json; do
    target=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["target"])' "$manifest")
    python3 scripts/render_host.py "$target" "$candidate/$target"
    python3 - "$manifest" "$candidate/$target/example.env" <<'ENV'
from pathlib import Path
import sys
source=Path(sys.argv[1]).parent/'gateway.env.example'
Path(sys.argv[2]).write_text(source.read_text().replace('REPLACE_WITH_DIGEST','a'*64))
ENV
    docker compose --env-file "$candidate/$target/example.env" -f "$candidate/$target/compose.yaml" config --format json | python3 scripts/check_gateway_config.py
    docker run --rm --env-file "$candidate/$target/example.env" -v "$candidate/$target/Caddyfile:/etc/caddy/Caddyfile:ro" gateway-check caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
done
