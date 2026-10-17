variable "name" {
  type = string
}

variable "region" {
  type = string
}

variable "vpc_cidr" {
  type = string
}

variable "az_count" {
  type = number
}

variable "cluster_name" {
  type = string
}

variable "k8s_version" {
  type = string
}

variable "node_type" {
  type = string
}

variable "node_disk_gb" {
  type = number
}

variable "node_min" {
  type = number
}

variable "node_desired" {
  type = number
}

variable "node_max" {
  type = number
}

variable "db_engine_version" {
  type = string
}

variable "db_instance_class" {
  type = string
}

variable "db_disk_gb" {
  type = number
}

variable "db_max_disk_gb" {
  type = number
}

variable "db_name" {
  type = string
}

variable "db_user" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_backup_days" {
  type = number
}

variable "db_multi_az" {
  type = bool
}

variable "s3_bucket" {
  type = string
}

variable "backup_bucket" {
  type = string
}

variable "ecr_repository" {
  type = string
}

variable "ecr_keep_images" {
  type = number
}

variable "log_retention_days" {
  type = number
}

variable "alarm_email" {
  type = string
}

variable "k8s_namespace" {
  type = string
}

variable "service_name" {
  type = string
}

variable "db_alarm_cpu" {
  type    = number
  default = 85
}

variable "db_alarm_free_gb" {
  type    = number
  default = 5
}

variable "node_max_pods" {
  type    = number
  default = 110
}

variable "db_replicas" {
  type    = number
  default = 0
}

variable "db_apply_now" {
  type    = bool
  default = false
}

variable "admin_cidrs" {
  type    = list(string)
  default = []
}
