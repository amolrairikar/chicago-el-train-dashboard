---
layout: ../layouts/Base.astro
title: Methodology
description: How the CTA 'L' dashboard collects data and computes its metrics.
---

# Methodology

How the data is collected, processed and turned into the metrics on the Service and Trends pages.

## Data sources

TODO: CTA Train Tracker API endpoints used (positions, arrivals) and the GTFS static feed.

## Collection

TODO: polling cadence, Cloud Functions and Cloud Scheduler setup, and the BigQuery raw tables and retention.

## Metric definitions

### Trains in service

TODO: distinct run numbers (`rn`) reporting a position in a given window.

### Delay rate

TODO: share of trains flagged delayed (`isDly = 1`).

### Headway

TODO: average minutes between consecutive trains at the same platform (`stpId`): each run's (`rn`) arrival time (`arrT`), sorted, minus the previous run's arrival time.

### Data availability

TODO: share of polls where `errCd` is 0, and what the 900 and 102 error codes mean.

## Known limitations

TODO: what the API does not report, gaps from outages, and how missing polls are handled.
