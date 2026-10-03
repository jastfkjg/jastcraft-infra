# Jastcraft infrastructure

统一维护 AWS/阿里云的云资源、主机公共运行环境和 Caddy 网关。业务仓库独立维护应用镜像、Compose、数据库迁移、业务健康检查与回退。推送本仓库仅验证；云资源、网关和应用都不会随推送自动更新。

| 层次 | 目录 | 管理边界 |
| --- | --- | --- |
| 云资源 | `terraform/modules`、`terraform/stacks/<云>/<地域>/<编号>` | VPC、网络规则、虚拟机、加密系统盘、私有备份桶及实例角色；可选镜像仓库 |
| 主机运行环境 | `host`、`hosts/<云>/<地域>/<编号>` | Docker、部署账号、目录、主机目标标记、备份与基础健康检查 |
| 公共网关 | `gateway`、`scripts` | 仅该主机的域名、Caddy 路由、证书卷和本地代理网络 |
| 业务发布 | 各业务仓库 | 已测试镜像的手动发布、业务数据与兼容性迁移 |

当前目标清单：

- `aws-singapore-01`：新加坡 EC2（`ap-southeast-1`），当前网关接入 echooo、ShadowTable、文旅拾光。
- `aliyun-beijing-01`：北京 ECS（`cn-beijing`），当前网关接入 ShadowTable、just-works。

主机 ID 按云厂商、地域、编号命名，不绑定业务或环境；`host.json` 中的 `services` 决定承载业务，`environment` 单独描述当前业务发布环境（两台目前均为 `prod`）。新增业务不需要改主机 ID。

主机初始化 `host/bootstrap.sh` 支持 Ubuntu 22.04/24.04 和 Alibaba Cloud Linux 3（含 3.2104 LTS），自动选择 apt/dnf 安装流程；两种系统使用相同的部署账号、目录与目标标记。

云资源使用独立 Terraform state；部署凭据按 GitHub Environment 隔离；每台主机保留自己的证书卷和 Docker bridge 网络。业务应用与数据库不映射公网端口。

第一次使用、GitHub 配置、现有 EC2 接入、ECS 初始化、网关发布和备份启用，按照 **[多云操作指南](docs/multicloud.md)** 执行。

现有 EC2/ECS 不需要重建或重新初始化。主机改名时按操作指南更新 GitHub Environment 和服务器标记，保留真实证书卷及已有 Terraform state 配置。原 `gateway/compose.sh` 在尚未启用主机清单时继续使用旧配置；启用后自动读取 `/opt/gateway/config/compose.yaml`。原证书卷名字必须保留。历史首次拆分方案见 [旧网关迁移指南](docs/legacy-gateway-migration.md)。

本地检查：

```bash
python3 -m unittest discover -s tests
bash scripts/verify.sh
terraform fmt -check -recursive terraform
```

`Verify infrastructure` 自动校验所有主机路由、部署故障边界与各 Terraform stack；执行 `init -backend=false` / `validate` 及 mock provider 的 plan 测试，不访问远程 state、不执行真实云资源 plan/apply。`Publish gateway image` 只发布镜像；`Deploy gateway` 手动选择主机和 immutable digest 后才更新网关。

Provider 锁文件包含 GitHub Actions 的 `linux_amd64` 和本地 Apple Silicon 的 `darwin_arm64` 校验和。修改 provider 约束或新增 stack 后，在仓库根目录更新并提交锁文件：

```bash
for stack in terraform/stacks/*/*/*; do
  terraform -chdir="$stack" init -backend=false -input=false
  terraform -chdir="$stack" providers lock -platform=linux_amd64 -platform=darwin_arm64
done
git diff -- 'terraform/stacks/**/.terraform.lock.hcl'
```

该流程从官方 registry 验证各平台包，保留已有 provider 版本；有意升级时才给 `init` 添加 `-upgrade`。CI 保持 `-lockfile=readonly`，锁文件缺失或不匹配时应在本地修复并提交，再运行新提交上的工作流。

新增主机时添加 `hosts` 清单、独立 Terraform stack、对应 GitHub Environment 和工作流目标选项。新增业务时添加 `gateway/routes/<业务>.caddy` 与 `scripts/render_host.py` 服务映射，并由业务仓库提供本地代理网络/别名。按主机选择服务，避免把所有业务写入每一台服务器的网关。
