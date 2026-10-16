# chicago-el-train-dashboard
A dashboard showing unofficial CTA service metrics using the CTA Train Tracker API. NOTE: This project is not affiliated with nor created by the CTA. The data is provided by CTA's Train Tracker API and metrics reflect available data.

## Deploying the site
The static site in `web/` is served by a Cloudflare Worker managed with Terraform in `infrastructure/`.

1. Build the site (Terraform uploads `web/dist` but does not build it):
   `cd web && npm ci && npm run build`
2. Create `infrastructure/terraform.tfvars` (gitignored) with a Cloudflare API token that has the Workers Scripts Edit permission:
   ```
   cloudflare_account_id = "..."
   cloudflare_api_token  = "..."
   ```
3. Apply: `cd infrastructure && terraform init && terraform apply`
