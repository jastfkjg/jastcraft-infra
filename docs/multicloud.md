# 多云部署操作指南

本仓库提供代码和配置模板，不包含真实云账号、私钥或数据库。当前实现支持 EC2/ECS 和已有腾讯云轻量应用服务器的 Docker Compose 单主机运行方式；Terraform 资源模块目前仅覆盖 AWS/阿里云。跨云双活和数据库复制不在此通道中；ShadowTable 生产只保留一个写入端。

## 1. 提交代码与配置 GitHub

先完成本节的GitHub配置，再分别提交并推送 `jastcraft-infra` 与 `ShadowTable` 的本次修改到 main。ShadowTable push main 只运行 CI 并发布镜像，已经取消 AWS 自动部署。infra push 只验证配置和 Terraform schema。

ShadowTable 仓库级 Variables：`ACR_REGISTRY` / `ACR_NAMESPACE` / `ACR_REPOSITORY`；Secrets：`ACR_USERNAME` / `ACR_PASSWORD`。构建沿用现有 ACR 配置，详见业务 `docs/deployment.md`。各主机可以继续共用现有 ACR，先验证实际拉取连通性，不必新购镜像服务。

infra 网关镜像构建继续使用现有仓库级 Variables `ACR_REGISTRY` / `ACR_NAMESPACE` / `ACR_REPOSITORY` 和 Secrets `ACR_USERNAME` / `ACR_PASSWORD`。建立或保留独立 Caddy 镜像仓库。

两仓库的部署目标名称不同，以区分业务环境与具体主机：

| 服务器 | ShadowTable Environment | infra Environment / 主机目标 |
| --- | --- | --- |
| 新加坡 EC2 | `aws-prod` | `aws-singapore-01` |
| 北京 ECS | `aliyun-prod` | `aliyun-beijing-01` |
| 上海腾讯云轻量 | 尚未配置业务部署目标 | `tencent-shanghai-01` |

AWS/阿里云两台已有业务；腾讯云主机目前仅登记，服务清单为空，尚未初始化或部署。没有独立 staging 服务器。主机 ID 不包含业务或环境；主机清单中的 `services`、`environment` 与 `region` 分别描述承载业务、业务环境和云 API 地域。

在每个仓库建立需要的 Environments，将部署分支限制为 main。每个 Environment 配置 `SSH_HOST`、`SSH_PORT`（默认22）、`SSH_USER`、`SSH_KEY`、`SSH_KNOWN_HOSTS` Secrets。host key 通过云控制台/可信管理连接核验；非22端口使用 `[host]:port` 格式。不要在仓库级保存一组共用 SSH Secrets，以免多个目标回落到同一服务器。

ShadowTable Environment Variable `DEPLOY_TARGET` 必须等于业务环境名；infra Environment Variable `GATEWAY_TARGET` 必须等于主机目标 ID。服务器标记也必须一致：`/opt/shadowtable/deployment-target` 存业务环境名，`/opt/gateway/deployment-target` 存主机 ID。缺失/不匹配时发布会拒绝执行。

目标是不同服务器。当前 `/opt/shadowtable`、Compose 项目与 proxy 网络不能在同一主机承载两份 staging/prod 实例。按目标限制部署并发，服务器端另有 flock 锁。

## 2. 选择现有主机或创建新主机

### 2.1 接入现有 EC2/ECS 与更新主机名称

现有 EC2/ECS 继续使用现有 Docker、业务数据和证书卷，不要把新主机 Terraform stack 直接 apply 到它。先备份 `/opt/gateway/gateway.env`、`/opt/gateway/config` 并记录实际证书卷名称。更新服务器 infra 检出到新版本。

先在 GitHub 建立 `aws-singapore-01`、`aliyun-beijing-01` Environments，分别迁入对应主机的 SSH Secrets，设置同名 `GATEWAY_TARGET`，部署分支限制为 main。旧 Environment 不会因代码改名自动迁移；确认新目标发布成功后再删除旧 Environment。ShadowTable 的 `aws-prod` / `aliyun-prod` 与应用标记保留。

部署账号在对应服务器补充或更新标记，新加坡 EC2：

```bash
printf '%s\n' aws-singapore-01 > /opt/gateway/deployment-target
printf '%s\n' aws-prod > /opt/shadowtable/deployment-target
mkdir -p /opt/gateway/releases
```

北京 ECS：

```bash
printf '%s\n' aliyun-beijing-01 > /opt/gateway/deployment-target
printf '%s\n' aliyun-prod > /opt/shadowtable/deployment-target
mkdir -p /opt/gateway/releases
```

保留 `/opt/gateway/gateway.env` 里的真实域名、邮箱、镜像和 `CADDY_DATA_VOLUME/CADDY_CONFIG_VOLUME`，不要用新主机示例覆盖这些值。权限600、部署账号所有。网关改名不需要更改卷名，否则会使用新的证书卷。使用新的主机目标手动发布网关以更新生成配置。旧 release 的 `host` 文件可能仍记录旧名称，不要批量覆盖历史 release。

需要后续把现有资源纳管时，按实际 VPC/子网/实例/磁盘拓扑编写配置并 import，审查 plan 达到无意外替换后再 apply。本仓库的资源模块定义的是新建独立主机，不自动识别现有 EC2/ECS。

Terraform 目录现在是 `terraform/stacks/aws/singapore/01` 与 `terraform/stacks/aliyun/beijing/01`。若旧目录已经管理过资源，把原真实 tfvars/backend 配置和本地 state（若有）安全迁入新目录，保留原资源 `name`、实际地域以及 backend bucket/key/prefix/锁配置，不要用新建模板覆盖。目录和主机 ID 改名不会迁移远程 state；尤其不要因示例路径更新而连接空 state 再 apply。已有资源的系统盘/user_data 更新按原保护策略处理。

### 2.2 手动准备新的 ECS/EC2

支持 Ubuntu 22.04/24.04 和 Alibaba Cloud Linux 3（含 3.2104 LTS），脚本自动选择 apt/dnf。设置管理机和 GitHub runner 出口的 SSH 访问规则，公网仅开放80/443业务入口。先从管理机上传本仓库或使用可信方式 clone，再执行：

```bash
sudo bash host/bootstrap.sh deploy shadowtable,just-works aliyun-beijing-01 prod
```

新加坡主机使用 `sudo bash host/bootstrap.sh deploy echooo,shadowtable,wenlv aws-singapore-01 prod`。第四个参数显式描述业务环境，默认 `prod`；主机 ID 不再推导业务环境。初始化安装 Docker/Compose、Python、SQLite 等工具，创建账号、目录和目标标记，不格式化磁盘、不发布业务。将专用部署公钥配置到 `deploy` 的 authorized_keys，重新登录使 Docker 组生效，检查 `docker info` 和 `docker compose version`（至少2.24）。已有数据目录保留原所有者。 Alibaba Cloud Linux 3 使用[阿里云 Docker CE 镜像源和 releasever 兼容插件](https://help.aliyun.com/zh/ecs/user-guide/install-and-use-docker)。脚本不会自动卸载 Docker、Podman 或删除容器数据；已有 Docker 可用时仅按需安装 Compose 插件，要求 Compose >=2.24。

### 2.3 使用 Terraform 新建主机（可选）

安装 Terraform >=1.10（CI固定1.14.9）。按独立目录操作，例如阿里云正式主机：

```bash
cd terraform/stacks/aliyun/beijing/01
cp terraform.tfvars.example terraform.tfvars
cp backend.tfbackend.example backend.tfbackend
```

填写 region、可用区、当地可用的实例类型、所选系统镜像ID（Ubuntu 22.04/24.04 或 Alibaba Cloud Linux 3）、SSH公钥、管理机/runner真实出口CIDR、全局唯一的备份桶名称；部署用户默认 `deploy`。示例值不能直接 apply，`ssh_cidrs` 不允许 `0.0.0.0/0`。只有80/443公网入口被创建。ARM64镜像需选择匹配的实例架构；业务镜像同时包含amd64/arm64。

state 存储必须先存在，独立于业务备份桶：

- AWS：预建私有 S3 state bucket，启用版本控制；backend 使用 `encrypt=true` 与 `use_lockfile=true`。凭据包含 state 对象和锁文件的必要权限。
- 阿里云：预建私有 OSS state bucket，启用版本控制；预建 TableStore instance/table，String 主键名为 `LockID`，填写 endpoint/table 以启用锁。backend 使用 `encrypt=true`。

云凭据通过 CLI profile/环境变量注入；不要写入 tfvars 或 backend 文件。所有真实 `*.tfvars`、`*.tfbackend`、state 和 plan 文件已被忽略。

```bash
terraform init -backend-config=backend.tfbackend
terraform plan -out=host.tfplan
# 审查资源、地域、规格、网络和费用后再执行：
terraform apply host.tfplan
terraform output
```

模块创建 VPC、子网/交换机、安全组、虚拟机、加密系统盘、私有备份桶（版本控制、90天备份保留、旧版本30天）及限于 shadowtable备份前缀的实例 IAM/RAM role。cloud-init 自动执行初始化脚本。AWS使用EIP，阿里云使用实例公网IP。等待 `cloud-init status --wait` 成功再配置发布；实例名称与云IAM/RAM role名称需在账号内唯一。

虚拟机和备份桶配置防删除保护。AWS user_data/镜像改变可能要求替换实例，Terraform会因防删除保护拒绝；阿里云 provider 可能在原地替换系统盘，故明确忽略 image_id/user_data 后续漂移。OS和初始化脚本升级要单独安排，不通过修改image_id直接更新存有生产数据的系统盘。

镜像资源是可选的：默认 `image_repositories=[]`，继续用现有ACR。AWS填入列表会创建私有不可覆盖tag的ECR仓库；阿里云填入列表还需现有ACR企业版 `acr_instance_id`，创建私有namespace/repository，不自动购买企业版实例。现有个人版ACR继续在控制台管理。构建切换ECR还需额外的OIDC登录适配，当前ACR构建路径可直接服务两云。

资源层目前通过上述 CLI plan/apply 执行；GitHub仅校验，不自动创建或修改云资源。

### 2.4 接入已有腾讯云轻量应用服务器

上海主机 `tencent-shanghai-01` 使用 `ap-shanghai`，公网 IP 为 `124.220.81.113`，系统为 Ubuntu 24.04。清单 `hosts/tencent/shanghai/01/host.json` 当前设置 `services=[]`，只登记部署目标。腾讯云主机支持、空清单检查和 COS 备份入口已具备，服务器初始化、GitHub Environment 设置及业务发布后续单独执行，详见[腾讯云轻量服务器接入指南](tencent-lighthouse.md)。不要把现有 AWS/阿里云 Terraform stack 用于这台轻量服务器。

## 3. 配置并发布每台主机的网关

阿里云清单位于 `hosts/aliyun/beijing/01/host.json`，当前包含 `shadowtable`、`just-works`、`inkmind` 和 `directo`；AWS 清单位于 `hosts/aws/singapore/01/host.json`，当前包含三项业务。主机名不限制可承载的业务。真实域名放在服务器env，不放清单。

腾讯云清单当前为空，`python3 scripts/render_host.py tencent-shanghai-01 --check` 可校验登记信息。`render`、`reload` 和 `Deploy gateway` 会拒绝空服务清单，发布入口在建立 SSH 连接和操作 Docker 前停止。首次发布前，先填写实际 `services`、对应域名和业务网络配置；不要为占位主机填入无关业务。

新主机复制其示例到 `/opt/gateway/gateway.env`（以下在已有本仓库检出的服务器执行）：

```bash
cp hosts/aliyun/beijing/01/gateway.env.example /opt/gateway/gateway.env
chmod 600 /opt/gateway/gateway.env
```

编辑真实域名、邮箱和独立卷名；把占位 `CADDY_IMAGE` 替换为合法不可变镜像。服务器部署用户执行 `docker login <ACR_REGISTRY>`，使用只读拉取凭据。各主机使用自己的证书卷；已有EC2保留原卷名，禁止 `down -v`。

infra Actions → **Publish gateway image**，分支main，成功后复制Summary中的 `image@sha256`。也可以复用已保留的旧Caddy digest。

验证与发布构建遇到 Docker Hub 令牌或镜像元数据端点的 HTTP 500/502/503/504 时，最多尝试三次，重试前分别等待10秒、20秒。持续失败时稍后重新运行工作流；认证拒绝、标签不存在或其他构建错误会立即失败。

infra Actions → **Deploy gateway** → Run workflow，分支main，选择主机ID并填写digest。流程校验主机标记/env权限/域名/image，按清单生成Caddyfile与Compose，创建本机所需proxy网络和证书卷，验证候选配置，再启动网关。失败会恢复原网关配置/镜像；首次失败停掉候选网关。不会启停任何业务容器。

新应用尚未部署时，其域名返回502是预期。发布应用后逐站验收HTTPS、登录、API与流式输出；网关Docker health检查仅覆盖Caddy进程/管理接口，不替代业务验收。

新主机证书签发要求域名DNS和80/443连通。演练先用独立测试域名并配置对应WEB_ORIGIN，避免同时把正式域名指向两份独立SQLite数据。使用中国内地服务器时，域名备案/新增接入手续按实际接入商的[阿里云备案流程](https://help.aliyun.com/zh/icp-filing/basic-icp-service/user-guide/icp-filing-application-overview)或[腾讯云备案流程](https://cloud.tencent.com/document/product/243/18909)处理。

在服务器检出本仓库后可查看运行状态：

```bash
bash gateway/compose.sh ps
bash gateway/compose.sh logs --tail 100 caddy
```

仅路由内容变更可运行 `bash gateway/reload.sh`；主机service列表、env、镜像或网络变化重新运行 **Deploy gateway**。reload发现Compose内容变化会拒绝，避免只加载路由却漏接网络。

已成功发布的生成配置位于 `/opt/gateway/current`，前一个生成版本位于 `/opt/gateway/previous`。回退网关时恢复与旧版本匹配的gateway.env，再在 `/opt/gateway/deploy.lock` 锁下复制previous的 `Caddyfile/compose.yaml/image.env/host` 到config，运行compose up，逐站验收并更新current；首次从旧共享网关迁移的配置备份位于该候选release的 `previous-config`。不要恢复或删除业务数据/证书卷。

## 4. 发布业务及正式迁移

ShadowTable Actions → **Container CI and build**，main构建成功后复制Build run ID；然后 **Deploy tested image** 选择 `aliyun-prod`（北京 ECS）或 `aws-prod`（新加坡 EC2）和该编号，全过程不重新构建镜像。北京 ECS 尚未接正式流量时，可先用独立临时域名与测试数据验收；当前没有独立 staging 部署目标。业务Secrets/app.env独立，详细说明见ShadowTable的部署指南。

正式跨云迁移需要停旧实例写入，备份并搬完整SQLite数据目录，部署新端后切DNS。域名健康检查会访问新主机本机Caddy并校验证书，防止误验旧EC2。旧端保持停止；新端开始写入后回切需要明确的数据恢复策略。确认迁移完成后，从AWS主机清单的services移除shadowtable，再手动发布AWS网关，保留其他业务路由。

## 5. 启用备份和基础监控

在服务器本仓库检出中执行：

```bash
sudo bash host/install-operations.sh
sudo cp host/backup.env.example /etc/jastcraft/backup.env
sudo chmod 600 /etc/jastcraft/backup.env
```

编辑 `BACKUP_CLOUD=aws|aliyun|tencent`，对应 `BACKUP_DESTINATION=s3://.../shadowtable/prod`、`oss://.../shadowtable/prod` 或 `cos://.../shadowtable/prod`。现有业务主机的环境均为 prod，各自备份桶/路径独立。安装对应官方CLI [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) / [ossutil](https://help.aliyun.com/zh/oss/developer-reference/ossutil-overview/) / [COSCLI](https://cloud.tencent.com/document/product/436/63144)，配置对应存储的访问凭据，先用上传命令验证目标前缀权限。AWS/阿里云可使用已绑定的 IAM/RAM 实例角色；腾讯云 COS 使用 `host/backup-tencent.env.example`，显式设置 `BACKUP_COS_ENDPOINT=cos.ap-shanghai.myqcloud.com` 并配置 COSCLI 凭据，不假定轻量主机已有实例角色。systemd任务以root运行，CLI和凭据配置也必须在root环境可用。不要把云AccessKey写进仓库。空主机没有业务数据库，不运行备份任务或启用备份 timer。

```bash
sudo systemctl start jastcraft-backup.service
sudo journalctl -u jastcraft-backup.service --no-pager -n 50
# 首次上传成功且做过恢复验证后启用：
sudo systemctl enable --now jastcraft-backup.timer
systemctl list-timers jastcraft-backup.timer jastcraft-health.timer
```

备份通过SQLite backup API生成一致快照、验证quick_check、权限600，随后上传对象存储。持有与发布相同的flock锁，上传成功后保留14天本地在线备份。AWS/阿里云 Terraform 创建的备份桶默认保留90天；手动创建的桶（含腾讯云 COS）需自行设置版本控制和生命周期。每日约UTC03:15（北京时间11:15），随机延迟0–15分钟。迁移用停写的整个数据目录归档；在线恢复可以使用这里生成的单文件快照，先停止应用，隔离旧WAL/SHM并恢复权限，再启动并验证，不直接覆盖运行中数据库。

安装operations默认仅启用五分钟一次的Docker/disk检查：85%磁盘使用或unhealthy容器使service失败并写journal。备份timer不会在未配置凭据时自动启动。当前检查不包含已停止业务、证书到期、外部HTTP可用性或自动通知；可以在云监控中接入systemd失败/外部HTTPS探测。定期检查日志与备份对象，安排恢复演练。

## 6. 增加后续服务或主机

新主机添加 `hosts/<云>/<地域>/<编号>` 清单；通过现有 AWS/阿里云模块创建云资源时另建独立 stack/state，已有腾讯云轻量服务器直接接入。复制并修改Environment与工作流的target选项，不复制整套业务发布脚本。允许 `services=[]` 先登记空主机，后续选择服务后再配置域名和发布。新的业务路由加入 `gateway/routes`，并注册域名变量映射；应用Compose加入自己的本地proxy网络且声明固定upstream别名，数据库留在业务私有网络。

应用镜像、schema迁移、应用回退始终留在各业务仓库。服务与数据库尽量在同云同区域；如果同一服务要多实例运行，先解决共享数据库、并发更新、会话和缓存，再评估托管容器平台。


### 6.1 just-works 静态站接入北京 ECS

`just-works` 业务仓库保留 Cloudflare Pages，同时独立构建静态站镜像、发布到
ACR，再手动部署到 `aliyun-prod`。这里仅管理域名、网络和公共网关；页面内容、
应用镜像、健康检查及回退由 `just-works/DEPLOYMENT.md` 中的业务流程管理。

已有 ECS 无需重新 bootstrap 或执行 Terraform apply。以 root 创建
`/opt/just-works` 和 `/opt/just-works/releases`，属主设为实际部署账号，权限 700；
再由该账号写入 `/opt/just-works/deployment-target`，内容为 `aliyun-prod`。
静态站没有数据库，不需要 data/backups 目录或新备份桶权限。

1. 阿里云入口使用 `https://me.jastcraft.com`。完成备案及接入要求后，将
   `jastcraft.com` 的 `me` A 记录指向北京 ECS 公网 IPv4 地址；保留现有 Cloudflare Pages 发布通道。
2. 在现有 `/opt/gateway/gateway.env` 补充 `JUST_WORKS_DOMAIN=me.jastcraft.com`，保留
   ShadowTable 域名、现有证书卷名和其他配置。同步业务 `app.env` 的 `SITE_DOMAIN=me.jastcraft.com`。
3. 提交新路由及主机清单后，手动 **Deploy gateway** 到 `aliyun-beijing-01`，
   可复用现有 Caddy digest。它会创建 `just-works_proxy` 并连接网关；新增服务涉及
   Compose/network/env 变化，不能只运行 reload。首次接入会重建共享网关容器，
   安排短维护窗口并回测 ShadowTable。
4. 在业务仓库手动 **Deploy tested image**。业务容器提供内部 8080 端口并声明
   `just-works-upstream` 别名，不映射公网端口。首次业务发布前网站返回 502 属预期。
5. 验证网站首页、六个详情页及 `/health`；健康响应需包含 `service=just-works`
   和目标源码 revision。后续页面发布只更新业务容器，不操作网关。

AWS 主机清单保持原样。顶层 `gateway/Caddyfile` / `gateway/compose.yaml` 是旧兼容
路径；北京主机使用 `host.json` 与 `gateway/routes/just-works.caddy` 渲染的配置。

### 6.2 InkMind 接入北京 ECS

域名 `inkmind.jastcraft.com`，服务映射 `inkmind_proxy` / `inkmind-upstream:80`。
在现有 `gateway.env` 增加 `INKMIND_DOMAIN=inkmind.jastcraft.com`，将 DNS 指向北京 ECS，
随后手动发布网关（保留真实证书卷和现有服务配置）。应用发布由 InkMind 仓库负责。
已有主机无需重新 bootstrap：仅增加 `/opt/inkmind/releases`、`backups`（部署账号 700）、
`data`（UID/GID 1000，700）和 `deployment-target`（`aliyun-prod`），不要覆盖旧目录和数据库。
首次迁移步骤、配置及 GitHub Environment 见 InkMind 的 `docs/DEPLOYMENT.md`。

InkMind 的在线备份必须以 root 运行（data 为 UID 1000、700），使用与发布相同的部署锁。
`backup.sh` 支持 `BACKUP_SERVICE=inkmind`，使用 `host/backup-inkmind.env.example`，
对象存储目的地使用独立的 `inkmind/prod` 前缀，并配置相应桶权限。
可使用 `jastcraft-backup@inkmind.timer` 和 `/etc/jastcraft/backup-inkmind.env` 独立启用，
原 ShadowTable 的非模板备份服务保持不变。首次手动运行并确认远程上传、恢复测试通过后启用 timer。

### 6.3 Directo 手动部署容器接入北京 ECS

入口为 `https://directo.jastcraft.com`，DNS A 记录指向 `39.106.102.121`。
当前Web容器为 `script2video_web`，端口映射为宿主机3000到容器80；
API容器为 `script2video_app`，内部监听3001。两者通过 `directo_proxy` 网络接入网关：

| 请求路径 | 网关目标 | Docker网络别名 |
| --- | --- | --- |
| `/api/*`，包括 `/api/v1/auth/login` | API容器3001 | `directo-api-upstream` |
| 其他路径，包括 `/login` 和前端静态文件 | Web容器80 | `directo-upstream` |

网关使用 `handle` 保留 `/api/v1` 前缀，API转发启用即时刷新以支持流式响应。
本仓库管理网关路由；Directo镜像、容器启动、应用环境变量和数据继续由业务的手动部署流程管理。

HTTPS前端必须使用同域名的 `/api/v1` 地址。旧Web镜像将
`http://39.106.102.121:3001/api/v1` 编译进JavaScript，浏览器会因mixed content拦截请求。
只添加网关路由或重启旧Web容器不能修复该地址，需按以下步骤重新构建业务前端。

#### 首次接入或修复HTTPS登录

1. 在服务器确认业务容器名及端口映射：

   ```bash
   docker ps --format 'table {{.Names}}\t{{.Ports}}'
   docker inspect --format '目录={{index .Config.Labels "com.docker.compose.project.working_dir"}} 配置={{index .Config.Labels "com.docker.compose.project.config_files"}} 服务={{index .Config.Labels "com.docker.compose.service"}}' \
     script2video_web script2video_app
   ```

   `script2video_web` 的 `3000->80/tcp` 对应当前路由。如果后续内部端口改变，先将
   `gateway/routes/directo.caddy` 的目标端口改为实际内部端口，并同步测试中的端口预期。
   应用在容器内应监听 `0.0.0.0` 和实际内部端口，而非只监听容器的 loopback。
   记录Compose标签显示的工作目录、配置文件和服务名，后续修改并使用这份实际生产配置。
   多个Compose文件需保留原来的 `-f` 顺序；如果标签为空，则沿用原业务的 `docker run` 启动流程。

2. 使用有Docker权限的账号给Web和API容器增加网络连接。已连接的容器先确认别名，
   跳过对应的 `connect` 命令；已完成Web接入时通常只需连接API：

   ```bash
   docker network inspect directo_proxy >/dev/null 2>&1 || docker network create directo_proxy
   docker inspect --format '{{.Name}} {{json .NetworkSettings.Networks}}' script2video_web script2video_app
   docker network connect --alias directo-upstream directo_proxy script2video_web
   docker network connect --alias directo-api-upstream directo_proxy script2video_app
   ```

   将网络和别名写入业务启动配置，避免重建容器后丢失。Compose用户将以下片段
   合并到实际Web和API服务；示例的 `web`、`app` 需换成第1步查到的真实服务名，已有私有网络继续保留，
   数据库无需连接 proxy 网络：

   ```yaml
   services:
     web:
       networks:
         default: {}
         directo_proxy:
           aliases:
             - directo-upstream
     app:
       networks:
         default: {}
         directo_proxy:
           aliases:
             - directo-api-upstream
   networks:
     default: {}
     directo_proxy:
       external: true
       name: directo_proxy
   ```

   使用 `docker run` 时，在Web原启动命令中增加
   `--network directo_proxy --network-alias directo-upstream`，API增加
   `--network directo_proxy --network-alias directo-api-upstream`，同时保留其连接数据库和Redis的原网络。
   这些参数位于镜像名之前；镜像、环境变量、数据卷等继续使用业务原有配置。

3. 以网关部署账号备份并编辑现有 `/opt/gateway/gateway.env`：

   ```bash
   cp /opt/gateway/gateway.env "/opt/gateway/gateway.env.bak.$(date +%Y%m%d%H%M%S)"
   ```

   增加 `DIRECTO_DOMAIN=directo.jastcraft.com`，保留其他域名、镜像和真实证书卷名称。
   文件仍应由网关部署账号所有，权限600；不要用示例文件覆盖它。
   确认安全组和主机防火墙允许80/443、ICP备案及阿里云接入手续已完成。

4. 更新业务后端的实际环境变量文件：在现有 `ALLOWED_ORIGINS` 逗号分隔列表中加入
   `https://directo.jastcraft.com`。例如保留原IP入口时可为：

   ```dotenv
   ALLOWED_ORIGINS=http://39.106.102.121:3000,https://directo.jastcraft.com
   ```

   原有的其他来源也要保留。确认 `PORT=3001`；保留JWT密钥、数据库、Redis和其他业务配置。
   在第1步查到的生产Compose目录，使用原配置文件及服务名重建API容器：

   ```bash
   docker compose -f 实际生产compose文件 up -d --no-deps --force-recreate 实际API服务名
   ```

   仅修改环境变量和网络不需要构建新API镜像。**`docker restart` 不会重新读取Compose的 `env_file`**。
   若使用 `docker run`，用更新后的环境变量和完整原启动参数重建API容器。
   重建后检查网络与健康状态，确保新的API容器仍使用 `directo-api-upstream` 别名。

5. 准备业务前端的新镜像。已有 `apps/web/Dockerfile` 接受 `VITE_API_BASE_URL` 构建参数；
   在业务仓库根目录、与ECS架构匹配的构建环境执行（也可在ECS上构建）：

   ```bash
   DIRECTO_WEB_IMAGE=crpi-tro81pekkwccidl8.cn-beijing.personal.cr.aliyuncs.com/script2video/script2video-web:domain-20261010
   docker build --build-arg VITE_API_BASE_URL=/api/v1 -t "$DIRECTO_WEB_IMAGE" apps/web
   docker push "$DIRECTO_WEB_IMAGE"
   ```

   推送前使用业务已有凭据登录ACR；后续版本使用新的唯一tag。
   如果改用 `docker-compose.build.yml` 构建，将 `web.build.args.VITE_API_BASE_URL` 改为 `/api/v1`，
   同时使用实际ACR镜像地址。不要仅在运行时给Nginx容器增加这个变量，Vite会在构建时将其编译进JS。

6. 将本仓库改动提交到main，等待 **Verify infrastructure** 通过，再运行
   **Deploy gateway**，选择 `aliyun-beijing-01`，填写完整的当前 Caddy
   `registry/repository@sha256:...` 引用。可在服务器查看：

   ```bash
   GATEWAY_CONTAINER=$(docker ps -q \
     --filter label=com.docker.compose.project=jastcraft-gateway \
     --filter label=com.docker.compose.service=caddy)
   docker inspect --format '{{.Config.Image}}' "$GATEWAY_CONTAINER"
   ```

   路由和Compose由发布流程生成，可复用当前不可变镜像，无需重新发布 Caddy 镜像。
   首次新增Directo服务涉及网关网络和环境变量，必须执行完整发布。
   如果Directo已接入且这次只改路由，更新服务器infra检出后也可运行 `bash gateway/reload.sh`；
   它不会重建共享Caddy。使用Actions完整发布时安排短维护窗口并回测其他站点。

7. 网关就绪后，将实际生产Compose里Web的 `image` 更新为第5步推送的完整新镜像引用，
   并保留第2步的网络别名。然后在服务器的实际业务部署目录执行：

   ```bash
   docker compose -f 实际生产compose文件 pull 实际Web服务名
   docker compose -f 实际生产compose文件 up -d --no-deps --force-recreate 实际Web服务名
   ```

   如果使用 `docker run`，拉取新镜像后用完整原启动参数和Web网络别名重建容器。
   保留旧Web镜像引用用于回退，不用本地开发Compose覆盖生产配置。

8. 验证HTTPS、API和登录会话：

   ```bash
   curl -sS -o /dev/null -w 'HTTP %{http_code}\n' https://directo.jastcraft.com/
   GATEWAY_CONTAINER=$(docker ps -q \
     --filter label=com.docker.compose.project=jastcraft-gateway \
     --filter label=com.docker.compose.service=caddy)
   docker exec "$GATEWAY_CONTAINER" wget -S -O /dev/null http://directo-upstream:80/
   docker exec "$GATEWAY_CONTAINER" wget -S -O /dev/null http://directo-api-upstream:3001/health
   curl -i -X OPTIONS https://directo.jastcraft.com/api/v1/auth/login \
     -H 'Origin: https://directo.jastcraft.com' \
     -H 'Access-Control-Request-Method: POST' \
     -H 'Access-Control-Request-Headers: content-type'
   curl -i -X POST https://directo.jastcraft.com/api/v1/auth/refresh \
     -H 'Origin: https://directo.jastcraft.com' \
     -H 'Content-Type: application/json' -d '{}'
   ```

   API健康检查应成功，预检应返回204并允许当前来源；不带登录Cookie的refresh请求应返回
   **401和JSON**（未登录的预期结果），而非HTML。浏览器强制刷新后，确认登录请求指向
   `https://directo.jastcraft.com/api/v1/auth/login`，没有HTTP3001请求或mixed-content错误；
   使用业务账号验证登录、刷新页面后的会话保持和退出登录，以及原ShadowTable、just-works、InkMind入口。
   登录Cookie使用Secure、HttpOnly和 `/api/v1/auth/` 路径，保持该路径完整转发。
   如返回502，检查网络、别名、内部端口和监听地址；401 JSON表示请求已到API但尚未认证；
   200 HTML表示请求仍落到Web；预检500则检查API的 `ALLOWED_ORIGINS` 是否已生效。

#### 后续手动部署

保持Web和API容器加入 `directo_proxy`，分别使用 `directo-upstream`、`directo-api-upstream` 别名，
内部端口分别为80和3001。前端每次构建继续传入 `VITE_API_BASE_URL=/api/v1`。
使用更新后的Compose或 `docker run` 命令创建容器即可，无需再次修改DNS或发布网关。
同一别名应只分配给当前提供服务的应用容器，避免旧、新容器同时接收流量。
应用重建期间可能短暂返回502。

域名验收通过后关闭安全组的公网3000和3001入口。后续业务重建时，移除这两个服务Compose的公网
`ports` 映射或 `docker run` 的 `-p 3000:80`、`-p 3001:3001`；内部代理访问不需要发布宿主机端口。
保留业务原有数据卷和环境变量，无需重新bootstrap或执行Terraform apply。
