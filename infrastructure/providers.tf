terraform {
  required_version = ">= 1.15"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.5"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.8"
    }
  }
}

provider "google" {
  project = "chicago-el-train-dashboard"
  region  = "us-central1"
  zone    = "us-central1-a"

  default_labels = {
    "environment" = "prod"
    "project"     = "chicago-el-train-dashboard"
    "managed-by"  = "terraform"
  }
}
