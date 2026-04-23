"""
agent/main.py — autonomous poll loop + force-eval trigger.

Run modes:
  python -m agent.main               — autonomous polling on schedule
  python -m agent.main --force-eval  — one-shot force eval for all bots

File-based trigger: dashboard writes {store_dir}/force_eval.trigger.
The poll loop checks for this file each cycle, deletes it, and runs immediately.
"""
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

# Force UTF-8 stdout/stderr so emoji in lore.py don't crash on Windows CP1252 terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import psutil

from . import dataverse
from . import eval_client
from . import events as ev
from . import logger as logger_mod
from . import lore
from . import notifier
from . import reasoning
from . import report
from . import store
from .auth import AuthError


def _auth_error_path(store_dir: str) -> str:
    return os.path.join(_agent_dir(store_dir), "auth_error.json")


def _write_auth_error(store_dir: str, msg: str):
    path = _auth_error_path(store_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(json.dumps({
        "error": msg,
        "ts":    datetime.now(timezone.utc).isoformat(),
    }))


def _clear_auth_error(store_dir: str):
    try:
        os.remove(_auth_error_path(store_dir))
    except FileNotFoundError:
        pass


def _shutdown_path(store_dir: str) -> str:
    return os.path.join(_agent_dir(store_dir), "shutdown.trigger")


def _cleanup_all_locks(store_dir: str):
    """Remove all eval lock and progress files left by mid-flight evals."""
    adir = _agent_dir(store_dir)
    if not os.path.exists(adir):
        return
    for fname in os.listdir(adir):
        if (fname.startswith("eval_active_") and fname.endswith(".lock")) or \
           (fname.startswith("eval_progress_") and fname.endswith(".json")):
            try:
                os.remove(os.path.join(adir, fname))
            except Exception:
                pass


def _fatal_auth_error(store_dir: str, msg: str, log):
    log.critical(f"AUTH ERROR — agent shutting down: {msg}")
    _write_auth_error(store_dir, msg)
    ev.agent_stop(store_dir)
    _cleanup_all_locks(store_dir)
    _remove_pid(store_dir)
    os._exit(1)   # terminate all threads immediately


def load_cfg(path: str = None) -> dict:
    path = path or os.environ.get("CONFIG_PATH", "config.json")
    config_dir    = os.path.dirname(os.path.abspath(path))
    defaults_path = os.path.join(config_dir, "defaults.json")
    defaults: dict = {}
    try:
        with open(defaults_path, encoding="utf-8") as f:
            defaults = json.loads(f.read())
    except Exception:
        pass
    with open(path, encoding="utf-8") as f:
        user_cfg = json.loads(f.read())
    cfg = {**defaults, **user_cfg}
    cfg.setdefault("llm", {})
    cfg.setdefault("smtp", {})
    return cfg


def _agent_dir(store_dir: str) -> str:
    return os.path.join(store_dir, "agent")


def _check_file_trigger(store_dir: str) -> bool:
    """Return True and delete the global force_eval.trigger if it exists.
    Returns False if delete fails — otherwise the next eval loop iteration would
    see the file again and re-trigger in an infinite loop."""
    path = os.path.join(_agent_dir(store_dir), "force_eval.trigger")
    if not os.path.exists(path):
        return False
    try:
        os.remove(path)
        return True
    except Exception as e:
        lore.eval_error("trigger", e)
        return False


def _check_bot_trigger(store_dir: str, bot_id: str) -> bool:
    """Return True and delete a per-bot force_eval trigger if it exists.
    Returns False if delete fails — see _check_file_trigger."""
    path = os.path.join(_agent_dir(store_dir), f"force_eval_{bot_id}.trigger")
    if not os.path.exists(path):
        return False
    try:
        os.remove(path)
        return True
    except Exception as e:
        lore.eval_error("trigger", e)
        return False


def _has_pending_triggers(store_dir: str) -> bool:
    """Return True if any per-bot trigger file is waiting to be consumed."""
    adir = _agent_dir(store_dir)
    if not os.path.exists(adir):
        return False
    return any(
        f.startswith("force_eval_") and f.endswith(".trigger")
        for f in os.listdir(adir)
    )


def _clear_stale_triggers(store_dir: str):
    """Delete any leftover trigger or lock files from a previous stopped session."""
    adir = _agent_dir(store_dir)
    if not os.path.exists(adir):
        return
    for fname in os.listdir(adir):
        if (
            fname == "force_eval.trigger"
            or (fname.startswith("force_eval_") and fname.endswith(".trigger"))
            or (fname.startswith("eval_active_") and fname.endswith(".lock"))
            or (fname.startswith("eval_progress_") and fname.endswith(".json"))
        ):
            try:
                os.remove(os.path.join(adir, fname))
            except Exception:
                pass


def _build_bot_result(bot_name, old_ver, curr_ver, run_folder,
                      test_sets, prev_run, cfg, instructions="") -> dict:
    curr_metrics    = reasoning.extract_metrics_for_report(test_sets)
    prev_metrics    = (
        reasoning.extract_metrics_for_report(prev_run.get("testSets", {}))
        if prev_run else {}
    )
    classifications = reasoning.classify_run(prev_metrics, curr_metrics)
    analysis        = reasoning.analyse_variation(
        bot_name, old_ver, curr_ver, test_sets, prev_run, cfg, instructions
    )
    return {
        "botName":         bot_name,
        "oldModel":        old_ver,
        "newModel":        curr_ver,
        "runFolder":       run_folder,
        "currMetrics":     curr_metrics,
        "prevMetrics":     prev_metrics,
        "classifications": classifications,
        "verdictSummary":  reasoning.verdict_summary(classifications),
        "analysis":        analysis,
        "prevRun":         prev_run,
        "currRun":         {"testSets": test_sets},
    }


def _prune_reports(store_dir: str, keep: int):
    """Delete oldest report_{timestamp}.html files beyond the keep limit."""
    import glob as _glob
    reports = sorted(_glob.glob(os.path.join(store_dir, "report_*.html")))
    for path in reports[:-keep] if len(reports) > keep else []:
        try:
            os.remove(path)
        except Exception:
            pass


def _save_and_notify(bot_results, store_dir, cfg):
    html        = report.generate_report(bot_results)
    report_path = os.path.join(
        store_dir,
        f"report_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.html"
    )
    os.makedirs(store_dir, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    _prune_reports(store_dir, keep=cfg.get("max_runs_per_bot"))
    lore.report_saved(report_path)
    notifier.send_report(html, cfg)
    lore.cycle_complete(len(bot_results))


def run_cycle(cfg: dict, force: bool = False):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lore.cycle_start(ts)

    store_dir = cfg.get("store_dir", "data")
    log       = logger_mod.get()
    ev.cycle_start(store_dir, forced=force)

    # Consume ALL trigger files FIRST — before any network calls — so the
    # dashboard never gets stuck on "queued" regardless of what happens next.
    triggered_ids: set[str] = set()
    triggered_sources: dict[str, str] = {}   # bot_id -> "user" | "agent"
    adir = _agent_dir(store_dir)
    if os.path.exists(adir):
        for fname in os.listdir(adir):
            if fname.startswith("force_eval_") and fname.endswith(".trigger"):
                bot_id_from_file = fname[len("force_eval_"):-len(".trigger")]
                triggered_ids.add(bot_id_from_file)
                try:
                    content = open(os.path.join(adir, fname), encoding="utf-8").read().strip()
                    triggered_sources[bot_id_from_file] = content if content in ("user", "agent") else "agent"
                    os.remove(os.path.join(adir, fname))
                except Exception:
                    triggered_sources[bot_id_from_file] = "agent"
    if triggered_ids:
        log.info(f"Evaluation requested — picked up pending eval for {len(triggered_ids)} bot(s)")

    try:
        bots = dataverse.list_all_bots(cfg)
        log.info(f"Agent inventory loaded — {len(bots)} agent(s) found")
    except Exception as e:
        log.error(f"Could not load agent inventory from Dataverse — {e}")
        lore.eval_error("list_bots", e)
        bots = []

    # Any triggered bot not found in the current inventory was likely deleted or deactivated.
    found_ids = {b["botId"] for b in bots}
    for tid in triggered_ids:
        if tid not in found_ids:
            t    = store.load_tracking(store_dir, tid)
            name = t.get("botName", tid)
            log.warning(f"Bot '{name}' ({tid[:8]}...) was queued for eval but is not in the current "
                        f"agent inventory — it may have been deleted or deactivated. Skipping.")
            lore.eval_error(name, Exception("Bot not found in inventory — possibly deleted or deactivated"))

    if not bots and not triggered_ids:
        log.info("No agents to process this cycle")
        return

    # ── Phase 0: classify every bot ─────────────────────────────────────────
    bots_to_eval: list[dict]  = []
    bot_ctx: dict[str, dict]  = {}

    for bot in bots:
        bot_id     = bot["botId"]
        bot_name   = bot["name"]
        curr_ver   = bot["modelVersion"]
        bot_forced = bot_id in triggered_ids

        # If model version is unavailable and this is not a manual force, skip — we can't compare
        if curr_ver == "unknown" and not force and not bot_forced:
            log.info(f"Model version unavailable for {bot_name} — skipping eval until Dataverse token is available")
            continue

        # Skip eval: not globally forced, not per-bot forced, and model version unchanged
        if not force and not bot_forced and not store.model_changed(store_dir, bot_id, curr_ver):
            lore.no_change(bot_name)
            ev.stable(store_dir, bot_name, bot_id)
            continue

        tracking = store.load_tracking(store_dir, bot_id)
        old_ver  = tracking.get("modelVersion", curr_ver if (force or bot_forced) else "unknown")
        if not force and not bot_forced:
            lore.model_changed(bot_name, old_ver, curr_ver)
            ev.model_change(store_dir, bot_name, bot_id, old_ver, curr_ver)

        # Guard against Copilot Studio's ~20 eval/day cap per bot
        daily_count = store.daily_eval_count(store_dir, bot_id)
        if daily_count >= 20:
            log.warning(f"Daily eval limit reached for {bot_name} ({daily_count} evals today) — skipping until tomorrow")
            continue
        if daily_count >= 18:
            log.warning(f"Approaching daily eval limit for {bot_name} — {daily_count} of ~20 evals used today")

        run_folder    = store.make_run_folder_name(curr_ver)
        eval_start_ts = datetime.now(timezone.utc)

        ev.eval_start(store_dir, bot_name, bot_id, 0,
                      trigger_guid=run_folder, env_id=bot.get("ppEnvId", ""),
                      model_version=curr_ver)

        bot_ctx[bot_id] = {
            "bot":            bot,
            "old_ver":        old_ver,
            "curr_ver":       curr_ver,
            "run_folder":     run_folder,
            "eval_start_ts":  eval_start_ts,
            "bot_forced":     bot_forced,
            "trigger_source": triggered_sources.get(bot_id, "agent") if bot_forced else ("agent" if force else ""),
        }
        bots_to_eval.append(bot)

    if not bots_to_eval:
        lore.cycle_idle()
        return

    # Write a lock file per bot so the dashboard knows an eval is actively running.
    # Deleted in Phase 3 (inside finally) so it disappears even if processing fails.
    for bot in bots_to_eval:
        lock_path = os.path.join(_agent_dir(store_dir), f"eval_active_{bot['botId']}.lock")
        try:
            with open(lock_path, "w", encoding="utf-8") as f:
                import json as _j
                f.write(_j.dumps({
                    "startedAt":    datetime.now(timezone.utc).isoformat(),
                    "modelVersion": bot_ctx[bot["botId"]]["curr_ver"],
                }))
        except Exception:
            pass

    # ── Phase 1: trigger all test sets for all bots at once ─────────────────
    try:
        pool = eval_client.trigger_all_evals(bots_to_eval, cfg)
    except Exception as e:
        lore.eval_error("trigger phase", e)
        pool = []   # fall through to Phase 3 so lock files are always cleaned up

    # ── Phase 2: single-threaded round-robin poll until all done ────────────
    results_by_bot = eval_client.poll_all_runs(
        pool, cfg,
        timeout_s=cfg.get("eval_poll_timeout_seconds"),
        interval_s=cfg.get("eval_poll_interval_seconds"),
        store_dir=store_dir,
    )

    # ── Phase 3: process & persist results per bot ──────────────────────────
    bot_results: list[dict] = []

    for bot in bots_to_eval:
        bot_id   = bot["botId"]
        bot_name = bot["name"]
        ctx      = bot_ctx[bot_id]
        curr_ver = ctx["curr_ver"]
        old_ver  = ctx["old_ver"]
        run_folder    = ctx["run_folder"]
        eval_start_ts = ctx["eval_start_ts"]
        env_id   = bot.get("ppEnvId", "")
        org_url  = bot.get("orgUrl", "")

        lock_path = os.path.join(_agent_dir(store_dir), f"eval_active_{bot_id}.lock")
        try:
            results_by_type = results_by_bot.get(bot_id)
            if not results_by_type:
                ev.eval_no_sets(store_dir, bot_name, bot_id)
                store.save_tracking(store_dir, bot_id, curr_ver, None,
                                    bot_name=bot_name, env_name=bot.get("envName", ""),
                                    env_id=env_id, org_url=org_url)
                continue

            # Reshape poll results into the testSets format expected by store/reasoning modules
            test_sets = {
                mt: {
                    "apiRunId": result.get("id", result.get("runId", "")),
                    "results":  result,
                }
                for mt, result in results_by_type.items()
            }

            prev_run   = store.load_last_run(store_dir, bot_id)
            run_folder = store.save_run(
                store_dir, bot_id, curr_ver, test_sets,
                forced=(force or ctx["bot_forced"]), folder_name=run_folder,
                bot_name=bot_name, env_name=bot.get("envName", ""),
                env_id=env_id, org_url=org_url,
                trigger_source=ctx["trigger_source"],
            )
            store.prune_runs(store_dir, bot_id,
                             keep=cfg.get("max_runs_per_bot"))

            br = _build_bot_result(bot_name, old_ver, curr_ver, run_folder,
                                   test_sets, prev_run, cfg,
                                   instructions=bot.get("instructions", ""))

            # Persist the LLM analysis into the current run's run.json so the dashboard
            # can display it immediately without requiring the user to click "Ask āshokā".
            # The analysis is keyed by the baseline (previous) run folder name, matching
            # the schema used by the dashboard's patch_run calls.
            _analysis    = br.get("analysis", "")
            _prev_folder = prev_run.get("_folder", "") if prev_run else ""
            if _analysis and _prev_folder:
                store.patch_run(store_dir, bot_id, run_folder,
                                {"analyses": {_prev_folder: _analysis}})

            cls         = br.get("classifications", [])
            reg_metrics = [c["key"] for c in cls if c["verdict"] == "REGRESSED"]
            imp_metrics = [c["key"] for c in cls if c["verdict"] == "IMPROVED"]
            curr_m      = br.get("currMetrics", {})
            # Derive pass rate / avg score from whichever metric types the bot emits,
            # instead of assuming CompareMeaning. Average across all *.passRate and
            # *.score keys so other evaluators (ResponseRelevance, GroundedResponse,
            # etc.) surface real numbers in the event log.
            pass_rates = [v for k, v in curr_m.items() if k.endswith(".passRate") and isinstance(v, (int, float))]
            scores     = [v for k, v in curr_m.items() if k.endswith(".score")    and isinstance(v, (int, float))]
            pass_rate  = (sum(pass_rates) / len(pass_rates)) if pass_rates else 0.0
            avg_score  = (sum(scores)     / len(scores))     if scores     else 0.0
            verdict     = br.get("verdictSummary", "STABLE")
            duration_s  = int((datetime.now(timezone.utc) - eval_start_ts).total_seconds())

            ev.eval_complete(store_dir, bot_name, bot_id, pass_rate, avg_score, verdict,
                             trigger_guid=run_folder, env_id=env_id, duration_secs=duration_s,
                             model_version=curr_ver)
            if reg_metrics:
                ev.regression(store_dir, bot_name, bot_id, reg_metrics,
                              trigger_guid=run_folder, env_id=env_id, model_version=curr_ver)
            elif imp_metrics:
                ev.improvement(store_dir, bot_name, bot_id, imp_metrics,
                               trigger_guid=run_folder, env_id=env_id, model_version=curr_ver)

            store.save_tracking(store_dir, bot_id, curr_ver, run_folder,
                                bot_name=bot_name, env_name=bot.get("envName", ""),
                                env_id=env_id, org_url=org_url)
            store.increment_daily_eval_count(store_dir, bot_id)
            bot_results.append(br)
            lore.eval_done(bot_name)

        except Exception as e:
            lore.eval_error(bot_name, e)
            ev.error(store_dir, bot_name, bot_id, str(e))

        finally:
            # Lock file removed here so the dashboard button re-enables only after
            # this bot's full Phase 3 processing (not just trigger consumption).
            try:
                os.remove(lock_path)
            except Exception:
                pass

    if not bot_results:
        lore.cycle_idle()
        return

    _save_and_notify(bot_results, store_dir, cfg)


def _poll_trigger_path(store_dir: str) -> str:
    return os.path.join(_agent_dir(store_dir), "force_poll.trigger")


def _consume_poll_trigger(store_dir: str) -> bool:
    path = _poll_trigger_path(store_dir)
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass
        return True
    return False


def _interruptible_sleep(interval_s: int, store_dir: str):
    """Sleep for interval_s but wake immediately if force_poll.trigger or shutdown.trigger appears."""
    deadline = time.time() + interval_s
    while time.time() < deadline:
        if os.path.exists(_poll_trigger_path(store_dir)):
            break
        if os.path.exists(_shutdown_path(store_dir)):
            raise SystemExit(0)
        time.sleep(2)


def _watch_loop(cfg: dict):
    """Watcher thread — polls every poll_interval_minutes and writes a
    trigger file the moment a model version change is detected. Never runs evals."""
    store_dir  = cfg.get("store_dir", "data")
    # Clamp to a safe minimum — a 0/negative value would spin the watcher thread
    # at 100% CPU and hammer the Dataverse API.
    _poll_min  = int(cfg.get("poll_interval_minutes") or 1)
    interval_s = max(30, _poll_min * 60)
    log        = logger_mod.get()
    proc       = psutil.Process()
    mem_base   = proc.memory_info().rss / 1024 / 1024
    sweep      = 0

    while True:
        if os.path.exists(_shutdown_path(store_dir)):
            raise SystemExit(0)
        forced_poll = _consume_poll_trigger(store_dir)
        if forced_poll:
            log.info("Force poll requested — running watcher cycle immediately")
        try:
            bots = dataverse.list_all_bots(cfg)
            ev.scan_start(store_dir, len(bots))
            for bot in bots:
                bot_id   = bot["botId"]
                bot_name = bot["name"]
                curr_ver = bot["modelVersion"]
                trigger_path = os.path.join(_agent_dir(store_dir), f"force_eval_{bot_id}.trigger")
                lock_path    = os.path.join(_agent_dir(store_dir), f"eval_active_{bot_id}.lock")
                # Already queued or running — skip to avoid duplicate triggers
                if os.path.exists(trigger_path) or os.path.exists(lock_path):
                    continue
                # If model version is unavailable (no Dataverse token cached), skip change detection
                if curr_ver == "unknown":
                    log.info(f"Model version unavailable for {bot_name} — skipping change detection this sweep")
                    continue
                if store.model_changed(store_dir, bot_id, curr_ver):
                    tracking = store.load_tracking(store_dir, bot_id)
                    old_ver  = tracking.get("modelVersion", "unknown")
                    lore.model_changed(bot_name, old_ver, curr_ver)
                    ev.model_change(store_dir, bot_name, bot_id, old_ver, curr_ver)
                    ev.agent_eval(store_dir, bot_name, bot_id, old_ver, curr_ver)
                    with open(trigger_path, "w", encoding="utf-8") as f:
                        f.write("agent")
                    log.info(f"Model change detected for {bot_name}: {old_ver} → {curr_ver}")

            sweep += 1
            # Heartbeat every sweep so Logs tab shows the agent is alive
            # Bots with "unknown" model version are excluded from change count (Dataverse token unavailable)
            n_stable = sum(
                1 for b in bots
                if b["modelVersion"] != "unknown"
                and not store.model_changed(store_dir, b["botId"], b["modelVersion"])
            )
            n_unknown = sum(1 for b in bots if b["modelVersion"] == "unknown")
            status    = f"{n_stable} stable"
            if n_unknown:
                status += f", {n_unknown} version unavailable"
            log.info(f"Watching: checked {len(bots)} agent(s), {status} · next check in {interval_s}s")
            ev.scan_complete(store_dir, len(bots), n_stable, sweep)

            # Memory snapshot every 10 sweeps (~20 min at default interval)
            if sweep % 10 == 0:
                rss   = proc.memory_info().rss / 1024 / 1024
                delta = rss - mem_base
                log.info(f"Memory usage: {rss:.1f} MB (change since start: {delta:+.1f} MB)")
                if delta > mem_base * 0.5:
                    log.warning(f"Memory growing fast — was {mem_base:.1f} MB at startup, now {rss:.1f} MB · possible memory leak")

        except AuthError as e:
            _fatal_auth_error(store_dir, str(e), log)
        except Exception as e:
            lore.eval_error("watcher", e)
            log.error(f"Watcher check failed: {e}")
        _interruptible_sleep(interval_s, store_dir)


def _eval_loop(cfg: dict):
    """Evaluator thread — wakes every eval_loop_interval_seconds and runs a cycle
    if any trigger is waiting."""
    store_dir  = cfg.get("store_dir", "data")
    log        = logger_mod.get()
    # Clamp to a safe minimum — otherwise a 0 value spins at 100% CPU.
    interval_s = max(5, int(cfg.get("eval_loop_interval_seconds") or 5))
    while True:
        if os.path.exists(_shutdown_path(store_dir)):
            raise SystemExit(0)
        try:
            force = _check_file_trigger(store_dir)
            if force:
                ev.force_eval(store_dir)
            if force or _has_pending_triggers(store_dir):
                label = "forced" if force else "triggered"
                log.info(f"Evaluation cycle starting ({label})")
                run_cycle(cfg, force=force)
                log.info("Evaluation cycle complete")
        except AuthError as e:
            _fatal_auth_error(store_dir, str(e), log)
        except Exception as e:
            lore.eval_error("evaluator", e)
            log.error(f"Evaluation cycle failed: {e}")
        _interruptible_sleep(interval_s, store_dir)


def _write_pid(store_dir: str):
    adir = _agent_dir(store_dir)
    os.makedirs(adir, exist_ok=True)
    with open(os.path.join(adir, "agent.pid"), "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))


def _remove_pid(store_dir: str):
    try:
        os.remove(os.path.join(_agent_dir(store_dir), "agent.pid"))
    except Exception:
        pass


def main():
    import signal as _signal
    cfg       = load_cfg()
    store_dir = cfg.get("store_dir", "data")

    # SIGTERM handler — raises SystemExit so try/finally runs on Linux/Mac external kills
    def _sigterm_handler(signum, frame):
        raise SystemExit(0)
    try:
        _signal.signal(_signal.SIGTERM, _sigterm_handler)
    except (OSError, ValueError):
        pass  # Windows or non-main thread — ignore

    _write_pid(store_dir)
    _clear_stale_triggers(store_dir)
    # Remove any leftover shutdown trigger from a previous session
    try:
        os.remove(_shutdown_path(store_dir))
    except FileNotFoundError:
        pass
    _clear_auth_error(store_dir)   # fresh start — clear any previous auth-error state

    log = logger_mod.setup(store_dir, level=cfg.get("log_level"))

    # ── Startup banner ────────────────────────────────────────────────────────
    _watch_min = int(cfg.get("poll_interval_minutes") or 1)
    watch_s    = max(30, _watch_min * 60)
    poll_s     = cfg.get("eval_poll_interval_seconds")
    log.info(f"āshokā starting — checking every {watch_s}s ({_watch_min} min), polling every {poll_s}s")

    envs = cfg.get("environments", [])
    for e in envs:
        monitored = e.get("monitoredBots", [])
        label     = f"{len(monitored)} agent(s)" if monitored else "all agents"
        log.info(f"Monitoring environment: {e['name']} — {label}")

    if not envs:
        log.warning("no environments configured — nothing to watch (run Setup to configure)")

    try:
        lore.starting(watch_s // 60)
        total_bots = sum(len(e.get("monitoredBots", [])) for e in envs)
        ev.agent_start(store_dir, watch_s, len(envs), total_bots)

        watcher   = threading.Thread(target=_watch_loop, args=(cfg,),
                                     daemon=True, name="watcher")
        evaluator = threading.Thread(target=_eval_loop,  args=(cfg,),
                                     daemon=True, name="evaluator")
        watcher.start()
        log.info("watcher thread started")
        evaluator.start()
        log.info("evaluator thread started")

        bot_label  = f"{total_bots} agent(s)" if total_bots else "all agents"
        log.info(f"āshokā READY — {len(envs)} environment(s) · {bot_label} · watching every {watch_s}s")

        watcher.join()   # keeps main thread alive; both are daemon so Ctrl-C exits cleanly
        evaluator.join()
    finally:
        ev.scan_end(store_dir)
        ev.agent_stop(store_dir)
        _cleanup_all_locks(store_dir)
        _remove_pid(store_dir)
        try:
            os.remove(_shutdown_path(store_dir))
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--force-eval":
        run_cycle(load_cfg(), force=True)
    else:
        main()
