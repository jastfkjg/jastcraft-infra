resource "aws_vpc" "host" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  tags                 = { Name = var.name }
}
resource "aws_subnet" "host" {
  vpc_id                  = aws_vpc.host.id
  cidr_block              = var.subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = true
  tags                    = { Name = var.name }
}
resource "aws_internet_gateway" "host" { vpc_id = aws_vpc.host.id }
resource "aws_route_table" "host" {
  vpc_id = aws_vpc.host.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.host.id
  }
}
resource "aws_route_table_association" "host" {
  subnet_id      = aws_subnet.host.id
  route_table_id = aws_route_table.host.id
}
resource "aws_security_group" "host" {
  name   = var.name
  vpc_id = aws_vpc.host.id
}
resource "aws_vpc_security_group_ingress_rule" "web" {
  for_each          = toset(["80", "443"])
  security_group_id = aws_security_group.host.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = tonumber(each.value)
  to_port           = tonumber(each.value)
  ip_protocol       = "tcp"
}
resource "aws_vpc_security_group_ingress_rule" "ssh" {
  for_each          = var.ssh_cidrs
  security_group_id = aws_security_group.host.id
  cidr_ipv4         = each.value
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
}
resource "aws_vpc_security_group_egress_rule" "outbound" {
  security_group_id = aws_security_group.host.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
resource "aws_key_pair" "deploy" {
  key_name   = var.name
  public_key = var.ssh_public_key
}
resource "aws_s3_bucket" "backups" {
  bucket        = var.backup_bucket_name
  force_destroy = false
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket_public_access_block" "backups" {
  bucket                  = aws_s3_bucket.backups.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket     = aws_s3_bucket.backups.id
  depends_on = [aws_s3_bucket_versioning.backups]
  rule {
    id     = "shadowtable-backups"
    status = "Enabled"
    filter { prefix = "shadowtable/" }
    expiration { days = 90 }
    noncurrent_version_expiration { noncurrent_days = 30 }
  }
}
resource "aws_iam_role" "host" {
  name               = var.name
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ec2.amazonaws.com" } }] })
}
resource "aws_iam_role_policy" "backup" {
  name = "shadowtable-backup"
  role = aws_iam_role.host.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.backups.arn, Condition = { StringLike = { "s3:prefix" = ["shadowtable/*"] } } },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${aws_s3_bucket.backups.arn}/shadowtable/*" }
  ] })
}
resource "aws_iam_instance_profile" "host" {
  name = var.name
  role = aws_iam_role.host.name
}
resource "aws_instance" "host" {
  ami                         = var.image_id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.host.id
  vpc_security_group_ids      = [aws_security_group.host.id]
  key_name                    = aws_key_pair.deploy.key_name
  iam_instance_profile        = aws_iam_instance_profile.host.name
  user_data                   = var.cloud_init
  user_data_replace_on_change = true
  disable_api_termination     = true
  metadata_options { http_tokens = "required" }
  root_block_device {
    volume_type = "gp3"
    volume_size = var.disk_size_gb
    encrypted   = true
  }
  tags       = { Name = var.name }
  depends_on = [aws_route_table_association.host]
  lifecycle { prevent_destroy = true }
}
resource "aws_eip" "host" {
  domain     = "vpc"
  instance   = aws_instance.host.id
  depends_on = [aws_internet_gateway.host]
}
resource "aws_ecr_repository" "images" {
  for_each             = var.image_repositories
  name                 = each.value
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
  lifecycle { prevent_destroy = true }
}
