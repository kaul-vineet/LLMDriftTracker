"""
agent/eval_client.py — Copilot Studio Eval API wrapper.

Two-phase concurrent execution:
  trigger_all_evals()  — Phase 1: fire every test-set run for every bot at once
  poll_all_runs()      — Phase 2: single-threaded round-robin status checks
                         (I/O-bound; no threads needed)

run_eval_for_bot() is kept for single-bot interactive use (wizard, ad-hoc).
"""
import time
import requests
from .auth import get_eval_token, get_eval_token_agent, AuthError
from . import logger as logger_mod
from . import lore

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
             timeout_s: int = 1200, interval_s: int = 20) -> dict:
    url      = _eval_url(pp_env_id, bot_id, f"testruns/{run_id}")
    start    = time.time()
    deadline = start + timeout_s
    while time.time() < deadline:
        r = requests.get(url, headers=_headers(token), timeout=15)
        r.raise_for_status()
        data    = r.json()
        state   = data.get("state", "").lower()
        elapsed = int(time.time() - start)
        total   = data.get("totalTestCases", 0)
        lore.eval_polling(run_id, state, elapsed, timeout_s, total)
        if state in ("completed", "failed", "cancelled"):
            lore.eval_poll_done()
            return data
        time.sleep(interval_s)
    lore.eval_poll_done()
    raise TimeoutError(f"Eval run {run_id} did not complete within {timeout_s}s")


def get_historical_runs(pp_env_id: str, bot_id: str, token: str, n: int = 5) -> list[dict]:
    url = _eval_url(pp_env_id, bot_id, "testruns")
    r = requests.get(url, headers=_headers(token), timeout=15)
    r.raise_for_status()
    runs = r.json().get("value", [])
    return sorted(runs, key=lambda x: x.get("startTime", ""), reverse=True)[:n]


def _infer_metric_type(result: dict) -> str:
    """First non-empty metric type found; assumes all test cases in a set share the same type."""
    for case in (result.get("testCasesResults") or []):
        for m in case.get("metricsResults", []):
            t = m.get("type", "").strip()
            if t:
                return t
    return "Unknown"


def trigger_all_evals(bots_to_eval: list[dict], cfg: dict) -> list[dict]:
    """
    Phase 1 — trigger ALL active test sets for ALL bots in one pass.
    Returns a pool list: [{"run_id", "bot", "display_name"}, ...]
    Individual trigger failures are logged and skipped; the pool only contains
    runs that were successfully started.
    """
    log   = logger_mod.get()
    token = get_eval_token_agent(cfg)
    pool: list[dict] = []

    for bot in bots_to_eval:
        pp_env_id = bot["ppEnvId"]
        bot_id    = bot["botId"]
        try:
            test_sets = get_test_sets(pp_env_id, bot_id, token)
        except Exception as e:
            lore.eval_error(bot["name"], e)
            log.error(f"Could not load test sets for {bot['name']}: {e}")
            continue

        active = [s for s in test_sets if s.get("state") == "Active"]
        if not active:
            lore.eval_no_testsets(bot["name"])
            log.warning(f"No active test sets found for {bot['name']} — skipping eval")
            continue

        for ts in active:
            display_name = ts.get("displayName", ts["id"])
            lore.eval_start(bot["name"], display_name)
            try:
                run_id = trigger_run(pp_env_id, bot_id, ts["id"], token)
                log.info(f"Eval started for {bot['name']} [{display_name}] — run ID: {run_id[:8]}")
                pool.append({"run_id": run_id, "bot": bot, "display_name": display_name})
            except requests.HTTPError as he:
                body = (he.response.text if he.response is not None else "").lower()
                if he.response is not None and (
                    he.response.status_code == 429
                    or any(k in body for k in ("quota", "throttl", "daily", "limit"))
                ):
                    log.warning(f"Daily eval limit hit for {bot['name']} [{display_name}] "
                                f"(HTTP {he.response.status_code}) — try again tomorrow")
                else:
                    lore.eval_error(bot["name"], he)
                    log.error(f"Could not start eval for {bot['name']} [{display_name}]: {he}")
            except Exception as e:
                lore.eval_error(bot["name"], e)
                log.error(f"Could not start eval for {bot['name']} [{display_name}]: {e}")

    return pool


def _write_progress(store_dir: str | None, bot_id: str, bot_name: str,
                    test_set: str, state: str, total: int, done_cases: int,
                    elapsed: int, sets_done: int, sets_total: int):
    if not store_dir:
        return
    import json as _j, os as _os
    path = _os.path.join(store_dir, "agent", f"eval_progress_{bot_id}.json")
    try:
        _os.makedirs(_os.path.dirname(path), exist_ok=True)
        open(path, "w").write(_j.dumps({
            "botId":       bot_id,
            "botName":     bot_name,
            "testSetName": test_set,
            "state":       state,
            "totalCases":  total,
            "doneCases":   done_cases,
            "elapsedSecs": elapsed,
            "setsDone":    sets_done,
            "setsTotal":   sets_total,
        }))
    except Exception:
        pass


def _clear_progress(store_dir: str | None, bot_id: str):
    if not store_dir:
        return
    import os as _os
    try:
        _os.remove(_os.path.join(store_dir, "agent", f"eval_progress_{bot_id}.json"))
    except Exception:
        pass


def poll_all_runs(pool: list[dict], cfg: dict,
                  timeout_s: int = 1200, interval_s: int = 20,
                  store_dir: str | None = None) -> dict[str, dict[str, dict]]:
    """
    Phase 2 — round-robin poll every run_id until terminal state or timeout.
    Single-threaded: each sweep checks all pending runs (fast HTTP GETs), then
    sleeps once for the full interval.  No threads needed for I/O-bound polling.

    Returns dict[bot_id -> dict[metric_type -> full_run_result]].
    """
    log       = logger_mod.get()
    remaining = list(pool)
    completed: dict[str, list[tuple[str, dict]]] = {}   # bot_id -> [(display_name, result)]
    start     = time.time()
    deadline  = start + timeout_s

    # Pre-compute how many test sets each bot has so we can show X/N progress
    sets_total_by_bot: dict[str, int] = {}
    for ctx in pool:
        bid = ctx["bot"]["botId"]
        sets_total_by_bot[bid] = sets_total_by_bot.get(bid, 0) + 1

    while remaining and time.time() < deadline:
        still_pending: list[dict] = []
        token = get_eval_token_agent(cfg)   # MSAL returns cached token; refresh ensures no mid-run expiry

        for ctx in remaining:
            run_id    = ctx["run_id"]
            bot       = ctx["bot"]
            pp_env_id = bot["ppEnvId"]
            bot_id    = bot["botId"]
            url       = _eval_url(pp_env_id, bot_id, f"testruns/{run_id}")

            try:
                r     = requests.get(url, headers=_headers(token), timeout=15)
                r.raise_for_status()
                data  = r.json()
                state = data.get("state", "").lower()
                elapsed    = int(time.time() - start)
                total      = data.get("totalTestCases", 0)
                done_cases = len(data.get("testCasesResults") or [])
                sets_done  = len(completed.get(bot_id, []))
                sets_total = sets_total_by_bot.get(bot_id, 1)
                lore.eval_polling(run_id, state, elapsed, timeout_s, total)
                log.info(f"Waiting for eval result — {bot['name']} [{ctx['display_name']}]: "
                         f"{state}, {elapsed}s elapsed, {total} case(s)")
                _write_progress(store_dir, bot_id, bot["name"], ctx["display_name"],
                                state, total, done_cases, elapsed, sets_done, sets_total)
                if state in ("completed", "failed", "cancelled"):
                    lore.eval_poll_done()
                    log.info(f"Eval {state} for {bot['name']} — run {run_id[:8]}")
                    completed.setdefault(bot_id, []).append((ctx["display_name"], data))
                    _write_progress(store_dir, bot_id, bot["name"], ctx["display_name"],
                                    state, total, total, elapsed,
                                    len(completed[bot_id]), sets_total)
                else:
                    still_pending.append(ctx)
            except Exception as e:
                lore.eval_error(bot["name"], e)
                log.error(f"Error checking eval status for {bot['name']}: {e}")
                still_pending.append(ctx)   # retry next sweep

        remaining = still_pending
        if remaining:
            time.sleep(interval_s)

    # Clear progress files for all bots now that polling is done
    for bid in sets_total_by_bot:
        _clear_progress(store_dir, bid)

    for ctx in remaining:
        lore.eval_error(ctx["bot"]["name"],
                        TimeoutError(f"run {ctx['run_id']} did not complete within {timeout_s}s"))

    by_bot: dict[str, dict[str, dict]] = {}
    for bot_id, runs in completed.items():
        by_type: dict[str, dict] = {}
        for display_name, result in runs:
            mt = _infer_metric_type(result)
            if mt in by_type:
                mt = f"{mt}_{display_name}"
            by_type[mt] = result
        by_bot[bot_id] = by_type

    return by_bot


def probe_test_sets(pp_env_id: str, bot_id: str, cfg: dict) -> dict:
    """Connectivity probe — list test sets and return raw response. For diagnostics."""
    try:
        token     = get_eval_token_agent(cfg)
        test_sets = get_test_sets(pp_env_id, bot_id, token)
        active    = [s for s in test_sets if s.get("state") == "Active"]
        return {
            "ok":          True,
            "total":       len(test_sets),
            "active":      len(active),
            "test_sets":   [{"id": s["id"], "displayName": s.get("displayName", ""), "state": s.get("state")}
                            for s in test_sets],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def run_eval_for_bot(bot: dict, cfg: dict) -> dict[str, dict] | None:
    """
    Run ALL active test sets for a bot.
    Returns dict[metric_type -> full_run_result] or None if no active test sets found.
    Each test set is run sequentially. Individual failures are logged but don't abort others.
    """
    token     = get_eval_token_agent(cfg)
    pp_env_id = bot["ppEnvId"]
    bot_id    = bot["botId"]

    test_sets = get_test_sets(pp_env_id, bot_id, token)
    if not test_sets:
        lore.eval_no_testsets(bot["name"])
        return None

    active = [s for s in test_sets if s.get("state") == "Active"]
    if not active:
        lore.eval_no_testsets(bot["name"])
        return None

    results_by_type: dict[str, dict] = {}

    for test_set in active:
        test_set_id   = test_set["id"]
        display_name  = test_set.get("displayName", test_set_id)
        lore.eval_start(bot["name"], display_name)

        try:
            run_id = trigger_run(pp_env_id, bot_id, test_set_id, token)
            result = poll_run(
                pp_env_id, bot_id, run_id, token,
                timeout_s=cfg.get("eval_poll_timeout_seconds", 300),
                interval_s=cfg.get("eval_poll_interval_seconds", 45),
            )
            metric_type = _infer_metric_type(result)

            # If two test sets share the same inferred metric type, suffix with display name
            if metric_type in results_by_type:
                metric_type = f"{metric_type}_{display_name}"

            results_by_type[metric_type] = result
            lore.eval_done(bot["name"])

        except Exception as e:
            lore.eval_error(bot["name"], e)
            continue

    return results_by_type if results_by_type else None
