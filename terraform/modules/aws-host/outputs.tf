output "host_address" { value = aws_eip.host.public_ip }
output "instance_id" { value = aws_instance.host.id }
output "backup_destination" { value = "s3://${aws_s3_bucket.backups.bucket}/shadowtable" }
output "image_repositories" { value = { for name, repo in aws_ecr_repository.images : name => repo.repository_url } }
