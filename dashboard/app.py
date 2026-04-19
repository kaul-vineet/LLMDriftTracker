"""
dashboard/app.py — LLM Drift Tracker · Streamlit dashboard
Ouroboros-inspired dark theme · regression-first · trigger-based run model
"""
import json
import os
import time
from datetime import datetime, timezone

import plotly.graph_objects as go
import streamlit as st

from agent.reasoning import (
    extract_metrics_for_report as _extract_metrics,
    classify_run,
    verdict_summary,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LLM Drift Tracker",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={},
)

# ── Ouroboros design tokens ───────────────────────────────────────────────────
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

# ── Global CSS + matrix canvas ────────────────────────────────────────────────
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;600;700&display=swap');

  html, body, [data-testid="stAppViewContainer"] {{
    background: {C_BG} !important;
    color: {C_TEXT};
    font-family: {FONT};
  }}
  [data-testid="stSidebar"] {{
    background: {C_CARD} !important;
    border-right: 1px solid {C_BORDER};
  }}
  [data-testid="stSidebar"] * {{ color: {C_TEXT} !important; }}
  .block-container {{ padding-top: 1rem; padding-bottom: 2rem; }}
  section[data-testid="stSidebar"] > div {{ padding-top: 1rem; }}

  /* Streamlit chrome hide */
  #MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; }}
  [data-testid="stHeader"] {{ display: none; }}
  [data-testid="stSidebarCollapsed"],
  [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}

  /* Plotly iframe */
  .stPlotlyChart {{ background: transparent !important; }}

  /* Scrollbar */
  ::-webkit-scrollbar {{ width: 5px; }}
  ::-webkit-scrollbar-track {{ background: {C_BG}; }}
  ::-webkit-scrollbar-thumb {{ background: {C_BORDER}; border-radius: 3px; }}

  /* Stat bar */
  .stat-bar {{
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 1px;
    background: {C_BORDER};
    border: 1px solid {C_BORDER};
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 24px;
  }}
  .stat-cell {{
    background: {C_CARD};
    padding: 16px 20px;
    text-align: center;
  }}
  .stat-value {{
    font-size: 2rem;
    font-weight: 700;
    font-family: {FONT};
    line-height: 1;
  }}
  .stat-label {{
    font-size: 0.65rem;
    color: {C_DIM};
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-top: 5px;
  }}

  /* Bot tiles */
  .bot-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 14px;
    margin-bottom: 24px;
  }}
  .bot-tile {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 10px;
    padding: 16px 18px;
    cursor: pointer;
    transition: border-color .2s, transform .15s, box-shadow .2s;
  }}
  .bot-tile:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 30px rgba(0,240,255,.08);
  }}
  .bot-tile.regressed  {{ border-color: {C_RED};  box-shadow: 0 0 12px rgba(255,68,68,.15); }}
  .bot-tile.improved   {{ border-color: {C_GREEN}; box-shadow: 0 0 12px rgba(40,200,64,.10); }}
  .bot-tile.stable     {{ border-color: {C_BORDER}; }}
  .bot-tile.baseline   {{ border-color: {C_GOLD}; }}
  .tile-name  {{ font-weight:700; font-size:0.9rem; color:{C_TEXT}; }}
  .tile-model {{ font-size:0.7rem; color:{C_DIM}; font-family:{FONT}; margin-top:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .tile-env   {{ font-size:0.65rem; color:{C_MAGENTA}; margin-top:2px; }}
  .tile-badge {{ font-size:0.65rem; font-weight:700; letter-spacing:1px; margin-top:8px; font-family:{FONT}; }}

  /* Verdict badge */
  .vbadge {{
    display: inline-block;
    border-radius: 3px;
    padding: 2px 8px;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 1px;
    font-family: {FONT};
  }}

  /* Section label */
  .sec-label {{
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: {C_DIM};
    border-bottom: 1px solid {C_BORDER};
    padding-bottom: 6px;
    margin: 20px 0 14px;
    font-family: {FONT};
  }}

  /* Terminal log */
  .terminal {{
    background: {C_BG};
    border: 1px solid {C_BORDER};
    border-radius: 8px;
    padding: 16px;
    font-family: {FONT};
    font-size: 0.75rem;
    line-height: 1.8;
    max-height: 240px;
    overflow-y: auto;
  }}
  .log-ts     {{ color: {C_CYAN}; }}
  .log-action {{ color: {C_MAGENTA}; }}
  .log-value  {{ color: {C_GOLD}; }}
  .log-ok     {{ color: {C_GREEN}; }}
  .log-err    {{ color: {C_RED}; }}

  /* Analysis panel */
  .analysis-panel {{
    background: {C_BG};
    border-left: 3px solid {C_MAGENTA};
    border-radius: 0 8px 8px 0;
    padding: 16px 20px;
    font-size: 0.875rem;
    line-height: 1.75;
    color: {C_TEXT};
    margin-bottom: 20px;
  }}
  .analysis-label {{
    font-size: 0.65rem;
    font-weight: 700;
    color: {C_MAGENTA};
    letter-spacing: 2px;
    margin-bottom: 8px;
    font-family: {FONT};
  }}

  /* Run timeline */
  .timeline {{ padding: 8px 0; }}
  .tl-item {{
    display: flex;
    gap: 16px;
    padding: 12px 0;
    border-bottom: 1px solid {C_BORDER};
    align-items: flex-start;
  }}
  .tl-dot {{
    width: 10px; height: 10px;
    border-radius: 50%;
    margin-top: 4px;
    flex-shrink: 0;
  }}
  .tl-content {{ flex: 1; }}
  .tl-guid  {{ font-family:{FONT}; font-size:0.7rem; color:{C_DIM}; }}
  .tl-model {{ font-size:0.78rem; color:{C_TEXT}; font-family:{FONT}; }}
  .tl-ts    {{ font-size:0.68rem; color:{C_DIM}; }}
  .tl-verdict {{ font-size:0.68rem; font-weight:700; letter-spacing:1px; font-family:{FONT}; }}
</style>

<canvas id="matrix-canvas" style="position:fixed;top:0;left:0;width:100%;height:100%;
  z-index:0;pointer-events:none;opacity:0.04"></canvas>
<script>
(function() {{
  var c = document.getElementById('matrix-canvas');
  if (!c) return;
  var ctx = c.getContext('2d');
  c.width = window.innerWidth; c.height = window.innerHeight;
  var cols = Math.floor(c.width / 14);
  var drops = Array(cols).fill(1);
  var chars = '01アイウエオカキクケコ∆∇⊕⊗';
  function draw() {{
    ctx.fillStyle = 'rgba(10,10,15,0.05)';
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.fillStyle = '#00f0ff';
    ctx.font = '12px monospace';
    drops.forEach(function(y, i) {{
      var ch = chars[Math.floor(Math.random() * chars.length)];
      ctx.fillText(ch, i * 14, y * 14);
      if (y * 14 > c.height && Math.random() > 0.975) drops[i] = 0;
      drops[i]++;
    }});
  }}
  setInterval(draw, 80);
}})();
</script>
""", unsafe_allow_html=True)

# ── Data layer ────────────────────────────────────────────────────────────────
STORE_DIR = os.environ.get("STORE_DIR", "data")


def _load_json(path: str) -> dict:
    try:
        return json.loads(open(path).read())
    except Exception:
        return {}


def _fmt_ts(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %H:%M")
    except Exception:
        return iso or "—"


def _short_guid(g: str) -> str:
    return g[:8] if len(g) >= 8 else g


def load_all_bots() -> list[dict]:
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


def _metrics_for(trigger: dict) -> dict:
    return _extract_metrics(trigger.get("resultsByType", {}))


def _classifications_for(trigger_a: dict, trigger_b: dict) -> list[dict]:
    ma = _metrics_for(trigger_a)
    mb = _metrics_for(trigger_b)
    return classify_run(ma, mb)


def _bot_verdict(bot: dict) -> str:
    triggers = bot["triggers"]
    if len(triggers) < 2:
        return "BASELINE"
    cls = _classifications_for(triggers[-2], triggers[-1])
    if any(c["verdict"] == "REGRESSED" for c in cls):
        return "REGRESSED"
    if any(c["verdict"] == "IMPROVED" for c in cls):
        return "IMPROVED"
    return "STABLE"


def _cases_for_type(trigger: dict, metric_type: str) -> list[dict]:
    wrapper = trigger.get("resultsByType", {}).get(metric_type, {})
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


def _all_metric_types(trigger: dict) -> list[str]:
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


def chart_radar(classifications: list[dict], label_a: str, label_b: str) -> go.Figure:
    if not classifications:
        return go.Figure()
    prev_vals = [c["prev"] or 0 for c in classifications]
    curr_vals = [c["curr"] or 0 for c in classifications]
    labels    = [c["key"].split(".")[-1][:16] for c in classifications]

    def _norm(vals):
        return [round(v * 100, 1) if v <= 1 else round(v, 1) for v in vals]

    fig = go.Figure()
    for vals, label, color, fill in [
        (_norm(prev_vals), label_a, C_GOLD,    "rgba(255,215,0,0.08)"),
        (_norm(curr_vals), label_b, C_CYAN,    "rgba(0,240,255,0.08)"),
    ]:
        fig.add_trace(go.Scatterpolar(
            r=vals + [vals[0]], theta=labels + [labels[0]],
            fill="toself", name=label,
            line=dict(color=color, width=2),
            fillcolor=fill,
        ))
    fig.update_layout(
        **CHART_LAYOUT,
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(visible=True, range=[0, 100],
                            gridcolor=C_BORDER, linecolor=C_BORDER,
                            tickfont=dict(size=8, color=C_DIM)),
            angularaxis=dict(gridcolor=C_BORDER, linecolor=C_BORDER,
                             tickfont=dict(color=C_TEXT, size=9)),
        ),
        height=320,
    )
    return fig


def chart_delta_bar(cases_prev: list[dict], cases_curr: list[dict], title: str) -> go.Figure:
    """Sorted delta bar — worst regression first."""
    prev_by_id = {c["caseId"]: c for c in cases_prev}

    # Compute deltas
    items = []
    for i, cc in enumerate(cases_curr):
        pc    = prev_by_id.get(cc["caseId"], {})
        psc   = pc.get("score")
        csc   = cc.get("score")
        delta = round(csc - psc, 1) if isinstance(psc, float) and isinstance(csc, float) else 0
        items.append({"label": f"#{i+1}", "delta": delta, "status": cc.get("status", "")})

    items.sort(key=lambda x: x["delta"])  # worst first

    labels = [x["label"] for x in items]
    deltas = [x["delta"] for x in items]
    colors = [C_RED if d < -2 else (C_GREEN if d > 2 else C_DIM) for d in deltas]

    fig = go.Figure(go.Bar(
        x=labels, y=deltas,
        marker_color=colors,
        hovertemplate="%{x}: Δ%{y}<extra></extra>",
    ))
    fig.update_layout(**CHART_LAYOUT, title=dict(text=title, font=dict(size=11, color=C_DIM)),
                      height=240, showlegend=False)
    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(**_AXIS, zeroline=True, zerolinecolor=C_BORDER, zerolinewidth=1)
    return fig


def chart_status_grid(cases_prev: list[dict], cases_curr: list[dict]) -> go.Figure:
    """2×2 status transition heatmap."""
    prev_by_id = {c["caseId"]: c for c in cases_prev}
    pp = ff = pf = fp = 0
    for cc in cases_curr:
        pc = prev_by_id.get(cc["caseId"])
        if not pc:
            continue
        pv = pc.get("status") == "Pass"
        cv = cc.get("status") == "Pass"
        if pv and cv:   pp += 1
        if not pv and not cv: ff += 1
        if pv and not cv: pf += 1
        if not pv and cv: fp += 1

    z    = [[pp, pf], [fp, ff]]
    text = [[f"Stayed Pass\n{pp}", f"Pass→Fail\n{pf}"],
            [f"Fail→Pass\n{fp}", f"Stayed Fail\n{ff}"]]

    colorscale = [
        [0.0, C_BG], [0.33, C_CARD], [0.66, C_GREEN], [1.0, C_RED]
    ]
    # Override: pf cell always red emphasis, fp always green — use annotation colors instead
    cell_colors = [
        [C_CARD if pp > 0 else C_BG, f"rgba(255,68,68,{min(1, pf/max(1,pp+pf+fp+ff)+0.1):.2f})"],
        [f"rgba(40,200,64,{min(1, fp/max(1,pp+pf+fp+ff)+0.1):.2f})", C_BG if ff == 0 else C_CARD],
    ]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=["→ Pass", "→ Fail"],
        y=["Prev Pass", "Prev Fail"],
        text=text,
        texttemplate="%{text}",
        colorscale=[[0, C_BG], [0.5, C_CARD], [1, C_GREEN]],
        showscale=False,
        hovertemplate="%{text}<extra></extra>",
    ))
    fig.update_layout(**CHART_LAYOUT, height=200)
    fig.update_xaxes(**_AXIS)
    fig.update_yaxes(**_AXIS)
    return fig


def chart_metric_trend(bot: dict) -> go.Figure:
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


# ── Auth status (sidebar) ─────────────────────────────────────────────────────
def render_auth_status():
    from agent.auth import get_auth_state
    try:
        cfg   = _load_json("config.json")
        state = get_auth_state(cfg) if cfg else {"status": "UNKNOWN"}
    except Exception:
        state = {"status": "UNKNOWN"}

    status  = state.get("status", "UNKNOWN")
    account = state.get("account", "")

    if status == "AUTHENTICATED":
        st.markdown(
            f"<div style='background:rgba(40,200,64,.08);border:1px solid rgba(40,200,64,.3);"
            f"border-radius:6px;padding:8px 12px;margin-bottom:12px'>"
            f"<div style='color:{C_GREEN};font-size:0.65rem;font-weight:700;letter-spacing:1px;"
            f"font-family:{FONT}'>● TOKEN VALID</div>"
            f"<div style='color:{C_DIM};font-size:0.65rem;margin-top:2px'>{account}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    elif status == "PENDING_DEVICE_FLOW":
        code = state.get("user_code", "")
        st.markdown(
            f"<div style='background:rgba(255,68,68,.08);border:1px solid {C_RED};"
            f"border-radius:6px;padding:10px 12px;margin-bottom:12px'>"
            f"<div style='color:{C_RED};font-size:0.65rem;font-weight:700;letter-spacing:1px;"
            f"font-family:{FONT}'>⚠ ACTION REQUIRED</div>"
            f"<div style='color:{C_DIM};font-size:0.68rem;margin-top:4px'>Sign in at:</div>"
            f"<div style='color:{C_CYAN};font-size:0.68rem'>microsoft.com/devicelogin</div>"
            f"<div style='color:{C_CYAN};font-size:1.4rem;font-weight:700;letter-spacing:6px;"
            f"font-family:{FONT};margin-top:6px;text-align:center'>{code}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='background:{C_CARD};border:1px solid {C_BORDER};"
            f"border-radius:6px;padding:8px 12px;margin-bottom:12px'>"
            f"<div style='color:{C_DIM};font-size:0.65rem;font-weight:700;letter-spacing:1px;"
            f"font-family:{FONT}'>● AUTH UNKNOWN</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


def render_trigger_button():
    trigger_path = os.path.join(STORE_DIR, "force_eval.trigger")
    pending      = os.path.exists(trigger_path)

    if pending:
        st.markdown(
            f"<div style='color:{C_GOLD};font-size:0.7rem;font-family:{FONT};"
            f"text-align:center;padding:6px'>⏳ Eval queued — agent will pick up shortly</div>",
            unsafe_allow_html=True,
        )
    else:
        if st.button("▶ Run Eval Now", use_container_width=True, type="primary"):
            os.makedirs(STORE_DIR, exist_ok=True)
            open(trigger_path, "w").write(datetime.now(timezone.utc).isoformat())
            st.rerun()


# ── Verdict HTML helpers ──────────────────────────────────────────────────────
_V_COLORS = {"REGRESSED": C_RED, "IMPROVED": C_GREEN, "STABLE": C_DIM, "NEW": C_GOLD, "BASELINE": C_GOLD}


def _vbadge(verdict: str) -> str:
    c = _V_COLORS.get(verdict, C_DIM)
    return (f"<span style='color:{c};font-weight:700;font-family:{FONT};"
            f"font-size:0.7rem;letter-spacing:1px'>{verdict}</span>")


# ── Pages ─────────────────────────────────────────────────────────────────────
def page_overview(bots: list[dict]):
    # Stat bar
    total_cases = sum(
        len(_cases_for_type(b["lastTrigger"], mt))
        for b in bots
        for mt in _all_metric_types(b["lastTrigger"])
    )
    verdicts = [_bot_verdict(b) for b in bots]
    n_reg    = verdicts.count("REGRESSED")
    n_imp    = verdicts.count("IMPROVED")
    n_sta    = verdicts.count("STABLE")
    n_base   = verdicts.count("BASELINE")

    reg_color  = C_RED   if n_reg  else C_DIM
    imp_color  = C_GREEN if n_imp  else C_DIM
    sta_color  = C_DIM
    base_color = C_GOLD  if n_base else C_DIM

    st.markdown(f"""
    <div class='stat-bar'>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{C_CYAN}'>{total_cases}</div>
        <div class='stat-label'>Total Cases</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{reg_color}'>{n_reg}</div>
        <div class='stat-label'>Regressed</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{imp_color}'>{n_imp}</div>
        <div class='stat-label'>Improved</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{sta_color}'>{n_sta}</div>
        <div class='stat-label'>Stable</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-value' style='color:{base_color}'>{n_base}</div>
        <div class='stat-label'>Baseline</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not bots:
        st.markdown(
            f"<div style='text-align:center;padding:60px;color:{C_DIM}'>"
            f"<div style='font-size:2rem;margin-bottom:12px'>⚡</div>"
            f"<div style='color:{C_TEXT};font-size:0.9rem'>No bots tracked yet</div>"
            f"<div style='font-size:0.75rem;margin-top:6px'>Run the agent or click ▶ Run Eval Now</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(f"<div class='sec-label'>MONITORED AGENTS</div>", unsafe_allow_html=True)

    # Bot tiles — 4 per row
    cols = st.columns(4)
    for i, bot in enumerate(bots):
        verdict    = _bot_verdict(bot)
        tile_class = verdict.lower()
        v_color    = _V_COLORS.get(verdict, C_DIM)
        with cols[i % 4]:
            if st.button(
                f"{'🔴' if verdict=='REGRESSED' else '🟢' if verdict=='IMPROVED' else '🟡' if verdict=='BASELINE' else '⚪'} "
                f"{bot['botName']}\n"
                f"{bot['modelVersion'][:26]}\n"
                f"{_fmt_ts(bot['updatedAt'])} · {bot['triggerCount']} run{'s' if bot['triggerCount']!=1 else ''}",
                key=f"tile_{bot['botId']}",
                use_container_width=True,
            ):
                st.session_state.selected_bot = bot["botId"]
                st.session_state.page = "detail"
                st.rerun()


def page_bot_detail(bot: dict):
    import pandas as pd

    triggers = bot["triggers"]
    name     = bot["botName"]
    env      = bot["envName"]

    if not triggers:
        st.info("No eval runs yet.")
        return

    # Run selector
    def _run_label(t: dict) -> str:
        ts  = _fmt_ts(t.get("triggeredAt", ""))
        ver = t.get("modelVersion", "?")[:24]
        gid = _short_guid(t.get("triggerGuid", ""))
        return f"{ts}  ·  {gid}  ·  {ver}"

    run_labels = [_run_label(t) for t in triggers]

    c1, c2 = st.columns(2)
    with c1:
        idx_a = st.selectbox("Baseline", range(len(triggers)),
                             format_func=lambda i: run_labels[i],
                             index=max(0, len(triggers) - 2), key="sel_a")
    with c2:
        idx_b = st.selectbox("Current",  range(len(triggers)),
                             format_func=lambda i: run_labels[i],
                             index=len(triggers) - 1, key="sel_b")

    trig_a = triggers[idx_a]
    trig_b = triggers[idx_b]
    lbl_a  = run_labels[idx_a]
    lbl_b  = run_labels[idx_b]

    cls          = _classifications_for(trig_a, trig_b)
    v_summary    = verdict_summary(cls)
    reg_count    = sum(1 for c in cls if c["verdict"] == "REGRESSED")
    v_color      = C_RED if reg_count else (C_GREEN if any(c["verdict"]=="IMPROVED" for c in cls) else C_DIM)

    # Header
    st.markdown(f"""
    <div style='padding:16px 0 8px;border-bottom:1px solid {C_BORDER};margin-bottom:16px;
                display:flex;justify-content:space-between;align-items:center'>
      <div>
        <span style='font-size:1.1rem;font-weight:700;color:{C_TEXT};font-family:{FONT}'>{name}</span>
        <span style='color:{C_DIM};font-size:0.75rem;margin-left:12px'>{env}</span>
      </div>
      <span style='color:{v_color};font-weight:700;font-family:{FONT};
                   letter-spacing:2px;font-size:0.8rem'>{v_summary}</span>
    </div>
    """, unsafe_allow_html=True)

    # LLM Analysis at TOP
    analysis = (trig_b.get("analysis") or trig_a.get("analysis") or "").strip()
    if analysis:
        st.markdown(f"""
        <div class='analysis-panel'>
          <div class='analysis-label'>⚡ LLM DRIFT ANALYSIS</div>
          {analysis.replace(chr(10), '<br>')}
        </div>
        """, unsafe_allow_html=True)

    # Radar + metric summary table
    col_r, col_t = st.columns([1, 2])
    with col_r:
        st.markdown(f"<div class='sec-label'>RADAR</div>", unsafe_allow_html=True)
        fig_r = chart_radar(cls, lbl_a, lbl_b)
        if fig_r.data:
            st.plotly_chart(fig_r, use_container_width=True, config={"displayModeBar": False})

    with col_t:
        st.markdown(f"<div class='sec-label'>METRIC SUMMARY</div>", unsafe_allow_html=True)
        if cls:
            rows = []
            for c in cls:
                rows.append({
                    "Metric":   c["key"],
                    "Verdict":  c["verdict"],
                    "Prev":     round(c["prev"], 4) if c["prev"] is not None else None,
                    "Curr":     round(c["curr"], 4) if c["curr"] is not None else None,
                    "Δ":        f"{c['delta']:+.4f}" if c["delta"] is not None else "—",
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True,
                         height=min(380, 48 + len(rows) * 38))
        else:
            st.caption("No metrics — first run establishes baseline.")

    # Per-metric-type sections (REGRESSED expanded first)
    st.markdown(f"<div class='sec-label'>PER METRIC TYPE</div>", unsafe_allow_html=True)

    # Determine verdict per metric type
    _prio = {"REGRESSED": 0, "IMPROVED": 1, "STABLE": 2, "NEW": 3}
    verdict_by_type: dict[str, str] = {}
    for c in cls:
        for mt in _all_metric_types(trig_b):
            if c["key"].startswith(mt + "."):
                existing = verdict_by_type.get(mt, "STABLE")
                if _prio.get(c["verdict"], 9) < _prio.get(existing, 9):
                    verdict_by_type[mt] = c["verdict"]
    for mt in _all_metric_types(trig_b):
        if mt not in verdict_by_type:
            verdict_by_type[mt] = "NEW" if not _metrics_for(trig_a) else "STABLE"

    sorted_types = sorted(
        _all_metric_types(trig_b),
        key=lambda t: _prio.get(verdict_by_type.get(t, "STABLE"), 9),
    )

    for metric_type in sorted_types:
        verdict    = verdict_by_type.get(metric_type, "STABLE")
        v_c        = _V_COLORS.get(verdict, C_DIM)
        cases_prev = _cases_for_type(trig_a, metric_type)
        cases_curr = _cases_for_type(trig_b, metric_type)
        expanded   = verdict == "REGRESSED"

        with st.expander(f"{metric_type}  —  {verdict}", expanded=expanded):
            # Delta bar
            if cases_prev and cases_curr:
                fig_d = chart_delta_bar(cases_prev, cases_curr, "Score Δ per case (worst first)")
                if fig_d.data:
                    st.plotly_chart(fig_d, use_container_width=True,
                                    config={"displayModeBar": False})

            # Status transition grid
            if cases_prev and cases_curr:
                st.caption("Status transitions")
                fig_g = chart_status_grid(cases_prev, cases_curr)
                if fig_g.data:
                    st.plotly_chart(fig_g, use_container_width=True,
                                    config={"displayModeBar": False})

            # Case table
            if cases_curr:
                prev_by_id = {c["caseId"]: c for c in cases_prev}
                rows = []
                for i, cc in enumerate(cases_curr):
                    pc    = prev_by_id.get(cc["caseId"], {})
                    psc   = pc.get("score")
                    csc   = cc.get("score")
                    delta = round(csc - psc, 1) if isinstance(psc, float) and isinstance(csc, float) else None
                    rows.append({
                        "#":           i + 1,
                        "Prev status": pc.get("status", "—"),
                        "Prev score":  int(psc) if isinstance(psc, float) else None,
                        "Curr status": cc.get("status", "—"),
                        "Curr score":  int(csc) if isinstance(csc, float) else None,
                        "Δ":           delta,
                        "AI reason":   cc.get("reason", ""),
                    })
                rows.sort(key=lambda r: (r["Δ"] or 0))
                df = pd.DataFrame(rows).set_index("#")
                st.dataframe(df, use_container_width=True,
                             height=min(420, 48 + len(rows) * 38))

                # Failing cases
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

    # Trend chart
    if len(triggers) >= 2:
        st.markdown(f"<div class='sec-label'>METRIC TRENDS</div>", unsafe_allow_html=True)
        fig_t = chart_metric_trend(bot)
        if fig_t.data:
            st.plotly_chart(fig_t, use_container_width=True, config={"displayModeBar": False})

    # Run timeline
    st.markdown(f"<div class='sec-label'>RUN HISTORY</div>", unsafe_allow_html=True)
    timeline_items = ""
    for t in reversed(triggers):
        mt_list  = ", ".join(t.get("metricTypes", ["—"]))
        dot_col  = C_CYAN if not t.get("_legacy") else C_DIM
        timeline_items += (
            f"<div class='tl-item'>"
            f"<div class='tl-dot' style='background:{dot_col}'></div>"
            f"<div class='tl-content'>"
            f"<div class='tl-model'>{t.get('modelVersion', '—')[:36]}</div>"
            f"<div class='tl-guid'>{_short_guid(t.get('triggerGuid',''))}  ·  {mt_list}</div>"
            f"<div class='tl-ts'>{_fmt_ts(t.get('triggeredAt',''))}</div>"
            f"</div></div>"
        )
    st.markdown(f"<div class='timeline'>{timeline_items}</div>", unsafe_allow_html=True)


def page_history(bots: list[dict]):
    st.markdown(f"<div class='sec-label'>ALL RUNS — TIMELINE</div>", unsafe_allow_html=True)
    all_triggers = []
    for bot in bots:
        for t in bot["triggers"]:
            all_triggers.append({**t, "_botName": bot["botName"], "_botId": bot["botId"]})
    all_triggers.sort(key=lambda t: t.get("triggeredAt", ""), reverse=True)

    for t in all_triggers:
        mt_list = ", ".join(t.get("metricTypes", ["—"]))
        st.markdown(
            f"<div style='padding:10px 14px;border:1px solid {C_BORDER};border-radius:6px;"
            f"background:{C_CARD};margin-bottom:8px;display:flex;justify-content:space-between'>"
            f"<div>"
            f"<div style='font-weight:700;color:{C_TEXT};font-family:{FONT}'>{t['_botName']}</div>"
            f"<div style='font-size:0.7rem;color:{C_DIM};font-family:{FONT}'>{mt_list}</div>"
            f"<div style='font-size:0.68rem;color:{C_DIM};margin-top:2px'>{t.get('modelVersion','—')[:30]}</div>"
            f"</div>"
            f"<div style='text-align:right'>"
            f"<div style='font-size:0.68rem;color:{C_DIM}'>{_fmt_ts(t.get('triggeredAt',''))}</div>"
            f"<div style='font-size:0.65rem;color:{C_CYAN};font-family:{FONT};margin-top:2px'>"
            f"{_short_guid(t.get('triggerGuid',''))}</div>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

    if not all_triggers:
        st.markdown(f"<div style='color:{C_DIM};padding:40px;text-align:center'>No runs yet.</div>",
                    unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar(bots: list[dict]) -> str | None:
    with st.sidebar:
        st.markdown(f"""
        <div style='padding:4px 0 14px'>
          <div style='font-size:16px;font-weight:700;letter-spacing:3px;
                      color:{C_CYAN};font-family:{FONT}'>⚡ DRIFT TRACKER</div>
          <div style='font-size:0.6rem;color:{C_DIM};margin-top:2px;letter-spacing:1px'>
            copilot-eval-agent · v2.0</div>
        </div>
        """, unsafe_allow_html=True)

        render_auth_status()
        render_trigger_button()

        st.markdown(f"<div style='border-top:1px solid {C_BORDER};margin:10px 0'></div>",
                    unsafe_allow_html=True)

        # Nav
        if "page" not in st.session_state:
            st.session_state.page = "overview"

        for key, label in [("overview", "🏠  Overview"), ("history", "📋  History")]:
            active = st.session_state.page == key
            if st.button(label, key=f"nav_{key}", use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.page = key
                st.rerun()

        st.markdown(
            f"<div style='font-size:0.6rem;color:{C_DIM};letter-spacing:1px;"
            f"margin:14px 0 8px;font-family:{FONT}'>BOTS</div>",
            unsafe_allow_html=True,
        )

        if not bots:
            st.markdown(
                f"<div style='color:{C_DIM};font-size:0.75rem;padding:8px 0'>"
                "No bots tracked yet</div>",
                unsafe_allow_html=True,
            )
            return None

        selected = st.session_state.get("selected_bot")
        for bot in bots:
            verdict = _bot_verdict(bot)
            dot     = {"REGRESSED": "🔴", "IMPROVED": "🟢", "BASELINE": "🟡"}.get(verdict, "⚪")
            active  = selected == bot["botId"]
            if st.button(
                f"{dot} {bot['botName'][:22]}\n{bot['modelVersion'][:22]}\n"
                f"{bot['triggerCount']} run{'s' if bot['triggerCount']!=1 else ''}",
                key=f"btn_{bot['botId']}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                st.session_state.selected_bot = bot["botId"]
                st.session_state.page = "detail"
                st.rerun()

        return selected


# ── App header ────────────────────────────────────────────────────────────────
def render_header(bots: list[dict]):
    last_scan = max((b["updatedAt"] for b in bots), default="")
    ts_str    = _fmt_ts(last_scan) if last_scan else "no data yet"
    n_reg     = sum(1 for b in bots if _bot_verdict(b) == "REGRESSED")
    status    = f"<span style='color:{C_RED};font-weight:700'>{n_reg} REGRESSED</span>" if n_reg else \
                f"<span style='color:{C_GREEN}'>ALL STABLE</span>"
    st.markdown(f"""
    <div style='background:{C_CARD};border:1px solid {C_BORDER};border-radius:10px;
                padding:16px 24px;margin-bottom:20px;
                display:flex;justify-content:space-between;align-items:center'>
      <div>
        <div style='font-size:1.3rem;font-weight:700;letter-spacing:3px;color:{C_CYAN};
                    font-family:{FONT};text-shadow:0 0 20px rgba(0,240,255,.3)'>
          ⚡ LLM DRIFT TRACKER</div>
        <div style='font-size:0.65rem;color:{C_DIM};margin-top:3px;letter-spacing:1px'>
          copilot-eval-agent · {len(bots)} bots · {status}</div>
      </div>
      <div style='text-align:right'>
        <div style='font-size:0.65rem;color:{C_DIM}'>last activity</div>
        <div style='font-size:0.75rem;color:{C_TEXT};font-family:{FONT}'>{ts_str}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    bots     = load_all_bots()
    selected = render_sidebar(bots)
    render_header(bots)

    page = st.session_state.get("page", "overview")

    if page == "overview":
        page_overview(bots)
    elif page == "history":
        page_history(bots)
    else:
        bot = next((b for b in bots if b["botId"] == selected), None)
        if bot:
            page_bot_detail(bot)
        else:
            st.markdown(
                f"<div style='color:{C_DIM};padding:40px;text-align:center'>"
                "Select a bot from the sidebar.</div>",
                unsafe_allow_html=True,
            )


if __name__ == "__main__":
    main()
