#!/usr/bin/env bash
set -euo pipefail

# Retry only temporary Docker Hub responses, preserving other build failures.
log=$(mktemp)
trap 'rm -f "$log"' EXIT
for attempt in 1 2 3; do
    if docker "$@" 2>&1 | tee "$log"; then
        exit 0
    else
        status=${PIPESTATUS[0]}
    fi
    # A failed log writer must not turn a successful build into a retry.
    if (( status == 0 )); then exit 1; fi
    if (( attempt == 3 )) || ! grep -Eq 'unexpected status.*https://(auth\.docker\.io/token|registry-1\.docker\.io/).*: (500|502|503|504)([[:space:]:]|$)' "$log"; then
        exit "$status"
    fi
    delay=$((10 * attempt))
    printf 'Docker Hub returned a temporary server error; retrying build in %ss (attempt %s/3).\n' "$delay" "$((attempt + 1))" >&2
    sleep "$delay"
done
