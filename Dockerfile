FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ agent/
COPY dashboard/ dashboard/
COPY .streamlit/ .streamlit/
COPY config.json .

# Mounted at runtime:
#   -v ./data:/app/data                      (bot state + run history)
#   -v ./msal_token_cache.json:/app/msal_token_cache.json  (MSAL token)
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
