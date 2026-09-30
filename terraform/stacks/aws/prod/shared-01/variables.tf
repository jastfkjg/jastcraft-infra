variable "name" { type = string }
variable "image_id" { type = string }
variable "instance_type" { type = string }
variable "availability_zone" { type = string }
variable "ssh_public_key" {
  type = string
  validation {
    condition     = can(regex("^ssh-(ed25519|rsa) ", var.ssh_public_key))
    error_message = "Supply a deployment SSH public key, never a private key."
  }
}
variable "ssh_cidrs" {
  type = set(string)
  validation {
    condition     = length(var.ssh_cidrs) > 0 && alltrue([for cidr in var.ssh_cidrs : can(cidrnetmask(cidr)) && cidr != "0.0.0.0/0"])
    error_message = "Supply explicit IPv4 SSH source CIDRs; do not use 0.0.0.0/0."
  }
}
variable "backup_bucket_name" { type = string }
variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}
variable "subnet_cidr" {
  type    = string
  default = "10.42.1.0/24"
}
variable "disk_size_gb" {
  type    = number
  default = 40
}
variable "image_repositories" {
  type        = set(string)
  default     = []
  description = "Optional ECR repository names. Existing ACR can continue to serve AWS hosts."
}
variable "region" { type = string }
variable "deploy_user" {
  type    = string
  default = "deploy"
  validation {
    condition     = can(regex("^[a-z_][a-z0-9_-]*$", var.deploy_user))
    error_message = "Use a valid Linux deployment username."
  }
}
