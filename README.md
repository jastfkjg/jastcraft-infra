# Jastcraft infrastructure

独立管理同一台 EC2 的 Caddy 网关。业务仓库只更新自己的应用与数据服务，网关的变更独立审核、部署。此仓库不保存密钥、数据库或证书。

## 最终布局

- `/opt/gateway/repo`：本仓库的服务器检出；`/opt/gateway/config/Caddyfile`：运行配置。
- `/opt/gateway/gateway.env`：服务器专属域名、镜像 digest、卷名，权限 600。
- `/opt/echooo`、`/opt/shadowtable`：各自业务发布与持久数据。
- `echooo_proxy`：仅网关及 echooo 应用加入；数据库保留 echooo 默认网络。
- `shadowtable_proxy`：仅网关及 ShadowTable 加入。
- 只有网关发布 80/443；业务和数据库不发布宿主机端口。

需要 Linux、Docker Engine、Compose >=2.24、Bash、flock、curl、Python3、tar。基础设施首次迁移由有 Docker 权限的管理员执行。Docker 权限等同于宿主机高权限。

## 首次迁移（维护窗口）

先将三个仓库的修改发布到各自远程仓库。ShadowTable main 推送会自动部署，首次准备服务器期间应先禁用该仓库 Actions 或暂不配置部署 Secrets；等网关就绪后启用。暂停 echooo 发布，避免迁移期间旧流水线重建 proxy。

### 1. 盘点现有服务，保留恢复入口

在服务器记录旧 release 的真实路径并找出当前 proxy：

```bash
readlink -f /opt/echooo/current
docker ps --filter label=com.docker.compose.project=echooo
docker ps -q --filter label=com.docker.compose.project=echooo --filter label=com.docker.compose.service=proxy
```

将输出的 proxy 容器 ID 保存为 `OLD_PROXY_ID`（后续命令在同一 shell 执行）。检查它的镜像、挂载和网络：

```bash
docker inspect "$OLD_PROXY_ID" --format '{{.Config.Image}}'
docker inspect "$OLD_PROXY_ID" --format '{{json .Mounts}}'
docker inspect "$OLD_PROXY_ID" --format '{{json .NetworkSettings.Networks}}'
```

确认 `/data`、`/config` 对应的真实卷名。备份现有业务环境文件、Caddyfile 和 PostgreSQL（沿用 echooo 的 pg_dump 流程）。记录旧 PUBLIC_SCHEME、DOMAIN、COOKIE_SECURE。迁移时保留原 origin，不同时改数据库密码或业务域名。

### 2. 初始化独立网关

以下假定 `deploy` 是现有可信部署用户；按服务器实际账号替换。将本仓库检出到 `/opt/gateway/repo`，不要把真实环境文件加入 Git。

```bash
sudo install -d -o deploy -g deploy -m 700 /opt/gateway /opt/gateway/config
# 在此将仓库 clone/上传到 /opt/gateway/repo
docker network inspect echooo_proxy >/dev/null 2>&1 || docker network create echooo_proxy
docker network inspect shadowtable_proxy >/dev/null 2>&1 || docker network create shadowtable_proxy
cp /opt/gateway/repo/gateway/gateway.env.example /opt/gateway/gateway.env
chmod 600 /opt/gateway/gateway.env
cp /opt/gateway/repo/gateway/Caddyfile /opt/gateway/config/Caddyfile
```

编辑 gateway.env：

- `CADDY_IMAGE`：复制旧 echooo release 的 image.env 中 CADDY_IMAGE 的不可变 digest。首次无需重新发布镜像，但必须保留该 ACR digest，不能被 echooo 仓库清理策略删除。后续网关镜像由基础设施单独维护，可镜像到独立 ACR 仓库。
- `CADDY_DATA_VOLUME`、`CADDY_CONFIG_VOLUME`：上一步实际查到的卷名。网关将它们作为 external 卷接管，后续不依赖 echooo Compose 声明。
- `ECHOOO_ADDRESS`：现有 HTTPS 域名；如果 echooo 仍以 HTTP IP 提供服务，填原 `http://IP` 保持原入口。HTTPS 升级另行同步调整此项和 echooo origin/cookie。
- `SHADOWTABLE_DOMAIN`：牌桌正式域名（不带协议或路径）。两个业务不能使用相同域名。
- `ACME_EMAIL`：真实证书联系邮箱。

检查域名 A/AAAA、EC2 防火墙、安全组和 80/443。不要开放应用端口。

```bash
bash /opt/gateway/repo/gateway/compose.sh config --quiet
bash /opt/gateway/repo/gateway/compose.sh pull
bash /opt/gateway/repo/gateway/compose.sh run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

`run` 不发布服务端口，不会启动第二个公网入口。这里只校验配置；不能替代实际 HTTPS 验证。

### 3. 桥接现有 echooo 应用

找出当前应用容器并临时接入代理网络（让旧版本在网关切换期间仍能提供服务）：

```bash
ECHOOO_APP_ID=$(docker ps -q --filter label=com.docker.compose.project=echooo --filter label=com.docker.compose.service=app)
docker network connect --alias echooo-upstream echooo_proxy "$ECHOOO_APP_ID"
```

如果已连接，先 inspect 核对 alias，不要重复 connect。这个手工连接只用于首次迁移；新版 echooo Compose 已正式声明网络，后续重建自动加入。

### 4. 切换网关并验证 echooo

在旧 Caddy 停止后备份证书卷（下面需替换 `ACTUAL_DATA_VOLUME` 等真实值；备份目录应权限 700）：

```bash
docker stop "$OLD_PROXY_ID"
# 使用已经拉取的 Caddy 镜像及只读挂载，分别归档 /data 与 /config 卷。
# 示例：docker run --rm --entrypoint tar -v ACTUAL_DATA_VOLUME:/source:ro CADDY_IMAGE_DIGEST -C /source -czf - . > caddy-data.tgz
bash /opt/gateway/repo/gateway/compose.sh up -d
bash /opt/gateway/repo/gateway/compose.sh logs --tail 100 caddy
```

新旧 Caddy 不可同时占用端口、写同一证书卷。用实际 echooo origin 验证 `/health`、登录、流式输出，并确认 POST `/api/auth/setup` 返回 403。ShadowTable 尚未部署时其域名返回 502 属于此步骤的预期状态。

**切换失败的回退：**先 `bash /opt/gateway/repo/gateway/compose.sh stop caddy`，再 `docker start "$OLD_PROXY_ID"`，验证旧入口。保留旧容器、旧 release 和卷，排查后重试。不要执行 `down -v`。

### 5. 发布拆分后的 echooo

网关正常后，运行新版 echooo Actions。新版只发布 app/db，原 postgres 数据卷与项目名保持不变。成功后核对公网业务，移除停止的旧 proxy 容器：

```bash
docker rm "$OLD_PROXY_ID"
```

新版 Compose 可能提示旧 proxy 为 orphan，这是过渡期预期现象。不要使用旧工作流发布。**迁移后不能直接用旧 release 的 Compose 执行整栈 up：它会尝试重建旧 Caddy。** 要回退旧应用代码，使用拆分后的 Compose 和旧应用 image digest，保留当前数据库镜像；不恢复旧 proxy。

### 6. 部署 ShadowTable

按 ShadowTable 的 `docs/deployment.md` 初始化 `/opt/shadowtable`、环境与数据权限，配置 ACR/GitHub Secrets，再触发该项目 main 的部署。验证 `/health`、网页、访客登录、两台设备建房/加入及重启恢复。

最后恢复正常发布权限，保存迁移记录与证书备份，并安排业务数据的定时异机备份。

## 独立网关镜像发布

为基础设施建立独立 ACR 镜像仓库。在本仓库 GitHub Variables 配置 `ACR_REGISTRY`、`ACR_NAMESPACE`、`ACR_REPOSITORY`，Secrets 配置 `ACR_USERNAME`、`ACR_PASSWORD`。手动运行 **Publish gateway image**，它校验 Caddy 配置并构建 amd64/arm64 镜像，在 Actions 摘要输出不可变 digest。将其填入服务器 gateway.env 的 CADDY_IMAGE，再按下面的镜像升级步骤发布。

`gateway/Dockerfile` 固定 Caddy 版本，由基础设施单独升级。首次迁移可以直接使用独立仓库镜像，或复用原 digest 减少迁移变量；复用时保留旧镜像，待切换独立镜像并确认可回退后再调整旧仓库清理规则。业务 Actions 不再发布任何网关镜像。

## 日常网关变更

网关不跟随业务发布。更新仓库中的 Caddyfile、通过 CI 校验，服务器拉取对应提交后：

```bash
bash /opt/gateway/repo/gateway/reload.sh
```

脚本以运行中 Caddy 的环境和版本校验候选配置，原子替换文件并 reload；失败会恢复旧文件并重新加载。挂载整个 config 目录，避免单文件 bind mount 在替换 inode 后仍读取旧文件。reload 只针对 Caddyfile；不会更新容器环境变量。

**修改 gateway.env、镜像或 Compose 时**：备份旧 env 与 Git revision，使用 `compose.sh config --quiet`、`pull`、`run --rm --no-deps caddy caddy validate ...` 校验；在同一个 `/opt/gateway/deploy.lock` 锁下执行 `compose.sh up -d`，然后逐站验收。镜像更新应固定 digest。失败时恢复旧 env/配置/Git revision 后重新 up。环境变更通常重建网关，安排维护窗口。

证书自动续期依赖 DNS、80/443 连通和 `/data` 持久化。监控网关日志、证书、磁盘和 EC2 资源。公共网关及单台 EC2 仍是共享故障域；本设计隔离发布，不提供跨主机高可用。
