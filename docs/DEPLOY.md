# Deploying FinSight to Hugging Face Spaces

The Space runs only the API and frontend (`uvicorn finsight.api.main:app` on port 7860).
Ingestion runs locally; the Supabase database is already populated.

## 1. Create the Space
1. On huggingface.co: **New Space** → SDK **Docker** → hardware **CPU basic (free)**.
2. Add this front-matter at the very top of `README.md` (Spaces reads it):
   ```yaml
   ---
   title: FinSight
   sdk: docker
   app_port: 7860
   ---
   ```

## 2. Add secrets (Space → Settings → Variables and secrets)
| Name | Value |
|---|---|
| `GROQ_API_KEY` | your Groq key |
| `DATABASE_URL` | Supabase **session pooler** connection string |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | optional; tracing is off without them |
| `LANGFUSE_HOST` | optional, default `https://cloud.langfuse.com` |

Nothing secret is copied into the image (`.env` is in `.dockerignore`); all values are read
from the environment at runtime by `finsight.config`.

## 3. Push
```powershell
git remote add space https://huggingface.co/spaces/<user>/<space>
git push space main
```
The Space builds the `Dockerfile`: the locked dependencies (`uv export --frozen --no-dev`)
with PyTorch swapped for the CPU wheels of the same versions, then the embedding model and
reranker are downloaded into the image so cold starts skip that step.

Local test (optional, needs Docker Desktop running). Measured: first build ~5.5 min; about
2.4 GB on disk inside the image (Docker Desktop lists ~5.9 GB because its store counts the
compressed and unpacked layers); health check ready ~13 s after start.
```powershell
docker build -t finsight .
docker run --rm -p 7860:7860 --env-file .env finsight
```

## 4. Check
- `https://<user>-<space>.hf.space/api/health` → `{"status": "ok", "db": true}`
- Open the Space URL and ask a question.

## Notes
- The free CPU Space sleeps when idle; the first request after waking is slow.
- Rate limit: 10 questions per hour per client IP (in memory, resets on restart).
- Supabase pauses after 7 days without traffic; the keep-alive workflow (Phase 6) pings
  `/api/health` daily.
- CPU-only PyTorch is applied in the Dockerfile only: `uv.lock` still resolves the CUDA build
  for Linux, and local Windows installs (CPU PyTorch by default) are unaffected. If the lock's
  PyTorch version is ever missing from the CPU index, the Docker build fails at that step.
- Docling (ingestion only) is still installed in the image; moving it to an optional dependency
  group would shrink the image further.
