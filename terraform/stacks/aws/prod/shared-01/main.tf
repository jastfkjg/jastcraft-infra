terraform {
  required_version = ">= 1.10, < 2.0"
  backend "s3" {}
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}
provider "aws" { region = var.region }
locals {
  host = jsondecode(file("${path.module}/../../../../../hosts/aws/prod/shared-01/host.json"))
  cloud_init = templatefile("${path.module}/../../../../../host/cloud-init.yaml.tftpl", {
    deploy_user      = var.deploy_user
    ssh_public_key   = var.ssh_public_key
    bootstrap_base64 = base64encode(file("${path.module}/../../../../../host/bootstrap.sh"))
    host_target      = local.host.target
    services         = join(",", local.host.services)
  })
}
module "host" {
  source             = "../../../../modules/aws-host"
  name               = var.name
  image_id           = var.image_id
  instance_type      = var.instance_type
  availability_zone  = var.availability_zone
  ssh_public_key     = var.ssh_public_key
  ssh_cidrs          = var.ssh_cidrs
  backup_bucket_name = var.backup_bucket_name
  vpc_cidr           = var.vpc_cidr
  subnet_cidr        = var.subnet_cidr
  disk_size_gb       = var.disk_size_gb
  image_repositories = var.image_repositories
  cloud_init         = local.cloud_init
}
output "host_address" { value = module.host.host_address }
output "instance_id" { value = module.host.instance_id }
output "backup_destination" { value = module.host.backup_destination }
output "image_repositories" { value = module.host.image_repositories }
output "deploy_user" { value = var.deploy_user }
