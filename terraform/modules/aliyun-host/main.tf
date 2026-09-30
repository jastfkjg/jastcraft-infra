resource "alicloud_vpc" "host" {
  vpc_name   = var.name
  cidr_block = var.vpc_cidr
}
resource "alicloud_vswitch" "host" {
  vpc_id       = alicloud_vpc.host.id
  zone_id      = var.availability_zone
  cidr_block   = var.subnet_cidr
  vswitch_name = var.name
}
resource "alicloud_security_group" "host" {
  security_group_name = var.name
  vpc_id              = alicloud_vpc.host.id
}
resource "alicloud_security_group_rule" "web" {
  for_each          = toset(["80", "443"])
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "${each.value}/${each.value}"
  cidr_ip           = "0.0.0.0/0"
  security_group_id = alicloud_security_group.host.id
}
resource "alicloud_security_group_rule" "ssh" {
  for_each          = var.ssh_cidrs
  type              = "ingress"
  ip_protocol       = "tcp"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "22/22"
  cidr_ip           = each.value
  security_group_id = alicloud_security_group.host.id
}
resource "alicloud_security_group_rule" "outbound" {
  type              = "egress"
  ip_protocol       = "all"
  nic_type          = "intranet"
  policy            = "accept"
  port_range        = "-1/-1"
  cidr_ip           = "0.0.0.0/0"
  security_group_id = alicloud_security_group.host.id
}
resource "alicloud_ecs_key_pair" "deploy" {
  key_pair_name = var.name
  public_key    = var.ssh_public_key
}
resource "alicloud_oss_bucket" "backups" {
  bucket        = var.backup_bucket_name
  force_destroy = false
  versioning { status = "Enabled" }
  server_side_encryption_rule { sse_algorithm = "AES256" }
  lifecycle_rule {
    id      = "shadowtable-backups"
    prefix  = "shadowtable/"
    enabled = true
    expiration { days = 90 }
    noncurrent_version_expiration { days = 30 }
  }
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [acl]
  }
}
resource "alicloud_oss_bucket_acl" "backups" {
  bucket = alicloud_oss_bucket.backups.bucket
  acl    = "private"
}
resource "alicloud_ram_role" "host" {
  role_name                   = var.name
  assume_role_policy_document = jsonencode({ Version = "1", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = ["ecs.aliyuncs.com"] } }] })
}
resource "alicloud_ram_policy" "backup" {
  policy_name = "${var.name}-backup"
  policy_document = jsonencode({ Version = "1", Statement = [
    { Effect = "Allow", Action = ["oss:ListObjects"], Resource = ["acs:oss:*:*:${alicloud_oss_bucket.backups.bucket}"], Condition = { StringLike = { "oss:Prefix" = ["shadowtable/*"] } } },
    { Effect = "Allow", Action = ["oss:GetObject", "oss:PutObject"], Resource = ["acs:oss:*:*:${alicloud_oss_bucket.backups.bucket}/shadowtable/*"] }
  ] })
}
resource "alicloud_ram_role_policy_attachment" "backup" {
  role_name   = alicloud_ram_role.host.role_name
  policy_name = alicloud_ram_policy.backup.policy_name
  policy_type = "Custom"
}
resource "alicloud_instance" "host" {
  instance_name              = var.name
  image_id                   = var.image_id
  instance_type              = var.instance_type
  vswitch_id                 = alicloud_vswitch.host.id
  security_groups            = [alicloud_security_group.host.id]
  key_name                   = alicloud_ecs_key_pair.deploy.key_pair_name
  user_data                  = base64encode(var.cloud_init)
  instance_charge_type       = "PostPaid"
  internet_charge_type       = "PayByTraffic"
  internet_max_bandwidth_out = var.bandwidth_mbps
  system_disk_category       = "cloud_essd"
  system_disk_size           = var.disk_size_gb
  system_disk_encrypted      = true
  deletion_protection        = true
  depends_on                 = [alicloud_security_group_rule.web, alicloud_security_group_rule.ssh, alicloud_security_group_rule.outbound, alicloud_ram_role_policy_attachment.backup]
  lifecycle {
    prevent_destroy = true
    # The provider can replace the system disk in place on an image update; keep data intact.
    ignore_changes = [image_id, user_data]
  }
}
resource "alicloud_ecs_ram_role_attachment" "host" {
  instance_id   = alicloud_instance.host.id
  ram_role_name = alicloud_ram_role.host.role_name
  depends_on    = [alicloud_ram_role_policy_attachment.backup]
}
resource "alicloud_cr_ee_namespace" "images" {
  count              = length(var.image_repositories) > 0 ? 1 : 0
  instance_id        = var.acr_instance_id
  name               = var.acr_namespace
  auto_create        = false
  default_visibility = "PRIVATE"
  lifecycle { prevent_destroy = true }
}
resource "alicloud_cr_ee_repo" "images" {
  for_each    = var.image_repositories
  instance_id = var.acr_instance_id
  namespace   = alicloud_cr_ee_namespace.images[0].name
  name        = each.value
  repo_type   = "PRIVATE"
  summary     = "Jastcraft application image"
  lifecycle { prevent_destroy = true }
}
