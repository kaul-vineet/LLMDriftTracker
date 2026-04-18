```
  ██╗     ██╗     ███╗   ███╗    ██████╗ ██████╗ ██╗███████╗████████╗
  ██║     ██║     ████╗ ████║    ██╔══██╗██╔══██╗██║██╔════╝╚══██╔══╝
  ██║     ██║     ██╔████╔██║    ██║  ██║██████╔╝██║█████╗     ██║
  ██║     ██║     ██║╚██╔╝██║    ██║  ██║██╔══██╗██║██╔══╝     ██║
  ███████╗███████╗██║ ╚═╝ ██║    ██████╔╝██║  ██║██║██║        ██║
  ╚══════╝╚══════╝╚═╝     ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝        ╚═╝

  ⚡  T R A C K E R      copilot-eval-agent  ·  v1.0
```

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)
![Platform](https://img.shields.io/badge/Power_Platform-Copilot_Studio-742774?style=flat-square&logo=microsoft&logoColor=white)
![Auth](https://img.shields.io/badge/Auth-MSAL_delegated-0078D4?style=flat-square&logo=microsoftazure&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)

**Autonomous model drift detection for Microsoft Copilot Studio bots.**

*Know the moment your AI changes — before your users do.*

</div>

---

## The Problem

Your Copilot Studio bots run on top of large language models. Microsoft updates those models. When they do, your bot's behaviour can shift — subtly or dramatically — with zero warning. Accuracy drops. Tone changes. Topics misfire. You find out from a support ticket, not a dashboard.

## The Solution

**LLM Drift Tracker** watches every bot you care about, around the clock. The moment a model version change is detected in Dataverse, it fires the Copilot Studio Eval API, pulls the results, runs an LLM analysis of the metric delta, and emails you a clean side-by-side report — all before your users notice anything.

No pass/fail verdicts. No automated rollbacks. No changes to your bots. Pure, unobtrusive observation.

---

## How it works

```
┌─────────────────────────────────────────────────────────────────────┐
│                     copilot-eval-agent loop                         │
│                                                                     │
│   Every N minutes                                                   │
│     │                                                               │
│     ▼                                                               │
│   Dataverse ──► fetch all bots ──► filter: description has #monitor │
│                                         │                           │
│                                         ▼                           │
│                              gPTSettings.defaultSchemaName          │
│                              changed since last run?                │
│                                    │           │                    │
│                                   NO          YES                   │
│                                    │           │                    │
│                                  skip    Eval REST API              │
│                                            │                        │
│                                      poll until done                │
│                                            │                        │
│                                    extract metrics                  │
│                                    prev  ◄──► curr                  │
│                                            │                        │
│                                    LLM drift analysis               │
│                                            │                        │
│                                    HTML report ──► email            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Features

| Feature | Detail |
|---|---|
| **Multi-environment** | Watches bots across unlimited Power Platform environments |
| **Opt-in via `#monitor`** | Tag a bot's description — no config changes ever |
| **Zero-touch eval** | Discovers test sets automatically, triggers and polls the Eval API |
| **Side-by-side metrics** | Pass rate delta per metric — green/red gradient, no pass/fail label |
| **LLM reasoning** | Any OpenAI-compatible model explains the drift in plain English |
| **Self-healing auth** | Token expires? Emails admin a device code, resumes when signed in |
| **HTML reports** | Self-contained, email-ready, saved locally too |
| **Docker native** | Runs headless, mounts state as volumes |
| **No cloud storage** | All state is local JSON — no Dataverse writes, no blob storage |

---

## Directory structure

```
LLMDriftTracker/
│
├── agent.py              ← main loop — polls, orchestrates, saves reports
├── auth.py               ← dual-mode auth (az CLI locally · SP in Docker)
│                            self-healing eval token with email alert
├── bootstrap.py          ← one-time setup wizard (jazzy terminal UI)
│                            creates config.json, caches MSAL token
├── dataverse.py          ← fetches #monitor bots + model version from Dataverse
├── eval_client.py        ← Copilot Studio Eval REST API (get sets · trigger · poll)
├── reasoning.py          ← metric aggregation + LLM drift narrative
├── report.py             ← self-contained HTML report generator
├── notifier.py           ← SMTP email sender (env var overrides)
├── store.py              ← local JSON state per bot (tracking + run history)
│
├── Dockerfile            ← python:3.12-slim, volumes for data + secrets
├── .dockerignore
├── requirements.txt      ← requests · msal · schedule · openai · azure-identity
│
├── config.json           ← your config (gitignored — created by bootstrap)
├── msal_token_cache.json ← cached eval token (gitignored — mount into Docker)
│
└── data/                 ← runtime state (gitignored — mount into Docker)
    └── <botId>/
        ├── tracking.json          last known model version + run ID
        └── run_<runId>.json       full eval result payload
```

---

## Full setup — A to Z

### 1 — Prerequisites

| What | How |
|---|---|
| Python 3.11+ | [python.org](https://python.org) |
| Docker Desktop | [docker.com](https://docker.com) |
| Azure CLI | `winget install Microsoft.AzureCLI` |
| Power Platform admin access | For app registration + admin consent |
| Copilot Studio Maker access | To tag bots and create test sets |

---

### 2 — App registration (one-time)

The agent uses **delegated auth** — it calls the Eval API as you, not as a service. The app registration is the vehicle; your sign-in is the credential. This is a Microsoft requirement for the Eval API.

1. [portal.azure.com](https://portal.azure.com) → **Azure Active Directory** → **App registrations** → **New registration**
2. Name: `copilot-eval-agent` · Account type: **Single tenant** → **Register**
3. Note the **Application (client) ID** and **Directory (tenant) ID**
4. **API permissions** → **Add a permission** → **APIs my organization uses** → search `Power Platform API`
5. **Delegated permissions** → tick:
   - `CopilotStudio.MakerOperations.Read`
   - `CopilotStudio.MakerOperations.ReadWrite`
6. **Add permissions** → then **Grant admin consent for [tenant]** → confirm

---

### 3 — Tag bots you want monitored

The agent ignores every bot that isn't explicitly opted in. To enrol a bot:

1. Open [Copilot Studio](https://copilotstudio.microsoft.com) → your bot
2. **Settings** → **Details** → **Description**
3. Add `#monitor` anywhere in the text

```
Handles HR queries for APAC employees. Routes to payroll and leave topics. #monitor
```

4. Save

To stop monitoring: remove `#monitor` from the description. Takes effect on the next poll cycle. No restarts, no config edits.

---

### 4 — Create test sets in Copilot Studio

The Eval API only runs against test sets you define. Without them, the agent skips the bot.

1. Open Copilot Studio → your `#monitor` bot → **Evaluation** tab
2. **New test set** → add 10–20 utterances covering the bot's main topics
3. For each utterance, add expected responses or topic labels
4. Save

The agent discovers and runs all test sets automatically.

---

### 5 — Run the setup wizard

Clone and run `bootstrap.py` on your machine (not inside Docker). One-time.

```bash
git clone https://github.com/kaul-vineet/LLMDriftTracker.git
cd LLMDriftTracker
pip install -r requirements.txt
python bootstrap.py
```

```
  ╔══════════════════════════════════════════════════════════╗
  ║  ⚡  L L M   D R I F T   T R A C K E R  ⚡             ║
  ║     copilot-eval-agent  ·  v1.0  ·  Setup Wizard        ║
  ╚══════════════════════════════════════════════════════════╝

  Welcome. Five steps and you're done.

  [████████████░░░░░░░░░░░░]  50%  step 3/5

  ╔═══ ⚙️  Step 3 · Agent Settings ══════════════════════════╗
  ╚══════════════════════════════════════════════════════════╝
```

| Step | What it does |
|---|---|
| 1 · Environments | Org URLs + environment IDs for each Power Platform env |
| 2 · Credentials | Client ID + tenant ID from the app registration |
| 3 · Agent settings | Poll interval + LLM endpoint (Ollama / Azure OpenAI / any OpenAI-compatible) |
| 4 · Microsoft sign-in | Browser device code — one-time, token cached |
| 5 · SMTP | Mail server config + test email to confirm delivery |

Outputs: `config.json` + `msal_token_cache.json`

**Finding your environment details:**

| Field | Where |
|---|---|
| Org URL | Power Platform Admin Centre → Environments → [env] → Environment URL |
| Environment ID | The `org...` prefix in that URL (e.g. `orge71ae48e`) |

---

### 6 — Test locally

Verify end-to-end before committing to Docker.

```bash
python agent.py
```

Expected output:

```
[dataverse] Production: 2 bot(s) tagged #monitor
[agent] HRBot: model changed unknown → gpt-4o-2024-11-20
[eval]  HRBot: run abc123 completed
[agent] report saved → data/report_20250418T143012.html
[notifier] Report emailed to admin@contoso.com
[agent] ── cycle complete — 1 bot(s) reported ──
```

**Force a re-evaluation** (useful for first test — deletes prior tracking so agent treats current version as new):

```bash
rm data/<botId>/tracking.json
python agent.py
```

---

### 7 — Run in Docker

**Build:**
```bash
docker build -t copilot-eval-agent .
```

**Run — local auth (dev/test):**
```bash
docker run -d \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/msal_token_cache.json:/app/msal_token_cache.json \
  -v $(pwd)/config.json:/app/config.json \
  copilot-eval-agent
```

**Run — service principal auth (production):**
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

```bash
docker logs -f <container-id>
```

> `msal_token_cache.json` must always be mounted. It holds your delegated identity for the Eval API — a service principal cannot replace it.

---

## Dashboard (Streamlit)

A read-only web dashboard runs alongside the agent and visualises all drift data.

**Run locally:**
```bash
streamlit run app.py
```
Open `http://localhost:8501`

**Run in Docker (separate container, shared data volume):**
```bash
docker run -d \
  -p 8501:8501 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config.json:/app/config.json \
  --entrypoint streamlit \
  copilot-eval-agent run app.py --server.headless true
```

| Page | What you see |
|---|---|
| Overview | Fleet heatmap across all bots × model versions + KPI cards |
| Bot Detail | Radar chart · Metric trend lines · Box plots · Sankey test-case flow · Failure clusters · LLM analysis |

---

## Token expiry — self-healing

When the eval token expires, the agent emails the admin without any manual intervention:

```
Subject: [LLM Drift Tracker] Sign-in required — code XXXXXXXX

1. Open  https://microsoft.com/devicelogin
2. Enter code  XXXXXXXX

The agent resumes automatically once signed in.
Code expires in 15 minutes — a fresh one arrives next poll cycle if missed.
```

No container restart. No terminal access. The agent skips the affected cycle and re-issues a fresh code on every subsequent poll until sign-in is completed.

---

## The report

Every detected model change produces a self-contained HTML report — saved locally and emailed.

```
┌──────────────────────────────────────────────────────────────┐
│  HRBot  ·  model drift detected                              │
│  gpt-4o-mini-2024-07-18  →  gpt-4o-2024-11-20               │
├─────────────────────┬──────────────┬──────────────┬──────────┤
│ Metric              │ Previous     │ Current      │ Delta    │
├─────────────────────┼──────────────┼──────────────┼──────────┤
│ Utterance accuracy  │ 0.74         │ 0.81         │ ▲ +0.07  │  ← green
│ Topic match rate    │ 0.88         │ 0.85         │ ▼ −0.03  │  ← red
│ Response relevance  │ 0.71         │ 0.73         │ ▲ +0.02  │  ← grey
├─────────────────────┴──────────────┴──────────────┴──────────┤
│  Analysis                                                     │
│  The upgrade to gpt-4o improves overall accuracy but shows   │
│  a slight regression in topic routing. The payroll topic      │
│  accounts for most mismatches — review trigger phrases.       │
└──────────────────────────────────────────────────────────────┘
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
    "base_url": "http://localhost:11434/v1",   // any OpenAI-compatible endpoint
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

SMTP values can be overridden via env vars: `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` `SMTP_RECIPIENT`

---

## Auth reference

| Context | Dataverse / BAPI | Eval API |
|---|---|---|
| Local (dev) | `az account get-access-token` | MSAL device code → cached |
| Docker (prod) | `ClientSecretCredential` via env vars | Cached token, volume-mounted |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `0 bot(s) tagged #monitor` | Add `#monitor` to bot description — Copilot Studio → Settings → Details |
| `no test sets found` | Create a test set — Copilot Studio → bot → Evaluation tab |
| `no model changes detected` | Delete `data/<botId>/tracking.json` and re-run |
| `Dataverse token failed` | Run `az login` |
| `MSAL auth failed` | Re-run `python bootstrap.py` |
| `SMTP test failed` | Check credentials — Office 365 uses `smtp.office365.com:587` |
| Container exits immediately | Run `docker logs <id>` — likely a missing volume mount |

---

<div align="center">

Built with Python · MSAL · Copilot Studio Eval API · Dataverse Web API

*Tag it. Forget it. Know when things change.*

</div>
