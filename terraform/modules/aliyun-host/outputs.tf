output "host_address" { value = alicloud_instance.host.public_ip }
output "instance_id" { value = alicloud_instance.host.id }
output "backup_destination" { value = "oss://${alicloud_oss_bucket.backups.bucket}/shadowtable" }
output "image_repositories" { value = { for name, repo in alicloud_cr_ee_repo.images : name => repo.id } }
