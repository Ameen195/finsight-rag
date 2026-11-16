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
The Space builds the `Dockerfile`: dependencies with `uv sync --frozen --no-dev`, then the
embedding model and reranker are downloaded into the image so cold starts skip that step.

## 4. Check
- `https://<user>-<space>.hf.space/api/health` → `{"status": "ok", "db": true}`
- Open the Space URL and ask a question.

## Notes
- The free CPU Space sleeps when idle; the first request after waking is slow.
- Rate limit: 10 questions per hour per client IP (in memory, resets on restart).
- Supabase pauses after 7 days without traffic; the keep-alive workflow (Phase 6) pings
  `/api/health` daily.
- Image size: the current `uv.lock` resolves the CUDA build of PyTorch on Linux (several GB of
  `nvidia-*` wheels). Switching PyTorch to the CPU index in `pyproject.toml` shrinks the image a
  lot; this is a pending decision.
