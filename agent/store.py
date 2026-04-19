"""
agent/store.py — folder-per-trigger run storage.

Layout:
  {store_dir}/{bot_id}/
    runs/
      {trigger_guid}/
        meta.json           — trigger time, model version, metric types, analysis
        CompareMeaning.json — one file per test set result
        Groundedness.json
        ...
    tracking.json

Backward compat: old flat files ({runId}_{ts}.json) are detected and wrapped
as single-type "legacy" triggers so the dashboard can still read them.
"""
import json
import os
from datetime import datetime, timezone


def _bot_dir(store_dir: str, bot_id: str) -> str:
    path = os.path.join(store_dir, bot_id)
    os.makedirs(path, exist_ok=True)
    return path


def _load_json(path: str) -> dict:
    try:
        return json.loads(open(path).read())
    except Exception:
        return {}


# ── Tracking ──────────────────────────────────────────────────────────────────

def load_tracking(store_dir: str, bot_id: str) -> dict:
    path = os.path.join(_bot_dir(store_dir, bot_id), "tracking.json")
    if not os.path.exists(path):
        return {}
    return _load_json(path)


def save_tracking(store_dir: str, bot_id: str, model_version: str,
                  trigger_guid: str | None,
                  bot_name: str = "", env_name: str = "",
                  env_id: str = "", org_url: str = ""):
    path     = os.path.join(_bot_dir(store_dir, bot_id), "tracking.json")
    existing = _load_json(path)
    data = {
        **existing,
        "botId":            bot_id,
        "botName":          bot_name or existing.get("botName", bot_id),
        "envName":          env_name or existing.get("envName", ""),
        "envId":            env_id   or existing.get("envId",   ""),
        "orgUrl":           org_url  or existing.get("orgUrl",  ""),
        "modelVersion":     model_version,
        "lastTriggerGuid":  trigger_guid,
        "updatedAt":        datetime.now(timezone.utc).isoformat(),
    }
    open(path, "w").write(json.dumps(data, indent=2))


def model_changed(store_dir: str, bot_id: str, current_model: str) -> bool:
    return load_tracking(store_dir, bot_id).get("modelVersion") != current_model


# ── Trigger save ──────────────────────────────────────────────────────────────

def save_trigger(store_dir: str, bot_id: str, trigger_guid: str,
                 model_version: str, results_by_type: dict[str, dict],
                 analysis: str = "", bot_name: str = "",
                 env_name: str = "", env_id: str = "", org_url: str = ""):
    """
    Save all test set results for one trigger event.
    results_by_type: dict[metric_type -> full API run result]
    """
    trigger_dir = os.path.join(_bot_dir(store_dir, bot_id), "runs", trigger_guid)
    os.makedirs(trigger_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()

    meta = {
        "triggerGuid":  trigger_guid,
        "triggeredAt":  ts,
        "botId":        bot_id,
        "botName":      bot_name,
        "envId":        env_id,
        "envName":      env_name,
        "orgUrl":       org_url,
        "modelVersion": model_version,
        "metricTypes":  list(results_by_type.keys()),
        "analysis":     analysis,
    }
    open(os.path.join(trigger_dir, "meta.json"), "w").write(json.dumps(meta, indent=2))

    for metric_type, result in results_by_type.items():
        payload = {
            "metricType":  metric_type,
            "apiRunId":    result.get("id", result.get("runId", "unknown")),
            "storedAt":    ts,
            "triggerGuid": trigger_guid,
            "botId":       bot_id,
            "botName":     bot_name,
            "envId":       env_id,
            "orgUrl":      org_url,
            "results":     result,
        }
        safe_name = metric_type.replace("/", "_").replace("\\", "_")
        open(os.path.join(trigger_dir, f"{safe_name}.json"), "w").write(
            json.dumps(payload, indent=2)
        )


def update_trigger_analysis(store_dir: str, bot_id: str, trigger_guid: str, analysis: str):
    """Write analysis into meta.json after LLM call completes."""
    path = os.path.join(_bot_dir(store_dir, bot_id), "runs", trigger_guid, "meta.json")
    meta = _load_json(path)
    meta["analysis"] = analysis
    open(path, "w").write(json.dumps(meta, indent=2))


# ── Trigger load ──────────────────────────────────────────────────────────────

def _is_trigger_dir(path: str) -> bool:
    return os.path.isdir(path) and os.path.exists(os.path.join(path, "meta.json"))


def _wrap_legacy_file(path: str) -> dict | None:
    """Wrap an old flat run file as a trigger-shaped dict for backward compat."""
    data = _load_json(path)
    if not data:
        return None
    run_id      = data.get("runId", os.path.basename(path).split("_")[0])
    stored_at   = data.get("storedAt", "")
    model_ver   = data.get("modelVersion", "unknown")
    results     = data.get("results", data)
    metric_type = "CompareMeaning"
    for case in results.get("testCasesResults", []):
        for m in case.get("metricsResults", []):
            t = m.get("type", "").strip()
            if t:
                metric_type = t
                break
        break
    return {
        "triggerGuid":    run_id,
        "triggeredAt":    stored_at,
        "modelVersion":   model_ver,
        "metricTypes":    [metric_type],
        "analysis":       data.get("analysis", ""),
        "resultsByType":  {
            metric_type: {
                "metricType": metric_type,
                "apiRunId":   run_id,
                "storedAt":   stored_at,
                "results":    results,
            }
        },
        "_legacy": True,
    }


def load_trigger(store_dir: str, bot_id: str, trigger_guid: str) -> dict | None:
    trigger_dir = os.path.join(_bot_dir(store_dir, bot_id), "runs", trigger_guid)
    if not _is_trigger_dir(trigger_dir):
        return None
    meta = _load_json(os.path.join(trigger_dir, "meta.json"))
    results_by_type = {}
    for fname in sorted(os.listdir(trigger_dir)):
        if fname == "meta.json" or not fname.endswith(".json"):
            continue
        item = _load_json(os.path.join(trigger_dir, fname))
        mt   = item.get("metricType", fname.replace(".json", ""))
        results_by_type[mt] = item
    return {**meta, "resultsByType": results_by_type}


def list_triggers(store_dir: str, bot_id: str) -> list[dict]:
    """
    Return all triggers (new folder model + legacy flat files) sorted oldest→newest.
    Each entry is a full trigger dict from load_trigger / _wrap_legacy_file.
    """
    runs_dir = os.path.join(_bot_dir(store_dir, bot_id), "runs")
    if not os.path.exists(runs_dir):
        return []

    triggers = []
    for name in os.listdir(runs_dir):
        full = os.path.join(runs_dir, name)
        if _is_trigger_dir(full):
            t = load_trigger(store_dir, bot_id, name)
            if t:
                triggers.append(t)
        elif name.endswith(".json"):
            t = _wrap_legacy_file(full)
            if t:
                triggers.append(t)

    return sorted(triggers, key=lambda t: t.get("triggeredAt", ""))


def load_last_trigger(store_dir: str, bot_id: str) -> dict | None:
    triggers = list_triggers(store_dir, bot_id)
    return triggers[-1] if triggers else None
