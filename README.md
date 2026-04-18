# ⚡ LLM Drift Tracker — copilot-eval-agent

> Autonomous agent that watches every tagged Copilot Studio bot across your Power Platform
> environments, detects AI model version changes, runs programmatic evaluations, and
> emails a side-by-side drift analysis report — fully headless after first setup.

---

## How it works

```
Every N minutes
  └─ Fetch all bots from Dataverse (all environments)
       └─ Bot description contains #monitor?
            ├─ No  → skip (not enrolled)
            └─ Yes → model version changed since last run?
                       ├─ No  → skip (no drift)
                       └─ Yes → trigger Copilot Studio Eval API
                                  └─ Poll until complete
                                       └─ Compare metrics (prev vs curr)
                                            └─ LLM analyses the delta
                                                 └─ Email HTML report
```

No pass/fail verdicts. No published changes. Pure observation.

---

## Full setup — A to Z

### Step 1 — Prerequisites

| What | Where to get it |
|---|---|
| Python 3.11+ | python.org |
| Docker Desktop | docker.com |
| Azure CLI | `winget install Microsoft.AzureCLI` |
| Power Platform Admin access | For app registration + admin consent |
| Copilot Studio Maker access | To tag bots and create test sets |

---

### Step 2 — Create the app registration

This is a one-time Azure Portal task. The agent uses this registration to call the Copilot Studio Eval API.

1. Go to [portal.azure.com](https://portal.azure.com) → **Azure Active Directory** → **App registrations** → **New registration**
2. Name: `copilot-eval-agent` (or anything you like)
3. Supported account types: **Single tenant**
4. Click **Register**
5. Note down:
   - **Application (client) ID**
   - **Directory (tenant) ID**
6. Go to **API permissions** → **Add a permission** → **APIs my organization uses**
7. Search for `Power Platform API` → select it
8. Choose **Delegated permissions** → tick:
   - `CopilotStudio.MakerOperations.Read`
   - `CopilotStudio.MakerOperations.ReadWrite`
9. Click **Add permissions**
10. Click **Grant admin consent for [your tenant]** → confirm

> The agent uses **delegated auth** (your identity, not a service principal) because the Eval API requires it. The app registration is the vehicle — your sign-in is the credential.

---

### Step 3 — Tag the bots you want monitored

The agent only evaluates bots explicitly opted in. No tag = not watched.

1. Open [Copilot Studio](https://copilotstudio.microsoft.com)
2. Open the bot you want to monitor
3. Go to **Settings** → **Details**
4. Add `#monitor` anywhere in the **Description** field

```
Handles HR queries for APAC employees. Routes to payroll and leave topics. #monitor
```

5. Save

Repeat for every bot you want tracked. To stop monitoring a bot, remove `#monitor` from its description — takes effect on the next poll cycle. No restarts needed.

---

### Step 4 — Create test sets in Copilot Studio

The Eval API runs against test sets you define. Without them the agent has nothing to evaluate.

1. Open Copilot Studio → your `#monitor` bot → **Evaluation** tab
2. Click **New test set**
3. Add 10–20 sample utterances that cover the bot's main topics
4. For each utterance, add the expected response or topic
5. Save the test set

> Do this for every bot tagged `#monitor`. The agent discovers test sets automatically — you don't need to configure anything in the agent itself.

---

### Step 5 — Run the setup wizard

Clone the repo and run `bootstrap.py` on your host machine (not in Docker). This is a one-time step.

```bash
git clone https://github.com/kaul-vineet/LLMDriftTracker.git
cd LLMDriftTracker
pip install -r requirements.txt
python bootstrap.py
```

The wizard walks you through 5 steps:

| Step | What happens |
|---|---|
| 1 · Environments | Enter org URLs + environment IDs for each Power Platform env |
| 2 · Credentials | Paste the client ID and tenant ID from Step 2 |
| 3 · Agent settings | Poll interval, LLM endpoint (Ollama / Azure OpenAI / any OpenAI-compatible) |
| 4 · Microsoft sign-in | Browser device code flow — one-time, token cached for future runs |
| 5 · Email reports | SMTP config + test email fires to confirm delivery |

At the end, `config.json` and `msal_token_cache.json` are written to the project directory.

**Finding your environment details:**

| Field | Where to find it |
|---|---|
| Org URL | Power Platform Admin Centre → Environments → your env → copy the Environment URL |
| Environment ID | Same page — the `org` prefix in the URL (e.g. `orge71ae48e`) |

---

### Step 6 — Test locally before Docker

Run one cycle on your machine to confirm everything works end-to-end.

```bash
python agent.py
```

What to look for in the logs:

```
[dataverse] Production: 2 bot(s) tagged #monitor
[agent] HRBot: model changed unknown → gpt-4o-2024-11-20
[agent] report saved → data/report_20250418T143012.html
[notifier] Report emailed to admin@example.com
```

**If you see `no model changes detected`** — delete `data/<botId>/tracking.json` to force the agent to treat the current version as new and trigger an eval:

```bash
rm data/<botId>/tracking.json
python agent.py
```

---

### Step 7 — Build and run in Docker

Once local works, move to Docker for autonomous round-the-clock operation.

**Build:**
```bash
docker build -t copilot-eval-agent .
```

**Run (basic — local auth via az CLI):**
```bash
docker run -d \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/msal_token_cache.json:/app/msal_token_cache.json \
  -v $(pwd)/config.json:/app/config.json \
  copilot-eval-agent
```

**Run (production — service principal for Dataverse/BAPI auth):**
```bash
docker run -d \
  -e AZURE_TENANT_ID=<tenant-id> \
  -e AZURE_CLIENT_ID=<sp-client-id> \
  -e AZURE_CLIENT_SECRET=<sp-secret> \
  -e SMTP_PASSWORD=<smtp-password> \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/msal_token_cache.json:/app/msal_token_cache.json \
  -v $(pwd)/config.json:/app/config.json \
  copilot-eval-agent
```

**Watch logs:**
```bash
docker logs -f <container-id>
```

> The eval token (`msal_token_cache.json`) must always be mounted. It contains your delegated identity for the Eval API and cannot be replaced by a service principal.

---

## Token expiry — self-healing auth

The MSAL eval token expires periodically. When it does, the agent **emails the admin** automatically:

```
Subject: [LLM Drift Tracker] Sign-in required — code XXXXXXXX

1. Open https://microsoft.com/devicelogin
2. Enter code: XXXXXXXX

The agent will resume automatically once you sign in.
```

- The agent polls for 15 minutes after sending the email
- If the admin doesn't act in time, the current eval cycle is skipped
- A **fresh code is emailed on every subsequent poll cycle** until sign-in is completed
- No container restart needed — the agent self-recovers

---

## Files

```
bootstrap.py          Setup wizard — run once on host
agent.py              Main polling loop
auth.py               Dual-mode auth (local: az CLI / Docker: service principal)
dataverse.py          Fetch #monitor bots + model versions from Dataverse
eval_client.py        Copilot Studio Eval REST API client
reasoning.py          Metric aggregation + LLM drift analysis
report.py             HTML report generator
notifier.py           SMTP email sender
store.py              Local JSON state (data/{botId}/)
Dockerfile            Container definition
.dockerignore         Excludes secrets and data from image
config.json           Your config — gitignored, created by bootstrap
msal_token_cache.json Cached auth token — gitignored, mount into Docker
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
    },
    {
      "name": "UAT",
      "orgUrl": "https://orgYYYYY.crm.dynamics.com",
      "environmentId": "orgYYYYY"
    }
  ],

  "eval_app_client_id": "<app registration client id>",
  "eval_app_tenant_id": "<tenant id>",
  "token_cache_file":   "msal_token_cache.json",

  "store_dir":             "data",
  "poll_interval_minutes": 10,

  "llm": {
    "base_url": "http://localhost:11434/v1",
    "api_key":  "ollama",
    "model":    "llama3"
  },

  "smtp": {
    "host":      "smtp.office365.com",
    "port":      587,
    "user":      "sender@contoso.com",
    "password":  "...",
    "recipient": "admin@contoso.com"
  }
}
```

All SMTP values can be overridden via env vars: `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` `SMTP_RECIPIENT`.

---

## Auth reference

| Context | Dataverse / BAPI | Eval API |
|---|---|---|
| Local (dev) | `az account get-access-token` | MSAL device code → cached token |
| Docker (prod) | `ClientSecretCredential` via env vars | Same cached token, volume-mounted |

---

## Report format

Each detected model change produces a self-contained HTML report:

- Side-by-side metric scorecard — previous model vs current model
- Delta column with colour gradient (green = improved, red = regressed, grey = negligible)
- LLM narrative — plain English explanation of what changed and what to watch
- Saved to `data/report_<timestamp>.html` and emailed automatically

---

## Local state layout

```
data/
  <botId>/
    tracking.json       last known model version + run ID
    run_<runId>.json    full eval result payload
```

Delete `data/<botId>/tracking.json` to force a re-evaluation on the next cycle.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `0 bot(s) tagged #monitor` | Add `#monitor` to bot description in Copilot Studio → Settings → Details |
| `no test sets found` | Create a test set in Copilot Studio → bot → Evaluation tab |
| `no model changes detected` | Delete `data/<botId>/tracking.json` and re-run |
| `Dataverse token failed` | Run `az login` and re-authenticate |
| `MSAL auth failed` | Re-run `python bootstrap.py` to refresh token |
| `SMTP test failed` | Check host/port/credentials in config.json — Office 365 uses `smtp.office365.com:587` |
| Container exits immediately | Run `docker logs <id>` — likely missing volume mount for config.json |
