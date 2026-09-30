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
variable "bandwidth_mbps" {
  type    = number
  default = 5
}
variable "acr_instance_id" {
  type        = string
  default     = null
  description = "Existing ACR Enterprise instance; null retains the existing registry."
}
variable "acr_namespace" {
  type    = string
  default = "jastcraft"
}
variable "image_repositories" {
  type    = set(string)
  default = []
  validation {
    condition     = length(var.image_repositories) == 0 || var.acr_instance_id != null
    error_message = "Optional enterprise repositories require an existing acr_instance_id."
  }
}
variable "cloud_init" { type = string }
