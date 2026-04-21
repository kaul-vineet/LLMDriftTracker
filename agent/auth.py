"""
agent/auth.py — unified MSAL delegated auth for all Power Platform resources.

All three token types (Eval API, BAPI, Dataverse) share one PublicClientApplication
and one SerializableTokenCache file. Device flow is initiated once; subsequent calls
for other resources acquire silently via the cached refresh token.

On Azure: set token_cache_file to a path on the shared Azure Files volume so both
containers share the same authenticated session.
"""
import json
import msal
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

EVAL_SCOPES = ["https://api.powerplatform.com/.default"]
BAPI_SCOPES = ["https://service.powerapps.com/.default"]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _cache_path(cfg: dict) -> str:
    return cfg.get("token_cache_file", "msal_token_cache.json")


def _load_cache(cfg: dict) -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    path = _cache_path(cfg)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cache.deserialize(f.read())
    return cache


def _save_cache(cache: msal.SerializableTokenCache, cfg: dict):
    if cache.has_state_changed:
        with open(_cache_path(cfg), "w", encoding="utf-8") as f:
            f.write(cache.serialize())


def _app(cfg: dict, cache: msal.SerializableTokenCache) -> msal.PublicClientApplication:
    return msal.PublicClientApplication(
        client_id=cfg["eval_app_client_id"],
        authority=f"https://login.microsoftonline.com/{cfg['eval_app_tenant_id']}",
        token_cache=cache,
    )


def _write_auth_state(cfg: dict, state: dict):
    store_dir = cfg.get("store_dir", "data")
    os.makedirs(store_dir, exist_ok=True)
    path = os.path.join(store_dir, "auth_state.json")
    state["updatedAt"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(state, indent=2))


def _email_device_code(cfg: dict, code: str, expires_in: int):
    smtp = cfg.get("smtp", {})
    host      = os.environ.get("SMTP_HOST")      or smtp.get("host")
    port      = int(os.environ.get("SMTP_PORT")  or smtp.get("port", 587))
    user      = os.environ.get("SMTP_USER")      or smtp.get("user")
    password  = os.environ.get("SMTP_PASSWORD")  or smtp.get("password")
    recipient = os.environ.get("SMTP_RECIPIENT") or smtp.get("recipient")
    if not all([host, user, password, recipient]):
        return False
    mins = expires_in // 60
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = f"""<html><body style="font-family:sans-serif;background:#0a0a0f;color:#e0e0e0;padding:32px">
  <div style="max-width:520px;margin:auto;border:1px solid #1a1a2e;border-radius:8px;padding:28px;background:#12121a">
    <h2 style="color:#ff4444;margin-top:0;font-family:monospace">⚠ ACTION REQUIRED — Sign in to VARION</h2>
    <p>The agent needs re-authentication. Eval cycles are paused until you sign in.</p>
    <hr style="border-color:#1a1a2e">
    <p><strong>Step 1 —</strong> Open: <a href="https://microsoft.com/devicelogin" style="color:#00f0ff">https://microsoft.com/devicelogin</a></p>
    <p><strong>Step 2 —</strong> Enter this code:</p>
    <div style="font-size:28px;font-weight:bold;letter-spacing:6px;color:#00f0ff;
                background:#0a0a0f;padding:16px 24px;border-radius:6px;display:inline-block;font-family:monospace">
      {code}
    </div>
    <p style="color:#666">Expires in <strong style="color:#e0e0e0">{mins} minutes</strong>.</p>
    <p style="color:#666;font-size:12px;margin-top:24px">Sent {ts} · copilot-eval-agent</p>
  </div>
</body></html>"""
    msg            = MIMEMultipart("alternative")
    msg["Subject"] = f"[VARION] Sign-in required — code {code}"
    msg["From"]    = user
    msg["To"]      = recipient
    msg.attach(MIMEText(body, "html"))
    try:
        with smtplib.SMTP(host, port) as s:
            s.ehlo(); s.starttls(); s.login(user, password); s.send_message(msg)
        return True
    except Exception:
        return False


def _acquire(scopes: list[str], cfg: dict) -> str:
    """
    Try silent token acquisition. On failure, start device flow,
    write auth_state.json for dashboard to surface the code, email if SMTP configured.
    Blocks until user completes auth or flow expires.
    """
    cache  = _load_cache(cfg)
    app    = _app(cfg, cache)
    result = None

    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])

    if result and "access_token" in result:
        _save_cache(cache, cfg)
        _write_auth_state(cfg, {
            "status":  "AUTHENTICATED",
            "account": accounts[0].get("username", "unknown") if accounts else "unknown",
        })
        return result["access_token"]

    # Need interactive auth
    flow       = app.initiate_device_flow(scopes=scopes)
    code       = flow.get("user_code", "??????")
    expires_in = flow.get("expires_in", 900)

    _write_auth_state(cfg, {
        "status":           "PENDING_DEVICE_FLOW",
        "user_code":        code,
        "verification_uri": "https://microsoft.com/devicelogin",
        "expires_in":       expires_in,
        "message":          flow.get("message", ""),
        "scopes":           scopes,
    })

    try:
        emailed = _email_device_code(cfg, code, expires_in)
        if emailed:
            print(f"[auth] Token needed — device code {code} emailed")
        else:
            print(f"[auth] Token needed — {flow.get('message', '')}")
    except Exception as e:
        print(f"[auth] Token needed — email failed ({e})")
        print(f"[auth] {flow.get('message', '')}")

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        _write_auth_state(cfg, {"status": "FAILED", "error": result.get("error_description", "")})
        raise RuntimeError(f"MSAL auth failed: {result.get('error_description')}")

    _save_cache(cache, cfg)
    _write_auth_state(cfg, {
        "status":  "AUTHENTICATED",
        "account": app.get_accounts()[0].get("username", "unknown") if app.get_accounts() else "unknown",
    })
    return result["access_token"]


# ── Public API ────────────────────────────────────────────────────────────────

def get_eval_token(cfg: dict) -> str:
    """Token for Copilot Studio Eval API (api.powerplatform.com)."""
    return _acquire(EVAL_SCOPES, cfg)


def get_bapi_token(cfg: dict) -> str:
    """Token for Power Apps BAPI (service.powerapps.com) — environment discovery."""
    return _acquire(BAPI_SCOPES, cfg)


def get_dataverse_token(org_url: str, cfg: dict) -> str:
    """Token for a specific Dataverse org — bot discovery."""
    if not org_url.startswith("http"):
        org_url = "https://" + org_url
    scopes = [org_url.rstrip("/") + "/.default"]
    return _acquire(scopes, cfg)


def get_auth_state(cfg: dict) -> dict:
    """Read last known auth state written by _write_auth_state."""
    store_dir = cfg.get("store_dir", "data")
    path = os.path.join(store_dir, "auth_state.json")
    if not os.path.exists(path):
        return {"status": "UNKNOWN"}
    try:
        with open(path, encoding="utf-8") as f:
            return json.loads(f.read())
    except Exception:
        return {"status": "UNKNOWN"}


def probe(cfg: dict) -> dict:
    """Connectivity probe — acquire eval token and return token prefix + account. Safe to call."""
    try:
        token = get_eval_token(cfg)
        state = get_auth_state(cfg)
        return {
            "ok":      True,
            "account": state.get("account", "unknown"),
            "token_prefix": token[:12] + "…",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
