# 为现有公共网关增加文旅拾光

本流程只接入新站点，保留现有 Echooo/ShadowTable 域名、Caddy 镜像 digest 和证书卷。业务侧需要生产 Web 加入 `wenlv_proxy`，别名 `wenlv-upstream`，监听容器 80 端口。

1. 为新域名配置指向此服务器的 DNS，确认 80/443 可访问。
2. 备份 `/opt/gateway/gateway.env` 和当前 Git revision。更新 `/opt/gateway/repo` 到本次提交。
3. 在 `/opt/gateway/gateway.env` 增加 `WENLV_DOMAIN=实际域名`，必须与业务 `.env` 相同、与其他站点不同；保持其他配置原值。
4. 以有 Docker 权限且能写 `/opt/gateway/config` 的部署用户执行以下命令。需要 Bash、flock，安排一次短暂的公共网关重建窗口。

```bash
docker network inspect wenlv_proxy >/dev/null 2>&1 || docker network create wenlv_proxy
(
  set -euo pipefail
  exec 9>/opt/gateway/deploy.lock
  flock -n 9 || { echo 'Another gateway change is running'; exit 1; }
  gateway_repo=/opt/gateway/repo
  gateway_compose() { bash "$gateway_repo/gateway/compose.sh" "$@"; }
  gateway_compose config --quiet
  # Validate the candidate with NEW env/network settings, without publishing ports.
  gateway_compose run --rm --no-deps \
    -v "$gateway_repo/gateway/Caddyfile:/tmp/Caddyfile.candidate:ro" \
    caddy caddy validate --config /tmp/Caddyfile.candidate --adapter caddyfile
  cp /opt/gateway/config/Caddyfile /opt/gateway/config/Caddyfile.before-wenlv
  cp "$gateway_repo/gateway/Caddyfile" /opt/gateway/config/Caddyfile.next
  mv /opt/gateway/config/Caddyfile.next /opt/gateway/config/Caddyfile
  gateway_compose up -d --wait --wait-timeout 60 caddy
  gateway_compose logs --tail=100 caddy
)
```

这次不能只运行 `reload.sh`，因为运行中的容器还没有 `WENLV_DOMAIN` 环境变量和 `wenlv_proxy` 网络。已有证书卷继续沿用，无需重新发布网关镜像。

然后手动运行文旅拾光部署；应用就绪前仅新域名可能返回 502。完成后验证新域名的 `/api/health`、首页和登录，以及原 Echooo、ShadowTable 入口。后续业务发布不需要操作网关。

若网关更新失败，按相同 `/opt/gateway/deploy.lock` 锁恢复旧 Git revision、备份的 gateway.env 和 `Caddyfile.before-wenlv`（复制回运行配置），再用旧版 `compose.sh up -d` 恢复并验收原站点。不要删除或重新创建证书卷。业务数据库恢复由业务仓库单独管理。
