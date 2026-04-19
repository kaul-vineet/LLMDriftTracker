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
import schedule
import time
import uuid
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timezone

from . import dataverse
from . import eval_client
from . import events as ev
from . import lore
from . import notifier
from . import reasoning
from . import report
from . import store


def load_cfg(path: str = "config.json") -> dict:
    cfg = json.loads(open(path).read())
    # Overlay secrets from environment variables
    cfg.setdefault("llm", {})
    cfg.setdefault("smtp", {})
    cfg["llm"]["api_key"]   = os.environ.get("LLM_API_KEY",       cfg["llm"].get("api_key", ""))
    cfg["llm"]["base_url"]  = os.environ.get("LLM_BASE_URL",      cfg["llm"].get("base_url", ""))
    cfg["llm"]["model"]     = os.environ.get("LLM_MODEL",         cfg["llm"].get("model", ""))
    cfg["smtp"]["password"] = os.environ.get("SMTP_PASSWORD",     cfg["smtp"].get("password", ""))
    cfg["smtp"]["host"]     = os.environ.get("SMTP_HOST",         cfg["smtp"].get("host", ""))
    cfg["smtp"]["user"]     = os.environ.get("SMTP_USER",         cfg["smtp"].get("user", ""))
    cfg["smtp"]["recipient"]= os.environ.get("SMTP_RECIPIENT",    cfg["smtp"].get("recipient", ""))
    return cfg


def _check_file_trigger(store_dir: str) -> bool:
    """Return True and delete the trigger file if it exists."""
    path = os.path.join(store_dir, "force_eval.trigger")
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass
        return True
    return False


def _build_bot_result(bot_name, old_ver, curr_ver, trigger_guid,
                      results_by_type, prev_trigger, cfg) -> dict:
    curr_metrics = reasoning.extract_metrics_for_report(results_by_type)
    prev_metrics = (
        reasoning.extract_metrics_for_report(prev_trigger.get("resultsByType", {}))
        if prev_trigger else {}
    )
    classifications = reasoning.classify_run(prev_metrics, curr_metrics)
    analysis        = reasoning.analyse_drift(
        bot_name, old_ver, curr_ver, results_by_type, prev_trigger, cfg
    )
    return {
        "botName":          bot_name,
        "oldModel":         old_ver,
        "newModel":         curr_ver,
        "triggerGuid":      trigger_guid,
        "currMetrics":      curr_metrics,
        "prevMetrics":      prev_metrics,
        "classifications":  classifications,
        "verdictSummary":   reasoning.verdict_summary(classifications),
        "analysis":         analysis,
        "prevTrigger":      prev_trigger,
        "currResultsByType": results_by_type,
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

    store_dir   = cfg.get("store_dir", "data")
    ev.cycle_start(store_dir, forced=force)

    bots        = dataverse.list_all_bots(cfg)
    bot_results = []

    for bot in bots:
        bot_id   = bot["botId"]
        bot_name = bot["name"]
        curr_ver = bot["modelVersion"]

        if not force and not store.model_changed(store_dir, bot_id, curr_ver):
            lore.no_change(bot_name)
            ev.stable(store_dir, bot_name, bot_id)
            continue

        tracking = store.load_tracking(store_dir, bot_id)
        old_ver  = tracking.get("modelVersion", curr_ver if force else "unknown")
        if not force:
            lore.model_changed(bot_name, old_ver, curr_ver)
            ev.model_change(store_dir, bot_name, bot_id, old_ver, curr_ver)

        trigger_guid = str(uuid.uuid4()).replace("-", "")[:12]

        env_id  = bot.get("ppEnvId", "")
        org_url = bot.get("orgUrl", "")

        try:
            eval_start_ts = datetime.now(timezone.utc)
            ev.eval_start(store_dir, bot_name, bot_id, 0,
                          trigger_guid=trigger_guid, env_id=env_id)
            results_by_type = eval_client.run_eval_for_bot(bot, cfg)
            if not results_by_type:
                ev.eval_no_sets(store_dir, bot_name, bot_id)
                store.save_tracking(store_dir, bot_id, curr_ver, None,
                                    bot_name=bot_name, env_name=bot.get("envName", ""),
                                    env_id=env_id, org_url=org_url)
                continue

            prev_trigger = store.load_last_trigger(store_dir, bot_id)

            br = _build_bot_result(bot_name, old_ver, curr_ver, trigger_guid,
                                   results_by_type, prev_trigger, cfg)

            # Log verdict events
            cls = br.get("classifications", [])
            reg_metrics = [c["key"] for c in cls if c["verdict"] == "REGRESSED"]
            imp_metrics = [c["key"] for c in cls if c["verdict"] == "IMPROVED"]
            curr_m = br.get("currMetrics", {})
            pass_rate    = curr_m.get("CompareMeaning.passRate", 0.0)
            avg_score    = curr_m.get("CompareMeaning.score", 0.0)
            verdict      = br.get("verdictSummary", "STABLE")
            duration_s   = int((datetime.now(timezone.utc) - eval_start_ts).total_seconds())

            ev.eval_complete(store_dir, bot_name, bot_id, pass_rate, avg_score, verdict,
                             trigger_guid=trigger_guid, env_id=env_id, duration_secs=duration_s)
            if reg_metrics:
                ev.regression(store_dir, bot_name, bot_id, reg_metrics,
                              trigger_guid=trigger_guid, env_id=env_id)
            elif imp_metrics:
                ev.improvement(store_dir, bot_name, bot_id, imp_metrics,
                               trigger_guid=trigger_guid, env_id=env_id)

            store.save_trigger(store_dir, bot_id, trigger_guid, curr_ver,
                               results_by_type, analysis=br["analysis"],
                               bot_name=bot_name, env_name=bot.get("envName", ""),
                               env_id=env_id, org_url=org_url)
            store.save_tracking(store_dir, bot_id, curr_ver, trigger_guid,
                                bot_name=bot_name, env_name=bot.get("envName", ""),
                                env_id=env_id, org_url=org_url)
            bot_results.append(br)
            lore.eval_done(bot_name)

        except Exception as e:
            lore.eval_error(bot_name, e)
            ev.error(store_dir, bot_name, bot_id, str(e))

    if not bot_results:
        lore.cycle_idle()
        return

    _save_and_notify(bot_results, store_dir, cfg)


def _write_pid(store_dir: str):
    os.makedirs(store_dir, exist_ok=True)
    open(os.path.join(store_dir, "agent.pid"), "w").write(str(os.getpid()))


def _remove_pid(store_dir: str):
    try:
        os.remove(os.path.join(store_dir, "agent.pid"))
    except Exception:
        pass


def main():
    cfg       = load_cfg()
    interval  = cfg.get("poll_interval_minutes", 10)
    store_dir = cfg.get("store_dir", "data")

    _write_pid(store_dir)
    try:
        lore.starting(interval)
        run_cycle(cfg)

        def _scheduled_or_triggered():
            if _check_file_trigger(store_dir):
                print("\n[agent] force_eval.trigger detected — running immediately\n")
                ev.force_eval(store_dir)
                run_cycle(cfg, force=True)
            else:
                run_cycle(cfg)

        schedule.every(interval).minutes.do(_scheduled_or_triggered)

        while True:
            schedule.run_pending()
            if _check_file_trigger(store_dir):
                print("\n[agent] force_eval.trigger detected — running immediately\n")
                run_cycle(cfg, force=True)
            time.sleep(60)
    finally:
        _remove_pid(store_dir)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--force-eval":
        run_cycle(load_cfg(), force=True)
    else:
        main()
