import json
import os
from openai import OpenAI


def _build_client(cfg: dict) -> OpenAI:
    llm = cfg["llm"]
    return OpenAI(
        base_url=os.environ.get("LLM_BASE_URL") or llm["base_url"],
        api_key=os.environ.get("LLM_API_KEY") or llm["api_key"]
    )


def _model(cfg: dict) -> str:
    return os.environ.get("LLM_MODEL") or cfg["llm"]["model"]


def _extract_metrics(run: dict) -> dict:
    """Aggregate pass rate and numeric scores per metric type."""
    if not run:
        return {}
    totals: dict = {}
    counts: dict = {}
    for case in run.get("testCasesResults", []):
        for m in case.get("metricsResults", []):
            mtype  = m.get("type", "unknown")
            result = m.get("result", {})
            data   = result.get("data", {})
            status = result.get("status", "")

            # Pass/fail rate
            pk = f"{mtype}.passRate"
            counts[pk] = counts.get(pk, 0) + 1
            totals[pk] = totals.get(pk, 0) + (1 if status == "Pass" else 0)

            # Numeric/score fields (API returns scores as strings)
            for field, val in data.items():
                key = f"{mtype}.{field}"
                counts[key] = counts.get(key, 0) + 1
                if isinstance(val, bool):
                    totals[key] = totals.get(key, 0) + (1 if val else 0)
                elif isinstance(val, (int, float)):
                    totals[key] = totals.get(key, 0) + val
                elif isinstance(val, str):
                    try:
                        totals[key] = totals.get(key, 0) + float(val)
                    except ValueError:
                        counts.pop(key, None)

    return {k: round(totals[k] / counts[k], 4) for k in totals if k in counts}


def _build_prompt(bot_name: str, old_model: str, new_model: str,
                  prev_metrics: dict, curr_metrics: dict,
                  ai_reasons: list[str]) -> str:
    all_keys = sorted(set(list(prev_metrics.keys()) + list(curr_metrics.keys())))
    rows = []
    for k in all_keys:
        v_prev = prev_metrics.get(k, "N/A")
        v_curr = curr_metrics.get(k, "N/A")
        if isinstance(v_prev, float) and isinstance(v_curr, float):
            delta = round(v_curr - v_prev, 4)
            rows.append(f"  {k}: {v_prev} → {v_curr}  (Δ {delta:+.4f})")
        else:
            rows.append(f"  {k}: {v_prev} → {v_curr}")

    table = "\n".join(rows) if rows else "  No metrics available for comparison."
    reasons = "\n".join(f"  - {r}" for r in ai_reasons[:20]) if ai_reasons else "  None available."

    return f"""You are an AI quality analyst reviewing Copilot Studio agent evaluation results.

Agent: {bot_name}
Model change: {old_model}  →  {new_model}

Metric comparison (previous → current):
{table}

Sample AI evaluation reasons from failing/notable test cases:
{reasons}

Analyse the drift between model versions. Identify:
1. Which metrics regressed and by how much
2. Which metrics improved
3. Patterns in the AI reasons (e.g. topic clusters, capability gaps)
4. Whether the regression is significant or within noise
5. A clear recommendation: proceed with new model / investigate further / revert

Be concise. Use plain language. No bullet-point lists — write in short paragraphs."""


def analyse_drift(bot_name: str, old_model: str, new_model: str,
                  current_run: dict, previous_run: dict | None, cfg: dict) -> str:
    curr_metrics = _extract_metrics(current_run)
    prev_metrics = _extract_metrics(previous_run) if previous_run else {}

    ai_reasons = [
        m["result"]["aiResultReason"]
        for case in current_run.get("testCasesResults", [])
        for m in case.get("metricsResults", [])
        if m.get("result", {}).get("aiResultReason")
    ]

    if not prev_metrics:
        return (f"No previous run available for {bot_name}. "
                f"Baseline established for model {new_model}. "
                f"Current metrics: {json.dumps(curr_metrics, indent=2)}")

    prompt = _build_prompt(bot_name, old_model, new_model,
                           prev_metrics, curr_metrics, ai_reasons)

    try:
        client   = _build_client(cfg)
        response = client.chat.completions.create(
            model=_model(cfg),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"LLM analysis unavailable ({e}). Raw metrics: {json.dumps(curr_metrics, indent=2)}"


def extract_metrics_for_report(run: dict) -> dict:
    return _extract_metrics(run)
