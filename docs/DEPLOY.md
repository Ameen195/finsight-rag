# Deploying FinSight to Google Cloud Run (optional)

> **FinSight is not deployed.** It runs locally or in Docker (see the README). This guide is
> for anyone who wants to host it. Cloud Run needs a billing account, and storing the image in
> Artifact Registry costs a few cents a month.

The service runs only the API and frontend (`uvicorn finsight.api.main:app`, port 7860).
Ingestion runs locally; the Supabase database is already populated.

## Sizing (measured locally with `docker stats`)
- Idle after warm-up: ~520 MiB. Peak while answering 3 questions: ~675 MiB.
- → **1 GiB memory, 1 vCPU** (about 50% headroom over the measured peak).
- Container ready ~13 s after start (models are baked into the image), so a cold start after
  scale-to-zero takes roughly 15–20 s before the first answer.

## Cost notes (check current Google pricing before deploying)
- Cloud Run has a monthly free tier (request, vCPU-second and GiB-second allowances); with
  min instances 0 and light demo traffic the service should stay inside it.
- A **billing account must be linked** to the project even when usage stays in the free tier.
- The image (~2.4 GB) is stored in Artifact Registry, whose free storage is smaller than that,
  so expect a small monthly storage charge (cents). Set a budget alert.

## 1. One-time setup
1. Install the gcloud CLI and log in: `gcloud auth login`.
2. Create or pick a project and set it: `gcloud config set project <PROJECT_ID>`.
3. Enable APIs: `gcloud services enable run.googleapis.com artifactregistry.googleapis.com`.
4. Create a Docker repository (pick a region that has the Cloud Run free tier):
   `gcloud artifacts repositories create finsight --repository-format=docker --location=<REGION>`
5. Let Docker push there: `gcloud auth configure-docker <REGION>-docker.pkg.dev`.
6. In the console, **Billing → Budgets & alerts**: create a small budget (e.g. $5) with alerts.

## 2. Build and push the image
```powershell
docker build -t <REGION>-docker.pkg.dev/<PROJECT_ID>/finsight/finsight:latest .
docker push <REGION>-docker.pkg.dev/<PROJECT_ID>/finsight/finsight:latest
```
The Dockerfile installs CPU-only PyTorch (same locked version) for the image only;
`pyproject.toml`, `uv.lock` and local installs are unchanged.

## 3. Secrets (values never go into the image or the repo)
Store them in Secret Manager (`gcloud services enable secretmanager.googleapis.com`), then
create one secret per name and paste the value when prompted (console: **Secret Manager →
Create secret**):
`GROQ_API_KEY`, `DATABASE_URL` (Supabase session pooler), and optionally
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`. Grant the Cloud Run service account the
**Secret Manager Secret Accessor** role.

## 4. Deploy
```powershell
gcloud run deploy finsight `
  --image <REGION>-docker.pkg.dev/<PROJECT_ID>/finsight/finsight:latest `
  --region <REGION> --port 7860 `
  --memory 1Gi --cpu 1 --cpu-boost `
  --min-instances 0 --max-instances 1 --concurrency 4 `
  --allow-unauthenticated `
  --set-secrets "GROQ_API_KEY=GROQ_API_KEY:latest,DATABASE_URL=DATABASE_URL:latest,LANGFUSE_PUBLIC_KEY=LANGFUSE_PUBLIC_KEY:latest,LANGFUSE_SECRET_KEY=LANGFUSE_SECRET_KEY:latest"
```
- `--min-instances 0`: scales to zero when idle (no cost while unused).
- `--max-instances 1`: caps cost, and keeps the in-memory rate limit (10 questions/hour per IP)
  meaningful, since that limit is per instance.
- `--cpu-boost`: extra CPU during start-up to shorten cold starts.
- `--concurrency 4`: the app shares one DB connection per instance, so keep this low.
- Drop the two Langfuse entries from `--set-secrets` if you do not use tracing.

## 5. Check
- `https://<service-url>/api/health` → `{"status": "ok", "db": true}`
- Open the service URL and ask a question.

## Local container test (optional)
```powershell
docker build -t finsight .
docker run --rm -p 7860:7860 --env-file .env finsight
```
Measured: first build ~5.5 min; ~2.4 GB on disk inside the image (Docker Desktop lists
~5.9 GB because its store counts compressed and unpacked layers).

## Notes
- Supabase pauses after 7 days without traffic; the keep-alive workflow
  (`.github/workflows/keep-alive.yml`) runs a light query against the database every Monday. It
  does not call the Cloud Run service, so the service still scales to zero.
- Docling (ingestion only) is still installed in the image; moving it to an optional
  dependency group would shrink the image.
