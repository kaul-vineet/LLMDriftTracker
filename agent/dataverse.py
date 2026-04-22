"""
agent/dataverse.py — bot discovery via Power Platform Inventory API.

Bot listing uses the same Inventory API and eval token as the Setup page —
no Dataverse token required.  Model version is retrieved via a silent-only
Dataverse token; if none is cached it defaults to "unknown" so the watcher
never blocks on a device-flow prompt.
"""
import os
import requests
from .auth import get_bapi_token, get_eval_token_agent, AuthError
from . import logger as logger_mod
from . import lore

INVENTORY_URL = "https://api.powerplatform.com/resourcequery/resources/query"
BAPI_ENVS     = ("https://api.bap.microsoft.com/providers/"
                 "Microsoft.BusinessAppPlatform/environments")
CS_API_BASE   = "https://api.powerplatform.com/copilotstudio"
PP_API_VER    = "2024-10-01"


def _eval_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def _bapi_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _model_from_properties(p: dict) -> str:
    """Extract model name from Inventory API bot properties (no Dataverse needed).

    Tries aISettings.model.modelNameHint first (e.g. 'GPT5Chat', 'sonnet4-5'),
    then falls back to publishedConfiguration and gPTSettings paths.
    """
    import json as _j

    def _parse(raw) -> str:
        if isinstance(raw, str):
            try:
                raw = _j.loads(raw)
            except Exception:
                return ""
        if isinstance(raw, dict):
            hint = raw.get("model", {}).get("modelNameHint", "")
            if hint:
                return hint
        return ""

    for key in ("aISettings", "aiSettings", "aisettings"):
        hint = _parse(p.get(key, ""))
        if hint:
            return hint

    return "unknown"


# ── Environment discovery ─────────────────────────────────────────────────────

def list_environments(cfg: dict) -> list[dict]:
    """
    Fetch all Power Platform environments from BAPI (Setup/wizard only — not called by agent loop).
    Returns list of {name, displayName, orgUrl, environmentId}.
    """
    log   = logger_mod.get()
    token = get_bapi_token(cfg)   # full device-flow version — only called from Setup
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
    """
    List Copilot Studio agents via Power Platform Inventory API (eval token only).
    Returns each bot with model name extracted directly from Inventory API properties
    — no Dataverse call needed.
    """
    log = logger_mod.get()
    log.info(f"Querying bot inventory for environment {env_id[:12]}...")
    r = requests.post(
        INVENTORY_URL,
        params={"api-version": PP_API_VER},
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
        raise AuthError(f"Inventory API returned HTTP {r.status_code} — token may have expired")

    data = r.json().get("data", [])
    log.info(f"Inventory API returned {len(data)} agent(s) for env {env_id[:12]}...")

    if os.environ.get("VERBOSE") and data:
        import json
        p = data[0].get("properties", {})
        log.info(f"[verbose] First bot property keys: {sorted(p.keys())}")
        log.info(f"[verbose] First bot raw: {json.dumps(data[0], indent=2)[:800]}")

    bots = []
    for item in data:
        p  = item.get("properties", {})
        mv = _model_from_properties(p)
        bots.append({
            "botId":        item.get("name", ""),
            "name":         p.get("displayName", ""),
            "schemaName":   p.get("schemaName", ""),
            "modelVersion": mv,
        })
    return bots


def _fetch_model_version_cs_api(pp_env_id: str, bot_id: str, token: str) -> str:
    """
    Fallback: fetch model name via the Copilot Studio REST API (same eval token).
    Tries GET /copilotstudio/environments/{env}/bots/{bot} and reads aISettings.
    """
    log = logger_mod.get()
    try:
        url = f"{CS_API_BASE}/environments/{pp_env_id}/bots/{bot_id}?api-version={PP_API_VER}"
        r   = requests.get(url, headers=_eval_headers(token), timeout=15)
        if not r.ok:
            log.info(f"CS bot detail API returned HTTP {r.status_code} for {bot_id[:8]}")
            return "unknown"
        mv = _model_from_properties(r.json().get("properties", r.json()))
        if mv != "unknown":
            log.info(f"Model version for {bot_id[:8]} from CS API: {mv}")
        return mv
    except Exception as e:
        log.info(f"CS bot detail API error for {bot_id[:8]}: {e}")
        return "unknown"


def list_bots(env_id: str, org_url: str, monitored: list, cfg: dict) -> list[dict]:
    """
    List active bots for an environment using Power Platform APIs only (eval token throughout).
    Model name comes from Inventory API properties; if absent, falls back to Copilot Studio API.
    No Dataverse / Dynamics API calls.
    monitored: list of schemanames to filter; empty = return all.
    """
    log   = logger_mod.get()
    token = get_eval_token_agent(cfg)   # raises AuthError if no valid token
    raw   = _fetch_bots_inventory(env_id, token)

    if monitored:
        raw = [b for b in raw if b.get("schemaName") in monitored]
        log.info(f"Filtered to {len(raw)} monitored bot(s) from schema name list")

    bots = []
    for b in raw:
        bot_id = b["botId"]
        mv     = b.get("modelVersion", "unknown")
        if mv == "unknown":
            # Inventory API didn't carry aISettings — try CS bot detail endpoint
            mv = _fetch_model_version_cs_api(env_id, bot_id, token)
        bots.append({
            "botId":        bot_id,
            "name":         b.get("name", ""),
            "schemaName":   b.get("schemaName", ""),
            "modelVersion": mv,
            "orgUrl":       org_url,
        })
        log.info(f"Bot loaded: {b.get('name', bot_id)} (schema: {b.get('schemaName', '')}, model: {mv})")
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
