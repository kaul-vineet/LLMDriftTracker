from datetime import datetime, timezone


def _delta_color(delta: float) -> str:
    if abs(delta) < 0.02:
        return "#6b7280"      # grey — negligible
    return "#16a34a" if delta > 0 else "#dc2626"  # green / red


def _metric_row(key: str, prev: float | str, curr: float | str) -> str:
    if isinstance(prev, float) and isinstance(curr, float):
        delta = curr - prev
        color = _delta_color(delta)
        sign  = "+" if delta >= 0 else ""
        return (f"<tr>"
                f"<td>{key}</td>"
                f"<td>{prev:.4f}</td>"
                f"<td>{curr:.4f}</td>"
                f"<td style='color:{color};font-weight:600'>{sign}{delta:.4f}</td>"
                f"</tr>")
    return (f"<tr><td>{key}</td><td>{prev}</td><td>{curr}</td><td>—</td></tr>")


def _bot_section(bot_name: str, old_model: str, new_model: str,
                 prev_metrics: dict, curr_metrics: dict,
                 analysis: str, run_id: str) -> str:
    all_keys = sorted(set(list(prev_metrics.keys()) + list(curr_metrics.keys())))
    rows = ""
    for k in all_keys:
        rows += _metric_row(k,
                            prev_metrics.get(k, "N/A"),
                            curr_metrics.get(k, "N/A"))

    model_change = (f"<span style='color:#9ca3af'>{old_model}</span>"
                    f" &rarr; "
                    f"<span style='color:#1d4ed8;font-weight:600'>{new_model}</span>")

    no_prev = "<tr><td colspan='4' style='color:#9ca3af;text-align:center'>No previous run — baseline established</td></tr>"

    return f"""
    <section style='margin-bottom:2.5rem;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden'>
      <div style='background:#1e3a5f;color:#fff;padding:1rem 1.5rem'>
        <h2 style='margin:0;font-size:1.1rem'>{bot_name}</h2>
        <div style='font-size:0.85rem;margin-top:0.25rem;opacity:0.8'>{model_change}</div>
        <div style='font-size:0.75rem;opacity:0.6;margin-top:0.15rem'>Run ID: {run_id}</div>
      </div>
      <div style='padding:1.5rem'>
        <table style='width:100%;border-collapse:collapse;font-size:0.9rem'>
          <thead>
            <tr style='background:#f3f4f6'>
              <th style='text-align:left;padding:0.5rem 0.75rem'>Metric</th>
              <th style='text-align:left;padding:0.5rem 0.75rem'>{old_model or "Previous"}</th>
              <th style='text-align:left;padding:0.5rem 0.75rem'>{new_model}</th>
              <th style='text-align:left;padding:0.5rem 0.75rem'>Δ</th>
            </tr>
          </thead>
          <tbody style='font-family:monospace'>
            {rows if rows else no_prev}
          </tbody>
        </table>
        <div style='margin-top:1.5rem;padding:1rem;background:#f9fafb;border-radius:6px;
                    font-size:0.9rem;line-height:1.6;white-space:pre-wrap'>{analysis}</div>
      </div>
    </section>"""


def generate_report(bot_results: list[dict]) -> str:
    ts    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    count = len(bot_results)
    sections = "".join(
        _bot_section(
            b["botName"], b["oldModel"], b["newModel"],
            b["prevMetrics"], b["currMetrics"],
            b["analysis"], b["runId"]
        )
        for b in bot_results
    )

    return f"""<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset='UTF-8'>
  <title>Copilot Eval Drift Report — {ts}</title>
  <style>
    body {{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
           background:#f9fafb;margin:0;padding:2rem;color:#111827}}
    h1   {{font-size:1.4rem;margin-bottom:0.25rem}}
    .sub {{color:#6b7280;font-size:0.85rem;margin-bottom:2rem}}
    td, th {{padding:0.5rem 0.75rem;border-bottom:1px solid #e5e7eb}}
  </style>
</head>
<body>
  <h1>Copilot Studio — Model Drift Report</h1>
  <div class='sub'>{ts} &nbsp;·&nbsp; {count} agent(s) evaluated</div>
  {sections}
</body>
</html>"""
