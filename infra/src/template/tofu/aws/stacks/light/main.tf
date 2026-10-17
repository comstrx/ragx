locals {
  backup_bucket_arn = "arn:aws:s3:::${var.backup_bucket}"
}

module "network" {
  source = "../../modules/network"

  name       = var.name
  cidr       = var.vpc_cidr
  az_count   = var.az_count
  enable_nat = false
}

module "server" {
  source = "../../modules/ec2"

  name               = var.name
  vpc_id             = module.network.vpc_id
  subnet_id          = module.network.public_subnet_ids[0]
  instance_type      = var.ec2_type
  disk_gb            = var.ec2_disk_gb
  ubuntu_version     = var.ec2_ubuntu
  admin_cidrs        = var.admin_cidrs
  ssh_cidrs          = var.ssh_cidrs
  ssh_public_key     = var.ssh_public_key
  ecr_arns           = module.registry.repository_arns
  storage_bucket_arn = ""
  backup_bucket_arn  = ""
}

module "keys" {
  source = "../../modules/keys"

  name               = var.name
  storage_bucket_arn = module.storage.arn
  backup_bucket_arn  = local.backup_bucket_arn
}

module "storage" {
  source = "../../modules/s3"

  name   = var.s3_bucket
  public = true
}

module "registry" {
  source = "../../modules/ecr"

  repositories = [var.ecr_repository]
  keep_images  = var.ecr_keep_images
}
