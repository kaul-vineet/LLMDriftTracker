# ⚡ LLM Drift Tracker — copilot-eval-agent

> Autonomous agent that watches every Copilot Studio bot across your Power Platform
> environments, detects AI model version changes, runs programmatic evaluations, and
> emails you a side-by-side drift analysis report — all without you lifting a finger.

---

## What it does

```
Every N minutes
  └─ Fetch all bots from Dataverse (all environments)
       └─ Model version changed since last run?
            ├─ No  → skip
            └─ Yes → trigger Copilot Studio Eval API
                       └─ Poll until complete
                            └─ Compare metrics (prev vs curr)
                                 └─ LLM analyses the delta
                                      └─ Email HTML report
```

No pass/fail verdicts. No published changes. Pure observation.

---

## Quick start

### Prerequisites

| What | Why |
|---|---|
| Python 3.11+ | Run bootstrap |
| Docker | Run the agent |
| Azure CLI (`az`) | Local Dataverse auth |
| App registration | Eval API delegated auth — see below |

### 1 — App registration (one-time)

1. Azure Portal → **App registrations** → New
2. Name it anything (e.g. `copilot-eval-agent`)
3. **API permissions** → Add → APIs my org uses → search `Power Platform API`
4. Add delegated permissions: `CopilotStudio.MakerOperations.Read` + `ReadWrite`
5. **Grant admin consent**
6. Note the **Application (client) ID** and **Directory (tenant) ID**

### 2 — Run setup wizard

```bash
pip install msal
python bootstrap.py
```

The wizard will:
- Prompt for your environments, credentials, poll interval, LLM config
- Sign you in via Microsoft device code flow (browser, one-time)
- Set up SMTP and send a test email
- Write `config.json` and cache your token

### 3 — Build and run

```bash
docker build -t copilot-eval-agent .

docker run -d \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/msal_token_cache.json:/app/msal_token_cache.json \
  -v $(pwd)/config.json:/app/config.json \
  copilot-eval-agent
```

Logs: `docker logs -f <container-id>`

---

## Files

```
bootstrap.py        Setup wizard — run once on host
agent.py            Main polling loop
auth.py             Dual-mode auth (local: az CLI / Docker: service principal)
dataverse.py        Fetch bots + model versions from Dataverse
eval_client.py      Copilot Studio Eval REST API client
reasoning.py        Metric aggregation + LLM drift analysis
report.py           HTML report generator
notifier.py         SMTP email sender
store.py            Local JSON state (data/{botId}/)
config.json         Your config — gitignored, created by bootstrap
msal_token_cache.json  Cached auth token — gitignored, mount into Docker
```

---

## config.json reference

```jsonc
{
  "environments": [
    {
      "name": "Production",
      "orgUrl": "https://orgXXXXX.crm.dynamics.com",
      "environmentId": "orgXXXXX"
    }
  ],

  "eval_app_client_id": "<app registration client id>",
  "eval_app_tenant_id": "<tenant id>",
  "token_cache_file":   "msal_token_cache.json",

  "store_dir":             "data",
  "poll_interval_minutes": 10,

  "llm": {
    "base_url": "http://localhost:11434/v1",  // any OpenAI-compatible endpoint
    "api_key":  "ollama",
    "model":    "llama3"
  },

  "smtp": {
    "host":      "smtp.office365.com",
    "port":      587,
    "user":      "sender@example.com",
    "password":  "...",
    "recipient": "admin@example.com"
  }
}
```

All SMTP fields can be overridden with env vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_RECIPIENT`.

---

## Auth

### Local (development)
- **Dataverse / BAPI** — `az account get-access-token` (Azure CLI, logged-in user)
- **Eval API** — MSAL delegated device code, token cached to `msal_token_cache.json`

### Docker (production)
- **Dataverse / BAPI** — `ClientSecretCredential` via `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` / `AZURE_TENANT_ID` env vars
- **Eval API** — same cached MSAL token, mounted as a volume

### Token expiry (self-healing)
When the eval token expires, the agent emails the admin a device code and the sign-in link. The agent keeps polling for 15 minutes. If the admin doesn't act, the current eval cycle is skipped and a fresh code is emailed on the next poll. No container restart needed.

---

## Eval API pre-requisite

The Copilot Studio Eval API only runs against **test sets you have created** in the Copilot Studio UI.

1. Open Copilot Studio → your bot → **Evaluation** tab
2. Create a test set with sample utterances
3. The agent will discover and run it automatically

Without a test set, the agent logs `no test sets found` and skips the bot.

---

## Docker — passing credentials

```bash
docker run -d \
  -e AZURE_TENANT_ID=<tenant>   \
  -e AZURE_CLIENT_ID=<client>   \
  -e AZURE_CLIENT_SECRET=<secret> \
  -e SMTP_PASSWORD=<password>   \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/msal_token_cache.json:/app/msal_token_cache.json \
  -v $(pwd)/config.json:/app/config.json \
  copilot-eval-agent
```

---

## Report

Each cycle where a model change is detected produces:

- **`data/report_<timestamp>.html`** — self-contained HTML, emailed automatically
- Side-by-side metric scorecard (previous model vs current model)
- Delta column with colour gradient (green = improved, red = regressed)
- LLM narrative explaining what changed and why it matters

---

## Local state layout

```
data/
  <botId>/
    tracking.json      last known model version + run ID
    run_<runId>.json   full eval result
```

Delete `data/<botId>/tracking.json` to force a re-evaluation on the next cycle.
