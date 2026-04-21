"""
dashboard/pages/ashoka.py — Fleet view, bot detail, identity, and mission timeline.
"""
import json
import os
import sys
from datetime import datetime, timezone

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
from agent.events import load_events
from spinner import spinner as _spinner

STORE_DIR = os.environ.get("STORE_DIR", "data")
PID_FILE  = os.path.join(STORE_DIR, "agent.pid")


def _agent_running():
    try:
        pid = int(open(PID_FILE).read().strip())
    except Exception:
        return False
    try:
        if sys.platform == "win32":
            import subprocess as _sp
            r = _sp.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                        capture_output=True, text=True, timeout=3)
            return str(pid) in r.stdout
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


# ── Page-specific CSS ─────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  /* Stat bar */
  .stat-bar {{
    display:grid; grid-template-columns:repeat(5,1fr);
    gap:1px; background:{C_BORDER}; border:1px solid {C_BORDER};
    border-radius:8px; overflow:hidden; margin-bottom:20px;
  }}
  .stat-cell {{ background:{C_CARD}; padding:14px 20px; text-align:center; }}
  .stat-value {{ font-size:2.34rem; font-weight:700; font-family:{FONT}; line-height:1; }}
  .stat-label {{ font-size:0.78rem; color:{C_DIM}; letter-spacing:2px; text-transform:uppercase; margin-top:4px; }}

  /* Section label */
  .sec-label {{
    font-size:0.98rem; font-weight:700; letter-spacing:3px; text-transform:uppercase;
    color:{C_DIM}; border-bottom:1px solid {C_BORDER}; padding-bottom:6px;
    margin:20px 0 14px; font-family:{FONT};
  }}

  /* Analysis panel */
  .analysis-panel {{
    background:{C_BG}; border-left:3px solid {C_MAGENTA};
    border-radius:0 8px 8px 0; padding:16px 20px;
    font-size:1.14rem; line-height:1.75; color:{C_TEXT}; margin-bottom:20px;
  }}
  .analysis-label {{
    font-size:0.85rem; font-weight:700; color:{C_MAGENTA};
    letter-spacing:2px; margin-bottom:8px; font-family:{FONT};
  }}

  /* Run history timeline */
  .rh-timeline {{ padding:8px 0; }}
  .rh-item {{
    display:flex; gap:16px; padding:12px 0;
    border-bottom:1px solid {C_BORDER}; align-items:flex-start;
  }}
  .rh-dot {{ width:10px; height:10px; border-radius:50%; margin-top:4px; flex-shrink:0; }}
  .rh-content {{ flex:1; }}
  .rh-model {{ font-size:1.01rem; color:{C_TEXT}; font-family:{FONT}; }}
  .rh-guid  {{ font-size:0.91rem; color:{C_DIM}; font-family:{FONT}; }}
  .rh-ts    {{ font-size:0.88rem; color:{C_DIM}; }}

  /* Radar */
  .radar-wrap {{
    position:relative; width:200px; height:200px; margin:0 auto 8px;
    border-radius:50%;
    background:radial-gradient(circle, rgba(0,15,25,0.95) 0%, rgba(0,5,10,0.98) 100%);
    box-shadow:0 0 40px rgba(0,240,255,0.12), inset 0 0 60px rgba(0,0,0,0.7);
  }}
  .ring {{
    position:absolute; border-radius:50%; border:1px solid;
    top:50%; left:50%; transform:translate(-50%,-50%);
  }}
  .r1 {{ width:200px;height:200px; border-color:rgba(0,240,255,0.30); }}
  .r2 {{ width:145px;height:145px; border-color:rgba(0,240,255,0.45); }}
  .r3 {{ width:90px; height:90px;  border-color:rgba(0,240,255,0.65); }}
  .r4 {{ width:38px; height:38px;  border-color:{C_CYAN}; box-shadow:0 0 8px {C_CYAN}; }}
  .radar-h,.radar-v {{
    position:absolute; background:rgba(0,240,255,0.20);
    top:50%; left:50%; transform:translate(-50%,-50%);
  }}
  .radar-h {{ width:200px; height:1px; }}
  .radar-v {{ width:1px; height:200px; }}
  .sweep {{
    position:absolute; top:0; left:0; width:100%; height:100%; border-radius:50%;
    background:conic-gradient(rgba(0,240,255,0) 0deg, rgba(0,240,255,0) 250deg,
                               rgba(0,240,255,0.15) 290deg, rgba(0,240,255,0.55) 340deg,
                               rgba(0,240,255,0.85) 358deg, rgba(0,240,255,0) 360deg);
    animation:spin 3s linear infinite;
  }}
  .center-dot {{
    position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
    width:10px; height:10px; border-radius:50%;
    background:{C_CYAN}; box-shadow:0 0 16px {C_CYAN},0 0 30px rgba(0,240,255,0.5);
  }}
  @keyframes spin {{ from{{transform:rotate(0deg)}} to{{transform:rotate(360deg)}} }}
  @keyframes sys-blink {{ 0%,100%{{opacity:1}} 50%{{opacity:0.2}} }}
  @keyframes blink {{ 0%,100%{{opacity:1}} 50%{{opacity:0.25}} }}

  /* Title cards */
  .title-grid {{
    display:grid; grid-template-columns:repeat(2,1fr); gap:8px; margin:12px 0 16px;
  }}
  .title-card {{
    background:{C_CARD}; border:1px solid {C_BORDER}; border-radius:6px; padding:10px 14px;
  }}
  .title-sanskrit {{ font-size:0.6rem; letter-spacing:2px; color:{C_GOLD}; font-weight:700; margin-bottom:3px; }}
  .title-meaning  {{ font-size:0.72rem; color:{C_TEXT}; font-weight:600; }}

  /* Mission timeline */
  .etl-wrap {{ position:relative; padding-left:28px; margin-top:8px; }}
  .etl-line {{
    position:absolute; left:9px; top:0; bottom:0; width:1px;
    background:linear-gradient({C_CYAN}, {C_MAGENTA}, {C_BORDER});
  }}
  .etl-event {{ position:relative; margin-bottom:16px; }}
  .etl-dot {{
    position:absolute; left:-24px; top:4px;
    width:9px; height:9px; border-radius:50%;
    border:2px solid; background:{C_BG};
  }}
  .etl-dot.ok     {{ border-color:{C_GREEN};   box-shadow:0 0 5px {C_GREEN}; }}
  .etl-dot.warn   {{ border-color:{C_GOLD};    box-shadow:0 0 5px {C_GOLD}; }}
  .etl-dot.bad    {{ border-color:{C_RED};     box-shadow:0 0 5px {C_RED}; }}
  .etl-dot.info   {{ border-color:{C_CYAN};    box-shadow:0 0 5px {C_CYAN}; }}
  .etl-dot.origin {{ border-color:{C_MAGENTA}; box-shadow:0 0 8px {C_MAGENTA}; }}
  .etl-ts   {{ font-size:0.88rem; color:{C_DIM}; letter-spacing:1px; margin-bottom:1px; }}
  .etl-head {{ font-size:1.1rem; font-weight:700; color:{C_TEXT}; margin-bottom:1px; }}
  .etl-body {{ font-size:1.01rem; color:{C_DIM}; line-height:1.5; }}
  .etl-badge {{
    display:inline-block; font-size:0.68rem; letter-spacing:1px; font-weight:700;
    padding:1px 6px; border-radius:3px; margin-left:7px; vertical-align:middle;
  }}
  .etl-badge.reg   {{ background:rgba(255,68,68,.18);  color:{C_RED}; }}
  .etl-badge.imp   {{ background:rgba(40,200,64,.18);  color:{C_GREEN}; }}
  .etl-badge.stb   {{ background:rgba(102,102,102,.18);color:{C_DIM}; }}
  .etl-badge.new   {{ background:rgba(0,240,255,.12);  color:{C_CYAN}; }}
  .etl-badge.birth {{ background:rgba(255,0,170,.15);  color:{C_MAGENTA}; }}
  .etl-badge.warn  {{ background:rgba(255,215,0,.15);  color:{C_GOLD}; }}
</style>
""", unsafe_allow_html=True)


# ── Data helpers ──────────────────────────────────────────────────────────────
def _fmt_ts(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %H:%M")
    except Exception:
        return iso or "—"


def _fmt_ts_long(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y  %H:%M UTC")
    except Exception:
        return iso[:16] if iso else "—"


def load_all_bots():
    from agent.store import list_runs, load_tracking
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
        runs = list_runs(STORE_DIR, bot_id)
        bots.append({
            "botId":        bot_id,
            "botName":      tracking.get("botName", bot_id),
            "envName":      tracking.get("envName", "—"),
            "modelVersion": tracking.get("modelVersion", "unknown"),
            "updatedAt":    tracking.get("updatedAt", ""),
            "runCount":     len(runs),
            "runs":         runs,
            "lastRun":      runs[-1] if runs else {},
        })
    return sorted(bots, key=lambda b: b["updatedAt"], reverse=True)


def _metrics_for(run):
    return _extract_metrics(run.get("testSets", {}))


def _classifications_for(ra, rb):
    return classify_run(_metrics_for(ra), _metrics_for(rb))


def _bot_verdict(bot):
    runs = bot["runs"]
    if len(runs) < 2:
        return "BASELINE"  # need at least two runs to compare; first establishes baseline
    cls = _classifications_for(runs[-2], runs[-1])
    if any(c["verdict"] == "REGRESSED" for c in cls): return "REGRESSED"
    if any(c["verdict"] == "IMPROVED"  for c in cls): return "IMPROVED"
    return "STABLE"


def _cases_for_type(run, metric_type):
    wrapper    = run.get("testSets", {}).get(metric_type, {})
    run_result = wrapper.get("results", wrapper) if isinstance(wrapper, dict) else {}
    cases = []
    for case in run_result.get("testCasesResults", []):
        cid = case.get("testCaseId", "")
        for m in case.get("metricsResults", []):
            r   = m.get("result", {})
            raw = r.get("data", {}).get("score")
            try:   score = float(raw)
            except: score = None
            cases.append({"caseId": cid, "status": r.get("status",""),
                          "score": score, "reason": r.get("aiResultReason","")})
    return cases


def _all_metric_types(run):
    return list(run.get("testSets", {}).keys())


# ── Charts ────────────────────────────────────────────────────────────────────
_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
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
    n = len(labels)
    w = max(8, int(280 / max(n, 1)))
    fig = go.Figure()
    fig.add_trace(go.Barpolar(r=prev_vals, theta=labels, name=f"A: {label_a[:30]}", width=w,
                               marker=dict(color="rgba(255,215,0,0.35)", line=dict(color=C_GOLD, width=2.5))))
    fig.add_trace(go.Barpolar(r=curr_vals, theta=labels, name=f"B: {label_b[:30]}", width=w,
                               marker=dict(color="rgba(0,240,255,0.25)", line=dict(color=C_CYAN, width=2.5))))
    fig.update_layout(**_LAYOUT,
        polar=dict(bgcolor="rgba(0,0,0,0)",
                   radialaxis=dict(visible=True, range=[0,100], gridcolor=C_BORDER,
                                   linecolor=C_BORDER, tickfont=dict(size=7,color=C_DIM),
                                   tickvals=[25,50,75,100]),
                   angularaxis=dict(gridcolor=C_BORDER, linecolor=C_BORDER,
                                    tickfont=dict(color=C_TEXT,size=9), direction="clockwise"),
                   barmode="overlay"),
        height=340, showlegend=True)
    fig.update_layout(legend=dict(orientation="h", x=0.5, xanchor="center",
                                  y=-0.1, yanchor="top",
                                  bgcolor="rgba(0,0,0,0)", font=dict(size=8,color=C_DIM)))
    return fig


def chart_delta_bar(cases_prev, cases_curr, title):
    prev_by_id = {c["caseId"]: c for c in cases_prev}
    items = []
    for i, cc in enumerate(cases_curr):
        pc    = prev_by_id.get(cc["caseId"], {})
        psc, csc = pc.get("score"), cc.get("score")
        delta = round(csc - psc, 1) if isinstance(psc, float) and isinstance(csc, float) else 0
        items.append({"label": f"#{i+1}", "delta": delta})
    items.sort(key=lambda x: x["delta"])
    labels = [x["label"] for x in items]
    deltas = [x["delta"] for x in items]
    colors = [C_RED if d < -2 else (C_GREEN if d > 2 else C_DIM) for d in deltas]
    fig = go.Figure(go.Bar(x=labels, y=deltas, marker_color=colors,
                           hovertemplate="%{x}: Δ%{y}<extra></extra>"))
    fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(size=11,color=C_DIM)),
                      height=240, showlegend=False)
    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(**_AXIS, zeroline=True, zerolinewidth=1)
    return fig


def chart_status_grid(cases_prev, cases_curr):
    prev_by_id = {c["caseId"]: c for c in cases_prev}
    pp = ff = pf = fp = 0
    for cc in cases_curr:
        pc = prev_by_id.get(cc["caseId"])
        if not pc: continue
        pv = pc.get("status") == "Pass"
        cv = cc.get("status") == "Pass"
        if pv and cv:         pp += 1
        if not pv and not cv: ff += 1
        if pv and not cv:     pf += 1
        if not pv and cv:     fp += 1
    fig = go.Figure(go.Heatmap(
        z=[[pp,pf],[fp,ff]], x=["→ Pass","→ Fail"], y=["Prev Pass","Prev Fail"],
        text=[[f"Stayed Pass\n{pp}",f"Pass→Fail\n{pf}"],[f"Fail→Pass\n{fp}",f"Stayed Fail\n{ff}"]],
        texttemplate="%{text}",
        colorscale=[[0,C_BG],[0.5,C_CARD],[1,C_GREEN]],
        showscale=False, hovertemplate="%{text}<extra></extra>"))
    fig.update_layout(**_LAYOUT, height=200)
    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(**_AXIS)
    return fig


def chart_metric_trend(bot):
    runs = bot["runs"]
    if len(runs) < 2: return go.Figure()
    all_keys: set = set()
    data = []
    for r in runs:
        m = _metrics_for(r)
        all_keys.update(m.keys())
        data.append({"label": _fmt_ts(r.get("triggeredAt","")), "metrics": m})
    x = [d["label"] for d in data]
    fig = go.Figure()
    for i, key in enumerate(sorted(all_keys)):
        color = [C_CYAN,C_MAGENTA,C_GOLD,C_GREEN,C_RED][i % 5]
        fig.add_trace(go.Scatter(x=x, y=[d["metrics"].get(key) for d in data],
                                 name=key.split(".")[-1], mode="lines+markers",
                                 line=dict(color=color,width=2),
                                 marker=dict(color=color,size=5,line=dict(color=C_BG,width=1))))
    fig.update_layout(**_LAYOUT, height=280)
    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(**_AXIS)
    return fig


# ── Verdict helpers ───────────────────────────────────────────────────────────
_V_COLORS = {"REGRESSED":C_RED,"IMPROVED":C_GREEN,"STABLE":C_DIM,"NEW":C_GOLD,"BASELINE":C_GOLD}


# ── Timeline helpers ──────────────────────────────────────────────────────────
_EVENT_META = {
    "model_change":  ("warn","⚠","MODEL SHIFT","warn"),
    "eval_start":    ("info","▶","EVAL START", "new"),
    "eval_complete": ("info","✓","EVAL DONE",  "stb"),
    "eval_timeout":  ("bad", "✗","TIMEOUT",    "reg"),
    "eval_no_sets":  ("warn","·","NO TEST SETS","warn"),
    "regression":    ("bad", "✗","REGRESSION", "reg"),
    "improvement":   ("ok",  "✓","IMPROVED",   "imp"),
    "force_eval":    ("info","⚡","FORCE EVAL", "new"),
    "error":         ("bad", "✗","ERROR",       "reg"),
}

def _build_timeline_events(raw, model_lookup: dict | None = None):
    """model_lookup: {botId: modelVersion} for showing model alongside agent name."""
    out = []
    for e in raw:
        et = e.get("event","")
        if et in ("cycle_start","stable"):
            continue
        dot, icon, badge, badge_c = _EVENT_META.get(et, ("info","·",et.upper(),"stb"))
        if et == "eval_complete":
            v = e.get("verdict","")
            if v == "REGRESSED":  dot,badge,badge_c = "bad","REGRESSED","reg"
            elif v == "IMPROVED": dot,badge,badge_c = "ok","IMPROVED","imp"
            else:                 dot,badge,badge_c = "info","STABLE","stb"

        bot_name = e.get("botName") or "Agent"
        # For model_change use the new model; otherwise look up current model from bots
        if et == "model_change":
            model = e.get("newModel") or e.get("oldModel") or ""
        else:
            model = (model_lookup or {}).get(e.get("botId",""), "")

        out.append({"ts":e.get("ts",""), "dot":dot, "icon":icon,
                    "head":bot_name, "model":model,
                    "badge":badge, "badge_c":badge_c, "body":e.get("detail","")})
    return list(reversed(out))


# ── Header ────────────────────────────────────────────────────────────────────
def render_header(bots, raw_events):
    last_scan   = max((b["updatedAt"] for b in bots), default="")
    ts_str      = _fmt_ts(last_scan) if last_scan else "no data yet"
    n_reg       = sum(1 for b in bots if _bot_verdict(b) == "REGRESSED")
    dot_color   = C_RED if n_reg else C_GREEN
    dot_label   = f"{n_reg} REGRESSED" if n_reg else "ALL STABLE"
    total_evals = sum(1 for e in raw_events if e.get("event") == "eval_complete")
    n_imp       = sum(1 for e in raw_events if e.get("event") == "improvement")
    n_reg_ev    = sum(1 for e in raw_events if e.get("event") == "regression")
    agent_up    = _agent_running()
    sys_color   = C_GREEN if agent_up else C_DIM
    sys_label   = "SYSTEM ONLINE" if agent_up else "AGENT OFFLINE"
    blink_anim  = "sys-blink 1.4s ease-in-out infinite" if agent_up else "none"
    n_bots      = len(bots)
    n_plural    = "s" if n_bots != 1 else ""

    st.markdown(f"""
    <style>
      .sys-dot-hdr {{
        width:9px;height:9px;border-radius:50%;background:{sys_color};
        box-shadow:0 0 8px {sys_color};display:inline-block;margin-right:8px;
        animation:{blink_anim};vertical-align:middle;
      }}
    </style>
    <div style='text-align:center;max-width:780px;margin:0 auto 8px'>

      <div style='display:flex;justify-content:center;margin-bottom:20px'>
        <div class='radar-wrap'>
          <div class='ring r1'></div><div class='ring r2'></div>
          <div class='ring r3'></div><div class='ring r4'></div>
          <div class='radar-h'></div><div class='radar-v'></div>
          <div class='sweep'></div><div class='center-dot'></div>
        </div>
      </div>

      <div style='font-size:1.05rem;letter-spacing:4px;color:{sys_color};
                  font-weight:700;font-family:{FONT};margin-bottom:10px'>
        <span class="sys-dot-hdr"></span>{sys_label} &nbsp;·&nbsp; {dot_label}
      </div>

      <div style='font-size:3.64rem;font-weight:700;letter-spacing:12px;color:{C_CYAN};
                  font-family:{FONT};line-height:1;
                  text-shadow:0 0 30px rgba(0,240,255,.4),0 0 60px rgba(0,240,255,.15)'>
        ASHOKA</div>
      <div style='font-size:1.2rem;color:{C_MAGENTA};letter-spacing:3px;
                  font-weight:700;margin-top:6px'>THE INCORRUPTIBLE JUDGE</div>
      <div style='font-size:1.0rem;color:{C_DIM};letter-spacing:1px;margin-top:4px'>
        copilot-eval-agent &nbsp;·&nbsp; {n_bots} agent{n_plural} monitored
        &nbsp;·&nbsp; {ts_str} last activity</div>

    </div>
    <div class='stat-bar' style='margin-top:24px'>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{C_CYAN}'>{n_bots}</div>
        <div class='stat-label'>Monitored</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{C_TEXT}'>{total_evals}</div>
        <div class='stat-label'>Eval Runs</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{C_GREEN if n_imp else C_DIM}'>{n_imp}</div>
        <div class='stat-label'>Improved</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{C_RED if n_reg_ev else C_DIM}'>{n_reg_ev}</div>
        <div class='stat-label'>Regressions</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{C_RED if n_reg else C_DIM}'>{n_reg}</div>
        <div class='stat-label'>Alert Now</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Overview page ─────────────────────────────────────────────────────────────
def page_overview(bots, raw_events):
    # ── WHO I AM — centered, 75% width ───────────────────────────────────────
    st.markdown("<div class='sec-label'>WHO I AM</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='max-width:75%;margin:0 auto 20px;text-align:center;"
        f"background:{C_CARD};border:1px solid {C_BORDER};"
        f"border-radius:8px;padding:20px 28px;font-size:1.08rem;"
        f"line-height:1.85;color:{C_TEXT}'>"
        f"I am <b style='color:{C_CYAN}'>ASHOKA</b> — born April 1, 2026. "
        f"I watch the models powering your Copilot Studio bots. "
        f"The moment a model swaps, I trigger the Eval API, score every test case, "
        f"and send you a verdict before your users file a ticket."
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── MONITORED AGENTS ─────────────────────────────────────────────────────
    if not bots:
        st.markdown(
            f"<div style='text-align:center;padding:40px;color:{C_DIM}'>"
            f"<div style='font-size:1.17rem;color:{C_TEXT}'>No bots tracked yet</div>"
            f"<div style='font-size:0.98rem;margin-top:6px'>Start the agent — it will begin evaluating on the next poll cycle</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown("<div class='sec-label'>MONITORED AGENTS</div>", unsafe_allow_html=True)
        cols = st.columns(4)
        for i, bot in enumerate(bots):
            verdict = _bot_verdict(bot)
            with cols[i % 4]:
                icon = {"REGRESSED":"🔴","IMPROVED":"🟢","BASELINE":"🟡"}.get(verdict,"⚪")
                if st.button(
                    f"{icon} {bot['botName']}\n{bot['modelVersion'][:26]}\n"
                    f"{_fmt_ts(bot['updatedAt'])} · {bot['runCount']} run{'s' if bot['runCount']!=1 else ''}",
                    key=f"tile_{bot['botId']}", use_container_width=True,
                ):
                    st.session_state.selected_bot = bot["botId"]
                    st.session_state.page = "detail"
                    st.rerun()

    # ── MISSION TIMELINE ─────────────────────────────────────────────────────
    st.markdown("<div class='sec-label'>MISSION TIMELINE</div>", unsafe_allow_html=True)

    origin = [
        {"ts":"2026-04-01T20:01:00+00:00","dot":"origin","icon":"🎂",
         "head":"Born","badge":"ORIGIN","badge_c":"birth",
         "body":"First boot. Received a config.json and a mandate."},
        {"ts":"2026-04-02T00:01:00+00:00","dot":"info","icon":"🌙",
         "head":"Creator Goes to Sleep","badge":"AUTONOMOUS","badge_c":"new",
         "body":"Began autonomous polling. 20 evolution cycles by morning."},
        {"ts":"2026-04-02T08:33:00+00:00","dot":"info","icon":"☀️",
         "head":"Creator Returns","badge":"MILESTONE","badge_c":"new",
         "body":'"I built this in a cave with a box of scraps." Identity confirmed.'},
    ]

    model_lookup = {b["botId"]: b.get("modelVersion","") for b in bots}
    live       = _build_timeline_events(raw_events, model_lookup)
    all_events = sorted(origin + live, key=lambda e: e.get("ts",""))

    parts = []
    for ev in all_events:
        model = ev.get("model","")
        model_html = (
            f'<span style="color:{C_DIM};font-size:0.68rem;letter-spacing:1px;'
            f'font-family:monospace;margin-left:6px">· {model[:32]}</span>'
            if model else ""
        )
        parts.append(
            f'<div class="etl-event">'
            f'<div class="etl-dot {ev["dot"]}"></div>'
            f'<div class="etl-ts">{_fmt_ts_long(ev["ts"])}</div>'
            f'<div class="etl-head">{ev["icon"]}&nbsp; {ev["head"]}{model_html}'
            f'<span class="etl-badge {ev["badge_c"]}">{ev["badge"]}</span></div>'
            f'<div class="etl-body">{ev["body"]}</div>'
            f'</div>'
        )

    st.markdown(
        '<div style="max-width:680px;margin:0 auto">'
        '<div class="etl-wrap"><div class="etl-line"></div>'
        + "".join(parts)
        + '</div>'
        + f'<div style="text-align:center;margin-top:28px;padding-top:16px;'
          f'border-top:1px solid {C_BORDER}">'
          f'<div style="font-size:0.72rem;letter-spacing:3px;color:{C_DIM};'
          f'font-family:{FONT};font-weight:700">UI INSPIRED BY</div>'
          f'<div style="font-size:1.43rem;font-weight:700;letter-spacing:6px;'
          f'color:{C_MAGENTA};font-family:{FONT};margin-top:4px;'
          f'text-shadow:0 0 20px rgba(255,0,170,0.4)">'
          f'<a href="https://joi-lab.github.io/ouroboros/" target="_blank" '
          f'style="color:{C_MAGENTA};text-decoration:none">OUROBOROS</a></div>'
          f'<div style="font-size:0.72rem;color:{C_DIM};letter-spacing:2px;margin-top:3px">'
          f'THE SNAKE THAT EATS ITS OWN TAIL &nbsp;·&nbsp; 2026</div>'
          f'</div>'
        + '</div>',
        unsafe_allow_html=True,
    )


# ── Bot detail page ───────────────────────────────────────────────────────────
def page_bot_detail(bot):
    import pandas as pd
    runs = bot["runs"]
    name = bot["botName"]
    env  = bot["envName"]

    col_back, col_eval = st.columns([3, 1])
    with col_back:
        if st.button("← Back", key="back_btn"):
            st.session_state.page = "overview"
            st.rerun()
    with col_eval:
        bot_id       = bot["botId"]
        trigger_path = os.path.join(STORE_DIR, f"force_eval_{bot_id}.trigger")
        lock_path    = os.path.join(STORE_DIR, f"eval_active_{bot_id}.lock")
        queued       = os.path.exists(trigger_path)
        running      = os.path.exists(lock_path)
        agent_up     = _agent_running()
        if queued:
            st.markdown(
                f"<div style='color:{C_GOLD};font-size:0.7rem;font-family:{FONT};"
                f"text-align:right;padding:6px 0'>⏳ Eval queued</div>",
                unsafe_allow_html=True,
            )
        elif running:
            st.markdown(
                f"<div style='color:{C_GOLD};font-size:0.7rem;font-family:{FONT};"
                f"text-align:right;padding:6px 0'>⚡ Eval running</div>",
                unsafe_allow_html=True,
            )
        else:
            if st.button("▶ Force Eval", key="force_eval_btn",
                         use_container_width=True, type="secondary",
                         disabled=not agent_up,
                         help=None if agent_up else "Start the agent first"):
                os.makedirs(STORE_DIR, exist_ok=True)
                open(trigger_path, "w").write(datetime.now(timezone.utc).isoformat())
                st.rerun()

    if not runs:
        st.info("No eval runs yet.")
        return

    def _run_label(r):
        forced = " · FORCED" if r.get("forced") else ""
        return f"{_fmt_ts(r.get('triggeredAt',''))}  ·  {r.get('modelVersion','?')}{forced}"

    run_labels = [_run_label(r) for r in runs]
    idx_a = st.selectbox("Run A — older / baseline", range(len(runs)),
                         format_func=lambda i: run_labels[i],
                         index=max(0, len(runs)-2), key="sel_a")
    idx_b = st.selectbox("Run B — newer / comparison", range(len(runs)),
                         format_func=lambda i: run_labels[i],
                         index=len(runs)-1, key="sel_b")

    if idx_a == idx_b:
        st.warning("Run A and Run B are the same — select two different runs to compare.")
        return

    run_a, run_b = runs[idx_a], runs[idx_b]
    lbl_a, lbl_b = run_labels[idx_a], run_labels[idx_b]
    cls     = _classifications_for(run_a, run_b)
    v_sum   = verdict_summary(cls)
    reg_cnt = sum(1 for c in cls if c["verdict"]=="REGRESSED")
    v_color = C_RED if reg_cnt else (C_GREEN if any(c["verdict"]=="IMPROVED" for c in cls) else C_DIM)

    st.markdown(
        f"<div style='padding:14px 0 8px;border-bottom:1px solid {C_BORDER};margin-bottom:16px;"
        f"display:flex;justify-content:space-between;align-items:center'>"
        f"<div><span style='font-size:1.43rem;font-weight:700;color:{C_TEXT};font-family:{FONT}'>{name}</span>"
        f"<span style='color:{C_DIM};font-size:0.98rem;margin-left:12px'>{env}</span></div>"
        f"<span style='color:{v_color};font-weight:700;font-family:{FONT};letter-spacing:2px;font-size:1.04rem'>{v_sum}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div class='sec-label'>RADAR</div>", unsafe_allow_html=True)
    fig_r = chart_radar(cls, lbl_a, lbl_b)
    if fig_r.data:
        st.plotly_chart(fig_r, width="stretch", config={"displayModeBar": False})

    st.divider()

    st.markdown("<div class='sec-label'>METRIC SUMMARY</div>", unsafe_allow_html=True)
    if cls:
        rows = [{"Metric":c["key"],"Verdict":c["verdict"],
                 "Prev":round(c["prev"],4) if c["prev"] is not None else None,
                 "Curr":round(c["curr"],4) if c["curr"] is not None else None,
                 "Δ":f"{c['delta']:+.4f}" if c["delta"] is not None else "—"} for c in cls]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                     height=min(260, 48+len(rows)*38))
    else:
        st.caption("No metrics — first run establishes baseline.")

    st.markdown("<div class='sec-label'>PER METRIC TYPE</div>", unsafe_allow_html=True)
    _prio = {"REGRESSED":0,"IMPROVED":1,"STABLE":2,"NEW":3}
    vbt = {}
    for c in cls:
        for mt in _all_metric_types(run_b):
            if c["key"].startswith(mt+"."):
                if _prio.get(c["verdict"],9) < _prio.get(vbt.get(mt,"STABLE"),9):
                    vbt[mt] = c["verdict"]
    for mt in _all_metric_types(run_b):
        if mt not in vbt:
            vbt[mt] = "NEW" if not _metrics_for(run_a) else "STABLE"

    for mt in sorted(_all_metric_types(run_b), key=lambda t: _prio.get(vbt.get(t,"STABLE"),9)):
        verdict    = vbt.get(mt,"STABLE")
        cases_prev = _cases_for_type(run_a, mt)
        cases_curr = _cases_for_type(run_b, mt)
        with st.expander(f"{mt}  —  {verdict}", expanded=(verdict=="REGRESSED")):
            if cases_prev and cases_curr:
                fig_d = chart_delta_bar(cases_prev, cases_curr, "Score Δ per case (worst first)")
                if fig_d.data:
                    st.plotly_chart(fig_d, width="stretch", config={"displayModeBar":False})
                st.caption("Status transitions")
                fig_g = chart_status_grid(cases_prev, cases_curr)
                if fig_g.data:
                    st.plotly_chart(fig_g, width="stretch", config={"displayModeBar":False})
            if cases_curr:
                prev_by_id = {c["caseId"]:c for c in cases_prev}
                rows = []
                for i, cc in enumerate(cases_curr):
                    pc  = prev_by_id.get(cc["caseId"],{})
                    psc,csc = pc.get("score"),cc.get("score")
                    delta = round(csc-psc,1) if isinstance(psc,float) and isinstance(csc,float) else None
                    rows.append({"#":i+1,"Prev status":pc.get("status","—"),
                                 "Prev score":int(psc) if isinstance(psc,float) else None,
                                 "Curr status":cc.get("status","—"),
                                 "Curr score":int(csc) if isinstance(csc,float) else None,
                                 "Δ":delta,"AI reason":cc.get("reason","")})
                rows.sort(key=lambda r: (r["Δ"] or 0))
                df = pd.DataFrame(rows).set_index("#")

                def _style_status(val):
                    if val == "Pass":
                        return "background-color:rgba(40,200,64,0.15);color:#28c840;font-weight:700"
                    if val == "Fail":
                        return "background-color:rgba(255,68,68,0.15);color:#ff4444;font-weight:700"
                    return ""

                def _style_delta(val):
                    try:
                        v = float(val)
                        if v > 0:  return f"color:{C_GREEN};font-weight:700"
                        if v < 0:  return f"color:{C_RED};font-weight:700"
                    except (TypeError, ValueError):
                        pass
                    return f"color:{C_DIM}"

                styled = (
                    df.style
                    .map(_style_status, subset=["Prev status", "Curr status"])
                    .map(_style_delta,  subset=["Δ"])
                )
                st.dataframe(styled, width="stretch",
                             height=min(420, 48+len(rows)*38))
                failures = [r for r in rows if r["Curr status"]=="Fail"]
                if failures:
                    st.markdown(
                        f"<div style='font-size:0.85rem;color:{C_RED};font-weight:700;"
                        f"letter-spacing:1px;margin:12px 0 6px;font-family:{FONT}'>"
                        f"FAILING CASES ({len(failures)})</div>",
                        unsafe_allow_html=True,
                    )
                    for f in failures:
                        with st.expander(f"Case {f['#']} — Score {f['Curr score']}"):
                            st.write(f["AI reason"])
            else:
                st.caption("No test case data for this metric type.")

    if len(runs) >= 2:
        st.markdown("<div class='sec-label'>METRIC TRENDS</div>", unsafe_allow_html=True)
        fig_t = chart_metric_trend(bot)
        if fig_t.data:
            st.plotly_chart(fig_t, width="stretch", config={"displayModeBar":False})

    st.markdown("<div class='sec-label'>RUN HISTORY</div>", unsafe_allow_html=True)
    rh_html = ""
    for r in reversed(runs):
        mt_list = ", ".join(r.get("testSets", {}).keys()) or "—"
        dot_col = C_DIM if r.get("_legacy") else (C_GOLD if r.get("forced") else C_CYAN)
        forced_tag = "  · FORCED" if r.get("forced") else ""
        rh_html += (
            "<div class='rh-item'>"
            f"<div class='rh-dot' style='background:{dot_col}'></div>"
            "<div class='rh-content'>"
            f"<div class='rh-model'>{r.get('modelVersion','—')[:36]}{forced_tag}</div>"
            f"<div class='rh-guid'>{mt_list}</div>"
            f"<div class='rh-ts'>{_fmt_ts(r.get('triggeredAt',''))}</div>"
            "</div></div>"
        )
    st.markdown("<div class='rh-timeline'>" + rh_html + "</div>", unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────────────────────────────
_load_ph = st.empty()
_spinner(_load_ph, "LOADING")
bots       = load_all_bots()
raw_events = load_events(STORE_DIR)
page       = st.session_state.get("page", "overview")
selected   = st.session_state.get("selected_bot")

render_header(bots, raw_events)

if page == "detail":
    bot = next((b for b in bots if b["botId"] == selected), None)
    if bot:
        page_bot_detail(bot)
    else:
        st.session_state.page = "overview"
        st.rerun()
else:
    page_overview(bots, raw_events)

_load_ph.empty()
