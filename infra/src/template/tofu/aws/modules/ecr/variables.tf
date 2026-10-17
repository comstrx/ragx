variable "repositories" {
  type = list(string)
}

variable "keep_images" {
  type    = number
  default = 20
}
