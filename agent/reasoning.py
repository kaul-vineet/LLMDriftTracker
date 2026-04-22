# -*- coding: utf-8 -*-
"""
agent/reasoning.py - metric extraction, response variation classification, LLM analysis.

classify_run() returns verdicts sorted REGRESSED → IMPROVED → STABLE.
_build_prompt() leads with regressions.
extract_metrics_for_report() accepts the testSets dict shape:
  dict[metric_type -> {apiRunId, results: {testCasesResults: [...]}}]
"""
import json
import os
import time
from openai import OpenAI
from . import logger as logger_mod

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
                if isinstance(val, bool):
                    totals[key] = totals.get(key, 0) + (1 if val else 0)
                    counts[key] = counts.get(key, 0) + 1
                elif isinstance(val, (int, float)):
                    totals[key] = totals.get(key, 0) + val
                    counts[key] = counts.get(key, 0) + 1
                elif isinstance(val, str):
                    try:
                        totals[key] = totals.get(key, 0) + float(val)
                        counts[key] = counts.get(key, 0) + 1
                    except ValueError:
                        pass

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


# ── Tavily web search ─────────────────────────────────────────────────────────

def _search_model_context(old_model: str, new_model: str, cfg: dict) -> str:
    """Search for model-specific context via Tavily. Returns '' if key not set or search fails."""
    api_key = (cfg.get("tavily_api_key") or "").strip()
    if not api_key:
        return ""
    queries = [f"{new_model} release notes known issues instruction following"]
    if old_model.strip() and old_model != new_model:
        queries.append(f"{old_model} vs {new_model} documented capability differences")
    queries.append("Microsoft Copilot Studio best practices system prompt quality improvement")
    log = logger_mod.get()
    try:
        from tavily import TavilyClient
        client  = TavilyClient(api_key=api_key)
        chunks  = []
        for q in queries:
            resp = client.search(q, max_results=3, search_depth="basic")
            for r in resp.get("results", []):
                content = (r.get("content") or "").strip()
                url     = r.get("url", "")
                if content:
                    chunks.append(f"Source: {url}\n{content[:600]}")
        if not chunks:
            return ""
        log.info(f"Tavily search returned {len(chunks)} result(s) for {new_model}")
        return "\n\n".join(chunks)
    except Exception as e:
        log.error(f"Tavily search failed: {e}")
        return ""


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
    api_version = llm.get("api_version", "")
    kwargs: dict = {
        "base_url": llm["base_url"],
        "api_key":  llm["api_key"],
    }
    if api_version:
        kwargs["default_query"] = {"api-version": api_version}
    return OpenAI(**kwargs)


def _model(cfg: dict) -> str:
    return cfg["llm"]["model"]


def _extract_cases_by_type(test_sets: dict) -> dict[str, list[dict]]:
    """Extract per-case data from test_sets for per-case prompt comparison."""
    out: dict[str, list[dict]] = {}
    for metric_type, wrapper in test_sets.items():
        run_result = wrapper.get("results", wrapper) if isinstance(wrapper, dict) else {}
        cases = []
        for case in run_result.get("testCasesResults", []):
            cid = case.get("testCaseId", "")
            for m in case.get("metricsResults", []):
                r   = m.get("result", {})
                raw = r.get("data", {}).get("score")
                try:   score = float(raw)
                except: score = None
                cases.append({
                    "caseId": cid,
                    "status": r.get("status", ""),
                    "score":  score,
                    "reason": r.get("aiResultReason", ""),
                })
        out[metric_type] = cases
    return out


def _build_prompt(bot_name: str, old_model: str, new_model: str,
                  classifications: list[dict],
                  instructions: str = "",
                  prev_cases_by_type: dict | None = None,
                  curr_cases_by_type: dict | None = None,
                  extra_context: str = "") -> str:

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

    metric_table = (
        _section(regressed, "▼ REGRESSED:")
        + _section(improved,  "▲ IMPROVED:")
        + _section(stable,    "● STABLE:")
        + _section(new_,      "★ NEW (no baseline):")
    ) or "  No comparable metrics.\n"

    # Per-case comparison: old reason vs new reason for each test case
    case_lines: list[str] = []
    if prev_cases_by_type and curr_cases_by_type:
        for metric_type, curr_cases in curr_cases_by_type.items():
            prev_cases = (prev_cases_by_type or {}).get(metric_type, [])
            prev_by_id = {c["caseId"]: c for c in prev_cases}
            for i, cc in enumerate(curr_cases):
                pc     = prev_by_id.get(cc["caseId"], {})
                old_s  = pc.get("status", "—") if pc else "—"
                old_sc = pc.get("score") if pc else None
                new_s  = cc.get("status", "—")
                new_sc = cc.get("score")
                old_r  = pc.get("reason", "") if pc else ""
                new_r  = cc.get("reason", "")
                if old_sc is not None and new_sc is not None:
                    d   = new_sc - old_sc
                    tag = "▼ REGRESSION" if d < -2 else ("▲ IMPROVEMENT" if d > 2 else "● STABLE")
                elif not pc:
                    tag = "★ NEW"
                else:
                    tag = "?"
                old_str = (f"{old_s} / score {int(old_sc) if old_sc is not None else '?'}"
                           if pc else "no baseline")
                new_str = f"{new_s} / score {int(new_sc) if new_sc is not None else '?'}"
                case_lines.append(
                    f"\nCase {i+1}  [{old_str}  →  {new_str}]  {tag}"
                )
                if old_r:
                    case_lines.append(f"  {old_model}: {old_r}")
                case_lines.append(f"  {new_model}: {new_r}")

    cases_section = "\n".join(case_lines) if case_lines else "  Per-case data not available."
    instructions_section = (
        f"\nAgent system prompt (first 400 chars):\n{instructions[:400]}\n"
        if instructions else ""
    )
    extra_section = (
        f"\n## Additional context (provided by user)\n{extra_context.strip()}\n"
        if extra_context and extra_context.strip() else ""
    )
    force_eval = old_model == new_model

    if force_eval:
        task_line  = "Same model used in both runs (force evaluation - no model swap). Analyse consistency and variance."
        model_line = "Model: " + new_model
        questions  = (
            "Tell the story of this agent's consistency. Both runs used the same model, "
            "so any variation is signal about the agent itself - its prompts, its test cases, "
            "or inherent model variance. Which cases are persistently failing, and what do they "
            "have in common? Where is the variance acceptable and where is it a warning sign? "
            "What does the pattern tell an architect about where to invest in improving this agent?"
        )
    else:
        task_line  = "Analyse the quality impact of a model swap from " + old_model + " to " + new_model + "."
        model_line = "Old model: " + old_model + "\nNew model: " + new_model
        questions  = (
            "Tell the story of what happened when this agent moved from " + old_model + " to " + new_model + ".\n\n"
            "Ground every claim solely in the evidence above — the scores, statuses, and evaluator reasons "
            "in the case data. Do not assume or speculate about model capabilities, training data, "
            "or architecture beyond what the results directly show.\n\n"
            "Cover: which cases changed and why (cite the specific case evidence); "
            "what the pattern of failures reveals about how the new model handles this agent's tasks; "
            "what stayed stable and what that reveals about the agent's strengths."
        )

    return (
        "You are āshokā, an autonomous AI quality sentinel embedded inside a Copilot Studio monitoring platform. "
        "Your audience is a mixed group: solution architects who care about root cause and technical remediation, "
        "and business stakeholders who care about impact and decision. "
        "Write as if you are briefing both in the same room — tell them a story about what happened to this agent, "
        "not a report. Use a narrative voice: set the scene, build to the finding, land on best-practice guidance. "
        "No bullet lists. No headers. No numbered sections. Flowing prose only, "
        "organised as: what changed and where, why it happened (grounded in the case evidence), "
        "what it means for the agent's users, and what the best practice response looks like. "
        "Do NOT include a verdict label (PROCEED, INVESTIGATE, REVERT, or any equivalent). "
        "Do NOT use bold labels or section markers of any kind.\n\n"
        "## Task\n" + task_line + "\n\n"
        "## Agent\n"
        "Name: " + bot_name + instructions_section + "\n"
        + model_line + "\n\n"
        "## Aggregate metric shift\n"
        + metric_table + extra_section
        + "## Per-case evaluation comparison\n"
        "Scores: 0=completely wrong · 25=major mismatch · 50=partial · 75=mostly correct · 100=perfect\n"
        "For each case: OLD model (" + old_model + ") reason, then NEW model (" + new_model + ") reason.\n"
        + cases_section + "\n\n"
        "## Research questions\n"
        + questions + "\n\n"
        "Write 3 to 5 paragraphs. Open with what the data revealed the moment runs were compared. "
        "Build through the evidence to explain why. Close with the best-practice response — "
        "what a skilled Copilot Studio architect should do next, grounded in the failure pattern above. "
        "Speak plainly. Every claim must be traceable to a specific case or metric in the data above."
    )


def _build_bp_prompt(bot_name: str, old_model: str, new_model: str,
                     analysis: str, classifications: list[dict]) -> str:
    """Second-call prompt: best-practice recommendations grounded in the analysis."""
    regressed = [c["key"] for c in classifications if c["verdict"] == "REGRESSED"]
    improved  = [c["key"] for c in classifications if c["verdict"] == "IMPROVED"]
    metric_ctx = ""
    if regressed:
        metric_ctx += f"Regressed: {', '.join(regressed)}\n"
    if improved:
        metric_ctx += f"Improved: {', '.join(improved)}\n"
    return (
        "You are āshokā. You produced this analysis:\n\n"
        f"{analysis}\n\n"
        f"Agent: {bot_name}  ·  {old_model} → {new_model}\n"
        f"{metric_ctx}\n"
        "In 1-2 paragraphs of flowing prose — no headers, no bullets — "
        "add the best-practice layer for a Microsoft Copilot Studio solution architect. "
        "Consider: system prompt restructuring, grounding with knowledge sources, "
        "expanding test coverage to target the failing patterns, rollback decision criteria, "
        "and communicating impact to business stakeholders. "
        "Base every recommendation solely on the evidence in the analysis above — "
        "no assumptions, no speculation beyond what the data shows. "
        "Write as a natural continuation of the narrative."
    )


def analyse_variation(bot_name: str, old_model: str, new_model: str,
                      test_sets: dict,
                      prev_run: dict | None,
                      cfg: dict,
                      instructions: str = "",
                      extra_context: str = "") -> str:
    curr_metrics = extract_metrics_for_report(test_sets)
    prev_metrics = (
        extract_metrics_for_report(prev_run.get("testSets", {}))
        if prev_run else {}
    )
    classifications = classify_run(prev_metrics, curr_metrics)

    curr_cases_by_type = _extract_cases_by_type(test_sets)
    prev_cases_by_type = (
        _extract_cases_by_type(prev_run.get("testSets", {})) if prev_run else {}
    )

    if not prev_metrics:
        return (f"No previous run available for {bot_name}. "
                f"Baseline established for model {new_model}. "
                f"Current metrics: {json.dumps(curr_metrics, indent=2)}")

    if not extra_context:
        extra_context = _search_model_context(old_model, new_model, cfg)

    prompt = _build_prompt(
        bot_name, old_model, new_model, classifications, instructions,
        prev_cases_by_type, curr_cases_by_type, extra_context,
    )

    log      = logger_mod.get()
    model_id = _model(cfg)
    log.debug(f"LLM analysis call 1 — {bot_name} ({old_model} → {new_model}) model={model_id}",
              extra={"bot": bot_name, "model": model_id, "prompt": prompt})
    try:
        client = _build_client(cfg)
        t0     = time.monotonic()
        resp   = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
        )
        analysis_text = resp.choices[0].message.content
        duration_ms   = int((time.monotonic() - t0) * 1000)
        log.debug(f"LLM analysis call 1 complete — {bot_name} {len(analysis_text)} chars {duration_ms}ms",
                  extra={"bot": bot_name, "model": model_id,
                         "response": analysis_text, "duration_ms": duration_ms})

        non_stable = [c for c in classifications if c["verdict"] in ("REGRESSED", "IMPROVED")]
        if non_stable:
            bp_prompt = _build_bp_prompt(bot_name, old_model, new_model, analysis_text, classifications)
            log.debug(f"LLM analysis call 2 (best practices) — {bot_name}",
                      extra={"bot": bot_name, "model": model_id, "prompt": bp_prompt})
            bp_resp = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": bp_prompt}],
                max_tokens=400,
            )
            bp_text     = bp_resp.choices[0].message.content
            bp_duration = int((time.monotonic() - t0) * 1000) - duration_ms
            log.debug(f"LLM analysis call 2 complete — {bot_name} {len(bp_text)} chars {bp_duration}ms",
                      extra={"bot": bot_name, "model": model_id, "response": bp_text})
            return analysis_text + "\n\n" + bp_text

        return analysis_text
    except Exception as e:
        log.error(f"LLM analysis failed for {bot_name}: {e}",
                  extra={"bot": bot_name, "model": model_id, "error_detail": str(e)})
        summary = verdict_summary(classifications)
        return (f"LLM analysis unavailable ({e}).\n"
                f"Verdict: {summary}\n"
                f"Metrics: {json.dumps(curr_metrics, indent=2)}")
