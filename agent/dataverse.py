"""
agent/dataverse.py — Dataverse + BAPI bot/environment discovery.

All auth is now via MSAL (auth.py). No az CLI, no service principal.
"""
import re
import requests
from .auth import get_dataverse_token, get_bapi_token
from . import lore

DV_API     = "/api/data/v9.2"
BOT_SELECT = "botid,name,schemaname,publishedon,statecode"
BAPI_ENVS  = ("https://api.bap.microsoft.com/providers/"
              "Microsoft.BusinessAppPlatform/environments")

# The LLM the user picked in the Copilot Studio UI is stored on a *child* entity
# (botcomponents, keyed by gPTSettings.defaultSchemaName on the bot record) inside
# a YAML-valued column, at path aISettings.model.modelNameHint. This regex pulls
# it out without adding a PyYAML dependency. Case-insensitive to tolerate minor
# CPS schema drift. Using re.MULTILINE so ^ matches after indentation on each line.
_MODEL_HINT_RX = re.compile(
    r"^\s*modelNameHint\s*:\s*(\S+?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _dv_headers(token: str) -> dict:
    return {
        "Authorization":  f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "Accept":         "application/json",
    }


def _bapi_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _extract_default_schema_name(configuration: str) -> str:
    """gPTSettings.defaultSchemaName on the bot record is a pointer to the bot's
    default GPT child component (format: '{bot.schemaname}.gpt.default'). It is
    static — does NOT change on LLM swap — so it cannot be used as a model
    identifier on its own, only as the key to look up the child record."""
    import json
    try:
        cfg = json.loads(configuration or "{}")
        return cfg.get("gPTSettings", {}).get("defaultSchemaName", "")
    except Exception:
        return ""


def _fetch_bot_component(org_url: str, token: str, schema_name: str) -> dict:
    """Fetch the botcomponents record for a given schemaname. Returns {} on any
    failure so callers can fall back without raising.

    Retries once after a short backoff — in practice most child-lookup misses
    right after a publish are transient (Dataverse eventual consistency / token
    refresh mid-request). One retry clears the vast majority without turning
    the poll loop into a retry storm."""
    if not schema_name:
        return {}
    import time
    for attempt in range(2):
        try:
            r = requests.get(
                f"{org_url}{DV_API}/botcomponents",
                params={
                    "$filter": f"schemaname eq '{schema_name}'",
                    "$select": "data,content",
                },
                headers=_dv_headers(token),
                timeout=20,
            )
            if r.ok:
                items = r.json().get("value", [])
                return items[0] if items else {}
        except Exception:
            pass
        if attempt == 0:
            time.sleep(0.5)
    return {}


def extract_model_version(configuration: str,
                          org_url: str = "", token: str = "",
                          store_dir: str = "", bot_id: str = "") -> str:
    """Return the currently-selected LLM identifier for a bot (e.g. 'GPT5Chat').

    The bot record itself does not store the LLM — it stores only a pointer at
    gPTSettings.defaultSchemaName to a child 'botcomponents' record. The actual
    model lives in that child's YAML-valued `data` column at
    aISettings.model.modelNameHint.

    Fallback chain if the child lookup fails or returns no hint:
      1. Last known good value from tracking.json (if store_dir+bot_id passed)
      2. Schema name (first-run bootstrap only)

    Returning the last known good value on a transient lookup failure is
    critical: returning the static schema name would corrupt tracking.json
    and force a false-positive model_change event on the next poll, which is
    exactly the bug the main fix is supposed to solve.

    Legacy callers that pass only `configuration` (no org_url/token) get the
    schema name directly — preserved for backward compat with any callers
    that don't have auth context.
    """
    schema = _extract_default_schema_name(configuration)
    if not schema:
        return "unknown"
    if not (org_url and token):
        return schema  # legacy path — no way to follow the pointer

    rec = _fetch_bot_component(org_url, token, schema)
    yaml_text = rec.get("data") or rec.get("content") or ""
    m = _MODEL_HINT_RX.search(yaml_text) if yaml_text else None
    if m:
        return m.group(1)

    # Lookup failed or YAML missing the field — prefer last known good over the
    # schema name so a transient blip doesn't corrupt state.
    if store_dir and bot_id:
        from . import store as _store
        prior = _store.load_tracking(store_dir, bot_id).get("modelVersion")
        if prior and prior != schema:
            return prior
    return schema


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
    store_dir = cfg.get("store_dir", "data")
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
            "modelVersion": extract_model_version(
                details.get("configuration"), org_url, token,
                store_dir, bot_id),
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
