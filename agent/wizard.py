"""
agent/wizard.py — one-time setup wizard for copilot-eval-agent
Invoked via:  drift setup

Step order: credentials → sign-in → environments → agent settings → SMTP
Credentials must come first so MSAL tokens are available for BAPI/Dataverse discovery.
"""
import json, msal, os, sys, time, threading, smtplib, getpass, requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

# ── ANSI ──────────────────────────────────────────────────────────────────────
if sys.platform == "win32":
    os.system("")

CY = "\033[96m";  GR = "\033[92m";  YL = "\033[93m";  RD = "\033[91m"
MG = "\033[95m";  BL = "\033[94m";  DM = "\033[2m";   BD = "\033[1m"
RS = "\033[0m"

TOTAL_STEPS = 5


# ── Logo ──────────────────────────────────────────────────────────────────────
def print_logo():
    lines = [
        "",
        f"  {CY}{BD}╔══════════════════════════════════════════════════════════╗{RS}",
        f"  {CY}{BD}║                                                          ║{RS}",
        f"  {CY}{BD}║   {MG}⚡{RS}  {CY}{BD}L L M   D R I F T   T R A C K E R  {MG}⚡{RS}{CY}{BD}          ║{RS}",
        f"  {CY}{BD}║       {RS}{DM}copilot-eval-agent  ·  v1.0  ·  Setup Wizard{RS}{CY}{BD}       ║{RS}",
        f"  {CY}{BD}║                                                          ║{RS}",
        f"  {CY}{BD}╚══════════════════════════════════════════════════════════╝{RS}",
        "",
    ]
    for line in lines:
        print(line)
        time.sleep(0.06)


# ── Progress ──────────────────────────────────────────────────────────────────
def _progress_bar(step: int) -> str:
    filled = int((step / TOTAL_STEPS) * 24)
    bar    = f"{GR}{'█' * filled}{RS}{DM}{'░' * (24 - filled)}{RS}"
    pct    = int(step / TOTAL_STEPS * 100)
    return f"  {DM}[{RS}{bar}{DM}]{RS}  {CY}{BD}{pct}%{RS}  {DM}step {step}/{TOTAL_STEPS}{RS}"

def section_header(step: int, icon: str, title: str):
    print(f"\n{_progress_bar(step - 1)}")
    print(f"\n  {YL}{BD}╔═══ {icon}  Step {step} · {title} {RS}")
    print(f"  {YL}{BD}╚{'═' * 52}{RS}\n")

def section_ok(step: int, title: str):
    print(f"\n  {GR}{BD}╔═══ ✓  Step {step} · {title} — done{RS}")
    print(f"  {GR}{BD}╚{'═' * 52}{RS}")


# ── Text helpers ──────────────────────────────────────────────────────────────
def slow(text: str, delay: float = 0.020):
    for ch in text:
        sys.stdout.write(ch); sys.stdout.flush(); time.sleep(delay)
    print()

def hint(text: str):
    print(f"  {DM}{text}{RS}")

def step_ok(label: str):
    print(f"  {GR}✓{RS}  {label}")

def step_fail(label: str):
    print(f"  {RD}✗{RS}  {label}")

def ask(label: str, default: str = "", secret: bool = False) -> str:
    dflt = f"  {DM}[{default}]{RS}" if default else ""
    sys.stdout.write(f"  {CY}›{RS}  {label}{dflt}  ")
    sys.stdout.flush()
    val = getpass.getpass("") if secret else input()
    return val.strip() or default

def ask_int(label: str, default: int) -> int:
    while True:
        raw = ask(label, str(default))
        try:
            return int(raw)
        except ValueError:
            print(f"  {RD}  Must be a whole number.{RS}")


# ── Spinner ───────────────────────────────────────────────────────────────────
def _spin(stop: threading.Event, label: str):
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    i = 0
    while not stop.is_set():
        sys.stdout.write(f"\r  {CY}{frames[i % len(frames)]}{RS}  {label}  ")
        sys.stdout.flush(); time.sleep(0.08); i += 1
    sys.stdout.write(f"\r{' ' * 60}\r"); sys.stdout.flush()

def with_spinner(label: str, fn, *a, **kw):
    stop = threading.Event()
    t = threading.Thread(target=_spin, args=(stop, label), daemon=True)
    t.start()
    try:
        result = fn(*a, **kw); stop.set(); t.join(); step_ok(label); return result
    except Exception as e:
        stop.set(); t.join(); step_fail(label); raise


# ── Ping-pong + countdown ─────────────────────────────────────────────────────
def _ping_pong_countdown(stop: threading.Event, code: str, expires_in: int):
    width, pos, direction = 28, 0, 1
    start = time.time()
    while not stop.is_set():
        elapsed   = int(time.time() - start)
        remaining = max(0, expires_in - elapsed)
        mins, secs = divmod(remaining, 60)
        timer = f"{YL}{BD}{mins:02d}:{secs:02d}{RS}"
        ball  = f"{CY}{BD}●{RS}"
        trail = f"{DM}·{RS}"
        bar   = trail * pos + ball + trail * (width - pos)
        sys.stdout.write(f"\r  {MG}{BD}[{code}]{RS}  {bar}  {timer} remaining  ")
        sys.stdout.flush()
        pos += direction
        if pos >= width or pos <= 0:
            direction *= -1
        time.sleep(0.05)
    sys.stdout.write(f"\r{' ' * 72}\r"); sys.stdout.flush()


# ── Celebration ───────────────────────────────────────────────────────────────
def celebrate():
    palette = [CY, GR, YL, MG, BL, RD]
    art = [
        "  ✦  ·  ★   ·  ✦   ·   ★  ·   ✦  ·  ★   ·  ✦  ",
        "    ★   ✦  ·   ★  ✶   ·   ✦    ★   ·   ✸  ✦   ",
        "  ·  ✦   ·  ✸  ·   ✦   ★   ·  ✶   ✦  ·  ★   ·  ",
        "   ★   ·  ✦   ★  ·   ✦  ·   ★  ·   ✦    ✸   ★  ",
        "  ✦  ·  ✸  ·   ★   ·  ✦  ·   ★   ✦   ·  ★   ✦  ",
    ]
    for i, line in enumerate(art):
        print(f"  {palette[i % len(palette)]}{BD}{line}{RS}")
        time.sleep(0.09)


# ── MSAL auth (wizard-local device flow) ──────────────────────────────────────
def authenticate(cfg: dict) -> str:
    """Run device flow and cache token. Returns access token."""
    SCOPES     = ["https://api.powerplatform.com/.default"]
    cache_file = cfg.get("token_cache_file", "msal_token_cache.json")
    cache = msal.SerializableTokenCache()
    if os.path.exists(cache_file):
        cache.deserialize(open(cache_file).read())

    app = msal.PublicClientApplication(
        client_id=cfg["eval_app_client_id"],
        authority=f"https://login.microsoftonline.com/{cfg['eval_app_tenant_id']}",
        token_cache=cache
    )

    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            if cache.has_state_changed:
                open(cache_file, "w").write(cache.serialize())
            step_ok("Cached token found — no sign-in needed")
            return result["access_token"]

    flow       = app.initiate_device_flow(scopes=SCOPES)
    code       = flow.get("user_code", "??????")
    expires_in = flow.get("expires_in", 900)

    print(f"\n  {YL}{BD}┌──────────────────────────────────────────────────────┐{RS}")
    print(f"  {YL}{BD}│                                                      │{RS}")
    print(f"  {YL}{BD}│   1.  Open  {CY}https://microsoft.com/devicelogin{YL}       │{RS}")
    print(f"  {YL}{BD}│   2.  Enter code  {MG}{BD}{code}{YL}{BD}                             │{RS}")
    print(f"  {YL}{BD}│                                                      │{RS}")
    print(f"  {YL}{BD}└──────────────────────────────────────────────────────┘{RS}\n")

    stop = threading.Event()
    anim = threading.Thread(
        target=_ping_pong_countdown, args=(stop, code, expires_in), daemon=True
    )
    anim.start()
    result = app.acquire_token_by_device_flow(flow)
    stop.set(); anim.join()

    if "access_token" not in result:
        raise RuntimeError(result.get("error_description", "Unknown error"))

    if cache.has_state_changed:
        open(cache_file, "w").write(cache.serialize())

    return result["access_token"]


# ── SMTP test ─────────────────────────────────────────────────────────────────
def _send_test_email(host: str, port: int, user: str, password: str, recipient: str):
    msg           = MIMEMultipart("alternative")
    msg["Subject"] = "✅ LLM Drift Tracker — You're all set!"
    msg["From"]    = user
    msg["To"]      = recipient
    ts             = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = f"""<html><body style="font-family:sans-serif;background:#0d1117;color:#c9d1d9;padding:32px">
  <div style="max-width:520px;margin:auto;border:1px solid #30363d;border-radius:8px;padding:28px">
    <h2 style="color:#58a6ff;margin-top:0">⚡ LLM Drift Tracker</h2>
    <p style="color:#8b949e;font-size:13px;margin-top:-12px">copilot-eval-agent · v1.0</p>
    <hr style="border-color:#30363d">
    <p>Setup is complete. The agent will start monitoring your Copilot Studio bots and
    email drift analysis reports here whenever a model version change is detected.</p>
    <p style="color:#8b949e;font-size:12px;margin-top:24px">Configured {ts}</p>
  </div>
</body></html>"""
    msg.attach(MIMEText(body, "html"))
    with smtplib.SMTP(host, port) as s:
        s.ehlo(); s.starttls(); s.login(user, password); s.send_message(msg)


# ── Tenant / environment discovery via BAPI ───────────────────────────────────
def _fetch_environments_from_bapi(cfg: dict) -> list:
    """Fetch all environments using MSAL-acquired BAPI token."""
    from .auth import get_bapi_token
    token = get_bapi_token(cfg)
    resp = requests.get(
        "https://api.bap.microsoft.com/providers/Microsoft.BusinessAppPlatform/environments",
        params={"api-version": "2020-10-01"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    resp.raise_for_status()

    # Show raw response for connectivity diagnostics
    raw = resp.json()
    total = len(raw.get("value", []))
    hint(f"  BAPI returned {total} environment(s).")

    envs = []
    for item in raw.get("value", []):
        env_id  = item.get("name", "")
        props   = item.get("properties", {})
        display = props.get("displayName", env_id)
        url     = props.get("linkedEnvironmentMetadata", {}).get("instanceUrl", "")
        if url:
            envs.append({"name": display, "orgUrl": url.rstrip("/"), "environmentId": env_id})
    return envs


# ── Bot discovery per environment ─────────────────────────────────────────────
def _fetch_bots_for_env(org_url: str, cfg: dict) -> list:
    """Fetch active bots for one environment using MSAL-acquired Dataverse token."""
    from .auth import get_dataverse_token
    if not org_url.startswith("http"):
        org_url = "https://" + org_url
    token = get_dataverse_token(org_url, cfg)
    resp = requests.get(
        f"{org_url}/api/data/v9.2/bots",
        params={"$select": "botid,name,schemaname,statecode", "$filter": "statecode eq 0"},
        headers={"Authorization": f"Bearer {token}", "OData-MaxVersion": "4.0",
                 "Accept": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()

    # Show raw response count for diagnostics
    bots = resp.json().get("value", [])
    hint(f"  Dataverse returned {len(bots)} active bot(s).")
    return bots


def _pick_bots(env: dict, cfg: dict):
    """Populate env['monitoredBots'] with selected schemanames. Empty list = all."""
    print(f"\n  {CY}{BD}── 🤖 Bots in  {BD}{env['name']}{RS}  {'─' * 20}{RS}")
    try:
        bots = with_spinner(f"Fetching bots…", _fetch_bots_for_env, env["orgUrl"], cfg)
    except Exception as e:
        step_fail(f"Could not fetch bots ({e}) — will monitor all")
        env["monitoredBots"] = []
        return

    if not bots:
        hint("No active bots found — will monitor all when any appear.")
        env["monitoredBots"] = []
        return

    print()
    print(f"  {CY}{BD}╔═══ Active bots {'═' * 36}╗{RS}")
    print()
    for i, b in enumerate(bots, 1):
        print(f"    {GR}{BD}{i:>2}{RS}  {CY}●{RS}  {BD}{b['name']:<34}{RS}  {DM}{b['schemaname']}{RS}")
    print()
    print(f"  {CY}{BD}╚{'═' * 52}╝{RS}")
    print()
    hint("Enter numbers to monitor, comma-separated — or 'all'.")
    sel = ask("  Monitor bots", "all")

    if sel.strip().lower() == "all":
        env["monitoredBots"] = []
    else:
        chosen = []
        for part in sel.split(","):
            part = part.strip()
            try:
                chosen.append(bots[int(part) - 1]["schemaname"])
            except (ValueError, IndexError):
                print(f"  {YL}  Skipping invalid: {part}{RS}")
        env["monitoredBots"] = chosen if chosen else []

    if env["monitoredBots"]:
        for sn in env["monitoredBots"]:
            step_ok(sn)
    else:
        step_ok("All active bots")


# ── Step handlers ─────────────────────────────────────────────────────────────
def _step_environments_manual() -> list:
    hint("Add one or more Power Platform environments to monitor.")
    hint("Press Enter on Org URL to finish.\n")
    envs = []
    while True:
        idx    = len(envs) + 1
        print(f"  {CY}{BD}── Environment {idx} ──────────────────────────────{RS}")
        name   = ask("  Friendly name", f"Environment {idx}")
        org    = ask("  Org URL  (https://orgXXXXX.crm.dynamics.com)")
        if not org:
            if not envs:
                print(f"  {RD}  At least one environment is required.{RS}\n")
                continue
            break
        env_id = ask("  Environment ID  (e.g. orge71ae48e)")
        envs.append({"name": name, "orgUrl": org.rstrip("/"), "environmentId": env_id,
                     "monitoredBots": []})
        step_ok(f"Added: {BD}{name}{RS}  {DM}{org}{RS}")
        print()
        more = ask("  Add another? [y/N]", "N")
        if more.lower() != "y":
            break
        print()
    return envs


def step_environments(cfg: dict) -> list:
    """Discover environments via BAPI (uses MSAL token from cfg), fall back to manual."""
    print()
    try:
        raw = with_spinner("Fetching environments from tenant…", _fetch_environments_from_bapi, cfg)
    except Exception as e:
        step_fail(f"BAPI lookup failed: {e}")
        hint("Verify your App registration has Power Platform API permissions.")
        hint("Falling back to manual entry.\n")
        return _step_environments_manual()

    if not raw:
        step_fail("No environments with a Dataverse org URL found in tenant.")
        return _step_environments_manual()

    print()
    print(f"  {CY}{BD}╔═══ 🌐 Available Environments {'═' * 24}╗{RS}")
    print()
    for i, env in enumerate(raw, 1):
        org_short = env["orgUrl"].replace("https://", "")
        print(f"    {GR}{BD}{i:>2}{RS}  {CY}●{RS}  {BD}{env['name']:<28}{RS}  {DM}{org_short}{RS}")
    print()
    print(f"  {CY}{BD}╚{'═' * 52}╝{RS}")
    print()
    hint("Enter numbers to monitor, comma-separated — or 'all'.")
    sel = ask("  Select environments", "all")

    if sel.strip().lower() == "all":
        chosen = raw
    else:
        chosen = []
        for part in sel.split(","):
            part = part.strip()
            try:
                chosen.append(raw[int(part) - 1])
            except (ValueError, IndexError):
                print(f"  {YL}  Skipping invalid selection: {part}{RS}")

    if not chosen:
        print(f"  {RD}  No valid selection — using all environments.{RS}")
        chosen = raw

    print()
    for env in chosen:
        step_ok(f"{BD}{env['name']}{RS}  {DM}{env['orgUrl']}{RS}")

    # Bot picker — one sub-section per environment
    print()
    for env in chosen:
        _pick_bots(env, cfg)

    return chosen


def step_credentials() -> dict:
    hint("App registration with CopilotStudio.MakerOperations delegated permissions.\n")
    client_id = ask("App (client) ID")
    tenant_id = ask("Tenant ID  (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)")
    return {"eval_app_client_id": client_id, "eval_app_tenant_id": tenant_id,
            "token_cache_file": "msal_token_cache.json"}


def step_agent_settings() -> dict:
    poll = ask_int("Poll interval (minutes)", 10)
    print(f"\n  {DM}LLM for drift reasoning — leave blank to use Ollama defaults.{RS}\n")
    base_url = ask("LLM base URL", "http://localhost:11434/v1")
    api_key  = ask("LLM API key",  "ollama")
    model    = ask("LLM model",    "llama3")
    return {
        "store_dir": "data",
        "poll_interval_minutes": poll,
        "llm": {"base_url": base_url, "api_key": api_key, "model": model},
    }


def step_smtp() -> dict:
    hint("Drift reports are emailed as HTML. Leave host blank to skip.\n")
    print(f"  {DM}{'─' * 52}{RS}")
    print(f"  {CY}{BD}📄 config.json{RS}  — written to your project root when this wizard finishes.")
    print(f"  {DM}   Stores environments + monitored bots, credentials, poll interval,{RS}")
    print(f"  {DM}   LLM config, and SMTP. Edit by hand at any time or re-run{RS}")
    print(f"  {DM}   {RS}{CY}drift setup{RS}{DM}  to update any section.{RS}")
    print(f"  {DM}{'─' * 52}{RS}\n")
    host = ask("SMTP host", "smtp.office365.com")
    if not host:
        print(f"\n  {YL}⚠  Skipping — configure smtp in config.json later.{RS}")
        return {"host": "", "port": 587, "user": "", "password": "", "recipient": ""}

    port      = ask_int("SMTP port", 587)
    user      = ask("Sender email")
    password  = ask("Password", secret=True)
    recipient = ask("Recipient email")

    if not all([user, password, recipient]):
        print(f"\n  {YL}⚠  Incomplete — skipping SMTP.{RS}")
        return {"host": "", "port": 587, "user": "", "password": "", "recipient": ""}

    print()
    try:
        with_spinner(f"Sending test email → {recipient}",
                     _send_test_email, host, port, user, password, recipient)
    except Exception as e:
        step_fail(f"Test failed: {e}")
        hint("Continuing — fix smtp in config.json and re-run if needed.")
        return {"host": host, "port": port, "user": user, "password": password, "recipient": recipient}

    return {"host": host, "port": port, "user": user, "password": password, "recipient": recipient}


# ── Summary ───────────────────────────────────────────────────────────────────
def print_summary(cfg: dict):
    smtp      = cfg.get("smtp", {})
    recipient = smtp.get("recipient") or "not configured"
    llm       = cfg.get("llm", {})
    print(f"\n  {GR}{BD}  ┌─ Configuration ─────────────────────────────────┐{RS}")
    for env in cfg.get("environments", []):
        bots = env.get("monitoredBots", [])
        bot_label = f"{len(bots)} bot(s)" if bots else "all bots"
        print(f"  {GR}{BD}  │{RS}  {CY}●{RS}  {BD}{env['name']}{RS}  {DM}{bot_label}{RS}")
    print(f"  {GR}{BD}  │{RS}  {DM}Poll every        {RS}{cfg.get('poll_interval_minutes', 10)} min")
    print(f"  {GR}{BD}  │{RS}  {DM}LLM model         {RS}{llm.get('model', '—')}")
    print(f"  {GR}{BD}  │{RS}  {DM}Reports to        {RS}{recipient}")
    print(f"  {GR}{BD}  └─────────────────────────────────────────────────┘{RS}\n")


# ── Top-level re-run menu ─────────────────────────────────────────────────────
# Step order: 1=Credentials, 2=Sign-In, 3=Environments, 4=Agent Settings, 5=SMTP
_MENU = [
    ("🔑", "Credentials  (App ID / Tenant ID)"),
    ("🔐", "Sign-In  (Microsoft device flow)"),
    ("🌐", "Environments & monitored bots"),
    ("⚙️ ", "Agent Settings"),
    ("📧", "SMTP / Email"),
]

def _load_existing_cfg() -> dict:
    try:
        return json.loads(open("config.json").read())
    except Exception:
        return {}

def _top_menu() -> str:
    print(f"\n  {CY}{BD}╔═══ 🔄  config.json found — what would you like to update? ════╗{RS}")
    print(f"  {CY}│{RS}    {YL}{BD}0{RS}  ·  Full wizard (re-run all steps)")
    for i, (icon, label) in enumerate(_MENU, 1):
        print(f"  {CY}│{RS}    {GR}{BD}{i}{RS}  ·  {icon}  {label}")
    print(f"  {CY}│{RS}    {RD}{BD}q{RS}  ·  Quit (no changes)")
    print(f"  {CY}╚{'═' * 58}╝{RS}\n")
    return ask("  Choose", "0").strip().lower()

def _run_step(n: str, cfg: dict):
    if n == "1":
        section_header(1, "🔑", "Eval App Credentials")
        cfg.update(step_credentials())
        section_ok(1, "Credentials")
    elif n == "2":
        section_header(2, "🔐", "Microsoft Sign-In")
        if cfg.get("eval_app_client_id") and cfg.get("eval_app_tenant_id"):
            try:
                authenticate(cfg)
                print(f"\n  {GR}{BD}✓  Signed in!{RS}  Token cached → msal_token_cache.json")
            except Exception as e:
                step_fail(f"Auth failed: {e}")
                hint("Re-run  drift setup  to retry sign-in.")
        else:
            hint("Credentials not in config — run step 1 (Credentials) first.")
        section_ok(2, "Sign-In")
    elif n == "3":
        section_header(3, "🌐", "Power Platform Environments")
        if cfg.get("eval_app_client_id") and cfg.get("eval_app_tenant_id"):
            cfg["environments"] = step_environments(cfg)
        else:
            hint("Credentials not in config — run step 1 first, then sign in (step 2).")
        section_ok(3, "Environments")
    elif n == "4":
        section_header(4, "⚙️ ", "Agent Settings")
        cfg.update(step_agent_settings())
        section_ok(4, "Agent Settings")
    elif n == "5":
        section_header(5, "📧", "Email Reports")
        cfg["smtp"] = step_smtp()
        section_ok(5, "SMTP")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print_logo()
    existing = _load_existing_cfg()

    if existing:
        choice = _top_menu()
        if choice == "q":
            print(f"\n  {DM}No changes made. Goodbye.{RS}\n")
            return
        if choice in ("1", "2", "3", "4", "5"):
            cfg = existing.copy()
            _run_step(choice, cfg)
            open("config.json", "w").write(json.dumps(cfg, indent=2))
            step_ok("config.json updated")
            print()
            return
        cfg = {}
    else:
        slow(f"  {DM}Welcome. Five steps and you're done.{RS}", delay=0.018)
        time.sleep(0.3)
        cfg = {}

    # Step 1 — Credentials first: client_id + tenant_id needed for token acquisition
    section_header(1, "🔑", "Eval App Credentials")
    cfg.update(step_credentials())
    section_ok(1, "Credentials")

    # Step 2 — Microsoft sign-in (device flow, caches token)
    _run_step("2", cfg)

    # Step 3 — Environments + bot picker (uses BAPI + Dataverse tokens)
    section_header(3, "🌐", "Power Platform Environments")
    cfg["environments"] = step_environments(cfg)
    section_ok(3, "Environments")

    # Step 4 — Agent settings
    section_header(4, "⚙️ ", "Agent Settings")
    cfg.update(step_agent_settings())
    section_ok(4, "Agent Settings")

    # Step 5 — SMTP
    section_header(5, "📧", "Email Reports")
    cfg["smtp"] = step_smtp()
    section_ok(5, "Email")

    # Write config
    print()
    def _write():
        time.sleep(0.35)
        open("config.json", "w").write(json.dumps(cfg, indent=2))

    with_spinner("Writing config.json", _write)

    # Victory
    print()
    print(_progress_bar(TOTAL_STEPS))
    print()
    celebrate()
    print()
    slow(f"  {GR}{BD}  ALL SYSTEMS GO  🚀{RS}", delay=0.025)
    print_summary(cfg)
    print(f"  {DM}{'─' * 56}{RS}")
    print(f"  {DM}Locally →  drift run              # start agent{RS}")
    print(f"  {DM}           drift dashboard        # open dashboard{RS}")
    print(f"  {DM}           drift setup            # re-run this wizard{RS}")
    print()
    print(f"  {CY}{BD}📁 Project layout{RS}")
    print(f"  {DM}{'─' * 40}{RS}")
    tree = [
        (".",                      "project root"),
        ("├── agent/",             "agent package"),
        ("│   ├── main.py",        "poll loop entry point"),
        ("│   ├── wizard.py",      "this setup wizard"),
        ("│   ├── auth.py",        "MSAL + self-healing device flow"),
        ("│   ├── dataverse.py",   "bot discovery + monitoredBots filter"),
        ("│   ├── eval_client.py", "Copilot Studio Eval API"),
        ("│   ├── reasoning.py",   "LLM drift analysis"),
        ("│   ├── store.py",       "run history (local JSON)"),
        ("│   ├── notifier.py",    "SMTP email"),
        ("│   └── report.py",      "HTML report generator"),
        ("├── dashboard/",         "Streamlit read-only UI"),
        ("│   ├── app.py",         "fleet overview, radar, trends"),
        ("│   └── pages/",         ""),
        ("│       └── 1_Setup.py", "7-step Streamlit setup wizard"),
        ("├── .streamlit/",        "dark theme config"),
        ("├── drift / drift.bat",  "CLI entry points"),
        ("├── config.json",        "← generated by this wizard"),
        ("├── Dockerfile",         "production container image"),
        ("├── docker-compose.yml", "agent + dashboard services"),
        ("├── requirements.txt",   "Python deps"),
        ("└── README.md",          "full docs"),
    ]
    for path, desc in tree:
        print(f"  {DM}{path:<32}{RS}  {DM}{desc}{RS}")
    print()
    print(f"  {DM}Docker  →  docker compose up -d{RS}")
    print(f"  {DM}           docker compose logs -f drift-agent{RS}")
    print(f"  {DM}           open http://localhost:8501  # dashboard{RS}")
    print(f"  {DM}{'─' * 56}{RS}\n")


if __name__ == "__main__":
    main()
