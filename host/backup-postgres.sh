#!/usr/bin/env bash
# Called with the application's deploy.lock already held by backup.sh.
set -euo pipefail
umask 077
service_root=${1:?Set the RealQuest service directory}
container=$(docker ps -q --filter label=com.docker.compose.project=realquest --filter label=com.docker.compose.service=db)
[[ "$container" =~ ^[a-f0-9]{12,64}$ ]] || { echo 'Expected exactly one running RealQuest PostgreSQL container' >&2; exit 1; }
mkdir -p "$service_root/backups"
temporary=$(mktemp "$service_root/backups/realquest-$(date -u +%Y%m%dT%H%M%SZ).XXXXXXXX")
snapshot="$temporary.dump"
complete=false
cleanup() { [[ "$complete" == true ]] || rm -f "$snapshot" "$temporary"; }
trap cleanup EXIT
mv "$temporary" "$snapshot"
docker exec "$container" pg_dump -U realquest -d realquest --format=custom > "$snapshot"
[[ -s "$snapshot" ]]
docker exec -i "$container" pg_restore --list < "$snapshot" >/dev/null
complete=true
printf '%s\n' "$snapshot"
