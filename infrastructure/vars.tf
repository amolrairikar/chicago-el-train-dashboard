variable "services" {
  type = list(string)
  default = [
    "bigquery.googleapis.com"
  ]
}