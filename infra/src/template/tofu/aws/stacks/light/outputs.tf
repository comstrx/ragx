output "server_ip" {
  value = module.server.public_ip
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

output "app_access_key_id" {
  value = module.keys.app_access_key_id
}

output "app_secret_access_key" {
  value     = module.keys.app_secret_access_key
  sensitive = true
}

output "backup_access_key_id" {
  value = module.keys.backup_access_key_id
}

output "backup_secret_access_key" {
  value     = module.keys.backup_secret_access_key
  sensitive = true
}
