resource "google_project_service" "apis" {
  for_each           = toset(var.services)
  service            = each.value
  disable_on_destroy = false
}

resource "google_bigquery_dataset" "raw_dataset" {
  dataset_id                 = "raw"
  friendly_name              = "raw"
  description                = "Raw layer containing unprocessed CTA Train Tracker API responses"
  location                   = "US"
  delete_contents_on_destroy = true

  labels = {
    "environment" = "prod"
    "project"     = "chicago-el-train-dashboard"
    "managed-by"  = "terraform"
  }
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

  labels = {
    "environment" = "prod"
    "project"     = "chicago-el-train-dashboard"
    "managed-by"  = "terraform"
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

  labels = {
    "environment" = "prod"
    "project"     = "chicago-el-train-dashboard"
    "managed-by"  = "terraform"
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