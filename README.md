# Jastcraft infrastructure

统一维护 AWS/阿里云的云资源、主机公共运行环境和 Caddy 网关。业务仓库独立维护应用镜像、Compose、数据库迁移、业务健康检查与回退。推送本仓库仅验证；云资源、网关和应用都不会随推送自动更新。

| 层次 | 目录 | 管理边界 |
| --- | --- | --- |
| 云资源 | `terraform/modules`、`terraform/stacks/<云>/<环境>/<主机>` | VPC、网络规则、虚拟机、加密系统盘、私有备份桶及实例角色；可选镜像仓库 |
| 主机运行环境 | `host`、`hosts/<云>/<环境>/<主机>` | Docker、部署账号、目录、主机目标标记、备份与基础健康检查 |
| 公共网关 | `gateway`、`scripts` | 仅该主机的域名、Caddy 路由、证书卷和本地代理网络 |
| 业务发布 | 各业务仓库 | 已测试镜像的手动发布、业务数据与兼容性迁移 |

当前目标清单：

- `aws-prod-shared-01`：echooo、ShadowTable、文旅拾光共享 EC2。
- `aliyun-staging-shadowtable-01`：独立测试 ECS，仅接入 ShadowTable。
- `aliyun-prod-shadowtable-01`：正式 ECS，仅接入 ShadowTable。

云资源使用独立 Terraform state；部署凭据按 GitHub Environment 隔离；每台主机保留自己的证书卷和 Docker bridge 网络。业务应用与数据库不映射公网端口。

第一次使用、GitHub 配置、现有 EC2 接入、ECS 初始化、网关发布和备份启用，按照 **[多云操作指南](docs/multicloud.md)** 执行。

已有 EC2 不需要重建或重新初始化。原 `gateway/compose.sh` 在尚未启用主机清单时继续使用旧配置；启用后自动读取 `/opt/gateway/config/compose.yaml`。原证书卷名字必须保留。历史首次拆分方案见 [旧网关迁移指南](docs/legacy-gateway-migration.md)。

本地检查：

```bash
python3 -m unittest discover -s tests
bash scripts/verify.sh
terraform fmt -check -recursive terraform
```

`Verify infrastructure` 自动校验所有主机路由、部署故障边界与各 Terraform stack；执行 `init -backend=false` / `validate` 及 mock provider 的 plan 测试，不访问远程 state、不执行真实云资源 plan/apply。`Publish gateway image` 只发布镜像；`Deploy gateway` 手动选择主机和 immutable digest 后才更新网关。

新增主机时添加 `hosts` 清单、独立 Terraform stack、对应 GitHub Environment 和工作流目标选项。新增业务时添加 `gateway/routes/<业务>.caddy` 与 `scripts/render_host.py` 服务映射，并由业务仓库提供本地代理网络/别名。按主机选择服务，避免把所有业务写入每一台服务器的网关。
