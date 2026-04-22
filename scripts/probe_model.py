"""
scripts/probe_model.py — Probe the Inventory API and CS API for a specific bot
and dump the full raw response so we can identify the correct model-version field.

Run from repo root:
    python scripts/probe_model.py

Uses the same MSAL token cache as the agent (no interactive login needed if
the agent has authenticated at least once).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

import requests
from agent.auth import get_eval_token
from agent.dataverse import INVENTORY_URL, CS_API_BASE, PP_API_VER, _model_from_properties

SEP = "─" * 72


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def load_cfg(path="config.json") -> dict:
    return json.loads(open(path).read())


def probe_inventory(env_id: str, token: str) -> list[dict]:
    print(f"\n{SEP}")
    print("INVENTORY API — all bots in environment")
    print(SEP)
    r = requests.post(
        INVENTORY_URL,
        params={"api-version": PP_API_VER},
        headers=_headers(token),
        json={
            "TableName": "PowerPlatformResources",
            "Clauses": [
                {"$type": "where", "FieldName": "type",
                 "Operator": "==", "Values": ["'microsoft.copilotstudio/agents'"]},
                {"$type": "where", "FieldName": "properties.environmentId",
                 "Operator": "==", "Values": [f"'{env_id.lower()}'"]}
            ]
        },
        timeout=20,
    )
    print(f"HTTP {r.status_code}")
    if r.status_code != 200:
        print("ERROR:", r.text[:400])
        return []

    data = r.json().get("data", [])
    print(f"Total bots returned: {len(data)}\n")

    for item in data:
        p    = item.get("properties", {})
        name = p.get("displayName", item.get("name", "?"))
        mv   = _model_from_properties(p)
        print(f"  Bot: {name}")
        print(f"  ID : {item.get('name', '?')}")
        print(f"  model (extracted): {mv}")
        print(f"  property keys    : {sorted(p.keys())}")

        # Show aISettings / aiSettings / aisettings if present
        for key in ("aISettings", "aiSettings", "aisettings", "gPTSettings",
                    "publishedConfiguration", "modelSettings", "aiConfiguration"):
            val = p.get(key)
            if val is not None:
                print(f"  [{key}]: {json.dumps(val)[:300]}")

        print()

    return data


def probe_cs_api(env_id: str, bot_id: str, token: str):
    print(f"{SEP}")
    print(f"CS BOT DETAIL API — bot {bot_id}")
    print(SEP)
    url = f"{CS_API_BASE}/environments/{env_id}/bots/{bot_id}?api-version={PP_API_VER}"
    print(f"GET {url}\n")
    r = requests.get(url, headers=_headers(token), timeout=15)
    print(f"HTTP {r.status_code}")
    if not r.ok:
        print("ERROR:", r.text[:400])
        return

    body  = r.json()
    props = body.get("properties", body)
    mv    = _model_from_properties(props if isinstance(props, dict) else body)
    print(f"model (extracted): {mv}")

    if isinstance(props, dict):
        print(f"property keys    : {sorted(props.keys())}")
        for key in ("aISettings", "aiSettings", "aisettings", "gPTSettings",
                    "publishedConfiguration", "modelSettings", "aiConfiguration"):
            val = props.get(key)
            if val is not None:
                print(f"[{key}]: {json.dumps(val)[:400]}")

    print("\nFULL RESPONSE (first 3000 chars):")
    print(json.dumps(body, indent=2)[:3000])


def main():
    cfg = load_cfg()

    print("Loading eval token (uses cached MSAL token — no browser needed)...")
    try:
        token = get_eval_token(cfg)
    except Exception as e:
        print(f"ERROR getting token: {e}")
        sys.exit(1)
    print("Token OK\n")

    for env in cfg.get("environments", []):
        env_id   = env.get("environmentId", "")
        env_name = env.get("name", env_id)
        if not env_id:
            continue

        print(f"\n{'═' * 72}")
        print(f"ENVIRONMENT: {env_name}  ({env_id})")
        print(f"{'═' * 72}")

        data = probe_inventory(env_id, token)

        # Probe CS API for every bot that came back "unknown" from Inventory
        for item in data:
            p    = item.get("properties", {})
            bot_id = item.get("name", "")
            mv     = _model_from_properties(p)
            if mv == "unknown" and bot_id:
                probe_cs_api(env_id, bot_id, token)


if __name__ == "__main__":
    main()
