"""
dashboard/pages/ashoka.py — Fleet view + bot detail comparison page.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

import plotly.graph_objects as go
import streamlit as st

from theme import (
    C_BG, C_CARD, C_BORDER, C_CYAN, C_MAGENTA, C_GOLD,
    C_RED, C_GREEN, C_DIM, C_TEXT, FONT,
)
from agent.reasoning import (
    extract_metrics_for_report as _extract_metrics,
    classify_run,
    verdict_summary,
)

STORE_DIR = os.environ.get("STORE_DIR", "data")

# ── Data helpers ──────────────────────────────────────────────────────────────
def _load_json(path):
    try:
        return json.loads(open(path).read())
    except Exception:
        return {}


def _fmt_ts(iso):
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %H:%M")
    except Exception:
        return iso or "—"


def _short_guid(g):
    return g[:8] if len(g) >= 8 else g


def load_all_bots():
    from agent.store import list_triggers, load_tracking
    bots = []
    if not os.path.exists(STORE_DIR):
        return bots
    for bot_id in os.listdir(STORE_DIR):
        bot_dir = os.path.join(STORE_DIR, bot_id)
        if not os.path.isdir(bot_dir):
            continue
        tracking = load_tracking(STORE_DIR, bot_id)
        if not tracking:
            continue
        triggers = list_triggers(STORE_DIR, bot_id)
        bots.append({
            "botId":        bot_id,
            "botName":      tracking.get("botName", bot_id),
            "envName":      tracking.get("envName", "—"),
            "modelVersion": tracking.get("modelVersion", "unknown"),
            "updatedAt":    tracking.get("updatedAt", ""),
            "triggerCount": len(triggers),
            "triggers":     triggers,
            "lastTrigger":  triggers[-1] if triggers else {},
        })
    return sorted(bots, key=lambda b: b["updatedAt"], reverse=True)


def _metrics_for(trigger):
    return _extract_metrics(trigger.get("resultsByType", {}))


def _classifications_for(trigger_a, trigger_b):
    return classify_run(_metrics_for(trigger_a), _metrics_for(trigger_b))


def _bot_verdict(bot):
    triggers = bot["triggers"]
    if len(triggers) < 2:
        return "BASELINE"
    cls = _classifications_for(triggers[-2], triggers[-1])
    if any(c["verdict"] == "REGRESSED" for c in cls):
        return "REGRESSED"
    if any(c["verdict"] == "IMPROVED" for c in cls):
        return "IMPROVED"
    return "STABLE"


def _cases_for_type(trigger, metric_type):
    wrapper  = trigger.get("resultsByType", {}).get(metric_type, {})
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
    return cases


def _all_metric_types(trigger):
    return list(trigger.get("resultsByType", {}).keys())


# ── Chart builders ────────────────────────────────────────────────────────────
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=C_TEXT, family=FONT, size=10),
    margin=dict(l=10, r=10, t=30, b=10),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=C_BORDER, borderwidth=1,
                font=dict(color=C_DIM, size=9)),
)
_AXIS = dict(gridcolor=C_BORDER, linecolor=C_BORDER, zerolinecolor=C_BORDER,
             tickfont=dict(color=C_DIM))


def chart_radar(classifications, label_a, label_b):
    if not classifications:
        return go.Figure()

    def _norm(v):
        return round(v * 100, 1) if (v is not None and v <= 1) else round(v or 0, 1)

    labels    = [c["key"].split(".")[-1][:18] for c in classifications]
    prev_vals = [_norm(c["prev"]) for c in classifications]
    curr_vals = [_norm(c["curr"]) for c in classifications]
    n         = len(labels)
    width_each = max(8, int(280 / max(n, 1)))

    fig = go.Figure()
    fig.add_trace(go.Barpolar(
        r=prev_vals, theta=labels,
        name=f"A: {label_a[:30]}",
        width=width_each,
        marker=dict(color="rgba(255,215,0,0.35)", line=dict(color=C_GOLD, width=2.5)),
    ))
    fig.add_trace(go.Barpolar(
        r=curr_vals, theta=labels,
        name=f"B: {label_b[:30]}",
        width=width_each,
        marker=dict(color="rgba(0,240,255,0.25)", line=dict(color=C_CYAN, width=2.5)),
    ))
    fig.update_layout(
        **CHART_LAYOUT,
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(
                visible=True, range=[0, 100],
                gridcolor=C_BORDER, linecolor=C_BORDER,
                tickfont=dict(size=7, color=C_DIM),
                tickvals=[25, 50, 75, 100],
            ),
            angularaxis=dict(
                gridcolor=C_BORDER, linecolor=C_BORDER,
                tickfont=dict(color=C_TEXT, size=9),
                direction="clockwise",
            ),
            barmode="overlay",
        ),
        height=340, showlegend=True,
    )
    fig.update_layout(legend=dict(
        orientation="h", x=0.5, xanchor="center",
        y=-0.1, yanchor="top",
        bgcolor="rgba(0,0,0,0)", font=dict(size=8, color=C_DIM),
    ))
    return fig


def chart_delta_bar(cases_prev, cases_curr, title):
    prev_by_id = {c["caseId"]: c for c in cases_prev}
    items = []
    for i, cc in enumerate(cases_curr):
        pc    = prev_by_id.get(cc["caseId"], {})
        psc   = pc.get("score")
        csc   = cc.get("score")
        delta = round(csc - psc, 1) if isinstance(psc, float) and isinstance(csc, float) else 0
        items.append({"label": f"#{i+1}", "delta": delta})
    items.sort(key=lambda x: x["delta"])
    labels = [x["label"] for x in items]
    deltas = [x["delta"] for x in items]
    colors = [C_RED if d < -2 else (C_GREEN if d > 2 else C_DIM) for d in deltas]
    fig = go.Figure(go.Bar(x=labels, y=deltas, marker_color=colors,
                           hovertemplate="%{x}: Δ%{y}<extra></extra>"))
    fig.update_layout(**CHART_LAYOUT, title=dict(text=title, font=dict(size=11, color=C_DIM)),
                      height=240, showlegend=False)
    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(**_AXIS, zeroline=True, zerolinewidth=1)
    return fig


def chart_status_grid(cases_prev, cases_curr):
    prev_by_id = {c["caseId"]: c for c in cases_prev}
    pp = ff = pf = fp = 0
    for cc in cases_curr:
        pc = prev_by_id.get(cc["caseId"])
        if not pc:
            continue
        pv = pc.get("status") == "Pass"
        cv = cc.get("status") == "Pass"
        if pv and cv:         pp += 1
        if not pv and not cv: ff += 1
        if pv and not cv:     pf += 1
        if not pv and cv:     fp += 1
    z    = [[pp, pf], [fp, ff]]
    text = [[f"Stayed Pass\n{pp}", f"Pass→Fail\n{pf}"],
            [f"Fail→Pass\n{fp}", f"Stayed Fail\n{ff}"]]
    fig = go.Figure(go.Heatmap(
        z=z, x=["→ Pass", "→ Fail"], y=["Prev Pass", "Prev Fail"],
        text=text, texttemplate="%{text}",
        colorscale=[[0, C_BG], [0.5, C_CARD], [1, C_GREEN]],
        showscale=False, hovertemplate="%{text}<extra></extra>",
    ))
    fig.update_layout(**CHART_LAYOUT, height=200)
    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(**_AXIS)
    return fig


def chart_metric_trend(bot):
    triggers = bot["triggers"]
    if len(triggers) < 2:
        return go.Figure()
    all_keys: set = set()
    data = []
    for t in triggers:
        m = _metrics_for(t)
        all_keys.update(m.keys())
        data.append({"label": _fmt_ts(t.get("triggeredAt", "")), "metrics": m})
    x = [d["label"] for d in data]
    fig = go.Figure()
    colors = [C_CYAN, C_MAGENTA, C_GOLD, C_GREEN, C_RED]
    for i, key in enumerate(sorted(all_keys)):
        y     = [d["metrics"].get(key) for d in data]
        color = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=x, y=y, name=key.split(".")[-1],
            mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(color=color, size=5, line=dict(color=C_BG, width=1)),
        ))
    fig.update_layout(**CHART_LAYOUT, height=280)
    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(**_AXIS)
    return fig


# ── Verdict helpers ───────────────────────────────────────────────────────────
_V_COLORS = {
    "REGRESSED": C_RED, "IMPROVED": C_GREEN,
    "STABLE": C_DIM, "NEW": C_GOLD, "BASELINE": C_GOLD,
}


# ── Header ────────────────────────────────────────────────────────────────────
def render_header(bots):
    last_scan = max((b["updatedAt"] for b in bots), default="")
    ts_str    = _fmt_ts(last_scan) if last_scan else "no data yet"
    n_reg     = sum(1 for b in bots if _bot_verdict(b) == "REGRESSED")
    from datetime import datetime, timezone
    now_utc   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    dot_color = C_RED if n_reg else C_GREEN
    dot_label = f"{n_reg} REGRESSED" if n_reg else "ALL STABLE"

    st.markdown(f"""
    <style>
      @keyframes sys-blink {{ 0%,100%{{opacity:1}} 50%{{opacity:0.2}} }}
      .sys-dot-hdr {{
        width:9px;height:9px;border-radius:50%;background:{dot_color};
        box-shadow:0 0 8px {dot_color};display:inline-block;margin-right:8px;
        animation:sys-blink 1.4s ease-in-out infinite;vertical-align:middle;
      }}
    </style>
    <div style='margin-bottom:20px'>
      <div style='display:flex;align-items:center;justify-content:space-between;
                  padding:8px 0 14px;border-bottom:1px solid {C_BORDER}'>
        <div>
          <div style='font-size:0.6rem;letter-spacing:4px;color:{dot_color};
                      font-weight:700;font-family:{FONT};margin-bottom:6px'>
            <span class="sys-dot-hdr"></span>SYSTEM ONLINE &nbsp;·&nbsp; {dot_label}
          </div>
          <div style='font-size:2rem;font-weight:700;letter-spacing:8px;color:{C_CYAN};
                      font-family:{FONT};line-height:1;
                      text-shadow:0 0 30px rgba(0,240,255,.4),0 0 60px rgba(0,240,255,.15)'>
            ASHOKA</div>
          <div style='font-size:0.65rem;color:{C_MAGENTA};letter-spacing:3px;
                      font-weight:700;margin-top:4px'>THE INCORRUPTIBLE JUDGE</div>
          <div style='font-size:0.6rem;color:{C_DIM};letter-spacing:1px;margin-top:2px'>
            copilot-eval-agent &nbsp;·&nbsp; {len(bots)} agent{'s' if len(bots)!=1 else ''} monitored</div>
        </div>
        <div style='text-align:right'>
          <div style='font-size:0.6rem;color:{C_DIM};letter-spacing:1px'>LAST ACTIVITY</div>
          <div style='font-size:0.75rem;color:{C_TEXT};font-family:{FONT};margin-top:2px'>{ts_str}</div>
          <div style='font-size:0.6rem;color:{C_DIM};margin-top:6px'>{now_utc}</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Pages ─────────────────────────────────────────────────────────────────────
def page_overview(bots):
    total_cases = sum(
        len(_cases_for_type(b["lastTrigger"], mt))
        for b in bots for mt in _all_metric_types(b["lastTrigger"])
    )
    verdicts = [_bot_verdict(b) for b in bots]
    n_reg    = verdicts.count("REGRESSED")
    n_imp    = verdicts.count("IMPROVED")
    n_sta    = verdicts.count("STABLE")
    n_base   = verdicts.count("BASELINE")

    st.markdown(f"""
    <div class='stat-bar'>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{C_CYAN}'>{total_cases}</div>
        <div class='stat-label'>Total Cases</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{""+C_RED if n_reg else C_DIM}'>{n_reg}</div>
        <div class='stat-label'>Regressed</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{""+C_GREEN if n_imp else C_DIM}'>{n_imp}</div>
        <div class='stat-label'>Improved</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{C_DIM}'>{n_sta}</div>
        <div class='stat-label'>Stable</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{""+C_GOLD if n_base else C_DIM}'>{n_base}</div>
        <div class='stat-label'>Baseline</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not bots:
        st.markdown(
            f"<div style='text-align:center;padding:60px;color:{C_DIM}'>"
            f"<div style='font-size:2rem;margin-bottom:12px'>⚡</div>"
            f"<div style='color:{C_TEXT};font-size:0.9rem'>No bots tracked yet</div>"
            f"<div style='font-size:0.75rem;margin-top:6px'>Start the agent or click ▶ Force Eval Now</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown("<div class='sec-label'>MONITORED AGENTS</div>", unsafe_allow_html=True)

    cols = st.columns(4)
    for i, bot in enumerate(bots):
        verdict = _bot_verdict(bot)
        v_color = _V_COLORS.get(verdict, C_DIM)
        with cols[i % 4]:
            if st.button(
                f"{'🔴' if verdict=='REGRESSED' else '🟢' if verdict=='IMPROVED' else '🟡' if verdict=='BASELINE' else '⚪'} "
                f"{bot['botName']}\n{bot['modelVersion'][:26]}\n"
                f"{_fmt_ts(bot['updatedAt'])} · {bot['triggerCount']} run{'s' if bot['triggerCount']!=1 else ''}",
                key=f"tile_{bot['botId']}",
                use_container_width=True,
            ):
                st.session_state.selected_bot = bot["botId"]
                st.session_state.page = "detail"
                st.rerun()


def page_bot_detail(bot):
    import pandas as pd
    triggers = bot["triggers"]
    name     = bot["botName"]
    env      = bot["envName"]

    if st.button("← Back", key="back_btn"):
        st.session_state.page = "overview"
        st.rerun()

    if not triggers:
        st.info("No eval runs yet.")
        return

    def _run_label(t):
        ts  = _fmt_ts(t.get("triggeredAt", ""))
        ver = t.get("modelVersion", "?")
        gid = _short_guid(t.get("triggerGuid", ""))
        return f"{ts}  ·  {gid}  ·  {ver}"

    run_labels = [_run_label(t) for t in triggers]

    idx_a = st.selectbox("Run A — older / baseline", range(len(triggers)),
                         format_func=lambda i: run_labels[i],
                         index=max(0, len(triggers) - 2), key="sel_a")
    idx_b = st.selectbox("Run B — newer / comparison", range(len(triggers)),
                         format_func=lambda i: run_labels[i],
                         index=len(triggers) - 1, key="sel_b")

    if idx_a == idx_b:
        st.warning("Run A and Run B are the same — select two different runs to compare.")
        return

    trig_a = triggers[idx_a]
    trig_b = triggers[idx_b]
    lbl_a  = run_labels[idx_a]
    lbl_b  = run_labels[idx_b]
    cls    = _classifications_for(trig_a, trig_b)
    v_sum  = verdict_summary(cls)
    reg_count = sum(1 for c in cls if c["verdict"] == "REGRESSED")
    v_color   = C_RED if reg_count else (C_GREEN if any(c["verdict"]=="IMPROVED" for c in cls) else C_DIM)

    st.markdown(f"""
    <div style='padding:16px 0 8px;border-bottom:1px solid {C_BORDER};margin-bottom:16px;
                display:flex;justify-content:space-between;align-items:center'>
      <div>
        <span style='font-size:1.1rem;font-weight:700;color:{C_TEXT};font-family:{FONT}'>{name}</span>
        <span style='color:{C_DIM};font-size:0.75rem;margin-left:12px'>{env}</span>
      </div>
      <span style='color:{v_color};font-weight:700;font-family:{FONT};
                   letter-spacing:2px;font-size:0.8rem'>{v_sum}</span>
    </div>
    """, unsafe_allow_html=True)

    analysis = (trig_b.get("analysis") or trig_a.get("analysis") or "").strip()
    if analysis:
        if "LLM analysis unavailable" in analysis or "Error code" in analysis:
            st.caption("⚠ LLM analysis unavailable — check LLM_API_KEY / LLM_BASE_URL in your .env")
        else:
            st.markdown(
                f"<div class='analysis-panel'>"
                f"<div class='analysis-label'>⚡ LLM DRIFT ANALYSIS</div>"
                f"{analysis.replace(chr(10), '<br>')}</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div class='sec-label'>RADAR</div>", unsafe_allow_html=True)
    fig_r = chart_radar(cls, lbl_a, lbl_b)
    if fig_r.data:
        st.plotly_chart(fig_r, width="stretch", config={"displayModeBar": False})

    st.divider()

    st.markdown("<div class='sec-label'>METRIC SUMMARY</div>", unsafe_allow_html=True)
    if cls:
        rows = [{"Metric": c["key"], "Verdict": c["verdict"],
                 "Prev": round(c["prev"], 4) if c["prev"] is not None else None,
                 "Curr": round(c["curr"], 4) if c["curr"] is not None else None,
                 "Δ": f"{c['delta']:+.4f}" if c["delta"] is not None else "—"}
                for c in cls]
        import pandas as pd
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch", hide_index=True,
                     height=min(260, 48 + len(rows) * 38))
    else:
        st.caption("No metrics — first run establishes baseline.")

    st.markdown("<div class='sec-label'>PER METRIC TYPE</div>", unsafe_allow_html=True)
    _prio = {"REGRESSED": 0, "IMPROVED": 1, "STABLE": 2, "NEW": 3}
    verdict_by_type = {}
    for c in cls:
        for mt in _all_metric_types(trig_b):
            if c["key"].startswith(mt + "."):
                existing = verdict_by_type.get(mt, "STABLE")
                if _prio.get(c["verdict"], 9) < _prio.get(existing, 9):
                    verdict_by_type[mt] = c["verdict"]
    for mt in _all_metric_types(trig_b):
        if mt not in verdict_by_type:
            verdict_by_type[mt] = "NEW" if not _metrics_for(trig_a) else "STABLE"

    sorted_types = sorted(_all_metric_types(trig_b),
                          key=lambda t: _prio.get(verdict_by_type.get(t, "STABLE"), 9))

    for metric_type in sorted_types:
        verdict    = verdict_by_type.get(metric_type, "STABLE")
        cases_prev = _cases_for_type(trig_a, metric_type)
        cases_curr = _cases_for_type(trig_b, metric_type)
        expanded   = verdict == "REGRESSED"

        with st.expander(f"{metric_type}  —  {verdict}", expanded=expanded):
            if cases_prev and cases_curr:
                fig_d = chart_delta_bar(cases_prev, cases_curr, "Score Δ per case (worst first)")
                if fig_d.data:
                    st.plotly_chart(fig_d, width="stretch", config={"displayModeBar": False})
                st.caption("Status transitions")
                fig_g = chart_status_grid(cases_prev, cases_curr)
                if fig_g.data:
                    st.plotly_chart(fig_g, width="stretch", config={"displayModeBar": False})

            if cases_curr:
                prev_by_id = {c["caseId"]: c for c in cases_prev}
                rows = []
                for i, cc in enumerate(cases_curr):
                    pc    = prev_by_id.get(cc["caseId"], {})
                    psc   = pc.get("score")
                    csc   = cc.get("score")
                    delta = round(csc - psc, 1) if isinstance(psc, float) and isinstance(csc, float) else None
                    rows.append({
                        "#": i + 1, "Prev status": pc.get("status", "—"),
                        "Prev score": int(psc) if isinstance(psc, float) else None,
                        "Curr status": cc.get("status", "—"),
                        "Curr score": int(csc) if isinstance(csc, float) else None,
                        "Δ": delta, "AI reason": cc.get("reason", ""),
                    })
                rows.sort(key=lambda r: (r["Δ"] or 0))
                import pandas as pd
                df = pd.DataFrame(rows).set_index("#")
                st.dataframe(df, width="stretch", height=min(420, 48 + len(rows) * 38))

                failures = [r for r in rows if r["Curr status"] == "Fail"]
                if failures:
                    st.markdown(
                        f"<div style='font-size:0.65rem;color:{C_RED};font-weight:700;"
                        f"letter-spacing:1px;margin:12px 0 6px;font-family:{FONT}'>"
                        f"FAILING CASES ({len(failures)})</div>",
                        unsafe_allow_html=True,
                    )
                    for f in failures:
                        with st.expander(f"Case {f['#']} — Score {f['Curr score']}"):
                            st.write(f["AI reason"])
            else:
                st.caption("No test case data for this metric type.")

    if len(triggers) >= 2:
        st.markdown("<div class='sec-label'>METRIC TRENDS</div>", unsafe_allow_html=True)
        fig_t = chart_metric_trend(bot)
        if fig_t.data:
            st.plotly_chart(fig_t, width="stretch", config={"displayModeBar": False})

    st.markdown("<div class='sec-label'>RUN HISTORY</div>", unsafe_allow_html=True)
    tl_html = ""
    for t in reversed(triggers):
        mt_list = ", ".join(t.get("metricTypes", ["—"]))
        dot_col = C_CYAN if not t.get("_legacy") else C_DIM
        tl_html += (
            "<div class='tl-item'>"
            f"<div class='tl-dot' style='background:{dot_col}'></div>"
            "<div class='tl-content'>"
            f"<div class='tl-model'>{t.get('modelVersion','—')[:36]}</div>"
            f"<div class='tl-guid'>{_short_guid(t.get('triggerGuid',''))}  ·  {mt_list}</div>"
            f"<div class='tl-ts'>{_fmt_ts(t.get('triggeredAt',''))}</div>"
            "</div></div>"
        )
    st.markdown("<div class='timeline'>" + tl_html + "</div>", unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────────────────────────────
bots     = load_all_bots()
page     = st.session_state.get("page", "overview")
selected = st.session_state.get("selected_bot")

render_header(bots)

if page == "overview" or page not in ("detail",):
    page_overview(bots)
else:
    bot = next((b for b in bots if b["botId"] == selected), None)
    if bot:
        page_bot_detail(bot)
    else:
        st.session_state.page = "overview"
        st.rerun()
