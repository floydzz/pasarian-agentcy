# syntax=docker/dockerfile:1

# One image, one build, both halves of the product.
#
# The console fetches `/api/...` with no base URL, so if FastAPI serves the
# built SPA there is no second origin, no CORS, no proxy and nothing to
# configure per environment. That is why this is a single image rather than a
# web container beside an api container.

# ---- 1. the console ---------------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /web

# Manifests first: dependencies only reinstall when they actually change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ---- 2. python dependencies -------------------------------------------------
# Built in its own stage so the compilers chromadb's native wheels may need
# never reach the runtime image.
FROM python:3.13-slim AS deps
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY backend/pyproject.toml ./

# Read the dependency list out of pyproject rather than restating it here —
# a requirements file duplicated into a Dockerfile drifts on the first change.
RUN python -c "\
import pathlib, tomllib; \
project = tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']; \
pathlib.Path('requirements.txt').write_text('\n'.join(project['dependencies']))" \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt


# ---- 3. runtime -------------------------------------------------------------
FROM python:3.13-slim AS runtime

# DejaVu is what the compositor falls back to for headline and CTA type.
# FFmpeg turns Agentcy's product storyboard into a reviewable H.264 MP4.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=deps /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend \
    # Absolute, so it short-circuits the repo-relative default and lands on the
    # volume instead of inside the container's writable layer.
    CHROMA_PATH=/data/chroma \
    ASSETS_PATH=/data/assets

# The container mirrors the repo layout on purpose: the code resolves `data/`
# and `frontend/dist` relative to its own file, so /app is the repo root.
WORKDIR /app/backend
COPY backend/ /app/backend/
COPY --from=web /web/dist /app/frontend/dist
# The cinematic trailer uses these real application screens as protected
# inserts. They are copied into durable `/media` storage when a trailer is
# created, rather than being sent to a video model to be distorted.
COPY image-studio.png /app/image-studio.png
COPY hub.png /app/hub.png
COPY history-work.png /app/history-work.png
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /data/chroma /data/assets \
    && useradd --create-home --uid 10001 agentcy \
    && chown -R agentcy:agentcy /data /app

USER agentcy
EXPOSE 8000

ENTRYPOINT ["entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
