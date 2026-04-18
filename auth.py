import os
import subprocess
import msal

EVAL_SCOPES = ["https://api.powerplatform.com/.default"]


def get_dataverse_token(org_url: str) -> str:
    """
    Local: az account get-access-token (delegated, user context).
    Docker: ClientSecretCredential via AZURE_CLIENT_ID/SECRET/TENANT_ID env vars.
    """
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


def get_eval_token(cfg: dict) -> str:
    """Always MSAL delegated — device code on first run, silent refresh thereafter."""
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
    result = None
    if accounts:
        result = app.acquire_token_silent(EVAL_SCOPES, account=accounts[0])

    if not result or "access_token" not in result:
        flow = app.initiate_device_flow(scopes=EVAL_SCOPES)
        print(f"\n[AUTH] {flow['message']}\n")
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(f"MSAL auth failed: {result.get('error_description')}")

    if cache.has_state_changed:
        open(cache_file, "w").write(cache.serialize())

    return result["access_token"]
