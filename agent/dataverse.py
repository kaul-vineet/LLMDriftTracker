"""
agent/dataverse.py — bot discovery via Power Platform Inventory API.

Bot listing uses the same Inventory API and eval token as the Setup page —
no Dataverse token required.  Model version is retrieved via a silent-only
Dataverse token; if none is cached it defaults to "unknown" so the watcher
never blocks on a device-flow prompt.
"""
import os
import re
import requests
from .auth import get_eval_token, get_eval_token_agent, get_dataverse_token_silent, AuthError
from . import logger as logger_mod
from . import lore

INVENTORY_URL   = "https://api.powerplatform.com/resourcequery/resources/query"
PP_API_VER      = "2024-10-01"
_DV_API         = "/api/data/v9.2"
_DV_AUTH_NEEDED = "dv_auth_needed.json"


def _dv_flag_path(cfg: dict) -> str:
    return os.path.join(cfg.get("store_dir", "data"), "agent", _DV_AUTH_NEEDED)


def _write_dv_auth_needed(cfg: dict):
    path = _dv_flag_path(cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        open(path, "w").write("{}")


def _clear_dv_auth_needed(cfg: dict):
    try:
        os.remove(_dv_flag_path(cfg))
    except FileNotFoundError:
        pass

# Extracts modelNameHint from the YAML-valued `data` column of a botcomponents record.
_MODEL_HINT_RX = re.compile(
    r"^\s*modelNameHint\s*:\s*(\S+?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _extract_instructions(yaml_text: str) -> str:
    """Extract the bot system prompt from botcomponents YAML.

    Handles both block scalar (instructions: |) and inline forms.
    """
    if not yaml_text:
        return ""
    # Block scalar: instructions: | or instructions: >
    m = re.search(r"^instructions:\s*[|>][-+]?\s*\n((?:[ \t]+[^\n]*\n?)*)", yaml_text, re.MULTILINE)
    if m:
        block  = m.group(1)
        lines  = block.split("\n")
        indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
        min_i   = min(indents) if indents else 0
        return "\n".join(l[min_i:] for l in lines).strip()
    # Inline: instructions: some text  or  instructions: "quoted text"
    m = re.search(r"^instructions:\s+(.+)$", yaml_text, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    return ""


def _eval_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def _model_from_properties(p: dict) -> str:
    """Check Inventory API properties.model field (Preview, api-version 2024-10-01+)."""
    return p.get("model") or "unknown"


# ── Environment discovery ─────────────────────────────────────────────────────

def list_environments(cfg: dict) -> list[dict]:
    """
    Fetch all Power Platform environments via Inventory API (eval token — Setup/wizard only).
    Returns list of {name, displayName, orgUrl, environmentId}.
    """
    log   = logger_mod.get()
    token = get_eval_token(cfg)   # full device-flow version — called from Setup only
    log.info("Fetching environments from Power Platform Inventory API")
    r = requests.post(
        INVENTORY_URL,
        params={"api-version": PP_API_VER},
        headers=_eval_headers(token),
        json={"TableName": "PowerPlatformResources",
              "Clauses": [{"$type": "where", "FieldName": "type",
                           "Operator": "==",
                           "Values": ["'microsoft.powerplatform/environments'"]}]},
        timeout=20,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Inventory API (environments) HTTP {r.status_code}: {r.text[:200]}")

    data = r.json().get("data", [])
    log.info(f"Inventory API returned {len(data)} environment(s)")

    if os.environ.get("VERBOSE") and data:
        import json
        p = data[0].get("properties", {})
        log.info(f"[verbose] First env property keys: {sorted(p.keys())}")
        log.info(f"[verbose] First env raw: {json.dumps(data[0], indent=2)[:800]}")

    envs = []
    for item in data:
        p      = item.get("properties", {})
        env_id = item.get("name", "")
        name   = p.get("displayName", env_id)
        org_url = (p.get("linkedEnvironmentMetadata", {}).get("instanceUrl", "")
                   or p.get("url", "")
                   or p.get("instanceUrl", ""))
        envs.append({
            "name":          name,
            "displayName":   name,
            "orgUrl":        org_url.rstrip("/"),
            "environmentId": env_id,
        })
    log.info(f"Found {len(envs)} Power Platform environment(s)")
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

    verbose = os.environ.get("VERBOSE")
    bots = []
    for item in data:
        p  = item.get("properties", {})
        mv = _model_from_properties(p)
        if verbose and mv == "unknown":
            import json
            log.info(f"[verbose] model=unknown for '{p.get('displayName','?')}' "
                     f"— property keys: {sorted(p.keys())}")
            log.info(f"[verbose] raw properties: {json.dumps(p, indent=2)[:1200]}")
        bots.append({
            "botId":      item.get("name", ""),
            "name":       p.get("displayName", ""),
            "schemaName": p.get("schemaName", ""),
            "createdIn":  p.get("createdIn", ""),
        })
    return bots



def _fetch_model_via_botcomponent(org_url: str, bot_schema_name: str, cfg: dict) -> str:
    """Look up modelNameHint from the bot's default GPT botcomponent YAML.

    Copilot Studio stores the selected LLM in a child botcomponents record whose
    schema name follows the convention '{botSchemaName}.gpt.default'. The model
    name lives in that record's YAML-valued `data` column at
    aISettings.model.modelNameHint.

    Uses the same token path as the probe script — silent if cached, device-flow
    email fallback if not. Returns 'unknown' on any token or API failure.
    """
    if not (org_url and bot_schema_name):
        return "unknown", ""
    log      = logger_mod.get()
    dv_token = get_dataverse_token_silent(org_url, cfg)
    if not dv_token:
        log.warning(f"Dataverse token unavailable for '{org_url}' — "
                    f"add 'Dynamics CRM > user_impersonation' to the app registration "
                    f"and grant admin consent, then re-authenticate via Setup")
        _write_dv_auth_needed(cfg)
        return "unknown", ""
    _clear_dv_auth_needed(cfg)
    gpt_schema = f"{bot_schema_name}.gpt.default"
    try:
        r = requests.get(
            f"{org_url.rstrip('/')}{_DV_API}/botcomponents",
            params={"$filter": f"schemaname eq '{gpt_schema}'", "$select": "data,content"},
            headers={"Authorization": f"Bearer {dv_token}", "Accept": "application/json"},
            timeout=20,
        )
        if not r.ok:
            log.info(f"botcomponents lookup HTTP {r.status_code} for '{gpt_schema}'")
            return "unknown", ""
        items = r.json().get("value", [])
        if not items:
            log.info(f"botcomponents lookup: no record found for schema '{gpt_schema}'")
            return "unknown", ""
        yaml_text    = items[0].get("data") or items[0].get("content") or ""
        m            = _MODEL_HINT_RX.search(yaml_text) if yaml_text else None
        instructions = _extract_instructions(yaml_text)
        if m:
            hint = m.group(1)
            log.info(f"Model hint from botcomponents YAML for '{bot_schema_name}': {hint}")
            return hint, instructions
        # YAML exists but no modelNameHint — bot uses platform default model (model: {} or no aISettings)
        log.info(f"No custom model in botcomponents YAML for '{gpt_schema}' — treating as default")
        return "default", instructions
    except Exception as e:
        log.info(f"botcomponents lookup error for '{bot_schema_name}': {e}")
        return "unknown", ""


def list_bots(env_id: str, org_url: str, monitored: list, cfg: dict) -> list[dict]:
    """
    List active bots for an environment.
    Bot inventory comes from the Power Platform Inventory API (eval token).
    Model version comes from Dataverse botcomponents YAML (Dataverse token, silent).
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
        bot_id     = b["botId"]
        created_in = b.get("createdIn", "")
        # M365 Copilot Agent Builder agents don't have selectable models — skip Dataverse lookup
        if created_in == "Microsoft 365 Copilot Agent Builder":
            mv, instructions = "default", ""
        else:
            mv, instructions = _fetch_model_via_botcomponent(org_url, b.get("schemaName", ""), cfg)
        bots.append({
            "botId":        bot_id,
            "name":         b.get("name", ""),
            "schemaName":   b.get("schemaName", ""),
            "modelVersion": mv,
            "instructions": instructions,
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


def _scan_env(env: dict, cfg: dict, log) -> list[dict]:
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
        lore.bots_found(env["name"], len(bots), scope_label)
        log.info(f"Environment '{env['name']}': {len(bots)} agent(s) loaded")
        return bots
    except Exception as e:
        log.error(f"Failed to load bots from environment '{env['name']}': {e}")
        lore.bots_failed(env["name"], e)
        return []


def list_all_bots(cfg: dict) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    log  = logger_mod.get()
    envs = cfg["environments"]
    all_bots: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, len(envs))) as ex:
        futures = {ex.submit(_scan_env, env, cfg, log): env for env in envs}
        for fut in as_completed(futures):
            all_bots.extend(fut.result())
    log.info(f"Agent inventory complete — {len(all_bots)} agent(s) across {len(envs)} environment(s)")
    return all_bots
