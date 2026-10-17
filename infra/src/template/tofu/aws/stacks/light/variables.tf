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

variable "ec2_type" {
  type = string
}

variable "ec2_disk_gb" {
  type = number
}

variable "admin_cidrs" {
  type = list(string)
}

variable "ssh_public_key" {
  type    = string
  default = ""
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

variable "ec2_ubuntu" {
  type    = string
  default = "24.04"
}

variable "ssh_cidrs" {
  type    = list(string)
  default = []
}
