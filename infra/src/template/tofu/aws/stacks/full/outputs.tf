output "cluster_name" {
  value = module.cluster.cluster_name
}

output "cluster_endpoint" {
  value = module.cluster.cluster_endpoint
}

output "oidc_provider_arn" {
  value = module.cluster.oidc_provider_arn
}

output "autoscaler_role_arn" {
  value = module.cluster.autoscaler_role_arn
}

output "db_host" {
  value = module.database.endpoint
}

output "registry" {
  value = module.registry.registry
}

output "storage_bucket" {
  value = module.storage.bucket
}

output "backup_bucket" {
  value = var.backup_bucket
}

output "db_read_hosts" {
  value = join(",", module.database.replica_endpoints)
}

output "edge_eips" {
  value = join(",", aws_eip.edge[*].allocation_id)
}

output "edge_ips" {
  value = join(",", aws_eip.edge[*].public_ip)
}
