# RealQuest 接入上海腾讯云

## 已准备配置

| 项目 | 值 |
| --- | --- |
| infra 主机目标 / Environment | `tencent-shanghai-01` |
| RealQuest 业务目标 / Environment | `tencent-prod` |
| 域名 | `realquest.jastcraft.com` |
| 网关变量 | `REALQUEST_DOMAIN` |
| 前端代理网络 / 别名 / 端口 | `realquest_proxy` / `realquest-upstream` / `80` |
| 业务 Compose 项目 / 数据库卷 | `realquest` / `realquest_postgres_data` |

腾讯云清单已选择 `realquest`，网关只代理 RealQuest Nginx。Nginx 保留同源 `/api`，后端和 PostgreSQL 留在 RealQuest 私有网络。业务镜像、生产 Compose、迁移、CI 发布和回退逻辑在 RealQuest 仓库的 `deploy/`，具体流程见该仓库 `docs/deployment.md`。

当前只完成仓库部署适配。服务器初始化、GitHub Environment/Secrets、DNS/备案、镜像推送、云备份桶和实际应用部署后续执行。没有执行腾讯云资源创建或 Terraform apply。

## 后续初始化和发布

1. 通过可信连接接入服务器，配置轻量主机防火墙，确保管理机和实际 runner 的 SSH 可达；网站入口开放80/443。
2. 在服务器 infra 检出根目录执行 `sudo bash host/bootstrap.sh deploy realquest tencent-shanghai-01 prod`。脚本创建账号、运行环境、应用目录及两个部署标记，不启动业务。通用 `/opt/realquest/data` 目录不用于 PostgreSQL，实际数据使用固定命名卷。
3. 为 infra 建立 `tencent-shanghai-01` Environment，设置 `GATEWAY_TARGET=tencent-shanghai-01` 和独立 SSH Secrets；为 RealQuest 建立 `tencent-prod`，设置 `DEPLOY_TARGET=tencent-prod` 和对应 SSH Secrets。服务器两个标记必须分别匹配。
4. 配置服务器 `/opt/gateway/gateway.env`，沿用本主机的证书卷名，设置真实 Caddy digest、邮箱及 `REALQUEST_DOMAIN=realquest.jastcraft.com`。域名完成腾讯云备案/接入、DNS 指向 `124.220.81.113`、80/443 连通后，手动 **Deploy gateway** 到 `tencent-shanghai-01`。
5. 为 RealQuest 配置 ACR 前后端独立 repository 及 CI 推送凭据、部署账号只读拉取凭据、服务器 `/opt/realquest/app.env`。密码强随机、Cookie Secure、允许来源为 `https://realquest.jastcraft.com`，env 由部署账号所有且权限600。
6. RealQuest **Container CI and build** 成功后，手动 **Deploy tested images** 选择 `tencent-prod` 和 Build run ID。工作流使用同一已测试提交和镜像 digest，不重新构建。业务发布取得同一应用锁、已有库先备份、显式迁移、检查本机 HTTPS 及 `/api/health` 后才提升 current。

## PostgreSQL 定时备份

安装公共运维脚本后，以 root 准备单独的 RealQuest 配置：

```bash
sudo bash host/install-operations.sh
sudo install -m 600 host/backup-realquest.env.example /etc/jastcraft/backup-realquest.env
```

填入真实私有 COS 桶和 RealQuest 前缀、endpoint，配置 root 环境的 COSCLI 凭据。不要把云密钥写入仓库；桶版本控制、生命周期和所需访问权限单独设置。

`backup.sh` 取得 `/opt/realquest/deploy.lock`，`backup-postgres.sh` 要求恰好一个运行中的 `realquest` / `db` 容器，用 `pg_dump --format=custom` 生成权限600的 `.dump`，再用 `pg_restore --list` 验证。dump/验证失败删除不完整文件；上传失败保留完整本地快照；只有上传成功才清理14天以前的 `realquest-*.dump`，不改 SQLite 备份。

```bash
sudo systemctl start jastcraft-backup@realquest.service
sudo journalctl -u jastcraft-backup@realquest.service --no-pager -n 50
# 仅在首次上传及独立数据库恢复验证成功后启用：
sudo systemctl enable --now jastcraft-backup@realquest.timer
```

发布失败且数据库 revision 未变时业务脚本可恢复旧镜像；迁移失败、revision 变化或无法确认时保持应用停止，保留备份和数据库，需按 RealQuest 指南评估恢复，不自动覆盖数据库、downgrade 或删除卷。旅程凭证不代替数据库备份。本地 SQLite 存档迁移到 PostgreSQL 需要另行安排。
