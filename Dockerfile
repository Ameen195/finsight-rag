# FinSight API + frontend for Hugging Face Spaces (Docker SDK, CPU).
# Secrets (GROQ_API_KEY, DATABASE_URL, LANGFUSE_*) are NOT in the image: set them as Space
# secrets; they are read from the environment at runtime. Ingestion does not run here — the
# database is already populated.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /bin/

# Hugging Face Spaces runs containers as uid 1000
RUN useradd --create-home --uid 1000 user
USER user
ENV HOME=/home/user \
    VIRTUAL_ENV=/home/user/app/.venv \
    PATH=/home/user/app/.venv/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /home/user/app

# Dependencies (cached layer). uv.lock resolves the CUDA build of PyTorch on Linux (several GB
# of nvidia-* wheels); this Space is CPU-only, so the Docker build alone swaps in the CPU wheels
# of the same locked versions. pyproject.toml / uv.lock (and local installs) are unchanged.
COPY --chown=user pyproject.toml uv.lock ./
RUN set -eux; \
    uv venv "$VIRTUAL_ENV"; \
    uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/req.txt; \
    torch_v="$(sed -n 's/^torch==\([^ ;]*\).*/\1/p' /tmp/req.txt)"; \
    vision_v="$(sed -n 's/^torchvision==\([^ ;]*\).*/\1/p' /tmp/req.txt)"; \
    grep -vE '^(torch|torchvision|triton|nvidia-[a-z0-9-]+)==' /tmp/req.txt > /tmp/req-cpu.txt; \
    uv pip install --index-url https://download.pytorch.org/whl/cpu \
        "torch==${torch_v}" "torchvision==${vision_v}"; \
    uv pip install -r /tmp/req-cpu.txt; \
    rm /tmp/req.txt /tmp/req-cpu.txt

COPY --chown=user src ./src
RUN uv pip install --no-deps .

# bake the embedding model (and its tokenizer) and the reranker into the image so a cold
# start does not download them; names come from finsight.config defaults
RUN python -c "from finsight.ingest.embed import get_model; from finsight.retrieval.rerank import get_reranker; get_model(); get_reranker()"

EXPOSE 7860
CMD ["uvicorn", "finsight.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
