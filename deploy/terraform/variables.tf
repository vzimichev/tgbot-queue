variable "aws_region" {
  type        = string
  description = "AWS region."
  default     = "eu-central-1"
}
variable "project_name" {
  type        = string
  description = "Admin project name; use a different name for a parallel deployment."
  default     = "tgbot-queue"
  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9-]{0,62}$", var.project_name))
    error_message = "Use 1–63 alphanumeric characters or hyphens, starting with an alphanumeric character."
  }
}
variable "managed_project_name" {
  type        = string
  description = "Managed project name."
  default     = "tgbot-queue-managed"
  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9-]{0,62}$", var.managed_project_name))
    error_message = "Use 1–63 alphanumeric characters or hyphens, starting with an alphanumeric character."
  }
}
variable "function_name" {
  type        = string
  description = "Admin webhook Lambda name."
  default     = "tg-to-sqs"
}
variable "managed_function_name" {
  type        = string
  description = "Managed webhook Lambda name."
  default     = "managed-to-sqs"
}
variable "key_name" {
  type        = string
  description = "Existing EC2 key pair name; inbound SSH remains disabled."
}
variable "admin_bot_secret_arn" {
  type        = string
  description = "Existing secret ARN with ADMIN_BOT_TOKEN and ADMIN_BOT_OWNER_ID JSON."
}
variable "webhook_secret_arn" {
  type        = string
  description = "Existing secret ARN containing the plain webhook root secret."
}
variable "image_id_parameter" {
  type        = string
  description = "Ubuntu amd64 AMI SSM parameter."
  default     = "/aws/service/canonical/ubuntu/server/26.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

variable "sqs_visibility_timeout" {
  type    = number
  default = 3600
  validation {
    condition     = var.sqs_visibility_timeout >= 0 && var.sqs_visibility_timeout <= 43200 && floor(var.sqs_visibility_timeout) == var.sqs_visibility_timeout
    error_message = "Visibility timeout must be an integer from 0 to 43200."
  }
}
variable "managed_sqs_visibility_timeout" {
  type    = number
  default = 3600
  validation {
    condition     = var.managed_sqs_visibility_timeout >= 0 && var.managed_sqs_visibility_timeout <= 43200 && floor(var.managed_sqs_visibility_timeout) == var.managed_sqs_visibility_timeout
    error_message = "Visibility timeout must be an integer from 0 to 43200."
  }
}
