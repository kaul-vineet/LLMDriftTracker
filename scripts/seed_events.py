"""
Seed data/events.jsonl with sample agent action events.
Run: python scripts/seed_events.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agent import events as ev

STORE = "data"
BOT_ID   = "70e4f3ba-782e-f111-88b4-000d3a3ace47"
BOT_NAME = "Safe Travels And Times"

# Wipe existing seed so we don't double-up
log = os.path.join(STORE, "events.jsonl")
if os.path.exists(log):
    os.remove(log)

import json
from datetime import datetime, timezone, timedelta

def _write_at(ts_iso, event_type, bot_name="", bot_id="", detail="", extra=None):
    record = {"ts": ts_iso, "event": event_type, "botName": bot_name,
              "botId": bot_id, "detail": detail, **(extra or {})}
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

# Apr 10 — first cycle, model change detected, evals run, clean pass
_write_at("2026-04-10T09:20:00+00:00", "cycle_start",   detail="Scheduled poll cycle started")
_write_at("2026-04-10T09:20:05+00:00", "model_change",  BOT_NAME, BOT_ID,
          "crf98_safeTravels.gpt-4o.default  →  crf98_safeTravels.gpt.default",
          {"oldModel": "crf98_safeTravels.gpt-4o.default", "newModel": "crf98_safeTravels.gpt.default"})
_write_at("2026-04-10T09:20:08+00:00", "eval_start",    BOT_NAME, BOT_ID, "Eval triggered — fetching test sets")
_write_at("2026-04-10T09:22:11+00:00", "eval_complete", BOT_NAME, BOT_ID,
          "pass 60%  ·  avg score 35.0  ·  REGRESSED",
          {"passRate": 0.60, "avgScore": 35.0, "verdict": "REGRESSED"})
_write_at("2026-04-10T09:22:12+00:00", "regression",    BOT_NAME, BOT_ID,
          "Regression in: CompareMeaning.passRate, CompareMeaning.score",
          {"metrics": ["CompareMeaning.passRate", "CompareMeaning.score"]})

# Apr 14 — model settled, evals show improvement
_write_at("2026-04-14T11:00:00+00:00", "cycle_start",   detail="Scheduled poll cycle started")
_write_at("2026-04-14T11:00:04+00:00", "eval_start",    BOT_NAME, BOT_ID, "Eval triggered — fetching test sets")
_write_at("2026-04-14T11:05:33+00:00", "eval_complete", BOT_NAME, BOT_ID,
          "pass 100%  ·  avg score 72.5  ·  IMPROVED",
          {"passRate": 1.0, "avgScore": 72.5, "verdict": "IMPROVED"})
_write_at("2026-04-14T11:05:34+00:00", "improvement",   BOT_NAME, BOT_ID,
          "Improved: CompareMeaning.passRate, CompareMeaning.score",
          {"metrics": ["CompareMeaning.passRate", "CompareMeaning.score"]})

# Apr 18 — three cycles, last one shows slight regression
_write_at("2026-04-18T13:39:00+00:00", "cycle_start",   detail="Scheduled poll cycle started")
_write_at("2026-04-18T13:39:03+00:00", "stable",        BOT_NAME, BOT_ID, "No drift detected — all metrics stable")

_write_at("2026-04-18T13:54:00+00:00", "cycle_start",   detail="Scheduled poll cycle started")
_write_at("2026-04-18T13:54:02+00:00", "stable",        BOT_NAME, BOT_ID, "No drift detected — all metrics stable")

_write_at("2026-04-18T14:14:32+00:00", "force_eval",    detail="force_eval.trigger file detected — running eval immediately")
_write_at("2026-04-18T14:14:35+00:00", "eval_start",    BOT_NAME, BOT_ID, "Eval triggered — fetching test sets")
_write_at("2026-04-18T14:17:17+00:00", "eval_complete", BOT_NAME, BOT_ID,
          "pass 80%  ·  avg score 52.5  ·  REGRESSED",
          {"passRate": 0.80, "avgScore": 52.5, "verdict": "REGRESSED"})
_write_at("2026-04-18T14:17:18+00:00", "regression",    BOT_NAME, BOT_ID,
          "Regression in: CompareMeaning.passRate, CompareMeaning.score",
          {"metrics": ["CompareMeaning.passRate", "CompareMeaning.score"]})

print(f"Seeded {sum(1 for _ in open(log, encoding='utf-8'))} events -> {log}")
