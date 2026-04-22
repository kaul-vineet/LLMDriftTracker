"""
agent/report.py — HTML model-swap impact report with Ouroboros dark theme.

Layout (regression-first):
  Header → Verdict hero → LLM Analysis → Metric type summary table →
  Per-metric-type sections (REGRESSED expanded) → Radar chart
"""
import html
import json
import math
import uuid
from datetime import datetime, timezone

# Ouroboros palette
C_BG      = "#0a0a0f"
C_CARD    = "#12121a"
C_BORDER  = "#1a1a2e"
C_CYAN    = "#00f0ff"
C_MAGENTA = "#ff00aa"
C_GOLD    = "#ffd700"
C_RED     = "#ff4444"
C_GREEN   = "#28c840"
C_DIM     = "#666666"
C_TEXT    = "#e0e0e0"
FONT      = "'SF Mono','Cascadia Code','Fira Code',monospace"


def _esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def _radar_value(v, is_rate: bool) -> float:
    if v is None or not math.isfinite(float(v)) if isinstance(v, (int, float)) else True:
        return 0
    return round(float(v) * 100, 1) if is_rate else round(float(v), 1)


def _badge(status: str) -> str:
    color = C_GREEN if status == "Pass" else C_RED
    return (f"<span style='background:{color};color:#000;border-radius:3px;"
            f"padding:1px 8px;font-size:0.72rem;font-weight:700;font-family:{FONT}'>{status}</span>")


def _verdict_badge(verdict: str) -> str:
    colors = {"REGRESSED": C_RED, "IMPROVED": C_GREEN, "STABLE": C_DIM, "NEW": C_GOLD}
    c = colors.get(verdict, C_DIM)
    return (f"<span style='color:{c};font-weight:700;font-family:{FONT};"
            f"letter-spacing:1px;font-size:0.75rem'>{verdict}</span>")


def _fmt_score(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.0f}"
    except (ValueError, TypeError):
        return str(v)


def _extract_cases_by_type(test_sets: dict) -> dict[str, list[dict]]:
    """Return {metric_type: [{caseId, status, score, reason}]} for each type."""
    out = {}
    for metric_type, wrapper in test_sets.items():
        run_result = wrapper.get("results", wrapper) if isinstance(wrapper, dict) else {}
        cases = []
        for case in run_result.get("testCasesResults", []):
            cid = case.get("testCaseId", "")
            for m in case.get("metricsResults", []):
                r   = m.get("result", {})
                raw = r.get("data", {}).get("score")
                try:
                    score = float(raw)
                except (ValueError, TypeError):
                    score = None
                cases.append({
                    "caseId": cid,
                    "status": r.get("status", ""),
                    "score":  score,
                    "reason": r.get("aiResultReason", ""),
                })
        out[metric_type] = cases
    return out


def _metric_section(metric_type: str, verdict: str,
                    prev_cases: list[dict], curr_cases: list[dict]) -> str:
    """Per-metric-type expandable section with delta bar."""
    sid = uuid.uuid4().hex[:6]

    # Build per-case deltas
    prev_by_id = {c["caseId"]: c for c in prev_cases}
    rows_html  = ""
    failures   = []

    def _delta(cc):
        pc = prev_by_id.get(cc["caseId"], {})
        if isinstance(pc.get("score"), float) and isinstance(cc.get("score"), float):
            return cc["score"] - pc["score"]
        return 0

    sorted_curr = sorted(curr_cases, key=_delta)
    cases_detail_html = ""

    for i, cc in enumerate(sorted_curr):
        pc          = prev_by_id.get(cc["caseId"], {})
        ps          = pc.get("status", "—")
        cs          = cc.get("status", "—")
        psc         = pc.get("score")
        csc         = cc.get("score")
        prev_reason = (pc.get("reason") or "") if pc else ""
        curr_reason = cc.get("reason") or ""

        if isinstance(psc, float) and isinstance(csc, float):
            d     = csc - psc
            sign  = "+" if d >= 0 else ""
            dcol  = C_GREEN if d > 2 else (C_RED if d < -2 else C_DIM)
            dcell = (f"<td style='text-align:right;color:{dcol};font-weight:700;"
                     f"font-family:{FONT}'>{sign}{d:.0f}</td>")
            d_val = d
        else:
            dcell = f"<td style='color:{C_DIM}'>—</td>"
            d_val = None

        rows_html += (
            f"<tr style='border-bottom:1px solid {C_BORDER}'>"
            f"<td style='color:{C_DIM};padding:6px 8px'>{i+1}</td>"
            f"<td style='padding:6px 8px'>{_badge(ps) if ps != '—' else '—'}</td>"
            f"<td style='text-align:right;font-family:{FONT};padding:6px 8px'>{_fmt_score(psc)}</td>"
            f"<td style='padding:6px 8px'>{_badge(cs) if cs != '—' else '—'}</td>"
            f"<td style='text-align:right;font-family:{FONT};padding:6px 8px'>{_fmt_score(csc)}</td>"
            f"{dcell}"
            f"</tr>"
        )

        d_str      = f"{d_val:+.0f}" if d_val is not None else "—"
        border_col = C_RED if (d_val is not None and d_val < -2) else (
                     C_GREEN if (d_val is not None and d_val > 2) else C_BORDER)
        detail_open = " open" if (d_val is not None and d_val < -2) else ""
        prev_block  = (
            f"<div style='font-size:0.65rem;color:{C_DIM};letter-spacing:1px;"
            f"font-family:{FONT};margin-bottom:4px'>BASELINE EVALUATION</div>"
            f"<div style='font-size:0.82rem;color:{C_DIM};line-height:1.6;"
            f"margin-bottom:12px'>{_esc(prev_reason)}</div>"
        ) if prev_reason else ""
        cases_detail_html += (
            f"<details{detail_open} style='margin-bottom:6px;background:{C_BG};"
            f"border-left:2px solid {border_col};border-radius:0 4px 4px 0;overflow:hidden'>"
            f"<summary style='padding:8px 12px;cursor:pointer;font-family:{FONT};"
            f"font-size:0.78rem;color:{C_DIM};list-style:none'>"
            f"Case {i+1} &nbsp;·&nbsp; {_badge(ps)} {_fmt_score(psc)} "
            f"→ {_badge(cs)} {_fmt_score(csc)} &nbsp;·&nbsp; Δ {d_str}"
            f"</summary>"
            f"<div style='padding:12px 16px'>"
            f"{prev_block}"
            f"<div style='font-size:0.65rem;color:{C_CYAN};letter-spacing:1px;"
            f"font-family:{FONT};margin-bottom:4px'>CURRENT EVALUATION</div>"
            f"<div style='font-size:0.82rem;color:{C_TEXT};line-height:1.6'>{_esc(curr_reason)}</div>"
            f"</div></details>"
        )

    failures_html = ""

    v_colors   = {"REGRESSED": C_RED, "IMPROVED": C_GREEN, "STABLE": C_DIM, "NEW": C_GOLD}
    v_color    = v_colors.get(verdict, C_DIM)
    border_col = v_color

    table = "" if not rows_html else f"""
    <table style='width:100%;border-collapse:collapse;font-size:0.82rem;margin-top:12px'>
      <thead>
        <tr style='background:{C_BG};color:{C_DIM}'>
          <th style='text-align:left;padding:6px 8px;font-weight:600'>#</th>
          <th style='padding:6px 8px;font-weight:600'>Baseline</th>
          <th style='text-align:right;padding:6px 8px;font-weight:600'>Score</th>
          <th style='padding:6px 8px;font-weight:600'>Current</th>
          <th style='text-align:right;padding:6px 8px;font-weight:600'>Score</th>
          <th style='text-align:right;padding:6px 8px;font-weight:600'>Δ</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>"""

    details_section = (
        f"<div style='margin-top:14px'>"
        f"<div style='font-size:0.65rem;font-weight:700;color:{C_DIM};"
        f"letter-spacing:2px;margin-bottom:8px;font-family:{FONT}'>CASE EVALUATIONS</div>"
        f"{cases_detail_html}</div>"
    ) if cases_detail_html else ""

    no_prev_note = "" if prev_cases else (
        f"<div style='color:{C_GOLD};font-size:0.75rem;margin-top:8px;font-family:{FONT}'>"
        f"★ No previous run — baseline established</div>"
    )

    return f"""
    <div style='border:1px solid {border_col};border-radius:8px;margin-bottom:12px;
                background:{C_CARD};overflow:hidden'>
      <div style='padding:12px 16px;border-bottom:1px solid {C_BORDER};
                  display:flex;justify-content:space-between;align-items:center'>
        <span style='font-weight:700;color:{C_TEXT};font-family:{FONT};
                     letter-spacing:1px'>{metric_type}</span>
        {_verdict_badge(verdict)}
      </div>
      <div style='padding:12px 16px'>
        {no_prev_note}
        {table}
        {details_section}
      </div>
    </div>"""


def _bot_section(br: dict) -> str:
    bot_name        = _esc(br["botName"])
    old_model       = _esc(br["oldModel"])
    new_model       = _esc(br["newModel"])
    run_folder      = br.get("runFolder", "")
    verdict_line    = br.get("verdictSummary", "")
    analysis        = br.get("analysis", "")
    classifications = br.get("classifications", [])
    curr_test_sets  = br.get("currRun", {}).get("testSets", {})
    prev_run        = br.get("prevRun")

    curr_cases_by_type = _extract_cases_by_type(curr_test_sets)
    prev_cases_by_type = _extract_cases_by_type(
        prev_run.get("testSets", {}) if prev_run else {}
    )

    # Verdict pill color
    reg_count = sum(1 for c in classifications if c["verdict"] == "REGRESSED")
    imp_count = sum(1 for c in classifications if c["verdict"] == "IMPROVED")
    v_color   = C_RED if reg_count else (C_GREEN if imp_count else C_DIM)

    # Metric summary table rows (sorted by verdict)
    _order = {"REGRESSED": 0, "IMPROVED": 1, "STABLE": 2, "NEW": 3}
    sorted_cls = sorted(classifications, key=lambda c: _order.get(c["verdict"], 9))

    def _fv(v, spec=".4f"):
        return "N/A" if v is None else format(v, spec)

    def _delta_col(delta):
        d = delta or 0
        return C_GREEN if d > 0 else (C_RED if d < 0 else C_DIM)

    metric_rows = "".join(
        f"<tr style='border-bottom:1px solid {C_BORDER}'>"
        f"<td style='padding:5px 10px;font-family:{FONT};font-size:0.78rem;color:{C_TEXT}'>{c['key']}</td>"
        f"<td style='padding:5px 10px;text-align:right;font-family:{FONT};color:{C_DIM}'>"
        f"{_fv(c['prev'])}</td>"
        f"<td style='padding:5px 10px;text-align:right;font-family:{FONT};color:{C_TEXT}'>"
        f"{_fv(c['curr'])}</td>"
        f"<td style='padding:5px 10px;text-align:right'>{_verdict_badge(c['verdict'])}</td>"
        f"<td style='padding:5px 10px;text-align:right;font-family:{FONT};"
        f"color:{_delta_col(c['delta'])};font-weight:700'>"
        f"{_fv(c['delta'], '+.4f')}</td>"
        f"</tr>"
        for c in sorted_cls
    )

    # Per-metric-type sections sorted REGRESSED first
    verdict_by_type: dict[str, str] = {}
    for c in classifications:
        for mt in curr_cases_by_type:
            if c["key"].startswith(mt + "."):
                # Aggregate: if any key for this type is REGRESSED, type is REGRESSED
                existing = verdict_by_type.get(mt, "STABLE")
                prio = {"REGRESSED": 0, "IMPROVED": 1, "STABLE": 2, "NEW": 3}
                if prio.get(c["verdict"], 9) < prio.get(existing, 9):
                    verdict_by_type[mt] = c["verdict"]

    for mt in curr_cases_by_type:
        if mt not in verdict_by_type:
            verdict_by_type[mt] = "NEW"

    sorted_types = sorted(
        curr_cases_by_type.keys(),
        key=lambda t: _order.get(verdict_by_type.get(t, "STABLE"), 9),
    )

    type_sections = "".join(
        _metric_section(
            mt,
            verdict_by_type.get(mt, "STABLE"),
            prev_cases_by_type.get(mt, []),
            curr_cases_by_type[mt],
        )
        for mt in sorted_types
    )

    # Radar data for Chart.js
    sid          = uuid.uuid4().hex[:8]
    metric_keys  = [c["key"] for c in classifications]
    radar_labels = json.dumps([k.split(".")[-1][:16] for k in metric_keys])
    radar_prev   = json.dumps([_radar_value(c["prev"], "passRate" in c["key"]) for c in classifications])
    radar_curr   = json.dumps([_radar_value(c["curr"], "passRate" in c["key"]) for c in classifications])

    force_eval  = old_model == new_model
    model_line  = (
        f"<span style='color:{C_DIM}'>Force evaluation — model unchanged: {new_model}</span>"
        if force_eval else
        f"<span style='color:{C_DIM};font-family:{FONT}'>{old_model}</span>"
        f" <span style='color:{C_MAGENTA}'>→</span> "
        f"<span style='color:{C_CYAN};font-family:{FONT};font-weight:700'>{new_model}</span>"
    )

    return f"""
    <section style='margin-bottom:2.5rem;border:1px solid {C_BORDER};border-radius:12px;
                    overflow:hidden;background:{C_CARD}'>

      <!-- Header -->
      <div style='background:{C_BG};padding:20px 24px;
                  border-bottom:1px solid {C_BORDER};
                  display:flex;justify-content:space-between;align-items:flex-start'>
        <div>
          <div style='font-size:1.1rem;font-weight:700;color:{C_TEXT};
                      font-family:{FONT};letter-spacing:1px'>{bot_name}</div>
          <div style='font-size:0.85rem;margin-top:4px'>{model_line}</div>
          <div style='font-size:0.65rem;color:{C_DIM};margin-top:4px;
                      font-family:{FONT}'>run: {run_folder}</div>
        </div>
        <div style='text-align:right'>
          <div style='color:{v_color};font-weight:700;font-family:{FONT};
                      letter-spacing:2px;font-size:0.85rem'>{verdict_line}</div>
        </div>
      </div>

      <div style='padding:20px 24px'>

        <!-- LLM Analysis -->
        <div style='margin-bottom:20px;padding:16px 20px;
                    background:{C_BG};border-left:3px solid {C_MAGENTA};border-radius:0 6px 6px 0'>
          <div style='font-size:0.68rem;font-weight:700;color:{C_MAGENTA};
                      letter-spacing:2px;margin-bottom:8px;font-family:{FONT}'>⚡ RESPONSE VARIATION ANALYSIS</div>
          <div style='font-size:0.875rem;line-height:1.75;color:{C_TEXT};white-space:pre-wrap'>{_esc(analysis)}</div>
        </div>

        <!-- Metric Summary Table -->
        <div style='margin-bottom:20px'>
          <div style='font-size:0.68rem;font-weight:700;color:{C_DIM};
                      letter-spacing:2px;margin-bottom:10px;font-family:{FONT}'>METRIC SUMMARY</div>
          <table style='width:100%;border-collapse:collapse;font-size:0.82rem'>
            <thead>
              <tr style='background:{C_BG}'>
                <th style='text-align:left;padding:6px 10px;color:{C_DIM};font-weight:600'>Metric</th>
                <th style='text-align:right;padding:6px 10px;color:{C_DIM};font-weight:600'>Prev</th>
                <th style='text-align:right;padding:6px 10px;color:{C_DIM};font-weight:600'>Curr</th>
                <th style='text-align:right;padding:6px 10px;color:{C_DIM};font-weight:600'>Verdict</th>
                <th style='text-align:right;padding:6px 10px;color:{C_DIM};font-weight:600'>Δ</th>
              </tr>
            </thead>
            <tbody>
              {metric_rows or f'<tr><td colspan="5" style="color:{C_DIM};padding:10px;text-align:center">No previous run — baseline established</td></tr>'}
            </tbody>
          </table>
        </div>

        <!-- Radar Chart -->
        {'<div style="margin-bottom:20px"><div style="font-size:0.68rem;font-weight:700;color:'+C_DIM+';letter-spacing:2px;margin-bottom:10px;font-family:'+FONT+'">RADAR — CAPABILITY DIMENSIONS</div><canvas id="radar_'+sid+'" height="180"></canvas></div>' if metric_keys else ''}

        <!-- Per-metric-type sections -->
        <div style='margin-top:4px'>
          <div style='font-size:0.68rem;font-weight:700;color:{C_DIM};
                      letter-spacing:2px;margin-bottom:12px;font-family:{FONT}'>PER METRIC TYPE</div>
          {type_sections or f'<div style="color:{C_DIM}">No test case data available.</div>'}
        </div>

      </div>
    </section>

    <script>
    (function(){{
      var ctx = document.getElementById('radar_{sid}');
      if (!ctx || {json.dumps(not bool(metric_keys))}) return;
      new Chart(ctx, {{
        type: 'radar',
        data: {{
          labels: {radar_labels},
          datasets: [
            {{
              label: 'Previous',
              data: {radar_prev},
              borderColor: '{C_GOLD}',
              backgroundColor: 'rgba(255,215,0,0.08)',
              pointBackgroundColor: '{C_GOLD}',
              pointRadius: 4,
              borderWidth: 2,
            }},
            {{
              label: 'Current',
              data: {radar_curr},
              borderColor: '{C_CYAN}',
              backgroundColor: 'rgba(0,240,255,0.08)',
              pointBackgroundColor: '{C_CYAN}',
              pointRadius: 4,
              borderWidth: 2,
            }},
          ]
        }},
        options: {{
          responsive: false,
          plugins: {{
            legend: {{
              position: 'bottom',
              labels: {{ color: '{C_DIM}', font: {{ family: '{FONT}', size: 10 }} }}
            }}
          }},
          scales: {{
            r: {{
              min: 0, max: 100,
              ticks: {{ stepSize: 25, color: '{C_DIM}', font: {{ size: 9 }}, backdropColor: 'transparent' }},
              pointLabels: {{ color: '{C_TEXT}', font: {{ size: 10 }} }},
              grid: {{ color: '{C_BORDER}' }},
              angleLines: {{ color: '{C_BORDER}' }},
            }}
          }}
        }}
      }});
    }})();
    </script>"""


def generate_report(bot_results: list[dict]) -> str:
    ts    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    count = len(bot_results)

    total_reg = sum(
        sum(1 for c in br.get("classifications", []) if c["verdict"] == "REGRESSED")
        for br in bot_results
    )
    total_imp = sum(
        sum(1 for c in br.get("classifications", []) if c["verdict"] == "IMPROVED")
        for br in bot_results
    )

    sections = "".join(_bot_section(br) for br in bot_results)

    hero_color = C_RED if total_reg else (C_GREEN if total_imp else C_DIM)

    return f"""<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset='UTF-8'>
  <title>āshokā — Response Variation Report — {ts}</title>
  <script src='https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js'></script>
  <style>
    * {{ box-sizing:border-box; margin:0; padding:0 }}
    body {{
      font-family: {FONT};
      background: {C_BG};
      color: {C_TEXT};
      padding: 2rem;
    }}
    h1 {{ font-size:1.4rem; font-weight:700; color:{C_CYAN}; letter-spacing:3px }}
    .sub {{ color:{C_DIM}; font-size:0.8rem; margin-bottom:2.5rem; letter-spacing:1px }}
  </style>
</head>
<body>
  <h1>⚡ āshokā</h1>
  <div class='sub'>{ts} &nbsp;·&nbsp; {count} agent(s) evaluated &nbsp;·&nbsp;
    <span style='color:{hero_color};font-weight:700'>{total_reg} REGRESSED · {total_imp} IMPROVED</span>
  </div>
  {sections}
</body>
</html>"""
