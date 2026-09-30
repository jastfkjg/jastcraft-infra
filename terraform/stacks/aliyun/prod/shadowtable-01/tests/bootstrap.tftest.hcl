# Mock providers and plan only: no credentials, remote state or real cloud calls.
mock_provider "alicloud" {}
variables {
  name               = "test-host"
  region             = "cn-hangzhou"
  availability_zone  = "cn-hangzhou-i"
  image_id           = "ubuntu_24_04_x64"
  instance_type      = "ecs.c7.large"
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
}
