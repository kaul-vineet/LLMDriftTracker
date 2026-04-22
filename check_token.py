"""Confirm env filter works with the plain GUID from inventory response."""
import json, base64, os, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv()
import msal, requests

cfg        = json.load(open("config.json"))
CLIENT_ID  = cfg["eval_app_client_id"]
TENANT_ID  = cfg["eval_app_tenant_id"]
CACHE_FILE = cfg.get("token_cache_file", "msal_token_cache.json")

def get_token():
    cache = msal.SerializableTokenCache()
    if os.path.exists(CACHE_FILE):
        cache.deserialize(open(CACHE_FILE).read())
    app  = msal.PublicClientApplication(CLIENT_ID,
           authority=f"https://login.microsoftonline.com/{TENANT_ID}",
           token_cache=cache)
    accs = app.get_accounts()
    if not accs: return None
    r = app.acquire_token_silent(["https://api.powerplatform.com/.default"], account=accs[0])
    return r.get("access_token") if r else None

tok = get_token()

# Step 1: get all agents, collect unique environmentIds from response
r = requests.post(
    "https://api.powerplatform.com/resourcequery/resources/query",
    params={"api-version": "2024-10-01"},
    headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
    json={"TableName": "PowerPlatformResources",
          "Clauses": [{"$type": "where", "FieldName": "type",
                       "Operator": "==", "Values": ["'microsoft.copilotstudio/agents'"]}]},
    timeout=15,
)
data = r.json().get("data", [])
print(f"All agents: {len(data)}")

env_ids = sorted(set(a.get("properties", {}).get("environmentId", "") for a in data))
print(f"Unique environmentIds in response: {env_ids}")

# Step 2: filter by each env_id found
for env_id in env_ids:
    r2 = requests.post(
        "https://api.powerplatform.com/resourcequery/resources/query",
        params={"api-version": "2024-10-01"},
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        json={"TableName": "PowerPlatformResources",
              "Clauses": [{"$type": "where", "FieldName": "type",
                           "Operator": "==", "Values": ["'microsoft.copilotstudio/agents'"]},
                          {"$type": "where", "FieldName": "properties.environmentId",
                           "Operator": "==", "Values": [f"'{env_id}'"]}]},
        timeout=15,
    )
    d2 = r2.json()
    agents = d2.get("data", [])
    print(f"\nEnv {env_id}: HTTP {r2.status_code}, {d2.get('totalRecords')} agents")
    for a in agents:
        p = a.get("properties", {})
        print(f"  - {p.get('displayName')} | schemaName={p.get('schemaName')} | id={a.get('name')}")
