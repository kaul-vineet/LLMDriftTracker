import time
import requests
from .auth import get_eval_token

PP_API_BASE  = "https://api.powerplatform.com"
EVAL_API_VER = "2024-10-01"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _eval_url(pp_env_id: str, bot_id: str, path: str) -> str:
    return (f"{PP_API_BASE}/copilotstudio/environments/{pp_env_id}"
            f"/bots/{bot_id}/api/makerevaluation/{path}?api-version={EVAL_API_VER}")


def get_test_sets(pp_env_id: str, bot_id: str, token: str) -> list[dict]:
    url = _eval_url(pp_env_id, bot_id, "testsets")
    r = requests.get(url, headers=_headers(token), timeout=15)
    r.raise_for_status()
    return r.json().get("value", [])


def trigger_run(pp_env_id: str, bot_id: str, test_set_id: str, token: str) -> str:
    url = _eval_url(pp_env_id, bot_id, f"testsets/{test_set_id}/run")
    r = requests.post(url, headers=_headers(token), json={}, timeout=15)
    r.raise_for_status()
    return r.json()["runId"]


def poll_run(pp_env_id: str, bot_id: str, run_id: str, token: str,
             timeout_s: int = 300, interval_s: int = 15) -> dict:
    url = _eval_url(pp_env_id, bot_id, f"testruns/{run_id}")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.get(url, headers=_headers(token), timeout=15)
        r.raise_for_status()
        data = r.json()
        state = data.get("state", "").lower()
        processed = data.get("testCasesProcessed", 0)
        total = data.get("totalTestCases", 0)
        print(f"[eval] run {run_id[:8]}... state={state} {processed}/{total}")
        if state in ("completed", "failed", "cancelled"):
            return data
        time.sleep(interval_s)
    raise TimeoutError(f"Eval run {run_id} did not complete within {timeout_s}s")


def get_historical_runs(pp_env_id: str, bot_id: str, token: str, n: int = 5) -> list[dict]:
    url = _eval_url(pp_env_id, bot_id, "testruns")
    r = requests.get(url, headers=_headers(token), timeout=15)
    r.raise_for_status()
    runs = r.json().get("value", [])
    return sorted(runs, key=lambda x: x.get("startTime", ""), reverse=True)[:n]


def run_eval_for_bot(bot: dict, cfg: dict) -> dict | None:
    token = get_eval_token(cfg)
    pp_env_id = bot["ppEnvId"]
    bot_id    = bot["botId"]

    test_sets = get_test_sets(pp_env_id, bot_id, token)
    if not test_sets:
        print(f"[eval] {bot['name']}: no test sets — skipping")
        return None

    # Use the first active test set
    active = [s for s in test_sets if s.get("state") == "Active"]
    if not active:
        print(f"[eval] {bot['name']}: no active test sets — skipping")
        return None

    test_set_id = active[0]["id"]
    print(f"[eval] {bot['name']}: triggering run on test set {active[0].get('displayName')}")

    run_id = trigger_run(pp_env_id, bot_id, test_set_id, token)
    result = poll_run(
        pp_env_id, bot_id, run_id, token,
        timeout_s=cfg.get("eval_poll_timeout_seconds", 300),
        interval_s=cfg.get("eval_poll_interval_seconds", 15)
    )
    return result
