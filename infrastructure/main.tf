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
  dataset_id               = google_bigquery_dataset.raw_dataset.dataset_id
  table_id                 = "positions"
  description              = "Train position data from CTA Train Tracker API"
  deletion_protection      = false
  require_partition_filter = true

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
    "description": "Error name associated with the train position API response. Empty string indicates no error."
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
    "name": "nextStpId",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "GTFS ID of the next stop the train will arrive at."
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
  dataset_id               = google_bigquery_dataset.raw_dataset.dataset_id
  table_id                 = "arrivals"
  description              = "Train arrival prediction data from CTA Train Tracker API"
  deletion_protection      = false
  require_partition_filter = true

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
    "description": "The timestamp at which the train arrival snapshot was generated, in ISO 8601 format."
  },
  {
    "name": "errCd",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Error code associated with the train arrival API response. Zero indicates no error."
  },
  {
    "name": "errNm",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Error name associated with the train arrival API response. Empty string indicates no error."
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
    "name": "stpDe",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Textual description of platform for which this prediction applies."
  },
  {
    "name": "rn",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Run number corresponding to the train."
  },
  {
    "name": "rt",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Textual, abbreviated route name of train being predicted for."
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

locals {
  src_dir      = "${path.module}/../src"
  common_files = fileset("${local.src_dir}/common", "**/*.py")
  functions = {
    gtfs_fetch      = "gtfs-fetch"
    positions_fetch = "positions-fetch"
    arrivals_fetch  = "arrivals-fetch"
  }
}

data "archive_file" "function" {
  for_each    = local.functions
  type        = "zip"
  output_path = "${path.module}/${each.key}.zip"

  dynamic "source" {
    for_each = setunion(fileset("${local.src_dir}/${each.key}", "*.py"), ["requirements.txt"])
    content {
      content  = file("${local.src_dir}/${each.key}/${source.value}")
      filename = source.value
    }
  }

  dynamic "source" {
    for_each = local.common_files
    content {
      content  = file("${local.src_dir}/common/${source.value}")
      filename = "common/${source.value}"
    }
  }
}

resource "google_storage_bucket_object" "function-code" {
  for_each = local.functions
  name     = "code/${each.value}-${data.archive_file.function[each.key].output_md5}.zip"
  source   = data.archive_file.function[each.key].output_path
  bucket   = google_storage_bucket.private-bucket.name
}

##################################################
# Secret Manager
##################################################
resource "google_secret_manager_regional_secret" "cta-api-key" {
  secret_id = "cta-api-key"
  location  = "us-central1"
}

##################################################
# Cloud Run & Scheduler
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

resource "google_service_account" "cloud-function-service-account" {
  account_id   = "cloud-function-service-account"
  display_name = "Runtime service account for Cloud Functions"
}

resource "google_storage_bucket_iam_member" "cloud-functions-bucket-writer" {
  bucket = google_storage_bucket.private-bucket.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.cloud-function-service-account.email}"
}

resource "google_bigquery_table_iam_member" "cloud-functions-bigquery-writer" {
  for_each = {
    "positions" = google_bigquery_table.positions_table
    "arrivals"  = google_bigquery_table.arrivals_table
  }

  dataset_id = google_bigquery_dataset.raw_dataset.dataset_id
  table_id   = each.value.table_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.cloud-function-service-account.email}"
}

resource "google_secret_manager_regional_secret_iam_member" "cloud-functions-secret-reader" {
  secret_id = google_secret_manager_regional_secret.cta-api-key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud-function-service-account.email}"
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
        object = google_storage_bucket_object.function-code["gtfs_fetch"].name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "512M"
    timeout_seconds       = 300
    service_account_email = google_service_account.cloud-function-service-account.email
    environment_variables = {
      GCS_BUCKET = google_storage_bucket.private-bucket.name
    }
  }
}

resource "google_cloudfunctions2_function" "positions-fetch" {
  name        = "positions-data-fetch"
  description = "Function to fetch positions data from CTA Train Tracker API"
  location    = "us-central1"

  build_config {
    runtime           = "python314"
    entry_point       = "handler"
    docker_repository = google_artifact_registry_repository.functions-repo.id
    source {
      storage_source {
        bucket = google_storage_bucket.private-bucket.name
        object = google_storage_bucket_object.function-code["positions_fetch"].name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "512M"
    timeout_seconds       = 60
    service_account_email = google_service_account.cloud-function-service-account.email
    environment_variables = {
      GCS_BUCKET         = google_storage_bucket.private-bucket.name
      CTA_API_KEY_SECRET = "${google_secret_manager_regional_secret.cta-api-key.name}/versions/latest"
    }
  }
}

resource "google_cloudfunctions2_function" "arrivals-fetch" {
  name        = "arrivals-data-fetch"
  description = "Function to fetch arrivals data from CTA Train Tracker API"
  location    = "us-central1"

  build_config {
    runtime           = "python314"
    entry_point       = "handler"
    docker_repository = google_artifact_registry_repository.functions-repo.id
    source {
      storage_source {
        bucket = google_storage_bucket.private-bucket.name
        object = google_storage_bucket_object.function-code["arrivals_fetch"].name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    available_memory      = "512M"
    timeout_seconds       = 120
    service_account_email = google_service_account.cloud-function-service-account.email
    environment_variables = {
      GCS_BUCKET         = google_storage_bucket.private-bucket.name
      CTA_API_KEY_SECRET = "${google_secret_manager_regional_secret.cta-api-key.name}/versions/latest"
    }
  }
}

resource "google_service_account" "scheduler-service-account" {
  account_id = "cloud-functions-scheduler"
}

resource "google_cloud_run_service_iam_member" "scheduler-service-account" {
  for_each = {
    "gtfs-fetch"      = google_cloudfunctions2_function.gtfs-fetch
    "positions-fetch" = google_cloudfunctions2_function.positions-fetch
    "arrivals-fetch"  = google_cloudfunctions2_function.arrivals-fetch
  }

  location = each.value.location
  service  = each.value.service_config[0].service
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

resource "google_cloud_scheduler_job" "positions-fetch-scheduler" {
  name             = "positions-fetch-scheduler"
  description      = "Scheduler job to trigger positions data fetch function every minute"
  schedule         = "* * * * *"
  attempt_deadline = "70s"

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.positions-fetch.service_config[0].uri
    oidc_token {
      service_account_email = google_service_account.scheduler-service-account.email
      audience              = google_cloudfunctions2_function.positions-fetch.service_config[0].uri
    }
  }
}

resource "google_cloud_scheduler_job" "arrivals-fetch-scheduler" {
  name             = "arrivals-fetch-scheduler"
  description      = "Scheduler job to trigger arrivals data fetch function every 2 minutes"
  schedule         = "*/2 * * * *"
  attempt_deadline = "130s"

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.arrivals-fetch.service_config[0].uri
    oidc_token {
      service_account_email = google_service_account.scheduler-service-account.email
      audience              = google_cloudfunctions2_function.arrivals-fetch.service_config[0].uri
    }
  }
}