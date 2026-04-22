"""
dashboard/pages/ashoka.py — Fleet view, bot detail, identity, and mission timeline.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import re
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
from agent.events import load_events, eval_queued as _ev_queued
from agent.store import patch_run as _patch_run
from spinner import spinner as _spinner

STORE_DIR   = os.environ.get("STORE_DIR", "data")
CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
PID_FILE    = os.path.join(STORE_DIR, "agent", "agent.pid")


def _agent_running():
    try:
        pid = int(open(PID_FILE).read().strip())
    except Exception:
        return False
    try:
        import psutil as _ps
        p = _ps.Process(pid)
        return p.is_running() and p.status() != _ps.STATUS_ZOMBIE
    except Exception:
        return False


# ── Page-specific CSS ─────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  /* Stat bar */
  .stat-bar {{
    display:grid; grid-template-columns:repeat(4,1fr);
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


def _load_all_bots_uncached():
    import time as _t
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


def load_all_bots():
    import time as _t
    now = _t.time()
    if now - st.session_state.get("_bots_ts", 0) < 10:
        return st.session_state.get("_bots_cache", [])
    bots = _load_all_bots_uncached()
    st.session_state["_bots_cache"] = bots
    st.session_state["_bots_ts"] = now
    return bots


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


def _run_meta(run: dict) -> dict:
    """Extract API-level metadata from the first test set result."""
    for ts_data in run.get("testSets", {}).values():
        res = ts_data.get("results", ts_data) if isinstance(ts_data, dict) else {}
        if res.get("state") or res.get("startTime"):
            start = res.get("startTime", "")
            end   = res.get("endTime", "")
            dur   = ""
            try:
                s = datetime.fromisoformat(start.replace("Z", "+00:00"))
                e = datetime.fromisoformat(end.replace("Z",   "+00:00"))
                secs = int((e - s).total_seconds())
                dur  = f"{secs // 60}m {secs % 60}s"
            except Exception:
                pass
            return {
                "runId":          res.get("id", ""),
                "state":          res.get("state", ""),
                "startTime":      start,
                "endTime":        end,
                "duration":       dur,
                "totalTestCases": res.get("totalTestCases", 0),
            }
    return {}


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


def chart_score_comparison(cases_prev, cases_curr, label_a, label_b):
    """Grouped bar: Run A (gold) vs Run B (coloured by change) per case, sorted worst first."""
    prev_by_id = {c["caseId"]: c for c in cases_prev}
    items = []
    for i, cc in enumerate(cases_curr):
        pc  = prev_by_id.get(cc["caseId"], {})
        sa  = pc.get("score") if pc else None
        sb  = cc.get("score")
        d   = round(sb - sa, 1) if (sa is not None and sb is not None) else 0
        items.append({"label": f"#{i+1}", "sa": sa if sa is not None else 0,
                      "sb": sb if sb is not None else 0, "delta": d})
    items.sort(key=lambda x: x["delta"])
    labels   = [x["label"] for x in items]
    scores_a = [x["sa"] for x in items]
    scores_b = [x["sb"] for x in items]
    colors_b = [C_RED if x["delta"] < -2 else (C_GREEN if x["delta"] > 2 else C_CYAN)
                for x in items]
    fig = go.Figure()
    fig.add_trace(go.Bar(name=f"A  {label_a[:28]}", x=labels, y=scores_a,
                         marker_color=C_GOLD, opacity=0.7,
                         hovertemplate="%{x} · Run A: %{y}<extra></extra>"))
    fig.add_trace(go.Bar(name=f"B  {label_b[:28]}", x=labels, y=scores_b,
                         marker_color=colors_b, opacity=0.9,
                         hovertemplate="%{x} · Run B: %{y}<extra></extra>"))
    fig.update_layout(
        **_LAYOUT, barmode="group", height=260,
        title=dict(text="Score per case — A (gold) vs B, sorted worst Δ first",
                   font=dict(size=10, color=C_DIM)),
    )
    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(**_AXIS, range=[0, 110], tickvals=[0, 25, 50, 75, 100])
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
    # Fixed semantic z-values so each cell gets a distinct colour regardless of count
    # z=3→green (stayed pass), z=1→red (pass→fail), z=2→cyan (fail→pass), z=0→gold (stayed fail)
    colorscale = [
        [0.00, "rgba(255,215,0,0.45)"],   # z=0  stayed fail  → gold
        [0.24, "rgba(255,215,0,0.45)"],
        [0.25, "rgba(255,68,68,0.55)"],   # z=1  pass→fail    → red
        [0.49, "rgba(255,68,68,0.55)"],
        [0.50, "rgba(0,240,255,0.40)"],   # z=2  fail→pass    → cyan
        [0.74, "rgba(0,240,255,0.40)"],
        [0.75, "rgba(40,200,64,0.50)"],   # z=3  stayed pass  → green
        [1.00, "rgba(40,200,64,0.50)"],
    ]
    fig = go.Figure(go.Heatmap(
        z=[[3, 1], [2, 0]],
        x=["→ Pass", "→ Fail"],
        y=["Was Pass", "Was Fail"],
        text=[[f"Stayed Pass\n{pp}", f"Pass → Fail\n{pf}"],
              [f"Fail → Pass\n{fp}", f"Stayed Fail\n{ff}"]],
        texttemplate="%{text}",
        textfont=dict(color=C_TEXT, size=11),
        colorscale=colorscale, showscale=False,
        zmin=0, zmax=3,
        hovertemplate="%{text}<extra></extra>",
    ))
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
        m  = _metrics_for(r)
        mv = (r.get("modelVersion") or "").strip()
        mv = mv if mv and mv not in ("unknown", "?") else _fmt_ts(r.get("triggeredAt", ""))
        all_keys.update(m.keys())
        data.append({"label": mv, "metrics": m})
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


# ── Metric type label helper ──────────────────────────────────────────────────
_MT_MAP = {
    "CompareMeaning":      "Compare Meaning",
    "IntentRecognition":   "Intent Recognition",
    "ExactMatch":          "Exact Match",
    "PartialMatch":        "Partial Match",
    "SentenceSimilarity":  "Sentence Similarity",
    "EntityRecognition":   "Entity Recognition",
    "AdherenceToInstructions": "Adherence to Instructions",
    "GroundednessScore":   "Groundedness",
    "CoherenceScore":      "Coherence",
    "FluencyScore":        "Fluency",
    "RelevanceScore":      "Relevance",
}

def _readable_mt(mt: str) -> str:
    if mt in _MT_MAP:
        return _MT_MAP[mt]
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', mt)


# ── Verdict helpers ───────────────────────────────────────────────────────────
_V_COLORS = {"REGRESSED":C_RED,"IMPROVED":C_GREEN,"STABLE":C_DIM,"NEW":C_GOLD,"BASELINE":C_GOLD}


# ── Timeline helpers ──────────────────────────────────────────────────────────
_EVENT_META = {
    "agent_start":   ("info","🟢","AGENT START",  "new"),
    "agent_stop":    ("warn","🔴","AGENT STOP",   "warn"),
    "scan_start":    ("info","🔍","SCAN START",   "new"),
    "scan_end":      ("warn","🔲","SCAN END",     "warn"),
    "cycle_start":   ("info","📡","SCANNING",     "stb"),
    "model_change":  ("warn","🔄","MODEL SHIFT",  "warn"),
    "eval_queued":   ("info","⏳","EVAL QUEUED",  "new"),
    "agent_eval":    ("info","🤖","AGENT EVAL",   "new"),
    "eval_start":    ("info","🚀","EVAL START",   "new"),
    "eval_complete": ("info","✅","EVAL DONE",    "stb"),
    "eval_timeout":  ("bad", "⏱️","TIMEOUT",      "reg"),
    "eval_no_sets":  ("warn","📭","NO TEST SETS", "warn"),
    "force_eval":    ("info","⚡","USER EVAL",    "new"),
    "error":         ("bad", "🔥","ERROR",         "reg"),
}

def _build_timeline_events(raw, model_lookup: dict | None = None):
    """model_lookup: {botId: modelVersion} for showing model alongside agent name."""
    out = []
    for e in raw:
        et = e.get("event","")
        if et in ("cycle_start", "stable", "regression", "improvement"):
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
    return out


# ── Header ────────────────────────────────────────────────────────────────────
def render_header(bots, raw_events, page="overview"):
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

    if page == "overview":
        st.markdown(f"""
        <style>
          .sys-dot-hdr {{
            width:16px;height:16px;border-radius:50%;background:{sys_color};
            box-shadow:0 0 10px {sys_color},0 0 20px {sys_color}44;
            display:inline-block;margin-right:8px;
            animation:{blink_anim};vertical-align:middle;
          }}
          .radar-wrap {{ width:100px;height:100px; }}
          .r1 {{ width:100px;height:100px; }} .r2 {{ width:72px;height:72px; }}
          .r3 {{ width:45px;height:45px; }}  .r4 {{ width:19px;height:19px; }}
          .radar-h {{ width:100px; }} .radar-v {{ height:100px; }}
        </style>
        <div style='display:flex;align-items:center;gap:20px;max-width:860px;margin:0 auto 12px'>
          <div class='radar-wrap' style='flex-shrink:0'>
            <div class='ring r1'></div><div class='ring r2'></div>
            <div class='ring r3'></div><div class='ring r4'></div>
            <div class='radar-h'></div><div class='radar-v'></div>
            <div class='sweep'></div><div class='center-dot'></div>
          </div>
          <div>
            <div style='font-size:2rem;font-weight:700;letter-spacing:8px;color:{C_CYAN};
                        font-family:{FONT};line-height:1;
                        text-shadow:0 0 20px rgba(0,240,255,.4)'><span style='font-variant:small-caps'>āshokā</span></div>
            <div style='font-size:0.72rem;color:{C_DIM};letter-spacing:1px;margin-top:4px'>
              <span class="sys-dot-hdr"></span>{sys_label} &nbsp;·&nbsp; {n_bots} agent{n_plural} &nbsp;·&nbsp; {ts_str}</div>
          </div>
        </div>
        <div class='stat-bar'>
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
        </div>
        """, unsafe_allow_html=True)


# ── Overview page ─────────────────────────────────────────────────────────────
def page_overview(bots, raw_events):
    # ── WHO I AM — centered, 75% width ───────────────────────────────────────
    st.markdown("<div class='sec-label'>ĀSHOKĀ</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='max-width:75%;margin:0 auto 20px;text-align:center;"
        f"background:{C_CARD};border:1px solid {C_BORDER};"
        f"border-radius:8px;padding:20px 28px;font-size:1.08rem;"
        f"line-height:1.85;color:{C_TEXT}'>"
        f"I am <span style='color:{C_CYAN};font-variant:small-caps'>āshokā</span> — born April 1, 2026. "
        f"Model swaps. I score. You decide."
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── MONITORED AGENTS ─────────────────────────────────────────────────────
    if not bots:
        # Show configured bots from config.json even before first run
        _cfg_bots = []
        try:
            _cfg = json.loads(open(CONFIG_PATH).read())
            for _env in _cfg.get("environments", []):
                _monitored = _env.get("monitoredBots", [])
                if _monitored:
                    for _schema in _monitored:
                        _cfg_bots.append({"name": _schema, "env": _env["name"]})
                else:
                    _cfg_bots.append({"name": f"All agents", "env": _env["name"]})
        except Exception:
            pass

        st.markdown("<div class='sec-label'>MONITORED AGENTS</div>", unsafe_allow_html=True)
        if _cfg_bots:
            cols = st.columns(4)
            for i, b in enumerate(_cfg_bots):
                with cols[i % 4]:
                    if st.button(b["name"],
                                 key=f"cfg_tile_{i}", width="stretch"):
                        st.session_state["selected_cfg_bot"] = b
                        st.session_state.page = "cfg_detail"
                        st.rerun()
        else:
            st.markdown(
                f"<div style='color:{C_DIM};font-size:0.85rem;padding:20px 0'>"
                f"No agents configured — complete Setup to add environments and agents.</div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown("<div class='sec-label'>MONITORED AGENTS</div>", unsafe_allow_html=True)
        _dv_auth_missing = os.path.exists(os.path.join(STORE_DIR, "agent", "dv_auth_needed.json"))
        cols = st.columns(4)
        for i, bot in enumerate(bots):
            with cols[i % 4]:
                mv_warn = " ⚠" if (_dv_auth_missing and bot.get("modelVersion") == "unknown") else ""
                if st.button(
                    bot["botName"] + mv_warn,
                    key=f"tile_{bot['botId']}", width="stretch",
                ):
                    st.session_state.selected_bot = bot["botId"]
                    st.session_state.page = "detail"
                    st.rerun()

    # ── MISSION TIMELINE ─────────────────────────────────────────────────────
    st.markdown("<div class='sec-label'>MISSION TIMELINE</div>", unsafe_allow_html=True)

    model_lookup = {b["botId"]: b.get("modelVersion","") for b in bots}
    _NOISE       = ("cycle_start", "stable", "regression", "improvement")
    live         = _build_timeline_events(raw_events, model_lookup)[:15]

    # Pin lifecycle + heartbeat events at the bottom if pushed off by eval cycles
    _visible_ts  = {e.get("ts") for e in [r for r in raw_events if r.get("event") not in _NOISE][:15]}
    _pinned      = []
    # Most recent cycle_start = proof agent is scanning even when no changes detected
    _last_scan = next((e for e in raw_events if e.get("event") == "cycle_start"), None)
    if _last_scan and _last_scan.get("ts") not in _visible_ts:
        _pinned.extend(_build_timeline_events([_last_scan], model_lookup))
    for _etype in ("scan_end", "scan_start", "agent_stop", "agent_start"):
        _match = next((e for e in raw_events if e.get("event") == _etype), None)
        if _match and _match.get("ts") not in _visible_ts:
            _pinned.extend(_build_timeline_events([_match], model_lookup))

    all_events = live + _pinned

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
            f'&nbsp;<span class="etl-badge {ev["badge_c"]}">{ev["badge"]}</span></div>'
            f'<div class="etl-body">{ev["body"]}</div>'
            f'</div>'
        )

    st.markdown(
        '<div style="max-width:680px;margin:0 auto">'
        '<div class="etl-wrap"><div class="etl-line"></div>'
        + "".join(parts)
        + '</div></div>',
        unsafe_allow_html=True,
    )


# ── Eval live banner (fragment — auto-refreshes without blocking navigation) ──
@st.fragment(run_every=3)
def _eval_live_banner(bot_id: str):
    lock_path     = os.path.join(STORE_DIR, "agent", f"eval_active_{bot_id}.lock")
    progress_path = os.path.join(STORE_DIR, "agent", f"eval_progress_{bot_id}.json")
    if not os.path.exists(lock_path):
        st.rerun(scope="app")
        return
    lock_data = {}
    try:
        lock_raw = open(lock_path).read().strip()
        lock_data = json.loads(lock_raw) if lock_raw.startswith("{") else {}
    except Exception:
        pass
    prog = {}
    try:
        if os.path.exists(progress_path):
            prog = json.loads(open(progress_path).read())
    except Exception:
        pass
    elapsed     = prog.get("elapsedSecs", 0)
    elapsed_fmt = f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"
    mv          = lock_data.get("modelVersion", "")
    mv_label    = f" ON {mv}" if mv and mv not in ("unknown", "") else ""
    st.markdown(f"""
<style>
@keyframes bomb-tick {{
  0%,80%,100% {{ transform:rotate(0deg) scale(1); }}
  83%  {{ transform:rotate(-12deg) scale(1.08); }}
  86%  {{ transform:rotate(12deg)  scale(1.08); }}
  89%  {{ transform:rotate(-7deg)  scale(1.04); }}
  92%  {{ transform:rotate(7deg)   scale(1.04); }}
  95%  {{ transform:rotate(-3deg)  scale(1.01); }}
  98%  {{ transform:rotate(0deg)   scale(1); }}
}}
@keyframes fuse-burn {{
  0%,100% {{ opacity:1; text-shadow:0 0 6px #ff6600,0 0 12px #ff3300; }}
  50%     {{ opacity:0.4; text-shadow:0 0 3px #ffaa00; }}
}}
@keyframes banner-throb {{
  0%,100% {{ border-color:#ff4444; box-shadow:0 0 6px rgba(255,68,68,0.3); }}
  50%     {{ border-color:#ff7700; box-shadow:0 0 12px rgba(255,119,0,0.5); }}
}}
.eval-live {{
  display:flex; align-items:center; gap:8px;
  background:#1a0808; border:1px solid #ff4444;
  border-radius:8px; padding:10px 14px;
  animation:banner-throb 1.5s ease-in-out infinite;
}}
.eval-bomb {{
  font-size:1.4rem; line-height:1; display:inline-block;
  animation:bomb-tick 1.5s ease-in-out infinite;
}}
.eval-fuse {{
  font-size:0.7rem; display:inline-block;
  animation:fuse-burn 0.35s ease-in-out infinite;
}}
.eval-text {{
  font-family:monospace; font-size:0.88rem; color:#ff8888;
  display:flex; gap:12px; flex-wrap:wrap; align-items:center;
}}
</style>
<div class="eval-live">
  <span class="eval-bomb">💣</span>
  <span class="eval-fuse">✦</span>
  <div class="eval-text">
    <span>EVAL RUNNING{mv_label}</span>
    <span>{elapsed_fmt}</span>
  </div>
</div>""", unsafe_allow_html=True)


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
        trigger_path = os.path.join(STORE_DIR, "agent", f"force_eval_{bot_id}.trigger")
        lock_path    = os.path.join(STORE_DIR, "agent", f"eval_active_{bot_id}.lock")
        queued       = os.path.exists(trigger_path)
        running      = os.path.exists(lock_path)
        agent_up     = _agent_running()
        import time as _t
        queued_age   = (_t.time() - os.path.getmtime(trigger_path)) if queued else 0
        stale        = queued_age > 180  # stuck for >3 min
        if queued:
            qc1, qc2 = st.columns([3, 1])
            with qc1:
                label = "⚠ Eval stuck — click ✕" if (stale or not agent_up) else "⏳ Eval queued"
                st.button(label, key="btn_queued",
                          width="stretch", type="secondary", disabled=True)
            with qc2:
                if st.button("✕", key="btn_cancel_queued", width="stretch",
                             help="Cancel queued eval"):
                    try:
                        os.remove(trigger_path)
                    except Exception:
                        pass
                    st.rerun()
        elif running and agent_up:
            _eval_live_banner(bot_id)
        else:
            if st.button("▶ Force Eval", key="force_eval_btn",
                         width="stretch", type="secondary",
                         disabled=not agent_up,
                         help=None if agent_up else "Start the agent first"):
                os.makedirs(STORE_DIR, exist_ok=True)
                open(trigger_path, "w").write("user")
                _ev_queued(STORE_DIR, bot["botName"], bot_id)
                st.session_state["_ev_ts"] = 0
                st.rerun()

    if bot.get("modelVersion") == "unknown":
        _dv_flag = os.path.join(STORE_DIR, "agent", "dv_auth_needed.json")
        if os.path.exists(_dv_flag):
            st.warning(
                "**Model version unavailable.** "
                "ĀSHOKĀ cannot detect model changes for this agent until the app registration has "
                "**Dynamics CRM → user_impersonation** (delegated) with admin consent. "
                "Add the permission in Entra ID, grant consent, then re-authenticate via **Setup → Authentication**. "
                "Evals can still be forced manually.",
                icon="⚠️",
            )

    if not runs:
        st.info("No eval runs yet.")
        return

    def _run_label(r):
        src = r.get("triggerSource", "")
        mv  = r.get("modelVersion") or ""
        mv  = mv if mv and mv not in ("unknown", "?") else ""
        ts  = _fmt_ts(r.get("triggeredAt", ""))
        if r.get("forced"):
            if src == "agent":
                # Agent-triggered (model change): keep timestamp for context
                return (f"{ts}  ·  {mv}  ·  AGENT" if mv else f"{ts}  ·  AGENT") if ts else f"{mv}  ·  AGENT"
            else:
                # User-triggered force eval: no timestamp needed
                return f"{mv}  ·  USER" if mv else "USER"
        return (f"{ts}  ·  {mv}" if mv else ts)

    run_labels = [_run_label(r) for r in runs]
    run_b = runs[-1]
    lbl_b = run_labels[-1]

    st.markdown(
        f"<div style='font-size:0.75rem;color:{C_DIM};margin:6px 0 10px;"
        f"letter-spacing:0.5px'>Current &nbsp;·&nbsp; "
        f"<span style='color:{C_CYAN};font-family:{FONT}'>{lbl_b}</span></div>",
        unsafe_allow_html=True,
    )

    # ── Run B metadata strip ──────────────────────────────────────────────────
    meta  = _run_meta(run_b)
    mv_b  = run_b.get("modelVersion") or "—"
    mv_b  = mv_b if mv_b not in ("unknown", "?") else "—"
    cells = [
        ("MODEL",      mv_b),
        ("STATE",      meta.get("state", "—")),
        ("STARTED",    _fmt_ts(meta.get("startTime", ""))),
        ("DURATION",   meta.get("duration", "—")),
        ("TEST CASES", str(meta.get("totalTestCases", "—"))),
    ]
    cells_html = "".join(
        f"<div style='background:{C_CARD};padding:10px 16px;text-align:center;"
        f"border-right:1px solid {C_BORDER}'>"
        f"<div style='font-size:0.6rem;letter-spacing:2px;color:{C_DIM};font-family:{FONT}'>{lbl}</div>"
        f"<div style='font-size:0.9rem;font-weight:700;color:{C_TEXT};font-family:{FONT};margin-top:3px'>{val}</div>"
        f"</div>"
        for lbl, val in cells
    )
    st.markdown(
        f"<div style='display:grid;grid-template-columns:repeat({len(cells)},1fr);"
        f"border:1px solid {C_BORDER};border-radius:8px;overflow:hidden;margin-bottom:16px'>"
        f"{cells_html}</div>",
        unsafe_allow_html=True,
    )

    # ── Run A selector ────────────────────────────────────────────────────────
    c_sel, _ = st.columns([2, 3])
    with c_sel:
        idx_a = st.selectbox(
            "Baseline",
            range(len(runs) - 1),
            format_func=lambda i: run_labels[i],
            index=max(0, len(runs) - 2),
            key="sel_a",
        )
    run_a = runs[idx_a]
    lbl_a = run_labels[idx_a]

    cls     = _classifications_for(run_a, run_b)
    v_sum   = verdict_summary(cls)
    reg_cnt = sum(1 for c in cls if c["verdict"] == "REGRESSED")
    v_color = C_RED if reg_cnt else (C_GREEN if any(c["verdict"] == "IMPROVED" for c in cls) else C_DIM)

    st.markdown(
        f"<div style='padding:14px 0 8px;border-bottom:1px solid {C_BORDER};margin-bottom:16px;"
        f"display:flex;justify-content:space-between;align-items:center'>"
        f"<div><span style='font-size:1.43rem;font-weight:700;color:{C_TEXT};font-family:{FONT}'>{name}</span>"
        f"<span style='color:{C_DIM};font-size:0.98rem;margin-left:12px'>{env}</span></div>"
        f"<span style='color:{v_color};font-weight:700;font-family:{FONT};letter-spacing:2px;"
        f"font-size:1.04rem'>{v_sum}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div class='sec-label'>METRIC SUMMARY</div>", unsafe_allow_html=True)
    if cls:
        rows = [{"Metric": c["key"], "Verdict": c["verdict"],
                 "Baseline": round(c["prev"], 4) if c["prev"] is not None else None,
                 "Current":  round(c["curr"], 4) if c["curr"] is not None else None,
                 "Δ":        f"{c['delta']:+.4f}" if c["delta"] is not None else "—"} for c in cls]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                     height=min(260, 48 + len(rows) * 38))
    else:
        st.caption("No metrics — first run establishes baseline.")

    if len(runs) >= 2:
        st.markdown("<div class='sec-label'>METRIC TRENDS</div>", unsafe_allow_html=True)
        fig_t = chart_metric_trend(bot)
        if fig_t.data:
            st.plotly_chart(fig_t, use_container_width=True, config={"displayModeBar": False})

    # ── LLM Analysis ─────────────────────────────────────────────────────────
    st.markdown("<div class='sec-label'>ask āshokā</div>", unsafe_allow_html=True)
    _ana_key  = f"_llm_{bot['botId']}_{idx_a}_{len(runs)-1}"
    _folder_a = run_a.get("_folder", "")
    _folder_b = run_b.get("_folder", "")
    _skip_key = f"_skip_{_ana_key}"
    if _ana_key not in st.session_state and not st.session_state.get(_skip_key):
        # Try in-memory first, then read from disk (catches stale cache)
        _stored = run_b.get("analyses", {}).get(_folder_a, "")
        if not _stored and _folder_b and _folder_a:
            try:
                _rpath = os.path.join(STORE_DIR, bot["botId"], "transactions",
                                      _folder_b, "run.json")
                _rdisk = json.loads(open(_rpath, encoding="utf-8").read())
                _stored = _rdisk.get("analyses", {}).get(_folder_a, "")
            except Exception:
                pass
        if _stored:
            st.session_state[_ana_key] = _stored
    if _ana_key in st.session_state:
        _ana_text = st.session_state[_ana_key]
        st.markdown(
            f"<div class='analysis-panel'>"
            f"<div class='analysis-label'><span style='font-variant:small-caps'>āshokā</span> says</div>"
            + _ana_text.replace("\n\n", "<br><br>").replace("\n", " ")
            + "</div>",
            unsafe_allow_html=True,
        )
        if st.button("↺ Re-analyse", key=f"btn_reana_{_ana_key}", type="secondary"):
            del st.session_state[_ana_key]
            st.session_state[_skip_key] = True  # block auto-reload from disk
            st.rerun()
    else:
        _old_m = run_a.get("modelVersion") or "unknown"
        _new_m = run_b.get("modelVersion") or "unknown"
        if len(runs) >= 2:
            st.markdown(f"""
<style>
@keyframes ashoka-pulse {{
  0%,100% {{ box-shadow:0 0 4px {C_MAGENTA}55; border-color:{C_MAGENTA}66; }}
  50%     {{ box-shadow:0 0 16px {C_MAGENTA}bb; border-color:{C_MAGENTA}; }}
}}
.ashoka-cta {{
  background:{C_BG}; border:1px solid {C_MAGENTA}66; border-radius:8px;
  padding:14px 20px; margin-bottom:12px;
  animation:ashoka-pulse 2.8s ease-in-out infinite;
}}
</style>
<div class='ashoka-cta'>
  <div style='font-size:0.7rem;color:{C_MAGENTA};letter-spacing:2px;
              font-family:{FONT};font-weight:700;margin-bottom:5px'>
    ✦ &nbsp;<span style='font-variant:small-caps'>āshokā</span> &nbsp;— LLM ANALYSIS
  </div>
  <div style='font-size:0.85rem;color:{C_DIM};line-height:1.65'>
    Root cause &nbsp;·&nbsp; failure pattern &nbsp;·&nbsp; remediation steps
    &nbsp;·&nbsp; <strong style='color:{C_TEXT}'>PROCEED / INVESTIGATE / REVERT</strong> verdict.
    <br><span style='color:{C_TEXT}'>Click below — āshokā will search model docs and reason over every test case.</span>
  </div>
</div>""", unsafe_allow_html=True)
            if st.button("▶ Ask āshokā", key=f"btn_ana_{_ana_key}", type="primary"):
                with st.spinner("Searching and consulting āshokā…"):
                    try:
                        _cfg = json.loads(open(CONFIG_PATH).read())
                        from agent.reasoning import analyse_variation as _analyse
                        _text = _analyse(
                            bot_name=name, old_model=_old_m, new_model=_new_m,
                            test_sets=run_b.get("testSets", {}),
                            prev_run=run_a, cfg=_cfg,
                        )
                        st.session_state[_ana_key] = _text
                        st.session_state.pop(_skip_key, None)
                        if _folder_b and _folder_a:
                            _analyses = run_b.get("analyses", {})
                            _analyses[_folder_a] = _text
                            _patch_run(STORE_DIR, bot["botId"], _folder_b,
                                       {"analyses": _analyses})
                            run_b["analyses"] = _analyses
                            st.session_state["_bots_ts"] = 0
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Analysis failed: {_e}")

    st.markdown("<div class='sec-label'>PER METRIC TYPE</div>", unsafe_allow_html=True)
    _prio = {"REGRESSED": 0, "IMPROVED": 1, "STABLE": 2, "NEW": 3}
    vbt: dict[str, str] = {}
    for c in cls:
        for mt in _all_metric_types(run_b):
            if c["key"].startswith(mt + "."):
                if _prio.get(c["verdict"], 9) < _prio.get(vbt.get(mt, "STABLE"), 9):
                    vbt[mt] = c["verdict"]
    for mt in _all_metric_types(run_b):
        if mt not in vbt:
            vbt[mt] = "NEW" if not _metrics_for(run_a) else "STABLE"

    _verdict_icons = {"REGRESSED": "▼", "IMPROVED": "▲", "STABLE": "●", "NEW": "★"}
    for mt in sorted(_all_metric_types(run_b), key=lambda t: _prio.get(vbt.get(t, "STABLE"), 9)):
        verdict    = vbt.get(mt, "STABLE")
        _icon      = _verdict_icons.get(verdict, "●")
        _label     = f"{_icon}  {_readable_mt(mt)}  —  {verdict}"
        cases_prev = _cases_for_type(run_a, mt)
        cases_curr = _cases_for_type(run_b, mt)
        with st.expander(_label, expanded=(verdict == "REGRESSED")):

            # Score comparison chart (grouped bars A vs B)
            if cases_prev and cases_curr:
                fig_s = chart_score_comparison(cases_prev, cases_curr, lbl_a, lbl_b)
                if fig_s.data:
                    st.plotly_chart(fig_s, use_container_width=True, config={"displayModeBar": False})
                fig_g = chart_status_grid(cases_prev, cases_curr)
                if fig_g.data:
                    st.caption("Status transitions")
                    st.plotly_chart(fig_g, use_container_width=True, config={"displayModeBar": False})

            # Per-case detail: summary table + expandable reasons (scales to 100+ cases)
            if cases_curr:
                prev_by_id = {c["caseId"]: c for c in cases_prev}
                case_rows = []
                for i, cc in enumerate(cases_curr):
                    pc  = prev_by_id.get(cc["caseId"], {})
                    psc = pc.get("score")
                    csc = cc.get("score")
                    d   = round(csc - psc, 1) if (isinstance(psc, float) and isinstance(csc, float)) else None
                    ps  = pc.get("status", "")
                    cs  = cc.get("status", "")
                    if ps == "Pass" and cs == "Fail":
                        group = 0  # Regressed
                    elif ps == "Fail" and cs == "Pass":
                        group = 1  # Improved
                    elif cs == "Fail":
                        group = 2  # Persistent fail
                    else:
                        group = 3  # Stable pass
                    case_rows.append({
                        "i": i + 1, "group": group,
                        "prev_status": ps or "—",
                        "prev_score":  int(psc) if isinstance(psc, float) else None,
                        "curr_status": cs or "—",
                        "curr_score":  int(csc) if isinstance(csc, float) else None,
                        "delta":       d,
                        "prev_reason": pc.get("reason", "") if pc else "",
                        "curr_reason": cc.get("reason", ""),
                    })
                case_rows.sort(key=lambda r: (r["group"], -(abs(r["delta"]) if r["delta"] is not None else 0)))

                st.markdown(
                    f"<div style='font-size:0.7rem;font-weight:700;color:{C_DIM};"
                    f"letter-spacing:2px;margin:14px 0 4px;font-family:{FONT}'>CASE DETAIL</div>",
                    unsafe_allow_html=True,
                )

                _groups = [
                    (0, "Pass → Fail",      C_RED,   True),
                    (1, "Fail → Pass",      C_GREEN, False),
                    (2, "Fail → Fail",      C_GOLD,  False),
                    (3, "Pass → Pass",      C_DIM,   False),
                ]
                _grid = f"display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:6px;margin:6px 0 14px"

                for gid, glabel, gcol, gopen in _groups:
                    rows_in_group = [r for r in case_rows if r["group"] == gid]
                    if not rows_in_group:
                        continue
                    cards = []
                    for cr in rows_in_group:
                        d_val  = cr["delta"]
                        d_str  = f"{d_val:+.0f}" if d_val is not None else "—"
                        ps     = cr["prev_score"] if cr["prev_score"] is not None else "—"
                        cs_sc  = cr["curr_score"] if cr["curr_score"] is not None else "—"
                        border = (C_RED   if cr["group"] == 0 else
                                  C_GREEN if cr["group"] == 1 else
                                  C_GOLD  if cr["group"] == 2 else C_BORDER)
                        d_col  = (C_RED   if d_val is not None and d_val < -2 else
                                  C_GREEN if d_val is not None and d_val > 2  else C_DIM)
                        bs_col = C_GREEN if cr["prev_status"] == "Pass" else (C_RED if cr["prev_status"] == "Fail" else C_DIM)
                        cs_col = C_GREEN if cr["curr_status"] == "Pass" else (C_RED if cr["curr_status"] == "Fail" else C_DIM)
                        open_  = "open" if gopen else ""
                        prev_block = (
                            f"<div style='font-size:0.62rem;color:{C_DIM};letter-spacing:1px;"
                            f"font-family:{FONT};margin-bottom:3px'>BASELINE</div>"
                            f"<div style='font-size:0.82rem;color:{C_DIM};line-height:1.55;"
                            f"margin-bottom:10px'>{cr['prev_reason']}</div>"
                        ) if cr["prev_reason"] else ""
                        cards.append(
                            f"<details {open_} style='background:{C_CARD};border:1px solid {border};"
                            f"border-radius:6px;overflow:hidden'>"
                            f"<summary style='padding:8px 12px;cursor:pointer;list-style:none;"
                            f"display:flex;justify-content:space-between;align-items:center;gap:8px'>"
                            f"<span style='font-family:{FONT};font-size:0.72rem;color:{C_DIM};flex-shrink:0'>#{cr['i']}</span>"
                            f"<span style='font-size:0.78rem;flex:1;white-space:nowrap'>"
                            f"<span style='color:{bs_col}'>{cr['prev_status']}</span>"
                            f"<span style='color:{C_DIM}'>&nbsp;{ps}&nbsp;→&nbsp;</span>"
                            f"<span style='color:{cs_col}'>{cr['curr_status']}</span>"
                            f"<span style='color:{C_DIM}'>&nbsp;{cs_sc}</span>"
                            f"</span>"
                            f"<span style='font-family:{FONT};font-size:0.78rem;font-weight:700;"
                            f"color:{d_col};flex-shrink:0'>Δ&nbsp;{d_str}</span>"
                            f"<span style='font-size:0.6rem;color:{C_DIM};flex-shrink:0'>↕</span>"
                            f"</summary>"
                            f"<div style='padding:10px 14px;border-top:1px solid {C_BORDER}'>"
                            f"{prev_block}"
                            f"<div style='font-size:0.62rem;color:{C_CYAN};letter-spacing:1px;"
                            f"font-family:{FONT};margin-bottom:3px'>CURRENT</div>"
                            f"<div style='font-size:0.82rem;color:{C_TEXT};line-height:1.55'>"
                            f"{cr['curr_reason']}</div>"
                            f"</div></details>"
                        )
                    st.markdown(
                        f"<div style='font-size:0.68rem;font-weight:700;color:{gcol};"
                        f"letter-spacing:2px;margin:10px 0 4px;font-family:{FONT}'>"
                        f"{glabel} &nbsp;·&nbsp; {len(rows_in_group)}</div>"
                        f"<div style='{_grid}'>" + "".join(cards) + "</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No test case data for this metric type.")

    st.markdown("<div class='sec-label'>RUN HISTORY</div>", unsafe_allow_html=True)
    rh_html = ""
    for r in reversed(runs):
        mt_list = ", ".join(r.get("testSets", {}).keys()) or "—"
        dot_col = C_DIM if r.get("_legacy") else (C_GOLD if r.get("forced") else C_CYAN)
        _src       = r.get("triggerSource", "")
        forced_tag = ("  · USER" if _src == "user" else "  · AGENT") if r.get("forced") else ""
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

    # ── Delete all runs ───────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    st.divider()
    bot_id   = bot["botId"]
    _del_key = f"confirm_del_runs_{bot_id}"
    if st.session_state.get(_del_key):
        st.warning(f"This will permanently delete all {len(runs)} run(s) for **{name}**.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("⚠ Confirm — delete all runs", key=f"del_runs_yes_{bot_id}",
                         type="primary", width="stretch"):
                import shutil
                txn_dir = os.path.join(STORE_DIR, bot_id, "transactions")
                if os.path.isdir(txn_dir):
                    shutil.rmtree(txn_dir, ignore_errors=True)
                for suffix in (f"force_eval_{bot_id}.trigger",
                               f"eval_active_{bot_id}.lock",
                               f"eval_progress_{bot_id}.json"):
                    try:
                        os.remove(os.path.join(STORE_DIR, "agent", suffix))
                    except Exception:
                        pass
                st.session_state.pop(_del_key, None)
                st.session_state["_bots_ts"] = 0   # bust cache
                st.session_state.page = "overview"
                st.rerun()
        with c2:
            if st.button("Cancel", key=f"del_runs_no_{bot_id}",
                         type="secondary", width="stretch"):
                st.session_state.pop(_del_key, None)
                st.rerun()
    else:
        if st.button("✕ Delete all runs", key=f"del_runs_arm_{bot_id}",
                     width="content"):
            st.session_state[_del_key] = True
            st.rerun()


# ── Config bot detail (no tracking data yet) ──────────────────────────────────
def page_cfg_bot_detail(cfg_bot: dict):
    if st.button("← Back", key="cfg_back_btn"):
        st.session_state.page = "overview"
        st.session_state.pop("selected_cfg_bot", None)
        st.rerun()

    name = cfg_bot.get("name", "—")
    env  = cfg_bot.get("env", "—")

    st.markdown(
        f"<div style='padding:14px 0 8px;border-bottom:1px solid {C_BORDER};margin-bottom:20px'>"
        f"<span style='font-size:1.43rem;font-weight:700;color:{C_TEXT};font-family:{FONT}'>{name}</span>"
        f"<span style='color:{C_DIM};font-size:0.98rem;margin-left:12px'>{env}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div style='color:{C_DIM};font-size:0.98rem;padding:20px 0'>"
        f"No eval runs yet — force an eval to begin tracking this agent.</div>",
        unsafe_allow_html=True,
    )

    agent_up     = _agent_running()
    trigger_path = os.path.join(STORE_DIR, "agent", "force_eval.trigger")
    queued       = os.path.exists(trigger_path)

    if queued:
        st.button("⏳ Eval queued…", key="cfg_eval_queued",
                  width="content", type="secondary", disabled=True)
    else:
        if st.button("▶ Force Eval", key="cfg_force_eval_btn",
                     type="secondary",
                     disabled=not agent_up,
                     help=None if agent_up else "Start the agent first"):
            os.makedirs(os.path.join(STORE_DIR, "agent"), exist_ok=True)
            open(trigger_path, "w").write("user")
            st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────
@st.fragment(run_every=30)
def _main():
    import time as _t
    bots       = load_all_bots()
    _ev_now = _t.time()
    if _ev_now - st.session_state.get("_ev_ts", 0) >= 10:
        st.session_state["_ev_cache"] = load_events(STORE_DIR)
        st.session_state["_ev_ts"] = _ev_now
    raw_events = st.session_state.get("_ev_cache", [])
    page       = st.session_state.get("page", "overview")
    selected   = st.session_state.get("selected_bot")

    render_header(bots, raw_events, page=page)

    if page == "detail":
        bot = next((b for b in bots if b["botId"] == selected), None)
        if bot:
            page_bot_detail(bot)
        elif selected and os.path.exists(
            os.path.join(STORE_DIR, "agent", f"eval_active_{selected}.lock")
        ):
            # Tracking file mid-write during active eval — bust cache and retry
            st.session_state["_bots_ts"] = 0
            _t.sleep(1)
            st.rerun()
        else:
            st.session_state.page = "overview"
            st.rerun()
    elif page == "cfg_detail":
        cfg_bot = st.session_state.get("selected_cfg_bot")
        if cfg_bot:
            # If agent has now created tracking data, switch to real detail page
            real_bot = next((b for b in bots if b["botName"] == cfg_bot.get("name")
                             or b["botId"] in cfg_bot.get("name", "")), None)
            if real_bot:
                st.session_state.selected_bot = real_bot["botId"]
                st.session_state.page = "detail"
                st.session_state.pop("selected_cfg_bot", None)
                st.rerun()
            else:
                page_cfg_bot_detail(cfg_bot)
        else:
            st.session_state.page = "overview"
            st.rerun()
    else:
        page_overview(bots, raw_events)

_main()
