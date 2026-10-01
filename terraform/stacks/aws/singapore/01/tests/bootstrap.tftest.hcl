# Mock providers and plan only: no credentials, remote state or real cloud calls.
mock_provider "aws" {}
variables {
  name               = "test-host"
  region             = "ap-southeast-1"
  availability_zone  = "ap-southeast-1a"
  image_id           = "ami-0123456789abcdef0"
  instance_type      = "t3.small"
  ssh_public_key     = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExamplePublicKeyForMockTestsOnly"
  ssh_cidrs          = ["203.0.113.10/32"]
  backup_bucket_name = "jastcraft-mock-backup-test"
}
run "cloud_init_host_identity" {
  command = plan
  assert {
    condition     = yamldecode(local.cloud_init).runcmd[0][3] == join(",", local.host.services)
    error_message = "The bootstrap must receive its services as one argument, including shared hosts."
  }
  assert {
    condition     = yamldecode(local.cloud_init).runcmd[0][4] == local.host.target
    error_message = "The bootstrap must receive the selected host target identity."
  }
  assert {
    condition     = yamldecode(local.cloud_init).runcmd[0][5] == local.host.environment
    error_message = "The application environment must be explicit, separate from the host location."
  }
}

run "reject_wrong_host_region" {
  command = plan
  variables {
    region = "us-east-1"
  }
  expect_failures = [var.region]
}
