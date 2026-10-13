#!/usr/bin/env bash
# Exercise the actual route with local mock upstreams; no published host ports.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
image=${1:-gateway-check}
candidate=$(mktemp -d)
container="directo-route-check-$(basename "$candidate" | tr '[:upper:]' '[:lower:]')"
cleanup() {
    docker rm -f -v "$container" >/dev/null 2>&1 || true
    rm -rf "$candidate"
}
trap cleanup EXIT
cp "$root/gateway/routes/directo.caddy" "$candidate/directo.caddy"
cat > "$candidate/Caddyfile" <<'CADDY'
{
    admin off
}
import /etc/caddy/directo.caddy
:80 {
    respond "WEB {http.request.method} {http.request.uri}"
}
:3001 {
    respond "API {http.request.method} {http.request.uri} {http.request.header.X-Route-Test}"
}
CADDY
docker run -d --name "$container" --network none \
    --add-host directo-upstream:127.0.0.1 \
    --add-host directo-api-upstream:127.0.0.1 \
    -e DIRECTO_DOMAIN=http://directo.test:8080 \
    -v "$candidate:/etc/caddy:ro" "$image" \
    caddy run --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
ready=false
for attempt in {1..30}; do
    if docker exec "$container" wget -q -O /dev/null \
        --header='Host: directo.test' http://127.0.0.1:8080/login 2>/dev/null; then
        ready=true
        break
    fi
    sleep 0.2
done
if [[ "$ready" != true ]]; then
    docker logs "$container" >&2
    exit 1
fi
expect_response() {
    local expected=$1 actual
    shift
    actual=$(docker exec "$container" wget -q -O - --header='Host: directo.test' "$@")
    if [[ "$actual" != "$expected" ]]; then
        printf 'Expected: %s\nReceived: %s\n' "$expected" "$actual" >&2
        exit 1
    fi
}
expect_response 'WEB GET /login' http://127.0.0.1:8080/login
expect_response 'WEB GET /assets/index.js' http://127.0.0.1:8080/assets/index.js
expect_response 'WEB GET /apiary' http://127.0.0.1:8080/apiary
expect_response 'API POST /api/v1/auth/login?source=route-test forwarded' \
    --header='X-Route-Test: forwarded' --post-data='{"username":"route-test"}' \
    'http://127.0.0.1:8080/api/v1/auth/login?source=route-test'
options_response=$(printf 'OPTIONS /api/v1/auth/login HTTP/1.1\r\nHost: directo.test\r\nX-Route-Test: forwarded\r\nConnection: close\r\n\r\n' \
    | docker exec -i "$container" nc -w 5 127.0.0.1 8080)
if [[ "${options_response#*$'\r\n\r\n'}" != 'API OPTIONS /api/v1/auth/login forwarded' ]]; then
    printf 'Unexpected API preflight response: %s\n' "$options_response" >&2
    exit 1
fi
printf 'Directo routing: Web/static fallback and API method/path/query/header forwarding passed.\n'
