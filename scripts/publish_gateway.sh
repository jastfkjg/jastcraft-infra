#!/usr/bin/env bash
set -euo pipefail
[[ "${GATEWAY_TARGET:-}" == "${HOST_TARGET:?}" ]] || { echo 'Set GATEWAY_TARGET to the host ID in the selected Environment.' >&2; exit 1; }
[[ "${SSH_HOST:-}" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ && "${SSH_USER:-}" =~ ^[a-z_][a-z0-9_-]*$ ]]
SSH_PORT=${SSH_PORT:-22}
[[ "$SSH_PORT" =~ ^[0-9]+$ ]] && (( SSH_PORT >= 1 && SSH_PORT <= 65535 ))
[[ "$GITHUB_SHA" =~ ^[a-f0-9]{40}$ && "$GITHUB_RUN_ID" =~ ^[0-9]+$ && "$GITHUB_RUN_ATTEMPT" =~ ^[0-9]+$ ]]
[[ "$HOST_TARGET" =~ ^[a-z0-9][a-z0-9-]*$ && -n "$SSH_KEY" && -n "$SSH_KNOWN_HOSTS" ]]
python3 scripts/validate_image.py "$CADDY_IMAGE"
ssh_dir=$(mktemp -d)
trap 'rm -rf "$ssh_dir"' EXIT
chmod 700 "$ssh_dir"
printf '%s\n' "$SSH_KEY" > "$ssh_dir/key"
printf '%s\n' "$SSH_KNOWN_HOSTS" > "$ssh_dir/known_hosts"
chmod 600 "$ssh_dir/key" "$ssh_dir/known_hosts"
SSH=(ssh -i "$ssh_dir/key" -p "$SSH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$ssh_dir/known_hosts" -o ConnectTimeout=15)
target="$SSH_USER@$SSH_HOST"
release="/opt/gateway/releases/source-${GITHUB_SHA}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
"${SSH[@]}" "$target" "umask 077; mkdir -p '$release'"
tar --exclude='__pycache__' -czf - gateway scripts hosts | "${SSH[@]}" "$target" "tar -xzf - -C '$release'"
"${SSH[@]}" "$target" "bash '$release/gateway/deploy.sh' '$HOST_TARGET' '$CADDY_IMAGE'"
