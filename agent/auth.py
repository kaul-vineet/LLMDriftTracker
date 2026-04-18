import os
import smtplib
import subprocess
import msal
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

EVAL_SCOPES = ["https://api.powerplatform.com/.default"]


def get_dataverse_token(org_url: str) -> str:
    if os.environ.get("AZURE_CLIENT_ID"):
        from azure.identity import ClientSecretCredential
        resource = org_url.rstrip("/") + "/.default"
        cred = ClientSecretCredential(
            tenant_id=os.environ["AZURE_TENANT_ID"],
            client_id=os.environ["AZURE_CLIENT_ID"],
            client_secret=os.environ["AZURE_CLIENT_SECRET"]
        )
        return cred.get_token(resource).token
    else:
        resource = org_url.rstrip("/") + "/"
        cmd = f'az account get-access-token --resource {resource} --query accessToken -o tsv'
        r = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        if r.returncode != 0:
            raise RuntimeError(f"Dataverse token failed for {org_url}: {r.stderr.strip()}")
        return r.stdout.strip()


def get_bapi_token() -> str:
    if os.environ.get("AZURE_CLIENT_ID"):
        from azure.identity import ClientSecretCredential
        cred = ClientSecretCredential(
            tenant_id=os.environ["AZURE_TENANT_ID"],
            client_id=os.environ["AZURE_CLIENT_ID"],
            client_secret=os.environ["AZURE_CLIENT_SECRET"]
        )
        return cred.get_token("https://service.powerapps.com/.default").token
    else:
        cmd = 'az account get-access-token --resource https://service.powerapps.com/ --query accessToken -o tsv'
        r = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        if r.returncode != 0:
            raise RuntimeError(f"BAPI token failed: {r.stderr.strip()}")
        return r.stdout.strip()


def _email_device_code(cfg: dict, code: str, expires_in: int):
    smtp = cfg.get("smtp", {})
    host      = os.environ.get("SMTP_HOST")     or smtp.get("host")
    port      = int(os.environ.get("SMTP_PORT") or smtp.get("port", 587))
    user      = os.environ.get("SMTP_USER")     or smtp.get("user")
    password  = os.environ.get("SMTP_PASSWORD") or smtp.get("password")
    recipient = os.environ.get("SMTP_RECIPIENT") or smtp.get("recipient")

    if not all([host, user, password, recipient]):
        return False

    mins = expires_in // 60
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = f"""<html><body style="font-family:sans-serif;background:#0d1117;color:#c9d1d9;padding:32px">
  <div style="max-width:520px;margin:auto;border:1px solid #30363d;border-radius:8px;padding:28px">
    <h2 style="color:#f0883e;margin-top:0">⚠️ Action Required — Sign in to LLM Drift Tracker</h2>
    <p>The agent needs you to re-authenticate with Microsoft. Eval cycles are paused until you sign in.</p>
    <hr style="border-color:#30363d">
    <p><strong>Step 1 —</strong> Open your browser and go to:<br>
    <a href="https://microsoft.com/devicelogin" style="color:#58a6ff">https://microsoft.com/devicelogin</a></p>
    <p><strong>Step 2 —</strong> Enter this code:</p>
    <div style="font-size:28px;font-weight:bold;letter-spacing:6px;color:#58a6ff;
                background:#161b22;padding:16px 24px;border-radius:6px;display:inline-block">
      {code}
    </div>
    <p style="color:#8b949e">Code expires in <strong style="color:#c9d1d9">{mins} minutes</strong>.
    If it expires, the agent will send a fresh code on the next poll cycle.</p>
    <p style="color:#8b949e;font-size:12px;margin-top:24px">Sent {ts} · copilot-eval-agent v1.0</p>
  </div>
</body></html>"""

    msg           = MIMEMultipart("alternative")
    msg["Subject"] = f"[LLM Drift Tracker] Sign-in required — code {code}"
    msg["From"]    = user
    msg["To"]      = recipient
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP(host, port) as s:
        s.ehlo(); s.starttls(); s.login(user, password); s.send_message(msg)

    return True


def get_eval_token(cfg: dict) -> str:
    """Silent refresh on every call. When expired, emails device code to admin and polls."""
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
    result   = None
    if accounts:
        result = app.acquire_token_silent(EVAL_SCOPES, account=accounts[0])

    if not result or "access_token" not in result:
        flow       = app.initiate_device_flow(scopes=EVAL_SCOPES)
        code       = flow.get("user_code", "??????")
        expires_in = flow.get("expires_in", 900)

        try:
            emailed = _email_device_code(cfg, code, expires_in)
            if emailed:
                print(f"[auth] Token expired — device code {code} emailed to admin")
            else:
                print(f"[auth] Token expired — {flow['message']}")
        except Exception as e:
            print(f"[auth] Token expired — email failed ({e}), code: {code}")
            print(f"[auth] {flow['message']}")

        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(f"MSAL auth failed: {result.get('error_description')}")

    if cache.has_state_changed:
        open(cache_file, "w").write(cache.serialize())

    return result["access_token"]
