"""
bootstrap.py — one-time setup wizard for copilot-eval-agent
Run once on host before starting Docker.
"""
import json, msal, os, sys, time, threading, smtplib, getpass, subprocess, requests
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


# ── MSAL auth ─────────────────────────────────────────────────────────────────
def authenticate(cfg: dict) -> str:
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


# ── BAPI environment discovery ────────────────────────────────────────────────
def _fetch_environments_from_bapi() -> list:
    token = subprocess.check_output(
        ["az", "account", "get-access-token",
         "--resource", "https://service.powerapps.com/",
         "--query", "accessToken", "-o", "tsv"],
        stderr=subprocess.DEVNULL,
    ).decode().strip()
    resp = requests.get(
        "https://api.bap.microsoft.com/providers/Microsoft.BusinessAppPlatform/environments",
        params={"api-version": "2020-10-01"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    resp.raise_for_status()
    envs = []
    for item in resp.json().get("value", []):
        env_id  = item.get("name", "")
        props   = item.get("properties", {})
        display = props.get("displayName", env_id)
        url     = props.get("linkedEnvironmentMetadata", {}).get("instanceUrl", "")
        if url:
            envs.append({"name": display, "orgUrl": url.rstrip("/"), "environmentId": env_id})
    return envs


def _get_tenant_id_from_az() -> str:
    return subprocess.check_output(
        ["az", "account", "show", "--query", "tenantId", "-o", "tsv"],
        stderr=subprocess.DEVNULL,
    ).decode().strip()


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
        envs.append({"name": name, "orgUrl": org.rstrip("/"), "environmentId": env_id})
        step_ok(f"Added: {BD}{name}{RS}  {DM}{org}{RS}")
        print()
        more = ask("  Add another? [y/N]", "N")
        if more.lower() != "y":
            break
        print()
    return envs


def step_environments() -> list:
    print()
    try:
        raw = with_spinner("Fetching environments from tenant…", _fetch_environments_from_bapi)
    except Exception as e:
        step_fail(f"BAPI lookup failed: {e}")
        hint("Make sure you are signed in with:  az login")
        hint("Falling back to manual entry.\n")
        return _step_environments_manual()

    if not raw:
        step_fail("No environments with a Dataverse org URL found in tenant.")
        return _step_environments_manual()

    print()
    border = "═" * 52
    print(f"  {CY}{BD}╔═══ 🌐 Available Environments {border[:24]}╗{RS}")
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
    return chosen


def step_credentials() -> dict:
    hint("App registration with CopilotStudio.MakerOperations delegated permissions.\n")
    client_id = ask("App (client) ID")

    tenant_id = ""
    try:
        tenant_id = with_spinner("Reading tenant ID from az account…", _get_tenant_id_from_az)
    except Exception:
        pass

    if not tenant_id:
        tenant_id = ask("Tenant ID")
    else:
        print(f"  {GR}✓{RS}  Tenant  {DM}{tenant_id}{RS}  {DM}(from az account){RS}")

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
        print(f"  {GR}{BD}  │{RS}  {CY}●{RS}  {BD}{env['name']}{RS}  {DM}{env['orgUrl']}{RS}")
    print(f"  {GR}{BD}  │{RS}  {DM}Poll every        {RS}{cfg.get('poll_interval_minutes', 10)} min")
    print(f"  {GR}{BD}  │{RS}  {DM}LLM model         {RS}{llm.get('model', '—')}")
    print(f"  {GR}{BD}  │{RS}  {DM}Reports to        {RS}{recipient}")
    print(f"  {GR}{BD}  └─────────────────────────────────────────────────┘{RS}\n")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print_logo()
    slow(f"  {DM}Welcome. Five steps and you're done.{RS}", delay=0.018)
    time.sleep(0.3)

    cfg = {}

    # Step 1 — Environments
    section_header(1, "🌐", "Power Platform Environments")
    cfg["environments"] = step_environments()
    section_ok(1, "Environments")

    # Step 2 — Credentials
    section_header(2, "🔑", "Eval App Credentials")
    cfg.update(step_credentials())
    section_ok(2, "Credentials")

    # Step 3 — Agent settings
    section_header(3, "⚙️ ", "Agent Settings")
    cfg.update(step_agent_settings())
    section_ok(3, "Agent Settings")

    # Step 4 — Microsoft sign-in
    section_header(4, "🔐", "Microsoft Sign-In")
    if cfg.get("eval_app_client_id") and cfg.get("eval_app_tenant_id"):
        try:
            authenticate(cfg)
            print(f"\n  {GR}{BD}✓  Signed in!{RS}  Token cached → msal_token_cache.json")
        except Exception as e:
            step_fail(f"Auth failed: {e}")
            hint("Re-run bootstrap.py to retry sign-in.")
    else:
        hint("Skipping — credentials not provided.")
    section_ok(4, "Sign-In")

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
    print(f"  {DM}Next →  docker build -t copilot-eval-agent .{RS}")
    print(f"  {DM}        docker run -d \\{RS}")
    print(f"  {DM}          -v $(pwd)/data:/app/data \\{RS}")
    print(f"  {DM}          -v $(pwd)/msal_token_cache.json:/app/msal_token_cache.json \\{RS}")
    print(f"  {DM}          -v $(pwd)/config.json:/app/config.json \\{RS}")
    print(f"  {DM}          copilot-eval-agent{RS}")
    print(f"  {DM}{'─' * 56}{RS}")
    print()
    print(f"  {CY}{BD}📁 Project layout{RS}")
    print(f"  {DM}{'─' * 40}{RS}")
    tree = [
        (".",             "project root"),
        ("├── agent/",    "polling agent package"),
        ("│   ├── main.py",    "entry point — poll loop"),
        ("│   ├── auth.py",    "MSAL + self-healing device flow"),
        ("│   ├── dataverse.py","bot discovery (#monitor gate)"),
        ("│   ├── eval_client.py","Copilot Studio Eval API"),
        ("│   ├── reasoning.py","LLM drift analysis"),
        ("│   ├── store.py",   "run history (local JSON)"),
        ("│   ├── notifier.py","SMTP email"),
        ("│   └── report.py",  "HTML report generator"),
        ("├── dashboard/", "Streamlit read-only UI"),
        ("│   └── app.py",     "fleet heatmap, radar, trends"),
        ("├── .streamlit/", "dark theme config"),
        ("├── bootstrap.py","← you are here (setup wizard)"),
        ("├── config.json", "generated by this wizard"),
        ("├── Dockerfile",  "production container"),
        ("├── requirements.txt","Python deps"),
        ("└── README.md",  "full docs"),
    ]
    for path, desc in tree:
        print(f"  {DM}{path:<32}{RS}  {DM}{desc}{RS}")
    print()


if __name__ == "__main__":
    main()
