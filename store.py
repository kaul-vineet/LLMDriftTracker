import json
import os
from datetime import datetime, timezone


def _bot_dir(store_dir: str, bot_id: str) -> str:
    path = os.path.join(store_dir, bot_id)
    os.makedirs(path, exist_ok=True)
    return path


def load_tracking(store_dir: str, bot_id: str) -> dict:
    path = os.path.join(_bot_dir(store_dir, bot_id), "tracking.json")
    if not os.path.exists(path):
        return {}
    return json.loads(open(path).read())


def save_tracking(store_dir: str, bot_id: str, model_version: str, run_id: str | None,
                  bot_name: str = "", env_name: str = ""):
    path     = os.path.join(_bot_dir(store_dir, bot_id), "tracking.json")
    existing = {}
    if os.path.exists(path):
        try:
            existing = json.loads(open(path).read())
        except Exception:
            pass
    data = {
        **existing,
        "botId":        bot_id,
        "botName":      bot_name or existing.get("botName", bot_id),
        "envName":      env_name or existing.get("envName", ""),
        "modelVersion": model_version,
        "lastRunId":    run_id,
        "updatedAt":    datetime.now(timezone.utc).isoformat(),
    }
    open(path, "w").write(json.dumps(data, indent=2))


def save_run(store_dir: str, bot_id: str, run_id: str, model_version: str,
             results: dict, analysis: str = ""):
    fname = f"{run_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    path  = os.path.join(_bot_dir(store_dir, bot_id), "runs", fname)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "runId":        run_id,
        "modelVersion": model_version,
        "storedAt":     datetime.now(timezone.utc).isoformat(),
        "analysis":     analysis,
        "results":      results,
    }
    open(path, "w").write(json.dumps(payload, indent=2))


def load_last_run(store_dir: str, bot_id: str) -> dict | None:
    runs_dir = os.path.join(_bot_dir(store_dir, bot_id), "runs")
    if not os.path.exists(runs_dir):
        return None
    files = sorted(os.listdir(runs_dir))
    if not files:
        return None
    return json.loads(open(os.path.join(runs_dir, files[-1])).read())


def model_changed(store_dir: str, bot_id: str, current_model: str) -> bool:
    tracking = load_tracking(store_dir, bot_id)
    return tracking.get("modelVersion") != current_model
