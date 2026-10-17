locals {
  backup_bucket_arn = "arn:aws:s3:::${var.backup_bucket}"
}

resource "aws_eip" "edge" {
  count = var.az_count

  domain = "vpc"

  tags = { Name = "${var.name}-edge-${count.index}" }
}

module "network" {
  source = "../../modules/network"

  name         = var.name
  cidr         = var.vpc_cidr
  az_count     = var.az_count
  enable_nat   = true
  cluster_name = var.cluster_name
}

module "cluster" {
  source = "../../modules/eks"

  name          = var.cluster_name
  k8s_version   = var.k8s_version
  subnet_ids    = module.network.private_subnet_ids
  node_type     = var.node_type
  node_disk_gb  = var.node_disk_gb
  node_min      = var.node_min
  node_desired  = var.node_desired
  node_max      = var.node_max
  node_max_pods = var.node_max_pods

  public_access_cidrs = var.admin_cidrs
}

module "database" {
  source = "../../modules/rds"

  name              = var.name
  vpc_id            = module.network.vpc_id
  subnet_ids        = module.network.private_subnet_ids
  source_sg_id      = module.cluster.cluster_security_group_id
  engine_version    = var.db_engine_version
  instance_class    = var.db_instance_class
  disk_gb           = var.db_disk_gb
  max_disk_gb       = var.db_max_disk_gb
  db_name           = var.db_name
  db_user           = var.db_user
  db_password       = var.db_password
  backup_days       = var.db_backup_days
  multi_az          = var.db_multi_az
  replicas          = var.db_replicas
  apply_immediately = var.db_apply_now
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

module "identity" {
  source = "../../modules/identity"

  name               = var.name
  cluster_name       = module.cluster.cluster_name
  namespace          = var.k8s_namespace
  service_account    = var.service_name
  storage_bucket_arn = module.storage.arn
  backup_bucket_arn  = local.backup_bucket_arn
}

module "monitoring" {
  source = "../../modules/cloudwatch"

  name           = var.name
  log_groups     = ["/${var.name}/cluster"]
  retention_days = var.log_retention_days
  alarm_email    = var.alarm_email

  alarms = {
    db-cpu = {
      namespace  = "AWS/RDS"
      metric     = "CPUUtilization"
      threshold  = var.db_alarm_cpu
      dimensions = { DBInstanceIdentifier = var.name }
    }

    db-disk = {
      namespace  = "AWS/RDS"
      metric     = "FreeStorageSpace"
      threshold  = var.db_alarm_free_gb * 1000000000
      dimensions = { DBInstanceIdentifier = var.name }
      operator   = "LessThanThreshold"
    }
  }
}
