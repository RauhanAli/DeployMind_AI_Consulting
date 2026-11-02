variable "region" {
  type    = string
  default = "eu-west-2"
}
variable "environment" {
  description = "development | staging | production"
  type        = string
}
variable "domain_certificate_arn" {
  description = "ACM certificate ARN for the HTTPS listener"
  type        = string
}
variable "github_repository" {
  description = "owner/repo allowed to deploy via OIDC"
  type        = string
}
variable "image_tags" {
  description = "Image tags for each service"
  type        = map(string)
  default     = { api = "latest", worker = "latest", web = "latest", assistant = "latest" }
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}
variable "api_desired_count" {
  type    = number
  default = 2
}
