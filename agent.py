import json
import os
import schedule
import time
from datetime import datetime, timezone

import dataverse
import eval_client
import notifier
import reasoning
import report
import store


def load_cfg(path: str = "config.json") -> dict:
    return json.loads(open(path).read())


def run_cycle(cfg: dict):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n[agent] ── cycle start {ts} ──")

    store_dir   = cfg.get("store_dir", "data")
    bots        = dataverse.list_all_bots(cfg)
    bot_results = []

    for bot in bots:
        bot_id   = bot["botId"]
        bot_name = bot["name"]
        curr_ver = bot["modelVersion"]

        changed = store.model_changed(store_dir, bot_id, curr_ver)
        if not changed:
            print(f"[agent] {bot_name}: no model change — skipping eval")
            continue

        tracking  = store.load_tracking(store_dir, bot_id)
        old_ver   = tracking.get("modelVersion", "unknown")
        print(f"[agent] {bot_name}: model changed {old_ver} → {curr_ver}")

        try:
            result = eval_client.run_eval_for_bot(bot, cfg)
            if result is None:
                store.save_tracking(store_dir, bot_id, curr_ver, None)
                continue

            run_id    = result.get("id", result.get("runId", "unknown"))
            prev_run  = store.load_last_run(store_dir, bot_id)

            store.save_run(store_dir, bot_id, run_id, curr_ver, result)

            curr_metrics = reasoning.extract_metrics_for_report(result)
            prev_metrics = reasoning.extract_metrics_for_report(prev_run["results"]) if prev_run else {}

            analysis = reasoning.analyse_drift(
                bot_name, old_ver, curr_ver, result, prev_run["results"] if prev_run else None, cfg
            )

            bot_results.append({
                "botName":     bot_name,
                "oldModel":    old_ver,
                "newModel":    curr_ver,
                "runId":       run_id,
                "currMetrics": curr_metrics,
                "prevMetrics": prev_metrics,
                "analysis":    analysis
            })

            store.save_tracking(store_dir, bot_id, curr_ver, run_id)

        except Exception as e:
            print(f"[agent] {bot_name}: error — {e}")

    if not bot_results:
        print("[agent] no model changes detected this cycle")
        return

    html      = report.generate_report(bot_results)
    report_path = os.path.join(store_dir, f"report_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.html")
    os.makedirs(store_dir, exist_ok=True)
    open(report_path, "w", encoding="utf-8").write(html)
    print(f"[agent] report saved → {report_path}")

    notifier.send_report(html, cfg)
    print(f"[agent] ── cycle complete — {len(bot_results)} bot(s) reported ──")


def main():
    cfg      = load_cfg()
    interval = cfg.get("poll_interval_minutes", 10)
    print(f"[agent] starting — polling every {interval} minute(s)")

    run_cycle(cfg)  # run immediately on start

    schedule.every(interval).minutes.do(run_cycle, cfg=cfg)
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
