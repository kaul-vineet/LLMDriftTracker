"""
Generate dummy run data in the new {timestamp}_{modelVersion}/run.json format.
Run: python scripts/gen_dummy_data.py
"""
import json, os
from datetime import datetime, timezone

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


def make_api_result(api_run_id, triggered_at, scores):
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
    return {
        "id": api_run_id,
        "environmentId": "default-8b7a11d9-6513-4d54-a468-f6630df73c8b",
        "cdsBotId": BOT_ID,
        "testSetId": "6bd3ec84-4e4f-4a55-9dfe-ecfc9816848b",
        "state": "Completed",
        "startTime": triggered_at,
        "endTime":   triggered_at,
        "totalTestCases": len(scores),
        "testCasesResults": test_cases,
    }


def write_run(folder_name, triggered_at, model_version, scores, forced=False):
    run_dir = os.path.join(STORE_DIR, BOT_ID, "runs", folder_name)
    os.makedirs(run_dir, exist_ok=True)

    api_run_id  = folder_name[:12]
    api_result  = make_api_result(api_run_id, triggered_at, scores)
    pass_count  = sum(1 for s in scores if s >= 50)
    avg_score   = sum(scores) / len(scores)

    run = {
        "botId":        BOT_ID,
        "botName":      BOT_NAME,
        "envId":        "default-8b7a11d9-6513-4d54-a468-f6630df73c8b",
        "envName":      ENV_NAME,
        "orgUrl":       "https://org123.crm.dynamics.com",
        "modelVersion": model_version,
        "triggeredAt":  triggered_at,
        "forced":       forced,
        "testSets": {
            "CompareMeaning": {
                "apiRunId": api_run_id,
                "results":  api_result,
            }
        },
    }
    open(os.path.join(run_dir, "run.json"), "w").write(json.dumps(run, indent=2))
    print(f"  Written: {run_dir}  (pass={pass_count}/{len(scores)}, avg={avg_score:.1f})")
    return folder_name


RUNS = [
    {
        "folder":  "20260410T092211_crf98_safeTravels.gpt-4o.default",
        "date":    "2026-04-10T09:22:11.000000+00:00",
        "model":   "crf98_safeTravels.gpt-4o.default",
        "scores":  [50, 0, 0, 75, 50, 0, 50, 75, 50, 0],
        "forced":  False,
    },
    {
        "folder":  "20260414T110533_crf98_safeTravels.gpt.default",
        "date":    "2026-04-14T11:05:33.000000+00:00",
        "model":   "crf98_safeTravels.gpt.default",
        "scores":  [75, 75, 50, 75, 75, 50, 100, 75, 75, 75],
        "forced":  False,
    },
]

print("Generating dummy runs...")
last_folder = None
for r in RUNS:
    last_folder = write_run(r["folder"], r["date"], r["model"], r["scores"], r["forced"])

tracking_path = os.path.join(STORE_DIR, BOT_ID, "tracking.json")
existing = json.loads(open(tracking_path).read()) if os.path.exists(tracking_path) else {}
existing.update({
    "botId":          BOT_ID,
    "botName":        BOT_NAME,
    "envName":        ENV_NAME,
    "modelVersion":   RUNS[-1]["model"],
    "lastRunFolder":  last_folder,
    "updatedAt":      RUNS[-1]["date"],
})
existing.pop("lastTriggerGuid", None)
existing.pop("lastRunId", None)
open(tracking_path, "w").write(json.dumps(existing, indent=2))
print(f"  Updated: {tracking_path}")
print("Done.")
