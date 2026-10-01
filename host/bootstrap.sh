#!/usr/bin/env bash
# Root-only, rerunnable bootstrap for Ubuntu 22.04/24.04 and Alibaba Cloud Linux 3.
# Does not format disks, remove container data or deploy apps.
set -euo pipefail

compose_supported() {
    local version
    version=$(docker compose version --short 2>/dev/null) || return 1
    python3 - "$version" <<'PY'
import re, sys
match = re.match(r'v?(\d+)\.(\d+)\.(\d+)', sys.argv[1])
sys.exit(0 if match and tuple(map(int, match.groups())) >= (2, 24, 0) else 1)
PY
}

install_runtime() {
    local os_release=${1:-/etc/os-release}
    local ID='' VERSION_ID='' VERSION_CODENAME=''
    local install_engine=false install_compose=false
    . "$os_release"
    case "$ID:$VERSION_ID" in
        ubuntu:22.04|ubuntu:24.04|alinux:3|alinux:3.*) ;;
        *) echo 'Use Ubuntu 22.04/24.04 or Alibaba Cloud Linux 3.' >&2; return 1 ;;
    esac
    if ! command -v docker >/dev/null; then
        install_engine=true
    elif [[ "$(docker --version)" != 'Docker version '* ]]; then
        echo 'The existing docker command is not Docker Engine; configure Docker CE separately.' >&2
        return 1
    fi
    if [[ "$ID" == ubuntu ]]; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get install -y ca-certificates curl gnupg python3 sqlite3 tar util-linux
    else
        dnf -y install ca-certificates curl python3 sqlite tar util-linux
    fi
    compose_supported || install_compose=true
    if [[ "$install_engine" == true || "$install_compose" == true ]]; then
        if [[ "$ID" == ubuntu ]]; then
            install -m 0755 -d /etc/apt/keyrings
            curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
            chmod a+r /etc/apt/keyrings/docker.asc
            printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "$(dpkg --print-architecture)" "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.list
            apt-get update
            if [[ "$install_engine" == true ]]; then
                apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            else
                apt-get install -y docker-compose-plugin
            fi
        else
            dnf -y install dnf-plugins-core
            dnf config-manager --add-repo=https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
            dnf -y install dnf-plugin-releasever-adapter --repo alinux3-plus
            if [[ "$install_engine" == true ]]; then
                dnf -y install device-mapper-persistent-data lvm2
                dnf -y install --nobest docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            else
                dnf -y install --nobest docker-compose-plugin
            fi
        fi
    fi
    compose_supported || { echo 'Docker Compose 2.24+ required; check the package installation.' >&2; return 1; }
    docker compose version
}

# Sourcing exposes the runtime functions without installing packages or preparing a host.
[[ "${BASH_SOURCE[0]}" == "$0" ]] || return 0

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
install_runtime
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
