"""
agent/reasoning.py — metric extraction, response variation classification, LLM analysis.

classify_run() returns verdicts sorted REGRESSED → IMPROVED → STABLE.
_build_prompt() leads with regressions.
extract_metrics_for_report() accepts the testSets dict shape:
  dict[metric_type -> {apiRunId, results: {testCasesResults: [...]}}]
"""
import json
import os
from openai import OpenAI

REGRESS_THRESHOLD = 0.03   # absolute change to count as regression/improvement


# ── Metric extraction ─────────────────────────────────────────────────────────

def _extract_metrics(run: dict) -> dict:
    """Aggregate pass rate and numeric scores per metric type from one run result."""
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

            pk = f"{mtype}.passRate"
            counts[pk] = counts.get(pk, 0) + 1
            totals[pk] = totals.get(pk, 0) + (1 if status == "Pass" else 0)

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

    # Divide each accumulated total by its sample count to produce per-metric averages
    return {k: round(totals[k] / counts[k], 4) for k in totals if k in counts}


def extract_metrics_for_report(test_sets: dict) -> dict:
    """
    Accept testSets: dict[metric_type -> {apiRunId, results: {testCasesResults: [...]}}]
    Also accepts a bare run result dict (has "testCasesResults") for legacy callers.
    """
    if not test_sets:
        return {}
    if "testCasesResults" in test_sets:
        return _extract_metrics(test_sets)
    combined = {}
    for _type, wrapper in test_sets.items():
        if isinstance(wrapper, dict):
            run_result = wrapper.get("results", wrapper)
            combined.update(_extract_metrics(run_result))
    return combined


# ── Classification ────────────────────────────────────────────────────────────

def classify(prev_val: float | None, curr_val: float | None,
             threshold: float = REGRESS_THRESHOLD) -> str:
    if prev_val is None or curr_val is None:
        return "NEW"
    delta = curr_val - prev_val
    if delta <= -threshold:
        return "REGRESSED"
    if delta >= threshold:
        return "IMPROVED"
    return "STABLE"


_VERDICT_ORDER = {"REGRESSED": 0, "IMPROVED": 1, "STABLE": 2, "NEW": 3}


def classify_run(prev_metrics: dict, curr_metrics: dict) -> list[dict]:
    """
    Compare two metric dicts and return a list sorted REGRESSED → IMPROVED → STABLE.
    Each item: {key, verdict, prev, curr, delta}.
    """
    all_keys = sorted(set(list(prev_metrics.keys()) + list(curr_metrics.keys())))
    results  = []
    for k in all_keys:
        prev    = prev_metrics.get(k)
        curr    = curr_metrics.get(k)
        verdict = classify(prev, curr)
        delta   = round(curr - prev, 4) if prev is not None and curr is not None else None
        results.append({"key": k, "verdict": verdict, "prev": prev, "curr": curr, "delta": delta})

    # Sort by verdict severity first (REGRESSED→IMPROVED→STABLE), then by change magnitude
    return sorted(
        results,
        key=lambda x: (
            _VERDICT_ORDER.get(x["verdict"], 9),
            -(abs(x["delta"]) if x["delta"] is not None else 0),
        ),
    )


def verdict_summary(classifications: list[dict]) -> str:
    """Return a one-line summary string: '2 REGRESSED · 1 IMPROVED · 3 STABLE'."""
    counts = {"REGRESSED": 0, "IMPROVED": 0, "STABLE": 0, "NEW": 0}
    for c in classifications:
        counts[c["verdict"]] = counts.get(c["verdict"], 0) + 1
    parts = []
    if counts["REGRESSED"]:
        parts.append(f"{counts['REGRESSED']} REGRESSED")
    if counts["IMPROVED"]:
        parts.append(f"{counts['IMPROVED']} IMPROVED")
    if counts["STABLE"]:
        parts.append(f"{counts['STABLE']} STABLE")
    if counts["NEW"]:
        parts.append(f"{counts['NEW']} NEW")
    return " · ".join(parts) if parts else "NO METRICS"


# ── LLM analysis ──────────────────────────────────────────────────────────────

def _build_client(cfg: dict) -> OpenAI:
    llm = cfg["llm"]
    api_version = os.environ.get("LLM_API_VERSION") or llm.get("api_version", "")
    kwargs: dict = {
        "base_url": os.environ.get("LLM_BASE_URL") or llm["base_url"],
        "api_key":  os.environ.get("LLM_API_KEY")  or llm["api_key"],
    }
    if api_version:
        kwargs["default_query"] = {"api-version": api_version}
    return OpenAI(**kwargs)


def _model(cfg: dict) -> str:
    return os.environ.get("LLM_MODEL") or cfg["llm"]["model"]


def _build_prompt(bot_name: str, old_model: str, new_model: str,
                  classifications: list[dict], ai_reasons: list[str]) -> str:

    regressed = [c for c in classifications if c["verdict"] == "REGRESSED"]
    improved  = [c for c in classifications if c["verdict"] == "IMPROVED"]
    stable    = [c for c in classifications if c["verdict"] == "STABLE"]
    new_      = [c for c in classifications if c["verdict"] == "NEW"]

    def _row(c):
        p = f"{c['prev']:.4f}" if c["prev"] is not None else "N/A"
        q = f"{c['curr']:.4f}" if c["curr"] is not None else "N/A"
        d = f"{c['delta']:+.4f}" if c["delta"] is not None else "N/A"
        return f"  {c['key']}: {p} → {q}  (Δ {d})"

    def _section(items, label):
        if not items:
            return ""
        return f"{label}\n" + "\n".join(_row(c) for c in items) + "\n\n"

    table = (
        _section(regressed, "▼ REGRESSED:")
        + _section(improved,  "▲ IMPROVED:")
        + _section(stable,    "● STABLE:")
        + _section(new_,      "★ NEW (no baseline):")
    ) or "  No metrics available.\n"

    reasons = "\n".join(f"  - {r}" for r in ai_reasons[:20]) if ai_reasons else "  None available."

    return f"""You are an AI quality analyst measuring response variation after a model swap in a Copilot Studio agent.

Agent: {bot_name}
Model swap: {old_model}  →  {new_model}

Metric comparison (previous → current):
{table}
Sample AI evaluation reasons from failing/notable test cases:
{reasons}

Focus your analysis on regressions first. Identify:
1. Which metrics regressed and by how much — is this significant or noise?
2. Which metrics improved — is this meaningful?
3. Patterns in the AI reasons (topic clusters, capability gaps)
4. Root cause hypothesis for any regressions
5. Recommendation: proceed with new model / investigate further / revert

Be concise. Use plain language. Lead with the most important finding. No bullet lists — short paragraphs."""


def analyse_variation(bot_name: str, old_model: str, new_model: str,
                  test_sets: dict,
                  prev_run: dict | None,
                  cfg: dict) -> str:
    curr_metrics = extract_metrics_for_report(test_sets)
    prev_metrics = (
        extract_metrics_for_report(prev_run.get("testSets", {}))
        if prev_run else {}
    )

    classifications = classify_run(prev_metrics, curr_metrics)

    ai_reasons = []
    for _type, wrapper in test_sets.items():
        if isinstance(wrapper, dict):
            run_result = wrapper.get("results", wrapper)
            for case in run_result.get("testCasesResults", []):
                for m in case.get("metricsResults", []):
                    r = m.get("result", {}).get("aiResultReason", "")
                    if r:
                        ai_reasons.append(r)

    if not prev_metrics:
        return (f"No previous run available for {bot_name}. "
                f"Baseline established for model {new_model}. "
                f"Current metrics: {json.dumps(curr_metrics, indent=2)}")

    prompt = _build_prompt(bot_name, old_model, new_model, classifications, ai_reasons)

    try:
        client   = _build_client(cfg)
        response = client.chat.completions.create(
            model=_model(cfg),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        return response.choices[0].message.content
    except Exception as e:
        summary = verdict_summary(classifications)
        return (f"LLM analysis unavailable ({e}).\n"
                f"Verdict: {summary}\n"
                f"Metrics: {json.dumps(curr_metrics, indent=2)}")
