"""
Generate dummy trigger data in the new folder-per-trigger format.
Creates 2 historical triggers to complement the existing legacy run files.
Run: python scripts/gen_dummy_data.py
"""
import json, os, uuid
from datetime import datetime, timezone, timedelta

BOT_ID    = "70e4f3ba-782e-f111-88b4-000d3a3ace47"
BOT_NAME  = "Safe Travels And Times"
ENV_NAME  = "Contoso (default)"
STORE_DIR = "data"

TEST_CASES = [
    "13232ba2-6f5a-4712-a015-01048bb3dc49",
    "0d4a9702-e2d0-48f8-b787-042b42e23e7a",
    "d5494329-27b1-403a-8f49-49df9867c72d",
    "03db7594-3d93-42ff-95a3-4dbc6f71d1c7",
    "290ac7bd-13b1-4e42-bb75-7cf2f41af804",
    "1027f5a8-9d6f-417a-867d-97923c5a937a",
    "88760748-bb6e-40c0-bfe8-a7d89d4a56aa",
    "c96a561e-cfe5-4fc5-bde7-ab7be9702acd",
    "7c83e689-cea9-4a65-acd7-d25c26e0e396",
    "06928a1f-8415-4710-b4f0-d388f6905f0a",
]

REASONS = [
    "The Agent answer gives partial information but misses key details about entry requirements.",
    "The Agent answer correctly identifies the main requirement but omits supporting evidence.",
    "The Agent answer is factually incorrect — contradicts the expected response on a key point.",
    "The Agent answer covers most of the expected content with minor omissions.",
    "The Agent answer is comprehensive and aligns well with the expected response.",
    "The Agent answer addresses a different scenario than what was asked.",
    "The Agent answer includes all critical safety information plus helpful extras.",
    "The Agent answer identifies the correct procedure but misses some steps.",
    "The Agent answer gives accurate general guidance but lacks specificity.",
    "The Agent answer correctly references official sources but skips actionable advice.",
]


def make_run(trigger_guid, triggered_at, model_version, scores):
    """Build the full API run result shape from a list of scores (0/50/75/100)."""
    test_cases = []
    for i, (tc_id, score) in enumerate(zip(TEST_CASES, scores)):
        status = "Pass" if score >= 50 else "Fail"
        test_cases.append({
            "testCaseId": tc_id,
            "state": "Completed",
            "metricsResults": [{
                "type": "CompareMeaning",
                "result": {
                    "data": {"score": str(score)},
                    "status": status,
                    "errorReason": None,
                    "aiResultReason": REASONS[i % len(REASONS)],
                }
            }]
        })

    pass_count = sum(1 for s in scores if s >= 50)
    return {
        "id": trigger_guid,
        "environmentId": "default-8b7a11d9-6513-4d54-a468-f6630df73c8b",
        "cdsBotId": BOT_ID,
        "ownerId": "14f91736-72a8-4307-a973-63f6c2bafd80",
        "testSetId": "6bd3ec84-4e4f-4a55-9dfe-ecfc9816848b",
        "state": "Completed",
        "startTime": triggered_at,
        "endTime": triggered_at,
        "name": "Automated Test Triggered by API",
        "totalTestCases": len(scores),
        "mcsConnectionId": None,
        "testCasesResults": test_cases,
    }


def write_trigger(trigger_guid, triggered_at, model_version, scores, analysis):
    trigger_dir = os.path.join(STORE_DIR, BOT_ID, "runs", trigger_guid)
    os.makedirs(trigger_dir, exist_ok=True)

    pass_count = sum(1 for s in scores if s >= 50)
    avg_score  = sum(scores) / len(scores)

    meta = {
        "triggerGuid":  trigger_guid,
        "triggeredAt":  triggered_at,
        "modelVersion": model_version,
        "metricTypes":  ["CompareMeaning"],
        "analysis":     analysis,
    }
    open(os.path.join(trigger_dir, "meta.json"), "w").write(json.dumps(meta, indent=2))

    run_result = make_run(trigger_guid, triggered_at, model_version, scores)
    payload = {
        "metricType": "CompareMeaning",
        "apiRunId":   trigger_guid,
        "storedAt":   triggered_at,
        "results":    run_result,
    }
    open(os.path.join(trigger_dir, "CompareMeaning.json"), "w").write(
        json.dumps(payload, indent=2)
    )
    print(f"  Written: {trigger_dir}  (pass={pass_count}/{len(scores)}, avg={avg_score:.1f})")


# ── Dummy triggers ────────────────────────────────────────────────────────────

TRIGGERS = [
    {
        "guid":    "d1000000-aaaa-4000-8000-000000000001",
        "date":    "2026-04-10T09:22:11.000000+00:00",
        "model":   "crf98_safeTravels.gpt-4o.default",
        "scores":  [50, 0, 0, 75, 50, 0, 50, 75, 50, 0],   # 60% pass, avg 35
        "analysis": (
            "Baseline run on gpt-4o. Pass rate 60% with average score 35. "
            "Several test cases fail outright — particularly on country-specific entry rules "
            "and document requirements. The model frequently confuses adjacent countries and "
            "produces hallucinated document lists. Recommend monitoring after model upgrade."
        ),
    },
    {
        "guid":    "d2000000-bbbb-4000-8000-000000000002",
        "date":    "2026-04-14T11:05:33.000000+00:00",
        "model":   "crf98_safeTravels.gpt.default",
        "scores":  [75, 75, 50, 75, 75, 50, 100, 75, 75, 75],  # 100% pass, avg 72.5
        "analysis": (
            "Significant improvement following model upgrade to gpt.default. "
            "Pass rate rose to 100% with average score 72.5. "
            "The model no longer confuses Australia/NZ scenarios and document requirement "
            "responses are now accurate. Some test cases still score 50 due to omitted "
            "supporting context. Overall drift is positive — no regression detected."
        ),
    },
]

print("Generating dummy triggers...")
for t in TRIGGERS:
    write_trigger(t["guid"], t["date"], t["model"], t["scores"], t["analysis"])

# Update tracking.json to new format
tracking_path = os.path.join(STORE_DIR, BOT_ID, "tracking.json")
existing = json.loads(open(tracking_path).read()) if os.path.exists(tracking_path) else {}
existing.update({
    "botId":           BOT_ID,
    "botName":         BOT_NAME,
    "envName":         ENV_NAME,
    "modelVersion":    "crf98_safeTravels.gpt.default",
    "lastTriggerGuid": "c2eaabc2-73b0-4b82-844e-caabb21b179a",  # real legacy run
    "updatedAt":       "2026-04-18T14:17:17.449210+00:00",
})
# Remove old key if present
existing.pop("lastRunId", None)
open(tracking_path, "w").write(json.dumps(existing, indent=2))
print(f"  Updated: {tracking_path}")
print("Done.")
