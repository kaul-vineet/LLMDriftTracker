"""
agent/dataverse.py — bot discovery via Power Platform Inventory API.

Bot listing uses the same Inventory API and eval token as the Setup page —
no Dataverse token required.  Model version is retrieved via a silent-only
Dataverse token; if none is cached it defaults to "unknown" so the watcher
never blocks on a device-flow prompt.
"""
import os
import requests
from .auth import get_bapi_token, get_eval_token, get_dataverse_token_silent
from . import logger as logger_mod
from . import lore

INVENTORY_URL = "https://api.powerplatform.com/resourcequery/resources/query"
BAPI_ENVS     = ("https://api.bap.microsoft.com/providers/"
                 "Microsoft.BusinessAppPlatform/environments")
DV_API        = "/api/data/v9.2"


def _eval_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def _bapi_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _dv_headers(token: str) -> dict:
    return {
        "Authorization":    f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "Accept":           "application/json",
    }


def extract_model_version(configuration: str) -> str:
    import json
    try:
        cfg = json.loads(configuration or "{}")
        return cfg.get("gPTSettings", {}).get("defaultSchemaName", "unknown")
    except Exception:
        return "unknown"


# ── Environment discovery ─────────────────────────────────────────────────────

def list_environments(cfg: dict) -> list[dict]:
    """
    Fetch all Power Platform environments from BAPI that have a Dataverse org URL.
    Returns list of {name, displayName, orgUrl, environmentId}.
    """
    log   = logger_mod.get()
    token = get_bapi_token(cfg)
    log.info("Fetching Power Platform environments from BAPI")
    resp  = requests.get(
        BAPI_ENVS,
        params={"api-version": "2020-10-01"},
        headers=_bapi_headers(token),
        timeout=20,
    )
    resp.raise_for_status()
    raw = resp.json()

    if os.environ.get("VERBOSE"):
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
    log.info(f"Found {len(envs)} Power Platform environment(s) with Dataverse")
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


# ── Bot discovery via Inventory API ──────────────────────────────────────────

def _fetch_bots_inventory(env_id: str, token: str) -> list[dict]:
    """List Copilot Studio agents via Inventory API — eval token, no Dataverse needed."""
    log = logger_mod.get()
    log.info(f"Querying bot inventory for environment {env_id[:12]}...")
    r = requests.post(
        INVENTORY_URL,
        params={"api-version": "2024-10-01"},
        headers=_eval_headers(token),
        json={
            "TableName": "PowerPlatformResources",
            "Clauses": [
                {"$type": "where", "FieldName": "type",
                 "Operator": "==", "Values": ["'microsoft.copilotstudio/agents'"]},
                {"$type": "where", "FieldName": "properties.environmentId",
                 "Operator": "==", "Values": [f"'{env_id.lower()}'"]}
            ]
        },
        timeout=15,
    )
    if r.status_code != 200:
        log.error(f"Inventory API returned HTTP {r.status_code}: {r.text[:300]}")
        return []

    data = r.json().get("data", [])
    log.info(f"Inventory API returned {len(data)} agent(s) for env {env_id[:12]}...")

    if os.environ.get("VERBOSE"):
        import json
        if data:
            print(f"[probe] First bot sample: {json.dumps(data[0], indent=2)[:400]}")

    bots = []
    for item in data:
        p = item.get("properties", {})
        bots.append({
            "botId":      item.get("name", ""),
            "name":       p.get("displayName", ""),
            "schemaName": p.get("schemaName", ""),
        })
    return bots


def _fetch_model_version(org_url: str, bot_id: str, cfg: dict) -> str:
    """
    Read the active LLM model from botcomponents.aISettings.model.modelNameHint.
    This field (e.g. 'GPT5Chat', 'sonnet4-5', 'opus4-1') changes when the user
    picks a different model in Copilot Studio — unlike gPTSettings.defaultSchemaName
    on the bot record which is a static schema identifier that never changes.
    Returns 'unknown' without blocking if no Dataverse token is cached.
    """
    import json as _json
    log   = logger_mod.get()
    token = get_dataverse_token_silent(org_url, cfg)
    if not token:
        log.info(f"No cached Dataverse token for {org_url} — model version will be unavailable")
        return "unknown"
    try:
        r = requests.get(
            f"{org_url}{DV_API}/botcomponents",
            headers=_dv_headers(token),
            params={
                "$filter": f"_parentbotid_value eq {bot_id}",
                "$select": "name,aisettings",
                "$top":    "50",
            },
            timeout=20,
        )
        if not r.ok:
            log.warning(f"Dataverse botcomponents returned HTTP {r.status_code} for bot {bot_id[:8]}")
            return "unknown"

        components = r.json().get("value", [])
        log.info(f"Fetched {len(components)} botcomponent(s) for {bot_id[:8]}")

        for comp in components:
            raw = comp.get("aisettings") or ""
            if not raw:
                continue
            try:
                ai    = _json.loads(raw)
                hint  = ai.get("model", {}).get("modelNameHint", "")
                if hint:
                    log.info(f"Model version for {bot_id[:8]}: {hint} (from botcomponents.aISettings)")
                    return hint
            except Exception:
                continue

        log.warning(f"No aISettings.model.modelNameHint found in {len(components)} component(s) for bot {bot_id[:8]}")
    except Exception as e:
        log.warning(f"Could not fetch model version for {bot_id[:8]} from {org_url}: {e}")
    return "unknown"


def list_bots(env_id: str, org_url: str, monitored: list, cfg: dict) -> list[dict]:
    """
    List active bots for an environment using the Inventory API (eval token).
    Model version is fetched via silent Dataverse token; defaults to 'unknown' if unavailable.
    monitored: list of schemanames to filter; empty = return all.
    """
    log   = logger_mod.get()
    token = get_eval_token(cfg)
    raw   = _fetch_bots_inventory(env_id, token)

    if monitored:
        raw = [b for b in raw if b.get("schemaName") in monitored]
        log.info(f"Filtered to {len(raw)} monitored bot(s) from schema name list")

    bots = []
    for b in raw:
        bot_id        = b["botId"]
        model_version = _fetch_model_version(org_url, bot_id, cfg)
        bots.append({
            "botId":        bot_id,
            "name":         b.get("name", ""),
            "schemaName":   b.get("schemaName", ""),
            "modelVersion": model_version,
            "orgUrl":       org_url,
        })
        log.info(f"Bot loaded: {b.get('name', bot_id)} (schema: {b.get('schemaName', '')}, model: {model_version})")
    return bots


def probe_bots(org_url: str, cfg: dict) -> dict:
    """Connectivity probe — list bots for an org and return diagnostic info."""
    try:
        env_id = ""
        for e in cfg.get("environments", []):
            if e.get("orgUrl", "").rstrip("/") == org_url.rstrip("/"):
                env_id = e.get("environmentId", "")
                break
        bots = list_bots(env_id, org_url, [], cfg)
        return {
            "ok":    True,
            "count": len(bots),
            "bots":  [{"name": b["name"], "schemaName": b["schemaName"],
                       "modelVersion": b["modelVersion"]} for b in bots],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_all_bots(cfg: dict) -> list[dict]:
    log      = logger_mod.get()
    all_bots = []
    for env in cfg["environments"]:
        monitored   = env.get("monitoredBots", [])
        scope_label = f"{len(monitored)} selected" if monitored else "all"
        env_id      = env.get("environmentId", "")
        org_url     = env.get("orgUrl", "")
        log.info(f"Scanning environment '{env['name']}' — {scope_label} bots, env ID: {env_id[:12]}...")
        try:
            bots = list_bots(env_id, org_url, monitored, cfg)
            for b in bots:
                b["envName"] = env["name"]
                b["ppEnvId"] = env_id
            all_bots.extend(bots)
            lore.bots_found(env["name"], len(bots), scope_label)
            log.info(f"Environment '{env['name']}': {len(bots)} agent(s) loaded")
        except Exception as e:
            log.error(f"Failed to load bots from environment '{env['name']}': {e}")
            lore.bots_failed(env["name"], e)
    log.info(f"Agent inventory complete — {len(all_bots)} agent(s) across {len(cfg['environments'])} environment(s)")
    return all_bots
