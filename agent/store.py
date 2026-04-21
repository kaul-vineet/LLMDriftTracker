"""
agent/store.py — per-run storage.

Layout:
  {store_dir}/{bot_id}/
    tracking.json                   — latest model version + last run folder
    runs/
      {timestamp}_{modelVersion}/   — one folder per eval trigger
        run.json                    — all test set results + context

Backward compat: old trigger folders ({guid}/meta.json + type files)
are detected and wrapped into the new run shape.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone


def _bot_dir(store_dir: str, bot_id: str) -> str:
    path = os.path.join(store_dir, bot_id)
    os.makedirs(path, exist_ok=True)
    return path


def _load_json(path: str) -> dict:
    """Read a JSON file. Missing → {}. Corrupt → log to stderr and return {}."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.loads(f.read())
    except json.JSONDecodeError as e:
        print(f"[store] Corrupt JSON at {path}: {e}", file=sys.stderr)
        return {}
    except OSError as e:
        print(f"[store] Cannot read {path}: {e}", file=sys.stderr)
        return {}


def _atomic_write_json(path: str, data: dict):
    """Write JSON atomically: write to .tmp then os.replace() so a partial/disk-full
    write cannot corrupt the destination file. Callers expect existing contents to
    remain intact if the write fails."""
    tmp = f"{path}.tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2))
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass  # not all platforms / filesystems support fsync
    os.replace(tmp, path)


# Characters that are invalid in Windows filenames — also stripped on POSIX for portability.
_UNSAFE_PATH_CHARS = re.compile(r'[\\/:*?"<>|\s\x00-\x1f]')


def make_run_folder_name(model_version: str) -> str:
    ts         = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    safe_model = _UNSAFE_PATH_CHARS.sub("_", model_version or "unknown")
    # Also collapse repeats and trim trailing dots/underscores (Windows treats trailing
    # dots and spaces as invalid for folder names).
    safe_model = re.sub(r"_+", "_", safe_model).strip("._") or "unknown"
    return f"{ts}_{safe_model}"


# ── Tracking ──────────────────────────────────────────────────────────────────

def load_tracking(store_dir: str, bot_id: str) -> dict:
    path = os.path.join(_bot_dir(store_dir, bot_id), "tracking.json")
    if not os.path.exists(path):
        return {}
    return _load_json(path)


def save_tracking(store_dir: str, bot_id: str, model_version: str,
                  last_run_folder: str | None,
                  bot_name: str = "", env_name: str = "",
                  env_id: str = "", org_url: str = ""):
    path     = os.path.join(_bot_dir(store_dir, bot_id), "tracking.json")
    existing = _load_json(path)
    data = {
        **existing,
        "botId":          bot_id,
        "botName":        bot_name or existing.get("botName", bot_id),
        "envName":        env_name or existing.get("envName", ""),
        "envId":          env_id   or existing.get("envId",   ""),
        "orgUrl":         org_url  or existing.get("orgUrl",  ""),
        "modelVersion":   model_version,
        "lastRunFolder":  last_run_folder,
        "updatedAt":      datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write_json(path, data)


def model_changed(store_dir: str, bot_id: str, current_model: str) -> bool:
    return load_tracking(store_dir, bot_id).get("modelVersion") != current_model


# ── Run save ──────────────────────────────────────────────────────────────────

def save_run(store_dir: str, bot_id: str, model_version: str,
             test_sets: dict[str, dict], forced: bool = False,
             folder_name: str = "",
             bot_name: str = "", env_name: str = "",
             env_id: str = "", org_url: str = "") -> str:
    """
    Save one run. Returns the folder name.
    test_sets: dict[metric_type -> {apiRunId, results}]
    """
    folder = folder_name or make_run_folder_name(model_version)
    run_dir = os.path.join(_bot_dir(store_dir, bot_id), "runs", folder)
    os.makedirs(run_dir, exist_ok=True)

    run = {
        "botId":        bot_id,
        "botName":      bot_name,
        "envId":        env_id,
        "envName":      env_name,
        "orgUrl":       org_url,
        "modelVersion": model_version,
        "triggeredAt":  datetime.now(timezone.utc).isoformat(),
        "forced":       forced,
        "testSets":     test_sets,
    }
    _atomic_write_json(os.path.join(run_dir, "run.json"), run)
    return folder


# ── Run load ──────────────────────────────────────────────────────────────────

def _is_new_run_dir(path: str) -> bool:
    return os.path.isdir(path) and os.path.exists(os.path.join(path, "run.json"))


def _is_old_trigger_dir(path: str) -> bool:
    return os.path.isdir(path) and os.path.exists(os.path.join(path, "meta.json"))


def _wrap_old_trigger(folder_path: str) -> dict | None:
    """Wrap old format (meta.json + one JSON per metric type) into the current run shape."""
    meta = _load_json(os.path.join(folder_path, "meta.json"))
    if not meta:
        return None
    test_sets = {}
    for fname in sorted(os.listdir(folder_path)):
        if fname == "meta.json" or not fname.endswith(".json"):
            continue
        item = _load_json(os.path.join(folder_path, fname))
        mt = item.get("metricType", fname.replace(".json", ""))
        test_sets[mt] = {
            "apiRunId": item.get("apiRunId", ""),
            "results":  item.get("results", {}),
        }
    return {
        "botId":        meta.get("botId", ""),
        "botName":      meta.get("botName", ""),
        "envId":        meta.get("envId", ""),
        "envName":      meta.get("envName", ""),
        "orgUrl":       meta.get("orgUrl", ""),
        "modelVersion": meta.get("modelVersion", "unknown"),
        "triggeredAt":  meta.get("triggeredAt", ""),
        "forced":       False,
        "testSets":     test_sets,
        "_legacy":      True,
        "_folder":      os.path.basename(folder_path),
    }


def load_run(store_dir: str, bot_id: str, folder_name: str) -> dict | None:
    folder_path = os.path.join(_bot_dir(store_dir, bot_id), "runs", folder_name)
    if _is_new_run_dir(folder_path):
        run = _load_json(os.path.join(folder_path, "run.json"))
        return {**run, "_folder": folder_name} if run else None
    if _is_old_trigger_dir(folder_path):
        return _wrap_old_trigger(folder_path)
    return None


def list_runs(store_dir: str, bot_id: str) -> list[dict]:
    """Return all runs sorted oldest→newest."""
    runs_dir = os.path.join(_bot_dir(store_dir, bot_id), "runs")
    if not os.path.exists(runs_dir):
        return []
    runs = []
    for name in os.listdir(runs_dir):
        run = load_run(store_dir, bot_id, name)
        if run:
            runs.append(run)
    return sorted(runs, key=lambda r: r.get("triggeredAt", ""))


def load_last_run(store_dir: str, bot_id: str) -> dict | None:
    """Return the last run using tracking.json pointer, fallback to directory scan."""
    tracking    = load_tracking(store_dir, bot_id)
    last_folder = tracking.get("lastRunFolder")
    if last_folder:
        run = load_run(store_dir, bot_id, last_folder)
        if run:
            return run
    runs = list_runs(store_dir, bot_id)
    return runs[-1] if runs else None
