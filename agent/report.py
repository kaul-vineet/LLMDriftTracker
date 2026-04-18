import json
import uuid
from datetime import datetime, timezone


def _delta_color(delta: float) -> str:
    if abs(delta) < 0.02:
        return "#6b7280"
    return "#16a34a" if delta > 0 else "#dc2626"


def _metric_row(key: str, prev, curr) -> str:
    if isinstance(prev, float) and isinstance(curr, float):
        delta = curr - prev
        color = _delta_color(delta)
        sign  = "+" if delta >= 0 else ""
        return (f"<tr>"
                f"<td>{key}</td>"
                f"<td class='num'>{prev:.4f}</td>"
                f"<td class='num'>{curr:.4f}</td>"
                f"<td class='num' style='color:{color};font-weight:600'>{sign}{delta:.4f}</td>"
                f"</tr>")
    return f"<tr><td>{key}</td><td class='num'>{prev}</td><td class='num'>{curr}</td><td>—</td></tr>"


def _extract_cases(run_results: dict | None) -> dict:
    out = {}
    for case in (run_results or {}).get("testCasesResults", []):
        cid = case.get("testCaseId", "")
        for m in case.get("metricsResults", []):
            r = m.get("result", {})
            raw = r.get("data", {}).get("score")
            try:
                score = float(raw)
            except (ValueError, TypeError):
                score = None
            out[cid] = {
                "status": r.get("status", ""),
                "score":  score,
                "reason": r.get("aiResultReason", ""),
            }
    return out


def _badge(status: str) -> str:
    color = "#16a34a" if status == "Pass" else "#dc2626"
    return (f"<span style='background:{color};color:#fff;border-radius:3px;"
            f"padding:1px 7px;font-size:0.75rem;white-space:nowrap'>{status}</span>")


def _fmt(score) -> str:
    return f"{score:.0f}" if isinstance(score, float) else "—"


def _bot_section(bot_name: str, old_model: str, new_model: str,
                 prev_metrics: dict, curr_metrics: dict,
                 analysis: str, run_id: str,
                 prev_run: dict | None = None,
                 curr_run_results: dict | None = None) -> str:

    sid        = uuid.uuid4().hex[:8]
    force_eval = old_model == new_model

    prev_run_id = (prev_run or {}).get("runId", "")[:8]
    stored      = (prev_run or {}).get("storedAt", "")
    try:
        prev_date = datetime.fromisoformat(stored).strftime("%b %d %H:%M")
    except Exception:
        prev_date = stored[:16]
    curr_date = datetime.now(timezone.utc).strftime("%b %d %H:%M")

    if force_eval:
        old_label  = f"Run {prev_run_id} · {prev_date}" if prev_run_id else "Previous run"
        new_label  = f"Run {run_id[:8]} · {curr_date}"
        model_line = (f"<span style='opacity:.7'>Force evaluation — "
                      f"model unchanged: {new_model}</span>")
    else:
        old_label  = old_model or "Previous"
        new_label  = new_model
        model_line = (f"<span style='opacity:.7'>{old_model}</span> &rarr; "
                      f"<span style='font-weight:700'>{new_model}</span>")

    pr_key = next((k for k in curr_metrics if "passRate" in k), None)
    sc_key = next((k for k in curr_metrics if "passRate" not in k), None)

    prev_pass  = prev_metrics.get(pr_key, 0) if pr_key else 0
    curr_pass  = curr_metrics.get(pr_key, 0) if pr_key else 0
    prev_score = prev_metrics.get(sc_key, 0) if sc_key else 0
    curr_score = curr_metrics.get(sc_key, 0) if sc_key else 0
    score_delta = curr_score - prev_score

    def card_bg(delta):
        if abs(delta) < 0.5:
            return "#1e3a5f"
        return "#14532d" if delta > 0 else "#7f1d1d"

    # Per-case data
    prev_cases = _extract_cases((prev_run or {}).get("results"))
    curr_cases = _extract_cases(curr_run_results)
    all_ids    = list(curr_cases.keys())

    # Radar
    metric_keys  = sorted(set(list(prev_metrics) + list(curr_metrics)))
    radar_labels = json.dumps([k.split(".")[-1] for k in metric_keys])

    def norm(v, k):
        if v is None:
            return 0
        return round(float(v) * 100, 1) if "passRate" in k else round(float(v), 1)

    radar_prev = json.dumps([norm(prev_metrics.get(k), k) for k in metric_keys])
    radar_curr = json.dumps([norm(curr_metrics.get(k), k) for k in metric_keys])

    # Bar chart
    case_labels    = json.dumps([f"Case {i+1}" for i in range(len(all_ids))])
    bar_prev       = json.dumps([prev_cases.get(c, {}).get("score") or 0 for c in all_ids])
    bar_curr       = json.dumps([curr_cases.get(c, {}).get("score") or 0 for c in all_ids])
    bar_col_prev   = json.dumps(["rgba(59,130,246,.65)" if prev_cases.get(c, {}).get("status") == "Pass"
                                  else "rgba(239,68,68,.65)" for c in all_ids])
    bar_col_curr   = json.dumps(["rgba(34,197,94,.75)" if curr_cases.get(c, {}).get("status") == "Pass"
                                  else "rgba(239,68,68,.85)" for c in all_ids])

    # Metric table
    metric_rows = "".join(
        _metric_row(k, prev_metrics.get(k, "N/A"), curr_metrics.get(k, "N/A"))
        for k in metric_keys
    ) or "<tr><td colspan='4' style='color:#9ca3af;text-align:center'>No previous run — baseline established</td></tr>"

    # Case table + failures
    case_rows = ""
    failures  = []
    for i, cid in enumerate(all_ids):
        pc = prev_cases.get(cid, {})
        cc = curr_cases.get(cid, {})
        ps, psc = pc.get("status", "—"), pc.get("score")
        cs, csc = cc.get("status", "—"), cc.get("score")
        reason  = cc.get("reason", "")

        if isinstance(psc, float) and isinstance(csc, float):
            d    = csc - psc
            sign = "+" if d >= 0 else ""
            dcell = f"<td class='num' style='color:{_delta_color(d)};font-weight:600'>{sign}{d:.0f}</td>"
        else:
            dcell = "<td>—</td>"

        if cs == "Fail":
            failures.append({"num": i + 1, "score": csc, "reason": reason})

        short = (reason[:110] + "…") if len(reason) > 110 else reason
        case_rows += (f"<tr>"
                      f"<td style='color:#6b7280'>{i+1}</td>"
                      f"<td>{_badge(ps) if ps != '—' else '—'}</td>"
                      f"<td class='num'>{_fmt(psc)}</td>"
                      f"<td>{_badge(cs) if cs != '—' else '—'}</td>"
                      f"<td class='num'>{_fmt(csc)}</td>"
                      f"{dcell}"
                      f"<td style='color:#6b7280;font-size:0.8rem'>{short}</td>"
                      f"</tr>")

    failure_html = ""
    if failures:
        items = "".join(
            f"<div style='margin-bottom:.75rem;padding:.75rem 1rem;background:#fff;"
            f"border-left:3px solid #dc2626;border-radius:0 4px 4px 0'>"
            f"<div style='font-weight:600;margin-bottom:.2rem'>Case {f['num']} — Score {_fmt(f['score'])}</div>"
            f"<div style='color:#374151;font-size:.875rem;line-height:1.55'>{f['reason']}</div>"
            f"</div>"
            for f in failures
        )
        failure_html = (f"<div style='margin-top:1.5rem'>"
                        f"<div style='font-size:.8rem;font-weight:600;color:#dc2626;margin-bottom:.6rem'>"
                        f"⚠ Failing Cases ({len(failures)})</div>{items}</div>")

    old_label_js = old_label.replace("'", "\\'")
    new_label_js = new_label.replace("'", "\\'")

    return f"""
    <section style='margin-bottom:2.5rem;border:1px solid #e5e7eb;border-radius:10px;
                    overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.07)'>

      <div style='background:#1e3a5f;color:#fff;padding:1.25rem 1.5rem'>
        <h2 style='margin:0;font-size:1.1rem;font-weight:700'>{bot_name}</h2>
        <div style='font-size:.85rem;margin-top:.3rem'>{model_line}</div>
        <div style='font-size:.7rem;opacity:.5;margin-top:.15rem'>Run ID: {run_id}</div>
      </div>

      <div style='display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid #e5e7eb'>
        <div style='padding:.9rem 1rem;border-right:1px solid #e5e7eb;text-align:center'>
          <div style='font-size:.7rem;color:#6b7280;text-transform:uppercase;letter-spacing:.05em'>Cases</div>
          <div style='font-size:1.5rem;font-weight:700'>{len(all_ids)}</div>
        </div>
        <div style='padding:.9rem 1rem;border-right:1px solid #e5e7eb;text-align:center'>
          <div style='font-size:.7rem;color:#6b7280;text-transform:uppercase;letter-spacing:.05em'>Prev Pass Rate</div>
          <div style='font-size:1.5rem;font-weight:700'>{prev_pass*100:.0f}%</div>
        </div>
        <div style='padding:.9rem 1rem;border-right:1px solid #e5e7eb;text-align:center'>
          <div style='font-size:.7rem;color:#6b7280;text-transform:uppercase;letter-spacing:.05em'>Curr Pass Rate</div>
          <div style='font-size:1.5rem;font-weight:700'>{curr_pass*100:.0f}%</div>
        </div>
        <div style='padding:.9rem 1rem;text-align:center;background:{card_bg(score_delta)};color:#fff'>
          <div style='font-size:.7rem;opacity:.7;text-transform:uppercase;letter-spacing:.05em'>Score Δ</div>
          <div style='font-size:1.5rem;font-weight:700'>{"+" if score_delta >= 0 else ""}{score_delta:.1f}</div>
        </div>
      </div>

      <div style='padding:1.5rem'>

        <div style='display:grid;grid-template-columns:280px 1fr;gap:1.5rem;margin-bottom:1.75rem;align-items:start'>
          <div>
            <div style='font-size:.78rem;font-weight:600;color:#374151;margin-bottom:.4rem'>Metric Radar</div>
            <canvas id='radar_{sid}' width='260' height='260'></canvas>
          </div>
          <div>
            <div style='font-size:.78rem;font-weight:600;color:#374151;margin-bottom:.4rem'>Metric Comparison</div>
            <table style='width:100%;border-collapse:collapse;font-size:.875rem'>
              <thead>
                <tr style='background:#f3f4f6'>
                  <th style='text-align:left;padding:.4rem .75rem'>Metric</th>
                  <th style='text-align:right;padding:.4rem .75rem'>{old_label}</th>
                  <th style='text-align:right;padding:.4rem .75rem'>{new_label}</th>
                  <th style='text-align:right;padding:.4rem .75rem'>Δ</th>
                </tr>
              </thead>
              <tbody style='font-family:monospace'>{metric_rows}</tbody>
            </table>
          </div>
        </div>

        <div style='margin-bottom:1.75rem'>
          <div style='font-size:.78rem;font-weight:600;color:#374151;margin-bottom:.4rem'>
            Per-case Score — {old_label} (blue/red) vs {new_label} (green/red)
          </div>
          <canvas id='bar_{sid}' height='80'></canvas>
        </div>

        <div style='margin-bottom:1.5rem'>
          <div style='font-size:.78rem;font-weight:600;color:#374151;margin-bottom:.4rem'>Test Case Breakdown</div>
          <div style='overflow-x:auto'>
            <table style='width:100%;border-collapse:collapse;font-size:.825rem'>
              <thead>
                <tr style='background:#f3f4f6'>
                  <th style='text-align:left;padding:.35rem .6rem'>#</th>
                  <th style='padding:.35rem .6rem'>Prev</th>
                  <th style='text-align:right;padding:.35rem .6rem'>Score</th>
                  <th style='padding:.35rem .6rem'>Curr</th>
                  <th style='text-align:right;padding:.35rem .6rem'>Score</th>
                  <th style='text-align:right;padding:.35rem .6rem'>Δ</th>
                  <th style='text-align:left;padding:.35rem .6rem'>AI Reason (current run)</th>
                </tr>
              </thead>
              <tbody>
                {case_rows or '<tr><td colspan="7" style="color:#9ca3af;text-align:center;padding:1rem">No case data</td></tr>'}
              </tbody>
            </table>
          </div>
        </div>

        {failure_html}

        <div style='margin-top:1.75rem'>
          <div style='font-size:.78rem;font-weight:600;color:#374151;margin-bottom:.4rem'>🧠 LLM Drift Analysis</div>
          <div style='padding:1rem;background:#f9fafb;border-radius:6px;font-size:.875rem;
                      line-height:1.7;white-space:pre-wrap;color:#374151'>{analysis}</div>
        </div>

      </div>
    </section>

    <script>
    (function(){{
      new Chart(document.getElementById('radar_{sid}'),{{
        type:'radar',
        data:{{
          labels:{radar_labels},
          datasets:[
            {{label:'{old_label_js}',data:{radar_prev},
              borderColor:'rgba(59,130,246,.8)',backgroundColor:'rgba(59,130,246,.12)',
              pointBackgroundColor:'rgba(59,130,246,.8)',pointRadius:3}},
            {{label:'{new_label_js}',data:{radar_curr},
              borderColor:'rgba(16,185,129,.8)',backgroundColor:'rgba(16,185,129,.12)',
              pointBackgroundColor:'rgba(16,185,129,.8)',pointRadius:3}}
          ]
        }},
        options:{{responsive:false,
          plugins:{{legend:{{position:'bottom',labels:{{font:{{size:10}}}}}}}},
          scales:{{r:{{min:0,max:100,ticks:{{stepSize:25,font:{{size:9}}}},
            pointLabels:{{font:{{size:10}}}}}}}}
        }}
      }});
      new Chart(document.getElementById('bar_{sid}'),{{
        type:'bar',
        data:{{
          labels:{case_labels},
          datasets:[
            {{label:'{old_label_js}',data:{bar_prev},backgroundColor:{bar_col_prev},borderRadius:3}},
            {{label:'{new_label_js}',data:{bar_curr},backgroundColor:{bar_col_curr},borderRadius:3}}
          ]
        }},
        options:{{responsive:true,
          plugins:{{legend:{{position:'top',labels:{{font:{{size:10}}}}}}}},
          scales:{{
            y:{{min:0,max:100,ticks:{{stepSize:25}},grid:{{color:'rgba(0,0,0,.04)'}}}},
            x:{{grid:{{display:false}}}}
          }}
        }}
      }});
    }})();
    </script>"""


def generate_report(bot_results: list[dict]) -> str:
    ts    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    count = len(bot_results)
    sections = "".join(
        _bot_section(
            b["botName"], b["oldModel"], b["newModel"],
            b["prevMetrics"], b["currMetrics"],
            b["analysis"], b["runId"],
            prev_run=b.get("prevRunData"),
            curr_run_results=b.get("currRunData"),
        )
        for b in bot_results
    )
    return f"""<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset='UTF-8'>
  <title>Copilot Eval Drift Report — {ts}</title>
  <script src='https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js'></script>
  <style>
    *    {{ box-sizing:border-box;margin:0;padding:0 }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
            background:#f3f4f6;padding:2rem;color:#111827 }}
    h1   {{ font-size:1.4rem;font-weight:700;margin-bottom:.2rem }}
    .sub {{ color:#6b7280;font-size:.875rem;margin-bottom:2rem }}
    .num {{ text-align:right;font-family:monospace }}
    td,th {{ padding:.4rem .75rem;border-bottom:1px solid #e5e7eb }}
  </style>
</head>
<body>
  <h1>Copilot Studio — Model Drift Report</h1>
  <div class='sub'>{ts} &nbsp;·&nbsp; {count} agent(s) evaluated</div>
  {sections}
</body>
</html>"""
