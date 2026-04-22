# Artana Bio GCP Cost Snapshot

Date captured: March 6, 2026

Snapshot timestamp used for calculations: `2026-03-06T17:39:00Z`

Project:
- Project name: `Artana Bio`
- Project ID: `artana-bio`
- Project number: `722972042617`
- Project create time: `2026-03-04T00:06:15.225985Z`
- Billing enabled: `true`
- Linked billing account: `billingAccounts/014518-1378D9-E8F22C`
- Active gcloud account at capture time: `aandresalvarez@gmail.com`

## Executive Summary

This document records the Google Cloud cost footprint for `artana-bio` as observed on March 6, 2026.

The project is new and had no BigQuery billing export dataset configured at capture time, so the numbers below are estimates derived from:
- live resource inventory
- Cloud Monitoring usage metrics
- Cloud Billing Catalog API list prices

Estimated accrued cost as of `2026-03-06T17:39:00Z`:
- Likely invoice-impacting cost: about `$0.76`
- Upper bound if Cloud Run free tier is already consumed elsewhere on the same billing account: about `$0.96`

Estimated monthly run rate with the current footprint:
- About `$16.20/month`, dominated by Cloud SQL

## Important Limitation

No billing export dataset was found in BigQuery for this project at capture time.

That means:
- these are not invoice-exact charges
- they are resource-based and usage-based estimates
- Cloud Run may be effectively `$0` if free tier is still available on the linked billing account

## Resource Inventory

### Cloud Run

Three Cloud Run services were deployed in `us-central1`:

1. `med13-resource-library-staging`
   - Region: `us-central1`
   - Max scale: `2`
   - Container concurrency: `2`
   - CPU limit: `1000m`
   - Memory limit: `512Mi`
   - Billing model observed: request-based billing
   - Cloud SQL connection attached: `artana-bio:us-central1:med13-pg-staging`

2. `med13-admin-staging`
   - Region: `us-central1`
   - Max scale: `20`
   - Container concurrency: `80`
   - CPU limit: `1000m`
   - Memory limit: `512Mi`
   - Billing model observed: request-based billing

3. `med13-frontdoor-staging`
   - Region: `us-central1`
   - Container concurrency: `80`
   - CPU limit: `1000m`
   - Memory limit: `512Mi`
   - Billing model observed: request-based billing

Observed Cloud Run usage from Cloud Monitoring since project launch:
- CPU allocation time: `7,737.01 vCPU-seconds`
- Memory allocation time: `3,453.10 GiB-seconds`
- Requests: `19,102`

Usage breakdown by service:

| Service | CPU allocation time | Memory allocation time | Requests |
| --- | ---: | ---: | ---: |
| `med13-admin-staging` | `3,416.10 vCPU-s` | `1,579.27 GiB-s` | `13,622` |
| `med13-resource-library-staging` | `4,308.19 vCPU-s` | `1,872.95 GiB-s` | `5,480` |
| `med13-frontdoor-staging` | `12.72 vCPU-s` | `0.87 GiB-s` | `0` observed in query window |

List prices observed from Cloud Billing Catalog API for `us-central1`:
- CPU: `$0.00002400` per vCPU-second
- Memory: `$0.00000250` per GiB-second
- Requests: `$0.40` per 1,000,000 requests

Estimated Cloud Run cost at list price for observed usage:
- CPU: `7,737.01 * 0.00002400 = $0.1857`
- Memory: `3,453.10 * 0.00000250 = $0.0086`
- Requests: `19,102 * 0.40 / 1,000,000 = $0.0076`
- Total list-price estimate: about `$0.2020`

Cloud Run free-tier interpretation:
- If free tier is still available on the linked billing account, Cloud Run is likely effectively `$0` so far
- If free tier was already consumed by other projects under the same billing account, use the `$0.2020` figure as the likely accrued charge for Cloud Run

### Cloud SQL

One Cloud SQL instance was present:

- Instance name: `med13-pg-staging`
- Engine: `PostgreSQL 16`
- Installed version: `POSTGRES_16_12`
- Region: `us-central1`
- Zone: `us-central1-c`
- Tier: `db-f1-micro`
- Edition: `ENTERPRISE`
- Availability: `ZONAL`
- Activation policy: `ALWAYS`
- Disk size: `10 GB`
- Disk type: `PD_HDD`
- IPv4 enabled: `true`
- Public IP present: `34.61.214.246`
- Outgoing IP present: `34.44.140.115`
- Backups enabled: `false`
- Instance create time: `2026-03-05T07:26:09.615Z`
- State at capture: `RUNNABLE`

Hours elapsed from instance creation to snapshot:
- About `34.214 hours`

Observed Cloud SQL list prices from the Cloud Billing Catalog API:
- Micro instance: `$0.021/hour` for regional micro
- Zonal footprint assumption used in this estimate: half of regional micro, or `$0.0105/hour`
- Public IP reservation: `$0.01/hour`
- Storage assumption used: `10 GB * $0.000123288/GB-hour`

Why the zonal compute estimate is halved:
- The catalog entry visible from the API for micro PostgreSQL was the regional micro price
- The deployed instance is explicitly `ZONAL`
- A conservative zonal estimate was therefore taken as half of the regional micro price

Estimated accrued Cloud SQL cost:
- Instance compute: `34.214 h * $0.0105/h = $0.3592`
- Public IP: `34.214 h * $0.01/h = $0.3421`
- Storage: `34.214 h * 10 GB * $0.000123288 = $0.0422`
- Total estimated Cloud SQL accrued cost: about `$0.7436`

Estimated Cloud SQL monthly run rate with unchanged configuration:
- Instance compute: `$7.6778/month`
- Public IP: `$7.3056/month`
- Storage: `$0.8938/month`
- Total: about `$15.8772/month`

### Artifact Registry

One Artifact Registry repository was present:

- Repository: `cloud-run-source-deploy`
- Location: `us-central1`
- Format: `DOCKER`
- Mode: `STANDARD_REPOSITORY`
- Size: `3,144,502,120 bytes`
- Size in GiB: about `2.9285 GiB`
- Vulnerability scanning: disabled

Observed Artifact Registry pricing:
- First `0.5 GiB` storage free
- Additional storage: `$0.10/GiB-month`

Estimated Artifact Registry cost:
- Billable storage: `2.9285 - 0.5 = 2.4285 GiB`
- Monthly run rate: `2.4285 * 0.10 = $0.2429/month`
- Accrued since repository creation window: about `$0.0114`

### Cloud Storage

Two buckets were present:

1. `artana-bio_cloudbuild`
   - Location: `US`
   - Storage class: `STANDARD`
   - Size: `711,491,217 bytes`
   - Size in GiB: about `0.6626 GiB`
   - Pricing assumption: Standard Storage US Multi-region at `$0.026/GiB-month`

2. `run-sources-artana-bio-us-central1`
   - Location: `US-CENTRAL1`
   - Storage class: `STANDARD`
   - Size: `763,532,861 bytes`
   - Size in GiB: about `0.7111 GiB`
   - Pricing assumption: Standard Storage US Regional at `$0.02/GiB-month` after first `5 GiB` free

Estimated Cloud Storage monthly run rate:
- `artana-bio_cloudbuild`: `0.6626 * 0.026 = $0.0172/month`
- `run-sources-artana-bio-us-central1`: currently effectively `$0/month` because it is below the first `5 GiB` free regional standard storage tier used in this estimate
- Total monthly run rate: about `$0.0172/month`

Estimated accrued Cloud Storage cost:
- About `$0.0008`

### Secret Manager

Seven secrets were present:

- `med13-staging-admin-api-key`
- `med13-staging-database-url`
- `med13-staging-med13-dev-jwt-secret`
- `med13-staging-nextauth-secret`
- `med13-staging-openai-api-key`
- `med13-staging-read-api-key`
- `med13-staging-write-api-key`

Version counts observed:
- Each secret had `1` active version
- Total active secret versions observed: `7`

Observed Secret Manager pricing:
- First `6` active secret versions free
- Additional active secret versions: `$0.06/version-month`
- First `10,000` access operations free

Estimated Secret Manager cost:
- Billable versions: `7 - 6 = 1`
- Monthly run rate: `$0.06/month`
- Accrued so far: about `$0.0028`

### Cloud Build

Five successful builds were present in recent history:

| Build ID | Approx. duration | Primary image |
| --- | ---: | --- |
| `89520876-2427-43f6-8a53-d5dd0286c43a` | `2.59 min` | `med13-resource-library-staging:f0c930d4` |
| `431055ba-aac1-448c-b81b-abd77771c3e4` | `2.14 min` | `med13-resource-library-staging:ee151e6a` |
| `4f777227-531c-44e3-ba79-48495d0ee3e5` | `3.30 min` | `med13-admin-staging:74b3c020` |
| `f9305bbc-3453-4a41-a3f1-d4ad350930ed` | `5.05 min` | `med13-admin-staging:78617259` |
| `02c29389-1170-48b1-83a6-5d105b3612dc` | `5.78 min` | `med13-admin-staging:5eae4f24` |

Total observed build time:
- About `18.85 minutes`

Observed Cloud Build default pool list prices in `us-central1`:
- E2 CPU: `$0.0016/minute`
- E2 RAM: `$0.00035/minute`

Interpretation:
- At this scale, Cloud Build is likely still within free usage
- No meaningful billed amount was estimated for Cloud Build from the observed build minutes alone

### Enabled APIs With Potential Cost Relevance

The following enabled services were observed and can matter for cost depending on usage:
- `run.googleapis.com`
- `sqladmin.googleapis.com`
- `storage.googleapis.com`
- `artifactregistry.googleapis.com`
- `secretmanager.googleapis.com`
- `cloudbuild.googleapis.com` equivalent activity through build history
- `monitoring.googleapis.com`
- `logging.googleapis.com` default sinks
- `bigquery.googleapis.com`
- `pubsub.googleapis.com`

At capture time:
- no BigQuery datasets were found
- no Pub/Sub topics or subscriptions were inventoried in this cost pass
- no separate high-volume logging sink beyond `_Default` and `_Required` was found

## Estimated Cost Summary

### Accrued cost to snapshot

| Service | Estimated accrued cost |
| --- | ---: |
| Cloud SQL | `$0.7436` |
| Artifact Registry | `$0.0114` |
| Secret Manager | `$0.0028` |
| Cloud Storage | `$0.0008` |
| Cloud Run | `$0.0000` to `$0.2020` |
| Cloud Build | likely `$0.0000` |
| Total | about `$0.7586` to `$0.9606` |

### Monthly run rate with current footprint

| Service | Estimated monthly run rate |
| --- | ---: |
| Cloud SQL | `$15.8772/month` |
| Artifact Registry | `$0.2429/month` |
| Secret Manager | `$0.0600/month` |
| Cloud Storage | `$0.0172/month` |
| Cloud Run | usage-dependent, currently minimal |
| Cloud Build | usage-dependent, currently minimal |
| Total baseline excluding variable Cloud Run and Cloud Build | about `$16.1973/month` |

## Cost Drivers

The project's cost is currently dominated by Cloud SQL because:
- the instance is always on
- the instance has a public IP reservation
- the project is too new and too low-traffic for Cloud Run to matter much yet

Secondary cost drivers:
- Artifact Registry image storage
- Secret Manager version storage

Minor cost drivers:
- Cloud Storage buckets for Cloud Build and Cloud Run source deployments

## Pricing Assumptions Used

These assumptions were used to convert the observed footprint into dollar estimates:

1. Cloud Run
   - CPU: `$0.00002400/vCPU-second`
   - Memory: `$0.00000250/GiB-second`
   - Requests: `$0.40 per 1,000,000 requests`
   - Free tier may reduce effective billed cost to zero

2. Cloud SQL
   - Regional micro catalog price observed: `$0.021/hour`
   - Zonal estimate used for deployed `db-f1-micro`: `$0.0105/hour`
   - Public IP reservation: `$0.01/hour`
   - Storage estimate: `$0.000123288/GB-hour` for the configured `10 GB`

3. Artifact Registry
   - First `0.5 GiB` free
   - Additional storage at `$0.10/GiB-month`

4. Secret Manager
   - First `6` active secret versions free
   - Additional versions at `$0.06/version-month`
   - Access operation costs assumed zero at current usage

5. Cloud Storage
   - `US` standard storage bucket estimated at `$0.026/GiB-month`
   - `us-central1` regional standard storage estimated at `$0.02/GiB-month`
   - First `5 GiB` of regional standard storage assumed free for the observed regional bucket

## How To Refresh This Snapshot

Run the following commands from the repository root:

```bash
gcloud config list --format=json
gcloud beta billing projects describe artana-bio --format=json
gcloud projects describe artana-bio --format=json

gcloud run services list --platform=managed --region=us-central1 --project=artana-bio --format=json
gcloud sql instances list --project=artana-bio --format=json
gcloud storage buckets list --project=artana-bio --format=json
gcloud secrets list --project=artana-bio --format=json
gcloud artifacts repositories list --project=artana-bio --format=json
gcloud builds list --project=artana-bio --format=json --limit=100

gcloud storage du -s gs://artana-bio_cloudbuild gs://run-sources-artana-bio-us-central1
gcloud secrets list --project=artana-bio --format='value(name)' | while read -r full; do s=${full##*/}; count=$(gcloud secrets versions list "$s" --project=artana-bio --format='value(name)' | wc -l | tr -d " "); printf '%s %s\n' "$s" "$count"; done

bq ls --project_id=artana-bio --format=prettyjson
```

For Cloud Run usage totals, use the Monitoring API:

```bash
ACCESS_TOKEN=$(gcloud auth print-access-token)
START='2026-03-04T00:00:00Z'
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)

curl -sG -H "Authorization: Bearer $ACCESS_TOKEN" \
  'https://monitoring.googleapis.com/v3/projects/artana-bio/timeSeries' \
  --data-urlencode 'filter=metric.type="run.googleapis.com/container/cpu/allocation_time" AND resource.type="cloud_run_revision"' \
  --data-urlencode "interval.startTime=$START" \
  --data-urlencode "interval.endTime=$END" \
  --data-urlencode 'aggregation.alignmentPeriod=3600s' \
  --data-urlencode 'aggregation.perSeriesAligner=ALIGN_SUM' \
  --data-urlencode 'view=FULL'
```

Repeat the same query pattern for:
- `run.googleapis.com/container/memory/allocation_time`
- `run.googleapis.com/request_count`

## Recommendation For Exact Future Cost Tracking

To make this document invoice-exact next time:
- enable Cloud Billing export to BigQuery
- create a dataset dedicated to billing export
- query spend by service and SKU directly from the export tables

Without billing export:
- Cloud SQL estimates are directionally strong
- Cloud Run estimates depend on free-tier consumption across the billing account
- small services remain approximations

## Source References

- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Cloud SQL for PostgreSQL pricing](https://cloud.google.com/sql/docs/postgres/pricing)
- [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)
- [Secret Manager pricing](https://cloud.google.com/secret-manager/pricing)
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing)
- [Cloud Build pricing](https://cloud.google.com/build/pricing)
- [Google Cloud free tier](https://cloud.google.com/free/docs/gcp-free-tier)
