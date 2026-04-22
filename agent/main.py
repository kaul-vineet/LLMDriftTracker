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
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timezone

# Force UTF-8 stdout/stderr so emoji in lore.py don't crash on Windows CP1252 terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import psutil

from . import dataverse
from . import eval_client
from .auth import get_dataverse_token
from . import events as ev
from . import logger as logger_mod
from . import lore
from . import notifier
from . import reasoning
from . import report
from . import store


def load_cfg(path: str = "config.json") -> dict:
    cfg = json.loads(open(path).read())
    cfg.setdefault("llm", {})
    cfg.setdefault("smtp", {})
    cfg["llm"]["api_key"]    = os.environ.get("LLM_API_KEY",    cfg["llm"].get("api_key", ""))
    cfg["llm"]["base_url"]   = os.environ.get("LLM_BASE_URL",   cfg["llm"].get("base_url", ""))
    cfg["llm"]["model"]      = os.environ.get("LLM_MODEL",      cfg["llm"].get("model", ""))
    cfg["smtp"]["password"]  = os.environ.get("SMTP_PASSWORD",  cfg["smtp"].get("password", ""))
    cfg["smtp"]["host"]      = os.environ.get("SMTP_HOST",      cfg["smtp"].get("host", ""))
    cfg["smtp"]["user"]      = os.environ.get("SMTP_USER",      cfg["smtp"].get("user", ""))
    cfg["smtp"]["recipient"] = os.environ.get("SMTP_RECIPIENT", cfg["smtp"].get("recipient", ""))
    return cfg


def _agent_dir(store_dir: str) -> str:
    return os.path.join(store_dir, "agent")


def _check_file_trigger(store_dir: str) -> bool:
    """Return True and delete the global force_eval.trigger if it exists."""
    path = os.path.join(_agent_dir(store_dir), "force_eval.trigger")
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass
        return True
    return False


def _check_bot_trigger(store_dir: str, bot_id: str) -> bool:
    """Return True and delete a per-bot force_eval trigger if it exists."""
    path = os.path.join(_agent_dir(store_dir), f"force_eval_{bot_id}.trigger")
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass
        return True
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
        ):
            try:
                os.remove(os.path.join(adir, fname))
            except Exception:
                pass


def _build_bot_result(bot_name, old_ver, curr_ver, run_folder,
                      test_sets, prev_run, cfg) -> dict:
    curr_metrics    = reasoning.extract_metrics_for_report(test_sets)
    prev_metrics    = (
        reasoning.extract_metrics_for_report(prev_run.get("testSets", {}))
        if prev_run else {}
    )
    classifications = reasoning.classify_run(prev_metrics, curr_metrics)
    analysis        = reasoning.analyse_variation(
        bot_name, old_ver, curr_ver, test_sets, prev_run, cfg
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


def _save_and_notify(bot_results, store_dir, cfg):
    html        = report.generate_report(bot_results)
    report_path = os.path.join(
        store_dir,
        f"report_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.html"
    )
    os.makedirs(store_dir, exist_ok=True)
    open(report_path, "w", encoding="utf-8").write(html)
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
    adir = _agent_dir(store_dir)
    if os.path.exists(adir):
        for fname in os.listdir(adir):
            if fname.startswith("force_eval_") and fname.endswith(".trigger"):
                bot_id_from_file = fname[len("force_eval_"):-len(".trigger")]
                triggered_ids.add(bot_id_from_file)
                try:
                    os.remove(os.path.join(adir, fname))
                except Exception:
                    pass
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
                      trigger_guid=run_folder, env_id=bot.get("ppEnvId", ""))

        bot_ctx[bot_id] = {
            "bot":           bot,
            "old_ver":       old_ver,
            "curr_ver":      curr_ver,
            "run_folder":    run_folder,
            "eval_start_ts": eval_start_ts,
            "bot_forced":    bot_forced,
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
            open(lock_path, "w").write(datetime.now(timezone.utc).isoformat())
        except Exception:
            pass

    # ── Phase 1: trigger all test sets for all bots at once ─────────────────
    try:
        pool = eval_client.trigger_all_evals(bots_to_eval, cfg)
    except Exception as e:
        lore.eval_error("trigger phase", e)
        return

    # ── Phase 2: single-threaded round-robin poll until all done ────────────
    results_by_bot = eval_client.poll_all_runs(
        pool, cfg,
        timeout_s=cfg.get("eval_poll_timeout_seconds", 1200),
        interval_s=cfg.get("eval_poll_interval_seconds", 20),
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
            )

            br = _build_bot_result(bot_name, old_ver, curr_ver, run_folder,
                                   test_sets, prev_run, cfg)

            cls         = br.get("classifications", [])
            reg_metrics = [c["key"] for c in cls if c["verdict"] == "REGRESSED"]
            imp_metrics = [c["key"] for c in cls if c["verdict"] == "IMPROVED"]
            curr_m      = br.get("currMetrics", {})
            pass_rate   = curr_m.get("CompareMeaning.passRate", 0.0)
            avg_score   = curr_m.get("CompareMeaning.score", 0.0)
            verdict     = br.get("verdictSummary", "STABLE")
            duration_s  = int((datetime.now(timezone.utc) - eval_start_ts).total_seconds())

            ev.eval_complete(store_dir, bot_name, bot_id, pass_rate, avg_score, verdict,
                             trigger_guid=run_folder, env_id=env_id, duration_secs=duration_s)
            if reg_metrics:
                ev.regression(store_dir, bot_name, bot_id, reg_metrics,
                              trigger_guid=run_folder, env_id=env_id)
            elif imp_metrics:
                ev.improvement(store_dir, bot_name, bot_id, imp_metrics,
                               trigger_guid=run_folder, env_id=env_id)

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


def _watch_loop(cfg: dict):
    """Watcher thread — polls Dataverse every watch_interval_seconds and writes a
    trigger file the moment a model version change is detected. Never runs evals."""
    store_dir  = cfg.get("store_dir", "data")
    interval_s = cfg.get("watch_interval_seconds", 120)
    log        = logger_mod.get()
    proc       = psutil.Process()
    mem_base   = proc.memory_info().rss / 1024 / 1024
    sweep      = 0

    while True:
        try:
            bots = dataverse.list_all_bots(cfg)
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
                    open(trigger_path, "w").write(datetime.now(timezone.utc).isoformat())
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

            # Memory snapshot every 10 sweeps (~20 min at default interval)
            if sweep % 10 == 0:
                rss   = proc.memory_info().rss / 1024 / 1024
                delta = rss - mem_base
                log.info(f"Memory usage: {rss:.1f} MB (change since start: {delta:+.1f} MB)")
                if delta > mem_base * 0.5:
                    log.warning(f"Memory growing fast — was {mem_base:.1f} MB at startup, now {rss:.1f} MB · possible memory leak")

        except Exception as e:
            lore.eval_error("watcher", e)
            log.error(f"Watcher check failed: {e}")
        time.sleep(interval_s)


def _eval_loop(cfg: dict):
    """Evaluator thread — wakes every 30 s and runs a cycle if any trigger is waiting."""
    store_dir = cfg.get("store_dir", "data")
    log       = logger_mod.get()
    while True:
        try:
            force = _check_file_trigger(store_dir)
            if force or _has_pending_triggers(store_dir):
                label = "forced" if force else "triggered"
                log.info(f"Evaluation cycle starting ({label})")
                run_cycle(cfg, force=force)
                log.info("Evaluation cycle complete")
        except Exception as e:
            lore.eval_error("evaluator", e)
            log.error(f"Evaluation cycle failed: {e}")
        time.sleep(30)


def _write_pid(store_dir: str):
    adir = _agent_dir(store_dir)
    os.makedirs(adir, exist_ok=True)
    open(os.path.join(adir, "agent.pid"), "w").write(str(os.getpid()))


def _remove_pid(store_dir: str):
    try:
        os.remove(os.path.join(_agent_dir(store_dir), "agent.pid"))
    except Exception:
        pass


def main():
    cfg       = load_cfg()
    store_dir = cfg.get("store_dir", "data")

    _write_pid(store_dir)
    _clear_stale_triggers(store_dir)

    log = logger_mod.setup(store_dir, level=cfg.get("log_level", "INFO"))

    # ── Startup banner ────────────────────────────────────────────────────────
    watch_s = cfg.get("watch_interval_seconds", 120)
    poll_s  = cfg.get("eval_poll_interval_seconds", 20)
    log.info(f"VARION starting — checking every {watch_s}s, polling every {poll_s}s")

    envs = cfg.get("environments", [])
    for e in envs:
        monitored = e.get("monitoredBots", [])
        label     = f"{len(monitored)} agent(s)" if monitored else "all agents"
        log.info(f"Monitoring environment: {e['name']} — {label}")

    if not envs:
        log.warning("no environments configured — nothing to watch (run Setup to configure)")

    # Acquire Dataverse tokens for each environment once at startup so the watcher can
    # detect model version changes silently. If a token is not cached this triggers one
    # device flow — the dashboard surfaces the code. After sign-in the cache is warm and
    # no further interactive auth is needed during this session.
    for env in envs:
        org_url = env.get("orgUrl", "")
        if not org_url:
            continue
        try:
            get_dataverse_token(org_url, cfg)
            log.info(f"Dataverse token ready for {env['name']} — model version detection enabled")
        except Exception as e:
            log.warning(f"Dataverse auth failed for {env['name']}: {e} — model version detection disabled for this session")

    try:
        lore.starting(watch_s // 60)

        watcher   = threading.Thread(target=_watch_loop, args=(cfg,),
                                     daemon=True, name="watcher")
        evaluator = threading.Thread(target=_eval_loop,  args=(cfg,),
                                     daemon=True, name="evaluator")
        watcher.start()
        log.info("watcher thread started")
        evaluator.start()
        log.info("evaluator thread started")

        total_bots = sum(len(e.get("monitoredBots", [])) for e in envs)
        bot_label  = f"{total_bots} agent(s)" if total_bots else "all agents"
        log.info(f"ASHOKA READY — {len(envs)} environment(s) · {bot_label} · watching every {watch_s}s")

        watcher.join()   # keeps main thread alive; both are daemon so Ctrl-C exits cleanly
        evaluator.join()
    finally:
        _remove_pid(store_dir)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--force-eval":
        run_cycle(load_cfg(), force=True)
    else:
        main()
