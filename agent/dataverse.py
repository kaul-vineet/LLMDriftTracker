import json
import requests
from .auth import get_dataverse_token

DV_API = "/api/data/v9.2"
# configuration excluded — causes 400 in collection $select; fetched per-bot.
# Opt-in via config.json monitoredBots list (schemanames) per environment.
# Empty list = monitor all active bots in that environment.
BOT_SELECT = "botid,name,schemaname,publishedon,statecode"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "Accept": "application/json"
    }


def extract_model_version(configuration: str) -> str:
    try:
        cfg = json.loads(configuration or "{}")
        return cfg.get("gPTSettings", {}).get("defaultSchemaName", "unknown")
    except Exception:
        return "unknown"


def _fetch_bot_details(org_url: str, token: str, bot_id: str) -> dict:
    """Fetch full bot record (no $select) to get configuration and any computed fields."""
    try:
        r = requests.get(
            f"{org_url}{DV_API}/bots({bot_id})",
            headers=_headers(token),
            timeout=20,
        )
        if r.ok:
            return r.json()
    except Exception:
        pass
    return {}


def list_bots(org_url: str, monitored: list) -> list[dict]:
    token = get_dataverse_token(org_url)
    url = f"{org_url}{DV_API}/bots?$select={BOT_SELECT}&$filter=statecode eq 0"
    r = requests.get(url, headers=_headers(token), timeout=20)
    r.raise_for_status()

    bots = []
    for b in r.json().get("value", []):
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
            "orgUrl":       org_url
        })
    return bots


def list_all_bots(cfg: dict) -> list[dict]:
    all_bots = []
    for env in cfg["environments"]:
        monitored = env.get("monitoredBots", [])
        scope_label = f"{len(monitored)} selected" if monitored else "all"
        try:
            bots = list_bots(env["orgUrl"], monitored)
            for b in bots:
                b["envName"] = env["name"]
                b["ppEnvId"] = env["environmentId"]
            all_bots.extend(bots)
            print(f"[dataverse] {env['name']}: {len(bots)} bot(s) ({scope_label})")
        except Exception as e:
            print(f"[dataverse] {env['name']} failed: {e}")
    return all_bots
