```
              ███████╗ ███████╗██╗  ██╗ ██████╗ ██╗  ██╗ █████╗
              ██╔═══██╗██╔════╝██║  ██║██╔═══██╗██║ ██╔╝██╔══██╗
              ███████╔╝███████╗███████║██║   ██║█████╔╝ ███████║
              ██╔══██║ ╚════██║██╔══██║██║   ██║██╔═██╗ ██╔══██║
              ██║  ██║ ███████║██║  ██║╚██████╔╝██║  ██╗██║  ██║
              ╚═╝  ╚═╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝

              ⚡  āshokā  ·  autonomous eval agent  ·  v1.0
```

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)
![Platform](https://img.shields.io/badge/Power_Platform-Copilot_Studio-742774?style=flat-square&logo=microsoft&logoColor=white)
![Auth](https://img.shields.io/badge/Auth-MSAL_delegated-0078D4?style=flat-square&logo=microsoftazure&logoColor=white)
![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)

<br/>

### *Know the moment your AI changes — before your users do.*

<br/>

> **An autonomous evaluation agent and control plane for Microsoft Copilot Studio.**
> Watches your bots continuously. Detects model swaps, publish events, or any trigger you configure.
> Fires evaluations automatically. Uses an LLM to explain what changed and why.
> Fully headless — one browser setup, then hands-off forever.

</div>

---

## ⚡ The Problem

Microsoft updates the large language models powering your Copilot Studio bots **silently and without notice**. A model swap changes your bot's accuracy, tone, and topic coverage overnight. You have no visibility into when it happened, how much changed, or which test cases flipped.

You find out from a support ticket. Not a dashboard.

---

## 🎯 What āshokā does

**āshokā** is an autonomous agent that sits between your Copilot Studio bots and your team. It watches every bot you care about around the clock. The moment a trigger fires — a model version change, a manual force, or any event you wire in — āshokā:

1. **Fires the Copilot Studio Eval API** — discovers all test sets, triggers every one in parallel
2. **Scores every test case** — pass/fail, numeric scores, per-case AI reason text
3. **Compares against the previous run** — classifies each metric as REGRESSED, IMPROVED, or STABLE
4. **Consults an LLM** — uses web search + your bot's own system prompt to produce a plain-English analysis of what changed and why, distinguishing model effects from persistent agent weaknesses
5. **Reports** — persists everything locally, generates a self-contained HTML report, and emails it to you

All of this happens before your users notice anything.

---

## 🧭 Philosophy

> **āshokā observes. Humans decide.**

āshokā is a pure observer. It has no ability to roll back a model, modify a bot, or take corrective action. Its job is to surface the truth of what changed, with enough signal for a human to decide.

This is deliberate. Automated rollbacks of AI systems carry their own risks. āshokā gives your team the signal — the decision is always yours.

- No automated rollbacks or model changes
- No writes to Dataverse or Copilot Studio
- Pure, unobtrusive observation and structured reasoning

---

## 🔄 How it works

āshokā runs two independent threads inside one process. Detection never waits for evaluation to finish.

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │  THREAD 1 · WATCHER  (every N minutes)                               │
  │                                                                      │
  │   Poll Dataverse ──► model version changed?                          │
  │                              │                                       │
  │               ┌──── No ──────┴───── Yes ────┐                       │
  │               ▼                             ▼                        │
  │         log STABLE                 log MODEL_CHANGE                  │
  │           · sleep                  write trigger file  ───────────┐  │
  └─────────────────────────────────────────────────────────────────┬─┘  │
                                                                    │    │
                                              trigger file on disk ─┘    │
                                                                         │
  ┌──────────────────────────────────────────────────────────────────────┤
  │  THREAD 2 · EVALUATOR  (checks every 30 s)                           │
  │                                                                      │
  │   any trigger files? ──► pick up all pending bots                    │
  │          │                                                           │
  │          ▼                                                           │
  │   fire Eval API for all pending bots simultaneously                  │
  │          │                                                           │
  │          ▼                                                           │
  │   poll for completion  (round-robin, respects per-bot lock files)    │
  │          │                                                           │
  │          ▼                                                           │
  │   compare metrics vs last run  →  REGRESSED / IMPROVED / STABLE      │
  │          │                                                           │
  │          ▼                                                           │
  │   web search for model context  +  LLM reasoning analysis            │
  │          │                                                           │
  │          ├──► run.json saved   (raw eval + LLM analysis)             │
  │          ├──► HTML report saved                                      │
  │          └──► email to admin                                         │
  └──────────────────────────────────────────────────────────────────────┘

  A model change on bot 4 is detected within N minutes even while
  bots 1, 2, 3 are mid-eval — the watcher never waits.
```

---

## 🧠 LLM Reasoning — āshokā as a guide

āshokā doesn't just score test cases. It consults an LLM to explain the delta in plain language — acting as an intelligent guide, not just a metrics dashboard.

Before calling the LLM, āshokā:
- **Searches the web** (via Tavily, if configured) for release notes and known capability differences between the old and new model
- **Injects the bot's own system prompt** so the LLM understands the bot's purpose and instructions
- **Sends the full per-case comparison** — old model reason vs new model reason for every test case

The LLM is asked to distinguish:
- **Model effects** — cases where the old model passed and the new model failed (or vice versa) → these point to model capability changes
- **Persistent weaknesses** — cases where both models fail → these are agent/prompt issues, not model issues

The output is a two-part narrative written for a mixed architect and business audience:

1. **Analysis** — what changed, why it changed, grounded exclusively in the case evidence. No assumptions about model capabilities are made; every claim must trace to a specific score or evaluator reason in the data.
2. **Best-practice layer** *(only when metrics regressed or improved)* — a second LLM call produces architect-level recommendations: system prompt changes, grounding strategy, test coverage gaps, rollback criteria, and stakeholder communication — all tied to the failure pattern identified in part one.

The LLM analysis is generated automatically on every eval run and stored in `run.json`. It is also available on demand from the **ask āshokā** panel on the bot detail page.

You can use any OpenAI-compatible endpoint: OpenAI, Azure OpenAI, Azure AI Foundry, or a local model.

---

## ⚙️ āshokā as a general evaluation platform

āshokā is built around a simple concept: **any event can trigger a structured evaluation**. The model-swap detector is the default event source, but the architecture is designed to be extended.

```
  EVENT SOURCE                TRIGGER                   āshokā
  ─────────────               ───────                   ───────
  Model swap detected    →    trigger file    →    run eval, analyse, report
  Force eval (dashboard) →    trigger file    →    run eval, analyse, report
  External webhook       →    trigger file    →    run eval, analyse, report  ← extend here
  Publish event          →    trigger file    →    run eval, analyse, report  ← extend here
  Scheduled cron         →    trigger file    →    run eval, analyse, report  ← extend here
```

To wire a new event source, write a `force_eval_{botId}.trigger` file to the `data/agent/` directory. The evaluator picks it up within 30 seconds. No code changes needed inside the core agent.

**Examples of what you can build on top of āshokā:**
- Run evals automatically on every Copilot Studio **publish** event (via Power Automate webhook → trigger file)
- Run evals on a **weekly schedule** (cron → trigger file per bot)
- Run evals when a **support ticket volume spikes** (alert webhook → trigger file)
- Run evals as a **pre-deploy check** in a CI/CD pipeline

---

## 🏗️ Architecture

```
  ┌──────────────────────────────────────────────────────────────┐
  │  CONTROL PLANE  ─  Streamlit dashboard  (port 8501)          │
  │                                                              │
  │   ⚡ āshokā    fleet view · bot detail · run comparison     │
  │   ⚙ Setup      browser-based config — no terminal needed    │
  │   ⊞ Control    browse · delete runs, events, reports        │
  │   ≡ Logs        live log viewer · level filter · auto-refresh│
  │                                                              │
  │   ▶ Start Agent / ■ Stop Agent                              │
  └───────────────────────┬──────────────────────────────────────┘
                          │  shared  data/  volume
                          ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  AGENT  ─  python -m agent.main                              │
  │                                                              │
  │  ┌─ Watcher thread ──────────────────────────────────────┐  │
  │  │  dataverse.py   poll bot model versions               │──┼──► Dataverse
  │  │  → writes force_eval_{botId}.trigger on change        │  │
  │  └───────────────────────────────────────────────────────┘  │
  │                                                              │
  │  ┌─ Evaluator thread ────────────────────────────────────┐  │
  │  │  eval_client.py  trigger + poll Eval API              │──┼──► Copilot Studio Eval API
  │  │  reasoning.py    classify + LLM analysis              │──┼──► LLM endpoint + Tavily
  │  │  store.py        write run.json                       │  │
  │  │  report.py       generate HTML report                 │  │
  │  │  notifier.py     email report via SMTP                │──┼──► email
  │  └───────────────────────────────────────────────────────┘  │
  │                                                              │
  │  auth.py      unified MSAL — one cache, three APIs          │──► Microsoft Identity
  │  events.py    append-only JSONL event log                   │
  │  logger.py    rotating JSON file logger                     │
  └──────────────────────────────────────────────────────────────┘

  data/agent/
      agent.log            rotating operational log (5 MB × 3)
      events.jsonl         every agent action timestamped
      auth_state.json      auth status for dashboard display
      msal_token_cache.json
      force_eval_{botId}.trigger   ← any event source writes here

  data/{botId}/
      runs/tracking.json              current model version
      transactions/{ts}_{model}/
          run.json                    raw eval results + LLM analysis
```

---

## ✨ Features at a glance

| | Feature | Detail |
|---|---|---|
| 🌐 | **Multi-environment** | Scans all Power Platform environments |
| 📋 | **Opt-in per bot** | Choose which bots to monitor — empty = watch all |
| 🤖 | **Zero-touch eval** | Discovers all test sets, triggers Eval API, polls to completion automatically |
| 🧠 | **LLM analysis** | Two-call approach: analysis grounded only in case data (no model assumptions), followed by architect best-practice recommendations when metrics change |
| 📡 | **Event-driven** | File-based trigger system — any external event source can queue an eval in 30 seconds |
| 📊 | **Any-run comparison** | Compare any two historical runs — not just the latest pair |
| 🔐 | **Unified MSAL auth** | Single device-flow sign-in covers Eval API, Power Platform Inventory, and all Dataverse org URLs |
| 📋 | **Event log** | Append-only `events.jsonl` — every agent action timestamped with tag |
| ⚡ | **Force eval** | Trigger an immediate eval from the dashboard — globally or per-bot |
| 🔍 | **Trigger source** | Every eval tagged USER (dashboard button) or AGENT (model change detected) |
| 🧵 | **Non-blocking detection** | Watcher and evaluator are separate threads — new model changes are caught within N minutes even during a long eval cycle |
| 🩺 | **Memory monitoring** | Tracks agent RSS, warns at 50% growth above baseline |
| ⚙️ | **Browser setup** | Full configuration in the dashboard — no terminal, no YAML editing, no `.env` files |
| 📧 | **HTML reports** | Self-contained, email-ready, archived locally |
| ⊞ | **Storage management** | Browse, inspect, and delete runs, events, reports from the dashboard |
| 🐳 | **Docker Compose** | `docker compose up` starts agent + dashboard with a shared volume |
| ☁️ | **Azure Container Apps** | One-command deploy script — ACR, Azure Files, two container apps |
| 💾 | **No cloud storage** | All state is local JSON — no Dataverse writes, no blob storage |

---

## 🚀 Step-by-step setup

### Step 1 — Prerequisites

| | What | Notes |
|---|---|---|
| 🐍 | Python 3.11+ | [python.org](https://python.org) |
| 🔑 | Entra ID access | To create an app registration |
| 🤖 | Copilot Studio Maker | To create test sets on your bots |
| 🤖 | LLM endpoint | Any OpenAI-compatible API — OpenAI, Azure OpenAI, Azure AI Foundry |
| 🐳 | Docker Desktop | Optional — for containerised deployment |

---

### Step 2 — Create an Entra ID app registration

The agent uses **delegated auth** — it calls APIs as you, not as a service principal. Microsoft requires this for the Copilot Studio Eval API.

1. [portal.azure.com](https://portal.azure.com) → **Microsoft Entra ID** → **App registrations** → **New registration**
2. Name: `copilot-eval-agent` · Account type: **Single tenant** → **Register**
3. Copy the **Application (client) ID** and **Directory (tenant) ID** — you'll enter these in Setup
4. **Authentication** → **Add a platform** → **Mobile and desktop applications**
   → tick `https://login.microsoftonline.com/common/oauth2/nativeclient` → **Configure**
5. **API permissions** → **Add a permission** → **APIs my organization uses**
   → search `Power Platform API` (GUID `8578e004-a5c6-46e7-913e-12f58912df43`)
6. **Delegated permissions** → tick all three:

| Permission | Purpose |
|---|---|
| `CopilotStudio.MakerOperations.Read` | List test sets, retrieve eval results |
| `CopilotStudio.MakerOperations.ReadWrite` | Trigger a new evaluation run |
| `EnvironmentManagement.Environments.Read` | Auto-discover Power Platform environments |

7. **Add a permission** → **APIs my organization uses** → search `Dynamics CRM`
   (GUID `00000007-0000-0000-c000-000000000000`)
8. **Delegated permissions** → tick `user_impersonation` → **Add permissions**
9. **Grant admin consent for [tenant]** → confirm

| Permission | Purpose |
|---|---|
| `Dynamics CRM — user_impersonation` | Read bot model version from Dataverse — required for model-swap detection |

> **Note:** Without `user_impersonation`, model version shows as `unknown` and change detection is skipped. Without `ReadWrite`, āshokā can read test sets but cannot trigger eval runs. Without `EnvironmentManagement.Environments.Read`, use manual environment entry in Setup.

---

### Step 3 — Create test sets in Copilot Studio

Without test sets, āshokā has nothing to evaluate and will skip the bot.

```
Copilot Studio → your bot → Evaluation tab → New test set
```

Add 10–20 utterances covering your bot's main topics — especially edge cases and known weak spots. āshokā discovers and runs **all** test sets automatically on every trigger.

---

### Step 4 — Install

```bash
git clone https://github.com/kaul-vineet/LLMDriftTracker.git
cd LLMDriftTracker
pip install -r requirements.txt
```

No `.env` file needed. All configuration — including API keys and passwords — lives in `config.json`, written by the Setup page.

---

### Step 5 — Launch the dashboard

```bash
streamlit run dashboard/app.py
```

Open `http://localhost:8501` → **Setup** in the sidebar.

Each section shows a ✓ or ✗. Fill them top to bottom:

| Section | What to do |
|---|---|
| **1 · App Registration** | Paste Client ID + Tenant ID from Step 2 |
| **2 · Authentication** | Click **Sign In** — complete the device flow in your browser once. Token is cached. |
| **3 · Environments** | Click **Load Environments** to auto-discover, or add manually |
| **4 · Agents** | Click **Load Bots** per environment, select which to monitor (empty = all) |
| **5 · LLM** | Paste Base URL + model name + API key. Click **Test LLM** to validate live. |
| **6 · Web Search** | Optional — paste a Tavily API key to enable pre-analysis model context search |
| **7 · Notifications** | Optional — SMTP host, port, user, password, recipient for email reports |

Click **Save config.json** when all sections show ✓. Everything is saved to `config.json` — including keys.

---

### Step 6 — Start the agent

Click **▶ Start Agent** in the sidebar (only enabled when the config is complete and the Setup check passes). The agent runs as a background process. The dashboard stays open as your **control plane**.

```
● SYSTEM ONLINE · ALL STABLE
```

Click **■ Stop Agent** to stop it gracefully.

---

### Step 7 — Run your first evaluation

Don't wait for a model swap. On the **āshokā** page, open any bot and click **▶ Force Eval**. This queues an immediate evaluation — you'll see results within a few minutes depending on your test set size.

---

## 🐳 Docker Compose

```bash
# Copy the example config and fill in your values — or run Setup after launch
cp config.example.json config.json

docker compose -f docker/docker-compose.yml up --build -d

# Follow agent logs
docker compose -f docker/docker-compose.yml logs -f ashoka-agent

# Open dashboard
open http://localhost:8501        # macOS
start http://localhost:8501       # Windows
```

Two containers, one image, shared `./data` volume:

| Container | Command | Port |
|---|---|---|
| `ashoka-agent` | `python -m agent.main` | — |
| `ashoka-dashboard` | `streamlit run dashboard/app.py` | 8501 |

`config.json` is bind-mounted read-write so the Setup page can save changes that the agent picks up on its next poll cycle. The MSAL token cache lives at `./data/agent/msal_token_cache.json` on the shared volume — both containers use the same authenticated session.

---

## ☁️ Azure Container Apps — production deployment

`docker/azure-deploy.sh` provisions everything end-to-end with one command:

```bash
# Edit the variables at the top of the script, then:
bash docker/azure-deploy.sh
```

**What the script creates:**

| Resource | Name | Purpose |
|---|---|---|
| Resource Group | `ashoka-rg` | Container for all resources |
| Container Registry | `ashokaacr` | Stores the built image |
| Container Apps Environment | `ashoka-env` | Shared runtime for both apps |
| Storage Account | `ashokastore` | Backs the Azure Files shares |
| Azure Files — `ashoka-data` | mounted at `/app/data` | Eval run data, logs, MSAL cache |
| Azure Files — `ashoka-config` | mounted at `/app/config` | `config.json` — Setup page writes here |
| Container App — `ashoka-agent` | no ingress | Autonomous background process |
| Container App — `ashoka-dashboard` | external HTTPS · port 8501 | Web control plane |

`config.json` is uploaded to the config share before containers start. The Setup page writes changes back to the same share — the agent picks them up on its next poll without a restart. Set `CONFIG_PATH=/app/config/config.json` to tell both containers where to read it (the deploy script does this automatically).

**After deploy:**

```bash
# Tail logs
az containerapp logs show -n ashoka-agent     -g ashoka-rg --follow
az containerapp logs show -n ashoka-dashboard -g ashoka-rg --follow

# Update image after a code change
docker build -f docker/Dockerfile -t ashokaacr.azurecr.io/ashoka:latest .
docker push ashokaacr.azurecr.io/ashoka:latest
az containerapp update -n ashoka-agent     -g ashoka-rg --image ashokaacr.azurecr.io/ashoka:latest
az containerapp update -n ashoka-dashboard -g ashoka-rg --image ashokaacr.azurecr.io/ashoka:latest

# Tear down everything
az group delete --name ashoka-rg --yes --no-wait
```

---

## 📊 Dashboard pages

### ⚡ āshokā — Fleet · Detail · Timeline

The main view. Your eval control panel.

```
● SYSTEM ONLINE · ALL STABLE

       Ā S H O K Ā
  copilot-eval-agent · N agents monitored

[ MONITORED ]  [ EVAL RUNS ]  [ IMPROVED ]  [ REGRESSIONS ]

── ĀSHOKĀ ──────────────────────────────────────────────────────────
  I am āshokā — born April 1, 2026.
  Model swaps. I score. You decide.

── MONITORED AGENTS ───────────────────────────────────────────────
  🟢 Safe Travels  gpt-4o   Apr 18 · 4 runs   →
  🔴 HR Bot        gpt-4o   Apr 17 · 2 runs   →

── MISSION TIMELINE ───────────────────────────────────────────────
  Apr 22  🟢 AGENT START   Watching 1 agent(s) across 1 environment(s)
  Apr 22  ⏳ EVAL QUEUED   Safe Travels  Eval queued from dashboard
  Apr 22  🚀 EVAL START    Safe Travels  · gpt-4o  Eval triggered — fetching test sets
  Apr 22  ✅ STABLE        Safe Travels  · gpt-4o  pass 80% · avg score 60.0
  Apr 18  🤖 AGENT EVAL    Safe Travels  gpt-4o → gpt-4o-mini (auto-detected)
  Apr 18  🔄 MODEL SHIFT   Safe Travels  gpt-4o → gpt-4o-mini
  Apr 18  🚀 EVAL START    Safe Travels  · gpt-4o-mini  Eval triggered — fetching test sets
  Apr 18  ✅ REGRESSED     Safe Travels  · gpt-4o-mini  pass 70% · avg score 47.5
```

Click any bot to open the **detail view**:

- **Current strip** — timestamp · model version · trigger source (USER / AGENT)
- **METRIC TRENDS** — metric trajectory across all runs with model name on X-axis
- **Baseline selector** — pick any previous run as the comparison baseline
- **Radar chart** — current vs baseline overlaid on a polar chart
- **Metric table** — Pass/Fail highlighted, Δ column colour-coded
- **ask āshokā** — two-part LLM narrative: evidence-only analysis + architect best-practice layer; auto-generated on every eval and cached in `run.json`; regenerate on demand
- **Per-metric breakdown** — delta bar, status grid, per-case cards grouped by Pass→Fail / Fail→Pass / Fail→Fail / Pass→Pass
- **▶ Force Eval** — queue an immediate eval for this bot

### ⚙️ Setup — Control plane configuration

Full configuration without touching the terminal. Writes `config.json`. The sidebar shows ● READY when all prerequisites are met, with a checklist of what's missing. Start Agent is gated on ● READY.

### ⊞ Control — Storage management

Browse and clean up stored data. Two-click confirmation on all deletes.

- Per-run delete or bulk delete per bot
- Clear the event log
- Delete individual or all HTML reports
- Storage size summary

### ≡ Logs — Live log viewer

Real-time view into `data/agent/agent.log`.

- **Level filter** — ALL / ERROR / WARNING / INFO / DEBUG
- **Free-text search** — filter by message or thread (`watcher` / `evaluator`)
- **Auto-refresh** — polls every 5 s when toggled on
- **Newest first** — last 500 lines, colour-coded by severity

> LLM and web API calls are logged at DEBUG level — set `log_level: "DEBUG"` in config to surface them.

---

## 📋 Event log

Every agent action is appended to `data/agent/events.jsonl` — an append-only audit trail rendered in the Mission Timeline on the home page.

| Tag | Event type | Fires when |
|---|---|---|
| 🟢 `AGENT START` | `agent_start` | Agent process boots |
| 🔴 `AGENT STOP` | `agent_stop` | Agent process exits (clean, Ctrl-C, or exception) |
| 🔄 `MODEL SHIFT` | `model_change` | Watcher detects a model version change in Dataverse |
| 🤖 `AGENT EVAL` | `agent_eval` | Same moment — watcher queues eval automatically |
| ⏳ `EVAL QUEUED` | `eval_queued` | User clicks Force Eval button in dashboard |
| ⚡ `USER EVAL` | `force_eval` | Global `force_eval.trigger` file consumed |
| 🚀 `EVAL START` | `eval_start` | Eval API call initiated |
| ✅ `STABLE` / `IMPROVED` / `REGRESSED` | `eval_complete` | Eval finished — verdict derived from metric comparison |
| ⏱️ `TIMEOUT` | `eval_timeout` | Eval polling timed out |
| 📭 `NO TEST SETS` | `eval_no_sets` | Bot has no test sets configured |
| 🔥 `ERROR` | `error` | Unhandled exception during eval processing |

`cycle_start` and `stable` events are written to `events.jsonl` but filtered from the timeline (too noisy).

---

## 💾 Storage layout

```
data/
├── agent/
│   ├── agent.log                      ← rotating operational log (JSON lines, 5 MB × 3 files)
│   ├── agent.log.1 / .2 / .3         ← rotated backups
│   ├── agent.pid                      ← agent process ID (deleted on stop)
│   ├── auth_state.json                ← current auth state for dashboard display
│   ├── events.jsonl                   ← append-only business event log
│   ├── llm_status.json                ← result of last LLM test (Setup → Test LLM)
│   ├── msal_token_cache.json          ← MSAL token cache (shared between agent + dashboard)
│   ├── force_eval_{botId}.trigger     ← written on model change or Force Eval — evaluator picks up within 30 s
│   └── eval_active_{botId}.lock       ← present while a bot's eval is in flight
│
└── {botId}/
    ├── runs/
    │   └── tracking.json              ← current model version + last run folder name
    └── transactions/
        └── {timestamp}_{modelVersion}/
            ├── run.json               ← raw Eval API results + triggerSource (user/agent) + cached LLM analysis
            └── report.html            ← self-contained HTML report
```

All comparisons, classifications, and LLM analyses are stored in `run.json["analyses"]` keyed by the baseline folder name. No derived files are created — everything recomputes from the raw eval results on demand.

---

## 📁 Project structure

```
āshokā/
│
├── agent/                    autonomous monitoring agent
│   ├── main.py               watcher thread · evaluator thread · force-eval trigger · PID
│   ├── auth.py               unified MSAL — one cache for Eval API, Inventory, Dataverse
│   ├── dataverse.py          fetch bots + model versions from Dataverse
│   ├── eval_client.py        Copilot Studio Eval API — trigger + poll to completion
│   ├── reasoning.py          metric extraction · classify · web search · LLM analysis
│   ├── events.py             append-only JSONL event log
│   ├── logger.py             rotating JSON file logger
│   ├── store.py              run storage — transactions/{timestamp}_{model}/run.json
│   ├── report.py             self-contained HTML report generator
│   └── notifier.py           SMTP email sender
│
├── dashboard/                Streamlit control plane
│   ├── app.py                router · sidebar · agent start/stop controls
│   ├── theme.py              colour palette + font constants
│   └── _pages/
│       ├── ashoka.py         fleet view · bot detail · run comparison · LLM analysis · timeline
│       ├── setup.py          browser-based configuration — writes config.json
│       ├── control.py        storage browser and cleanup
│       └── logs.py           live log viewer — level filter · search · auto-refresh
│
├── config.example.json       template — copy to config.json, or fill via Setup
├── config.json               all configuration including secrets (gitignored)
├── docker/
│   ├── Dockerfile            Python 3.11-slim — STORE_DIR + CONFIG_PATH env defaults
│   ├── docker-compose.yml    two-service local stack with healthchecks
│   └── azure-deploy.sh       end-to-end Azure Container Apps deployment script
├── requirements.txt
└── .streamlit/config.toml   dark theme + server settings
```

---

## 🔐 Auth model

All API calls — Copilot Studio Eval API, Power Platform environmentmanagement, Power Platform Inventory, Dataverse — share one MSAL `PublicClientApplication` and one `SerializableTokenCache` file. Device flow runs once via the Setup page; all subsequent calls acquire silently via the cached refresh token.

| Scenario | Behaviour |
|---|---|
| First run | MSAL device flow — sign in once via the Setup page; token cached to disk |
| Subsequent runs | Silent refresh via cached token — no user interaction |
| Token expires | Agent emails a new device code to the configured recipient; polls for 15 min |
| Docker / Azure | `msal_token_cache.json` lives in `$STORE_DIR/agent/` — shared volume covers both containers |

No secrets in environment variables. All credentials — LLM API key, SMTP password, Tavily key — are stored in `config.json` and written exclusively by the Setup page.

---

## 🛠️ Configuration reference

`config.json` is written by the Setup page. You can also edit it directly — see `config.example.json` for the full schema with placeholder values.

| Key | Default | Description |
|---|---|---|
| `watch_interval_seconds` | `120` | How often the watcher polls Dataverse for model changes |
| `eval_poll_timeout_seconds` | `1200` | Max wait time for eval completion |
| `eval_poll_interval_seconds` | `20` | How often to ping the Eval API while polling |
| `max_runs_per_bot` | `6` | Number of run folders to keep per bot — oldest pruned when limit exceeded |
| `log_level` | `"INFO"` | Log verbosity — `"DEBUG"` to see LLM calls, `"ERROR"` for quiet |
| `llm.base_url` | — | OpenAI-compatible endpoint base URL |
| `llm.model` | — | Model or deployment name |
| `llm.api_key` | — | API key — written by Setup |
| `llm.api_version` | — | Required for Azure OpenAI and Azure AI Foundry |
| `tavily_api_key` | — | Optional — enables pre-analysis web search for model context |
| `smtp.host` / `port` / `user` / `password` / `recipient` | — | Optional SMTP config for email reports |

**Environment variables** (override config path and storage root — useful for Docker / ACA):

| Variable | Default | Description |
|---|---|---|
| `STORE_DIR` | `data` | Root directory for all persistent data |
| `CONFIG_PATH` | `config.json` | Path to `config.json` — override when mounting to a non-default location |

---

## 🩺 Troubleshooting

| Symptom | Fix |
|---|---|
| `0 bots found` | Rerun Setup → Agents → Load Bots — or check `monitoredBots` in `config.json` |
| `no test sets found` | Create a test set in Copilot Studio → your bot → Evaluation tab |
| Nothing in dashboard after setup | Use **▶ Force Eval** on the bot detail page to queue an immediate run |
| Model version shows `unknown` | App registration is missing `Dynamics CRM — user_impersonation` delegated permission with admin consent |
| `model swap: unknown → unknown` in LLM analysis | Same root cause — MSAL cannot exchange the refresh token for a Dataverse access token |
| M365 Copilot Agent Builder agents show `default` | Correct — these agents have no selectable model; āshokā skips Dataverse lookup |
| LLM 401 / 403 error | Check `llm.api_key` in `config.json` via the Setup page — key must match the endpoint |
| `MSAL auth failed` | Re-authenticate via Setup → Authentication → Sign In |
| 403 on Load Environments | App registration needs `EnvironmentManagement.Environments.Read` with admin consent |
| SMTP failed | Office 365: host `smtp.office365.com`, port `587`, TLS — check password in Setup → Notifications |
| Container exits immediately | `docker compose logs ashoka-agent` — check for missing volume mount or invalid `config.json` |
| Timeline empty | Run a force eval from the bot detail page — it writes the first events to `data/agent/events.jsonl` |
| Logs tab empty | Start the agent — `data/agent/agent.log` is created on first run |
| LLM calls not visible in Logs | Set `log_level: "DEBUG"` in config — LLM and web API calls are at DEBUG level by default |
| Memory warning in log | Agent RSS grew >50% from baseline — check for large Dataverse or eval API payloads |
| Eval quota reached | Copilot Studio Eval API caps at ~20 evals per bot per 24 h — `error` is logged, next cycle retries |
| `ask āshokā` shows button but no analysis | Analysis is auto-persisted on every agent run — click the button to regenerate on demand if the cached text is missing |

---

<div align="center">

```
  ✦  ·  ★   ·  ✦   ·   ★  ·   ✦  ·  ★   ·  ✦
    ★   ✦  ·   ★  ✶   ·   ✦    ★   ·   ✸  ✦
  ·  ✦   ·  ✸  ·   ✦   ★   ·  ✶   ✦  ·  ★  ·
```

Python · MSAL · Copilot Studio Eval API · Power Platform Inventory API · Dataverse · Streamlit

*Configure it. Forget it. Know when things change.*

**[github.com/kaul-vineet/LLMDriftTracker](https://github.com/kaul-vineet/LLMDriftTracker)**

</div>
