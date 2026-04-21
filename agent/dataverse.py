"""
agent/dataverse.py — Dataverse + BAPI bot/environment discovery.

All auth is now via MSAL (auth.py). No az CLI, no service principal.
"""
import requests
from .auth import get_dataverse_token, get_bapi_token
from . import lore

DV_API     = "/api/data/v9.2"
BOT_SELECT = "botid,name,schemaname,publishedon,statecode"
BAPI_ENVS  = ("https://api.bap.microsoft.com/providers/"
              "Microsoft.BusinessAppPlatform/environments")


def _dv_headers(token: str) -> dict:
    return {
        "Authorization":  f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "Accept":         "application/json",
    }


def _bapi_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def extract_model_version(configuration: str) -> str:
    import json
    try:
        cfg = json.loads(configuration or "{}")
        # Copilot Studio stores the LLM model under bot.configuration → gPTSettings → defaultSchemaName
        return cfg.get("gPTSettings", {}).get("defaultSchemaName", "unknown")
    except Exception:
        return "unknown"


# ── Environment discovery ─────────────────────────────────────────────────────

def list_environments(cfg: dict) -> list[dict]:
    """
    Fetch all Power Platform environments from BAPI that have a Dataverse org URL.
    Returns list of {name, displayName, orgUrl, environmentId}.
    Sample call — raw response printed for diagnostics if DRIFT_VERBOSE=1.
    """
    import os
    token = get_bapi_token(cfg)
    resp  = requests.get(
        BAPI_ENVS,
        params={"api-version": "2020-10-01"},
        headers=_bapi_headers(token),
        timeout=20,
    )
    resp.raise_for_status()
    raw = resp.json()

    if os.environ.get("DRIFT_VERBOSE"):
        import json
        print("[probe] BAPI /environments raw keys:", list(raw.keys()))
        print("[probe] First env sample:", json.dumps(raw.get("value", [{}])[0], indent=2)[:400])

    envs = []
    for item in raw.get("value", []):
        env_id  = item.get("name", "")
        props   = item.get("properties", {})
        display = props.get("displayName", env_id)
        url     = props.get("linkedEnvironmentMetadata", {}).get("instanceUrl", "")
        if url:
            envs.append({
                "name":          display,
                "displayName":   display,
                "orgUrl":        url.rstrip("/"),
                "environmentId": env_id,
            })
    return envs


def probe_environments(cfg: dict) -> dict:
    """Connectivity probe — list environments and return diagnostic info."""
    try:
        envs = list_environments(cfg)
        return {
            "ok":    True,
            "count": len(envs),
            "envs":  [{"name": e["name"], "orgUrl": e["orgUrl"]} for e in envs],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Bot discovery ─────────────────────────────────────────────────────────────

def _fetch_bot_details(org_url: str, token: str, bot_id: str) -> dict:
    try:
        r = requests.get(
            f"{org_url}{DV_API}/bots({bot_id})",
            headers=_dv_headers(token),
            timeout=20,
        )
        if r.ok:
            return r.json()
    except Exception:
        pass
    return {}


def list_bots(org_url: str, monitored: list, cfg: dict) -> list[dict]:
    """
    List active bots in a Dataverse environment.
    monitored: list of schemanames to filter; empty = return all active.
    """
    import os
    token = get_dataverse_token(org_url, cfg)
    url   = f"{org_url}{DV_API}/bots?$select={BOT_SELECT}&$filter=statecode eq 0"
    r     = requests.get(url, headers=_dv_headers(token), timeout=20)
    r.raise_for_status()
    raw   = r.json()

    if os.environ.get("DRIFT_VERBOSE"):
        import json
        print(f"[probe] Dataverse /bots raw keys: {list(raw.keys())}")
        print(f"[probe] Total bots returned: {len(raw.get('value', []))}")
        if raw.get("value"):
            print(f"[probe] First bot sample: {json.dumps(raw['value'][0], indent=2)[:300]}")

    bots = []
    for b in raw.get("value", []):
        if monitored and b.get("schemaname") not in monitored:
            continue
        bot_id  = b["botid"]
        details = _fetch_bot_details(org_url, token, bot_id)
        bots.append({
            "botId":        bot_id,
            "name":         b.get("name", ""),
            "schemaName":   b.get("schemaname", ""),
            "modelVersion": extract_model_version(details.get("configuration")),
            "publishedOn":  b.get("publishedon"),
            "orgUrl":       org_url,
        })
    return bots


def probe_bots(org_url: str, cfg: dict) -> dict:
    """Connectivity probe — list bots for an org and return diagnostic info."""
    try:
        bots = list_bots(org_url, [], cfg)
        return {
            "ok":    True,
            "count": len(bots),
            "bots":  [{"name": b["name"], "schemaName": b["schemaName"],
                       "modelVersion": b["modelVersion"]} for b in bots],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_all_bots(cfg: dict) -> list[dict]:
    all_bots = []
    for env in cfg["environments"]:
        monitored   = env.get("monitoredBots", [])
        scope_label = f"{len(monitored)} selected" if monitored else "all"
        try:
            bots = list_bots(env["orgUrl"], monitored, cfg)
            for b in bots:
                b["envName"] = env["name"]
                b["ppEnvId"] = env["environmentId"]
            all_bots.extend(bots)
            lore.bots_found(env["name"], len(bots), scope_label)
        except Exception as e:
            lore.bots_failed(env["name"], e)
    return all_bots
