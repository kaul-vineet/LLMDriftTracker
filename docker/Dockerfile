FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ agent/
COPY dashboard/ dashboard/
COPY .streamlit/ .streamlit/

# config.json, msal_token_cache.json, and data/ are mounted at runtime.
# They are NOT baked into the image so secrets never land in layers.
#
# docker-compose.yml mounts:
#   ./data:/app/data
#   ./config.json:/app/config.json
#   ./msal_token_cache.json:/app/msal_token_cache.json  (created on first auth)
VOLUME ["/app/data"]

ENV LLM_BASE_URL=""
ENV LLM_API_KEY=""
ENV LLM_MODEL=""
ENV SMTP_HOST=""
ENV SMTP_PORT=""
ENV SMTP_USER=""
ENV SMTP_PASSWORD=""
ENV SMTP_RECIPIENT=""

CMD ["python", "-m", "agent.main"]
