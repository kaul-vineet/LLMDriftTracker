# ── Stage: runtime ────────────────────────────────────────────────────────────
# Single-stage image — slim Python base, no build tools needed.
# Python 3.11 matches the development environment; avoids f-string parser
# differences present in earlier 3.x releases.
FROM python:3.11-slim

# Prevent .pyc files and ensure stdout/stderr are unbuffered so logs are
# visible immediately in 'docker logs' and Azure Container Apps log streams.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ── Runtime defaults ──────────────────────────────────────────────────────────
# These can be overridden with -e / --env-file in docker run, or via the
# 'environment:' block in docker-compose.yml, or as ACA environment variables.
#
# STORE_DIR   — persistent storage root; mounted from host or Azure Files share.
#               Holds run data, event log, MSAL token cache, agent lock files.
# CONFIG_PATH — path to config.json inside the container; mounted at runtime.
#               Override this when mounting config to a non-default location
#               (e.g. Azure Container Apps: /app/config/config.json).
ENV STORE_DIR=/app/data \
    CONFIG_PATH=/app/config.json

WORKDIR /app

# ── Dependencies ──────────────────────────────────────────────────────────────
# Install before copying app code so this layer is cached unless requirements change.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY agent/      agent/
COPY dashboard/  dashboard/
COPY .streamlit/ .streamlit/

# ── Runtime mounts (injected, never baked in) ─────────────────────────────────
# config.json       — all settings and secrets; written by the Setup page.
#                     Mount read-write so the dashboard can save changes.
# $STORE_DIR        — persistent run data, logs, MSAL token cache.
#                     Use a named volume (compose) or Azure Files share (ACA).
#
# Nothing secret lives in this image. Scanning the image layers reveals only
# source code and pip packages.

EXPOSE 8501

# Default: run the agent. Override with 'command:' in compose or ACA to run
# the dashboard instead (see docker-compose.yml and azure-deploy.sh).
CMD ["python", "-m", "agent.main"]
