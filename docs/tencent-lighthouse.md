# 腾讯云轻量服务器接入

## 当前登记状态

| 项目 | 配置 |
| --- | --- |
| 主机 ID / infra GitHub Environment | `tencent-shanghai-01` |
| 产品 | 腾讯云轻量应用服务器（Lighthouse） |
| 地域 | 上海，`ap-shanghai` |
| 公网 IPv4 | `124.220.81.113` |
| 系统 | Ubuntu 24.04 |
| 业务环境 | `prod` |
| 已选择服务 | RealQuest，`services=["realquest"]`；尚未实际部署 |

仓库已准备 RealQuest 网关、主机目录和 PostgreSQL/COS 备份支持。服务器初始化、GitHub Secrets、实际 DNS/备案及业务部署后续执行。腾讯云资源采用已购主机接入，本仓库目前没有腾讯云 Terraform 资源模块。RealQuest 接入细节见[网关与备份指南](realquest.md)。

可在本地校验当前发布配置：

```bash
python3 scripts/render_host.py tencent-shanghai-01 --check --require-services
```

空清单仍可用于登记其他待接入主机，测试使用隔离的空主机 fixture。渲染、重载或发布空主机网关会失败并要求先添加服务；Actions 发布在 SSH 前检查，服务器端发布在 Docker 和创建候选 release 前检查。将已有服务主机清单改为空也不会通过发布来关闭其网关。

## 后续主机初始化

以下步骤留到实际初始化时执行。先更新系统、核验 SSH 主机指纹并配置管理连接。通过轻量服务器的[防火墙管理](https://cloud.tencent.com/document/product/1207/44577)设置访问规则：SSH 限制到管理/部署来源，80/443 用于未来的公网网关，业务和数据库不映射公网端口。部署通道使用 GitHub Actions 时需单独确保 runner 的 SSH 可达性。

把本仓库通过可信渠道上传到服务器后，可初始化部署账号、Docker/Compose、网关及 RealQuest 目录：

```bash
sudo bash host/bootstrap.sh deploy realquest tencent-shanghai-01 prod
```

若仅准备主机而不创建业务目录，第二个参数可显式传入空字符串 `''`；省略参数仍沿用旧的 `shadowtable` 默认值。随后给 `deploy` 配置专用 SSH 公钥，重新登录并确认 `docker info`、`docker compose version` 正常。此脚本不启动网关或业务。

## 后续选择服务与发布

1. 在 `hosts/tencent/shanghai/01/host.json` 的 `services` 填入实际承载服务，当前已选择 RealQuest。现有路由支持 `echooo`、`shadowtable`、`wenlv`、`just-works`、`inkmind`、`directo`、`realquest`。新业务需要同时注册域名变量和路由，并扩展初始化脚本的服务白名单。
2. 将选中的服务列表作为 bootstrap 第二个参数再次运行，准备对应目录和 `tencent-prod` 业务标记。这里只准备主机目录，业务仓库需要另行增加自己的腾讯云发布目标；本仓库变更不会自动修改业务仓库。
3. 在对应 `gateway.env.example` 中加入选中服务的域名变量，当前已配置 `REALQUEST_DOMAIN=realquest.jastcraft.com`。复制到服务器 `/opt/gateway/gateway.env`，填入邮箱和实际 Caddy 镜像引用，设为部署账号所有、权限600。镜像使用已经构建成功的完整 `registry/repository@sha256:...`，配置只读拉取凭据；可以复用现有 ACR。
4. 在 infra 仓库手动创建 GitHub Environment `tencent-shanghai-01`，限制部署分支为 main。设置 Variable `GATEWAY_TARGET=tencent-shanghai-01`，以及 Secrets `SSH_HOST=124.220.81.113`、`SSH_PORT`（默认22）、`SSH_USER=deploy`、`SSH_KEY`、`SSH_KNOWN_HOSTS`。指纹从可信管理连接核验，不把私钥或密码提交到仓库。
5. 域名在中国大陆提供网站服务前完成[腾讯云备案](https://cloud.tencent.com/document/product/243/18909)；已在其他接入商备案的域名办理[腾讯云接入备案](https://cloud.tencent.com/document/product/243/97669)。再配置 DNS、80/443 连通和业务自己的站点地址、回调/CORS 等配置。
6. 手动运行 **Deploy gateway**，选择 `tencent-shanghai-01` 和已测试的不可变镜像。各业务仓库分别部署应用，使用本机 `<服务>_proxy` 网络和路由定义的 upstream 别名。网关发布不启停业务容器。先使用独立测试子域名完成 HTTPS 和业务验收，再接正式流量。

## 后续 COS 备份

主机与备份云可分别选择；可以继续使用 S3/OSS，也可以使用腾讯云 COS。只有部署了业务并已有真实数据库后，才配置备份任务。ShadowTable/InkMind 使用 SQLite，RealQuest 使用 PostgreSQL。

RealQuest 使用 `host/backup-realquest.env.example`；SQLite 服务可使用 `host/backup-tencent.env.example`。设置实际 `BACKUP_SERVICE`、`BACKUP_DESTINATION`（独立业务前缀）和 `BACKUP_COS_ENDPOINT`。默认示例使用上海 `cos.ap-shanghai.myqcloud.com`；目的地必须是 `cos://` 路径，桶名含实际 APPID。

安装并配置官方 [COSCLI](https://cloud.tencent.com/document/product/436/63144)。systemd 备份以 root 运行，CLI 及其凭据必须在 root 环境可用；使用仅能访问备份桶和业务前缀的凭据，存入受保护的 COSCLI 配置，不写入仓库或备份 env 模板。脚本使用 [coscli cp](https://intl.cloud.tencent.com/zh/document/product/436/43256) 上传一致数据库快照，并显式传递 endpoint；上传失败时不会清理本地历史备份。

COS 桶需单独创建并配置私有访问、版本控制和生命周期；仓库不会自动创建或修改桶。完成首次上传和恢复验证后，再按[多云操作指南](multicloud.md#5-启用备份和基础监控)启用相应 timer。空主机不启用备份任务。
