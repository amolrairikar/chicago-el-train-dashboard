resource "cloudflare_worker" "site" {
  account_id = var.cloudflare_account_id
  name       = "chicago-el-train-dashboard"

  subdomain = {
    enabled = true
  }
}

# Static site only: serve Astro's build output (run `npm run build` in web/ first).
resource "cloudflare_worker_version" "site" {
  account_id         = var.cloudflare_account_id
  worker_id          = cloudflare_worker.site.id
  compatibility_date = "2026-10-12"

  assets = {
    directory = "${path.module}/../web/dist"
    config = {
      not_found_handling = "404-page"
    }
  }
}

resource "cloudflare_workers_deployment" "site" {
  account_id  = var.cloudflare_account_id
  script_name = cloudflare_worker.site.name
  strategy    = "percentage"

  versions = [{
    version_id = cloudflare_worker_version.site.id
    percentage = 100
  }]
}
