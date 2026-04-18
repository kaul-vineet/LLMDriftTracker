"""
bootstrap.py — one-time MSAL auth setup for copilot-eval-agent
Run once on host before starting Docker.
"""
import json, msal, os, sys, time, threading

# ── ANSI ──────────────────────────────────────────────────────────────────────
if sys.platform == "win32":
    os.system("")          # enable ANSI on Windows terminal

CY  = "\033[96m"
GR  = "\033[92m"
YL  = "\033[93m"
RD  = "\033[91m"
DM  = "\033[2m"
BD  = "\033[1m"
RS  = "\033[0m"

# ── Logo ──────────────────────────────────────────────────────────────────────
LOGO = f"""
{CY}{BD}
  ╔══════════════════════════════════════════╗
  ║   🤖  copilot-eval-agent  v1.0          ║
  ║       Model Drift Tracker  ·  Setup     ║
  ╚══════════════════════════════════════════╝
{RS}"""

# ── Helpers ───────────────────────────────────────────────────────────────────
def slow(text: str, delay=0.025):
    for ch in text:
        sys.stdout.write(ch); sys.stdout.flush(); time.sleep(delay)
    print()

def step_ok(label: str):
    print(f"  {GR}✓{RS}  {label}")

def step_fail(label: str):
    print(f"  {RD}✗{RS}  {label}")

# ── Ping-pong animation ───────────────────────────────────────────────────────
def _ping_pong(stop: threading.Event, code: str):
    width, pos, direction = 34, 0, 1
    while not stop.is_set():
        bar = f"{DM}·{RS}" * pos + f"{CY}●{RS}" + f"{DM}·{RS}" * (width - pos)
        sys.stdout.write(f"\r  {YL}[{code}]{RS}  {bar}  ")
        sys.stdout.flush()
        pos += direction
        if pos >= width or pos <= 0:
            direction *= -1
        time.sleep(0.04)
    sys.stdout.write(f"\r{' ' * 60}\r"); sys.stdout.flush()

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
        result = fn(*a, **kw)
        stop.set(); t.join()
        step_ok(label)
        return result
    except Exception as e:
        stop.set(); t.join()
        step_fail(label)
        raise e

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

    # Silent refresh — no prompt needed
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            if cache.has_state_changed:
                open(cache_file, "w").write(cache.serialize())
            return result["access_token"]

    # Device code — show ping-pong while waiting
    flow = app.initiate_device_flow(scopes=SCOPES)
    code = flow.get("user_code", "??????")

    print(f"\n  {YL}┌──────────────────────────────────────────────┐{RS}")
    print(f"  {YL}│  Browser →  {BD}login.microsoft.com/device{RS}{YL}       │{RS}")
    print(f"  {YL}│  Code    →  {BD}{CY}{code}{RS}{YL}                          │{RS}")
    print(f"  {YL}└──────────────────────────────────────────────┘{RS}\n")

    stop = threading.Event()
    anim = threading.Thread(target=_ping_pong, args=(stop, code), daemon=True)
    anim.start()
    result = app.acquire_token_by_device_flow(flow)
    stop.set(); anim.join()

    if "access_token" not in result:
        raise RuntimeError(result.get("error_description", "Unknown error"))

    if cache.has_state_changed:
        open(cache_file, "w").write(cache.serialize())

    return result["access_token"]

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(LOGO)
    slow(f"  {DM}Powering up...{RS}", delay=0.02)
    time.sleep(0.2)

    # Load config
    try:
        cfg = with_spinner("Loading config.json", json.loads, open("config.json").read())
    except FileNotFoundError:
        step_fail("config.json not found — run from project root")
        sys.exit(1)
    except Exception as e:
        step_fail(str(e)); sys.exit(1)

    # Auth
    print(f"\n  {BD}Signing in to Microsoft...{RS}\n")
    try:
        authenticate(cfg)
        print(f"\n  {GR}{BD}✓  Authenticated!{RS}  Token saved → {cfg.get('token_cache_file','msal_token_cache.json')}\n")
    except Exception as e:
        step_fail(f"Auth failed: {e}"); sys.exit(1)

    # Done
    time.sleep(0.15)
    print(f"  {DM}{'─' * 47}{RS}")
    slow(f"  {GR}{BD}  All done. Ready to launch 🚀{RS}", delay=0.022)
    print(f"  {DM}{'─' * 47}{RS}\n")
    print(f"  {DM}Next →  docker build -t copilot-eval-agent .{RS}")
    print(f"  {DM}        docker run  ... copilot-eval-agent{RS}\n")

if __name__ == "__main__":
    main()
