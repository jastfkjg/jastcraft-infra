#!/usr/bin/env bash
# Root-only, rerunnable bootstrap for Ubuntu 22.04/24.04; does not format disks or deploy apps.
set -euo pipefail
[[ "$EUID" == 0 ]] || { echo 'Run bootstrap with sudo/root' >&2; exit 1; }
deploy_user=${1:-deploy}
services=${2:-shadowtable}
host_target=${3:?Usage: bootstrap.sh DEPLOY_USER SERVICES HOST_TARGET [APP_ENVIRONMENT]}
app_environment=${4:-prod}
[[ "$host_target" =~ ^(aws|aliyun)-([a-z0-9]+)-([0-9]{2})$ ]]
cloud=${BASH_REMATCH[1]}
[[ "$app_environment" =~ ^(prod|staging)$ ]]
app_target="$cloud-$app_environment"
[[ "$deploy_user" =~ ^[a-z_][a-z0-9_-]*$ ]]
[[ "$services" =~ ^(echooo|shadowtable|wenlv)(,(echooo|shadowtable|wenlv))*$ ]]
. /etc/os-release
[[ "$ID" == ubuntu && ( "$VERSION_ID" == 22.04 || "$VERSION_ID" == 24.04 ) ]] || { echo 'Use Ubuntu 22.04 or 24.04' >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg python3 sqlite3 tar util-linux
if ! command -v docker >/dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "$(dpkg --print-architecture)" "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
docker compose version
systemctl enable --now docker
id "$deploy_user" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$deploy_user"
usermod -aG docker "$deploy_user"
install -d -o "$deploy_user" -g "$deploy_user" -m 700 /opt/gateway /opt/gateway/config /opt/gateway/releases
if [[ -f /opt/gateway/deployment-target ]]; then
    [[ "$(cat /opt/gateway/deployment-target)" == "$host_target" ]] || { echo 'Existing host has a different deployment target' >&2; exit 1; }
else
    printf '%s\n' "$host_target" > /opt/gateway/deployment-target
    chown "$deploy_user:$deploy_user" /opt/gateway/deployment-target
fi
IFS=',' read -r -a app_services <<< "$services"
for service in "${app_services[@]}"; do
    install -d -o "$deploy_user" -g "$deploy_user" -m 700 "/opt/$service" "/opt/$service/releases" "/opt/$service/backups"
    # Preserve owners of existing data. Business-specific database setup remains in its repository.
    if [[ ! -d "/opt/$service/data" ]]; then install -d -o 1000 -g 1000 -m 700 "/opt/$service/data"; fi
    if [[ -f "/opt/$service/deployment-target" ]]; then
        [[ "$(cat "/opt/$service/deployment-target")" == "$app_target" ]] || { echo 'Existing application has a different deployment target' >&2; exit 1; }
    else
        printf '%s\n' "$app_target" > "/opt/$service/deployment-target"
        chown "$deploy_user:$deploy_user" "/opt/$service/deployment-target"
    fi
done
printf 'Bootstrap ready. Add the deployment public key to this account, log in again, and configure gateway.env and business env files.\n'
