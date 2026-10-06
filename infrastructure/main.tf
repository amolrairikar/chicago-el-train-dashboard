##################################################
# Enabled APIs/Services
##################################################

resource "google_project_service" "apis" {
  for_each           = toset(var.services)
  service            = each.value
  disable_on_destroy = false
}

##################################################
# BigQuery Datasets and Tables
##################################################

resource "google_bigquery_dataset" "raw_dataset" {
  dataset_id                 = "raw"
  friendly_name              = "raw"
  description                = "Raw layer containing unprocessed CTA Train Tracker API responses"
  location                   = "US"
  delete_contents_on_destroy = true
}

resource "google_bigquery_table" "positions_table" {
  dataset_id  = google_bigquery_dataset.raw_dataset.dataset_id
  table_id    = "positions"
  description = "Train position data from CTA Train Tracker API"

  time_partitioning {
    type          = "HOUR"
    field         = "tmst"
    expiration_ms = 604800000 # 7 days in milliseconds
  }

  schema = <<EOF
[
  {
    "name": "tmst",
    "type": "TIMESTAMP",
    "mode": "REQUIRED",
    "description": "The timestamp at which the train position snapshot was generated, in ISO 8601 format."
  },
  {
    "name": "errCd",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Error code associated with the train position API response. Zero indicates no error."
  },
  {
    "name": "errNm",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Error name associated with the train position API response. Null indicates no error."
  },
  {
    "name": "name",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Name of the train line."
  },
  {
    "name": "rn",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Run number corresponding to the train."
  },
  {
    "name": "destSt",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "GTFS ID of the destination station."
  },
  {
    "name": "destNm",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Name of the destination station."
  },
  {
    "name": "trDr",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Train direction, where 1 indicates northbound and 5 indicates southbound."
  },
  {
    "name": "nextStaId",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "GTFS ID of the next station the train will arrive at."
  },
  {
    "name": "nextStaNm",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Name of the next station the train will arrive at."
  },
  {
    "name": "prdt",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "The timestamp at which the arrival prediction was generated, in ISO 8601 format."
  },
  {
    "name": "arrT",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "The predicted arrival time at the next station, in ISO 8601 format."
  },
  {
    "name": "isApp",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Indicates whether the train is approaching the next station. 1 if approaching, 0 otherwise."
  },
  {
    "name": "isDly",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Indicates whether the train is delayed. 1 if delayed, 0 otherwise."
  },
  {
    "name": "flags",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Train flags, field not currently used by CTA API."
  },
  {
    "name": "lat",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Latitude of the train's current position."
  },
  {
    "name": "lon",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Longitude of the train's current position."
  },
  {
    "name": "heading",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "The heading of the train's current position in degrees."
  }
]
EOF
}

resource "google_bigquery_table" "arrivals_table" {
  dataset_id  = google_bigquery_dataset.raw_dataset.dataset_id
  table_id    = "arrivals"
  description = "Train arrival prediction data from CTA Train Tracker API"

  time_partitioning {
    type          = "HOUR"
    field         = "tmst"
    expiration_ms = 604800000 # 7 days in milliseconds
  }

  schema = <<EOF
[
  {
    "name": "tmst",
    "type": "TIMESTAMP",
    "mode": "REQUIRED",
    "description": "The timestamp at which the train position snapshot was generated, in ISO 8601 format."
  },
  {
    "name": "errCd",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Error code associated with the train position API response. Zero indicates no error."
  },
  {
    "name": "errNm",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Error name associated with the train position API response. Null indicates no error."
  },
  {
    "name": "staId",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "GTFS ID of the station which the arrival prediction is for (4xxxx value)."
  },
  {
    "name": "stpId",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "GTFS ID of the station's platform which the arrival prediction is for (3xxxx value)."
  },
  {
    "name": "staNm",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Name of the station which the arrival prediction is for."
  },
  {
    "name": "rn",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Run number corresponding to the train."
  },
  {
    "name": "destSt",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "GTFS ID of the destination station."
  },
  {
    "name": "destNm",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Name of the destination station."
  },
  {
    "name": "trDr",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Train direction, where 1 indicates northbound and 5 indicates southbound."
  },
  {
    "name": "prdt",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "The timestamp at which the arrival prediction was generated, in ISO 8601 format."
  },
  {
    "name": "arrT",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "The predicted arrival time at the next station, in ISO 8601 format."
  },
  {
    "name": "isApp",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Indicates whether the train is approaching the next station. 1 if approaching, 0 otherwise."
  },
  {
    "name": "isSch",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Indicates whether this is a live prediction or based on projected schedules in lieu of live data. 1 if based on projected schedules, 0 if live."
  },
  {
    "name": "isFlt",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Indicates whether the scheduled arrival time is not feasible due to a departure not having occurred. 1 if true, 0 otherwise."
  },
  {
    "name": "isDly",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Indicates whether the train is delayed. 1 if delayed, 0 otherwise."
  },
  {
    "name": "flags",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Train flags, field not currently used by CTA API."
  },
  {
    "name": "lat",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Latitude of the train's current position."
  },
  {
    "name": "lon",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Longitude of the train's current position."
  },
  {
    "name": "heading",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "The heading of the train's current position in degrees."
  }
]
EOF
}

##################################################
# GCS Buckets
##################################################
resource "google_storage_bucket" "private-bucket" {
  name                        = "chicago-el-train-dashboard-private"
  location                    = "US"
  force_destroy               = true
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      days_since_noncurrent_time = 7
    }
  }
}

data "archive_file" "gtfs_fetch" {
  type        = "zip"
  source_dir  = "${path.module}/../src/gtfs_fetch"
  output_path = "${path.module}/gtfs_fetch.zip"
  excludes = [
    "requirements-dev.txt",
    "**/__pycache__/**",
    ".pytest_cache/**",
    ".ruff_cache/**",
  ]
}

resource "google_storage_bucket_object" "gtfs-data-fetch-code" {
  name   = "code/gtfs-fetch-${data.archive_file.gtfs_fetch.output_md5}.zip"
  source = data.archive_file.gtfs_fetch.output_path
  bucket = google_storage_bucket.private-bucket.name
}

##################################################
# Cloud Run Jobs & Cloud Run Functions
##################################################
resource "google_artifact_registry_repository" "functions-repo" {
  repository_id = "cloud-functions"
  description   = "Container images built for Cloud Run functions"
  location      = "us-central1"
  format        = "DOCKER"

  cleanup_policies {
    id     = "delete-old-images"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "604800s" # 7 days
    }
  }

  cleanup_policies {
    id     = "keep-recent-images"
    action = "KEEP"
    most_recent_versions {
      keep_count = 3
    }
  }
}

resource "google_service_account" "gtfs-fetch-service-account" {
  account_id   = "gtfs-fetch-service-account"
  display_name = "Runtime service account for GTFS fetch function"
}

resource "google_storage_bucket_iam_member" "gtfs_fetch_writer" {
  bucket = google_storage_bucket.private-bucket.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.gtfs-fetch-service-account.email}"
}

resource "google_cloudfunctions2_function" "gtfs-fetch" {
  name        = "gtfs-data-fetch"
  description = "Function to fetch GTFS data .zip file"
  location    = "us-central1"

  build_config {
    runtime           = "python314"
    entry_point       = "handler"
    docker_repository = google_artifact_registry_repository.functions-repo.id
    source {
      storage_source {
        bucket = google_storage_bucket.private-bucket.name
        object = google_storage_bucket_object.gtfs-data-fetch-code.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "512M"
    timeout_seconds       = 300
    service_account_email = google_service_account.gtfs-fetch-service-account.email
    environment_variables = {
      GCS_BUCKET = google_storage_bucket.private-bucket.name
    }
  }
}

resource "google_service_account" "scheduler-service-account" {
  account_id = "gtfs-fetch-scheduler"
}

resource "google_cloud_run_service_iam_member" "scheduler-service-account" {
  location = google_cloudfunctions2_function.gtfs-fetch.location
  service  = google_cloudfunctions2_function.gtfs-fetch.service_config[0].service
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler-service-account.email}"
}

resource "google_cloud_scheduler_job" "gtfs-fetch-scheduler" {
  name             = "gtfs-fetch-scheduler"
  description      = "Scheduler job to trigger GTFS data fetch function every day at midnight UTC"
  schedule         = "0 0 * * *"
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.gtfs-fetch.service_config[0].uri
    oidc_token {
      service_account_email = google_service_account.scheduler-service-account.email
      audience              = google_cloudfunctions2_function.gtfs-fetch.service_config[0].uri
    }
  }
}