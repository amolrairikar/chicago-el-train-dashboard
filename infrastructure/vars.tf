variable "services" {
  type = list(string)
  default = [
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "bigquerystorage.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudfunctions.googleapis.com",
    "cloudscheduler.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com"
  ]
}
variable "cloudflare_account_id" {
  type        = string
  description = "Cloudflare account ID that owns the dashboard Worker."
}

variable "cloudflare_api_token" {
  type        = string
  description = "Cloudflare API token with Workers Scripts Edit permission."
  sensitive   = true
}
