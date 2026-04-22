"""
agent/events.py — append-only JSONL event log for the mission timeline.

One JSON object per line in {store_dir}/events.jsonl.
The dashboard reads this file to render the mission timeline.

Event types:
  cycle_start     — poll cycle began
  model_change    — model version shift detected for a bot
  eval_start      — eval triggered for a bot / test set
  eval_complete   — eval finished (includes pass rate + verdict)
  eval_timeout    — eval polling timed out
  eval_no_sets    — no test sets found for bot; skipped
  regression      — one or more metrics regressed
  improvement     — one or more metrics improved
  stable          — no change detected
  eval_queued     — eval queued from the dashboard Force Eval button
  force_eval      — force-eval triggered (file trigger or CLI flag)
  error           — unhandled exception during a cycle
"""
import json
import os
from datetime import datetime, timezone

_LOG_FILE = "events.jsonl"


def _log_path(store_dir: str) -> str:
    return os.path.join(store_dir, "agent", _LOG_FILE)


def _write(store_dir: str, event_type: str, bot_name: str = "", detail: str = "",
           bot_id: str = "", extra: dict | None = None):
    os.makedirs(os.path.join(store_dir, "agent"), exist_ok=True)
    record = {
        "ts":        datetime.now(timezone.utc).isoformat(),
        "event":     event_type,
        "botName":   bot_name,
        "botId":     bot_id,
        "detail":    detail,
        **(extra or {}),
    }
    with open(_log_path(store_dir), "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ── Public API ────────────────────────────────────────────────────────────────

def cycle_start(store_dir: str, forced: bool = False):
    _write(store_dir, "cycle_start",
           detail="Force eval triggered" if forced else "Scheduled poll cycle started")


def model_change(store_dir: str, bot_name: str, bot_id: str, old_ver: str, new_ver: str):
    _write(store_dir, "model_change", bot_name=bot_name, bot_id=bot_id,
           detail=f"{old_ver}  →  {new_ver}",
           extra={"oldModel": old_ver, "newModel": new_ver})


def eval_start(store_dir: str, bot_name: str, bot_id: str, test_set_count: int = 0,
               trigger_guid: str = "", env_id: str = "", model_version: str = ""):
    detail = f"Running {test_set_count} test set(s)" if test_set_count else "Eval triggered — fetching test sets"
    if model_version and model_version not in ("unknown", ""):
        detail += f"  ·  {model_version}"
    extra: dict = {}
    if trigger_guid:
        extra["triggerGuid"] = trigger_guid
    if env_id:
        extra["envId"] = env_id
    if model_version:
        extra["modelVersion"] = model_version
    _write(store_dir, "eval_start", bot_name=bot_name, bot_id=bot_id, detail=detail,
           extra=extra or None)


def eval_complete(store_dir: str, bot_name: str, bot_id: str,
                  pass_rate: float, avg_score: float, verdict: str,
                  trigger_guid: str = "", env_id: str = "", duration_secs: int | None = None,
                  model_version: str = ""):
    pct = f"{pass_rate * 100:.0f}%"
    mv_str = f"  ·  {model_version}" if model_version and model_version not in ("unknown", "") else ""
    extra: dict = {"passRate": pass_rate, "avgScore": avg_score, "verdict": verdict}
    if trigger_guid:
        extra["triggerGuid"] = trigger_guid
    if env_id:
        extra["envId"] = env_id
    if duration_secs is not None:
        extra["durationSecs"] = duration_secs
    if model_version:
        extra["modelVersion"] = model_version
    _write(store_dir, "eval_complete", bot_name=bot_name, bot_id=bot_id,
           detail=f"pass {pct}  ·  avg score {avg_score:.1f}  ·  {verdict}{mv_str}",
           extra=extra)


def eval_timeout(store_dir: str, bot_name: str, bot_id: str):
    _write(store_dir, "eval_timeout", bot_name=bot_name, bot_id=bot_id,
           detail="Eval polling timed out — check Power Platform status")


def eval_no_sets(store_dir: str, bot_name: str, bot_id: str):
    _write(store_dir, "eval_no_sets", bot_name=bot_name, bot_id=bot_id,
           detail="No test sets found — skipping eval")


def regression(store_dir: str, bot_name: str, bot_id: str, metrics: list[str],
               trigger_guid: str = "", env_id: str = "", model_version: str = ""):
    mv_str = f"  ·  {model_version}" if model_version and model_version not in ("unknown", "") else ""
    extra: dict = {"metrics": metrics}
    if trigger_guid:
        extra["triggerGuid"] = trigger_guid
    if env_id:
        extra["envId"] = env_id
    if model_version:
        extra["modelVersion"] = model_version
    _write(store_dir, "regression", bot_name=bot_name, bot_id=bot_id,
           detail=f"Regression in: {', '.join(metrics)}{mv_str}", extra=extra)


def improvement(store_dir: str, bot_name: str, bot_id: str, metrics: list[str],
                trigger_guid: str = "", env_id: str = "", model_version: str = ""):
    mv_str = f"  ·  {model_version}" if model_version and model_version not in ("unknown", "") else ""
    extra: dict = {"metrics": metrics}
    if trigger_guid:
        extra["triggerGuid"] = trigger_guid
    if env_id:
        extra["envId"] = env_id
    if model_version:
        extra["modelVersion"] = model_version
    _write(store_dir, "improvement", bot_name=bot_name, bot_id=bot_id,
           detail=f"Improved: {', '.join(metrics)}{mv_str}", extra=extra)


def stable(store_dir: str, bot_name: str, bot_id: str):
    _write(store_dir, "stable", bot_name=bot_name, bot_id=bot_id,
           detail="No change detected — all metrics stable")


def error(store_dir: str, bot_name: str, bot_id: str, err: str):
    _write(store_dir, "error", bot_name=bot_name, bot_id=bot_id,
           detail=str(err)[:200])


def eval_queued(store_dir: str, bot_name: str, bot_id: str):
    _write(store_dir, "eval_queued", bot_name=bot_name, bot_id=bot_id,
           detail="Eval queued from dashboard")


def force_eval(store_dir: str):
    _write(store_dir, "force_eval",
           detail="force_eval.trigger file detected — running eval immediately")


# ── Reader ────────────────────────────────────────────────────────────────────

def load_events(store_dir: str, limit: int = 200) -> list[dict]:
    """Return events newest-first, up to limit."""
    path = _log_path(store_dir)
    if not os.path.exists(path):
        return []
    lines = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []
    events = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return list(reversed(events[-limit:]))
