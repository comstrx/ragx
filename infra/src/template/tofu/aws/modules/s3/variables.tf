variable "name" {
  type = string
}

variable "versioning" {
  type    = bool
  default = true
}

variable "expire_days" {
  type    = number
  default = 0
}

variable "public" {
  type    = bool
  default = false
}
