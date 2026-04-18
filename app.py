"""
app.py — LLM Drift Tracker · Streamlit dashboard (read-only)
"""
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone

import plotly.graph_objects as go
import streamlit as st
from reasoning import extract_metrics_for_report as _extract_metrics_from_run

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LLM Drift Tracker",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design tokens ─────────────────────────────────────────────────────────────
C_BG       = "#0d1117"
C_CARD     = "#161b22"
C_BORDER   = "#30363d"
C_BLUE     = "#58a6ff"
C_GREEN    = "#3fb950"
C_RED      = "#f85149"
C_AMBER    = "#d29922"
C_PURPLE   = "#bc8cff"
C_DIM      = "#8b949e"
C_TEXT     = "#c9d1d9"

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  /* ── Base ── */
  html, body, [data-testid="stAppViewContainer"] {{
      background: {C_BG};
      color: {C_TEXT};
  }}
  [data-testid="stSidebar"] {{
      background: {C_CARD};
      border-right: 1px solid {C_BORDER};
  }}
  [data-testid="stSidebar"] * {{ color: {C_TEXT} !important; }}
  .block-container {{ padding-top: 1.5rem; padding-bottom: 2rem; }}
  section[data-testid="stSidebar"] > div {{ padding-top: 1rem; }}

  /* ── Header ── */
  .drift-header {{
      background: linear-gradient(135deg, {C_CARD} 0%, #0d1117 100%);
      border: 1px solid {C_BORDER};
      border-radius: 12px;
      padding: 20px 28px;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
  }}
  .drift-title {{
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 2px;
      color: {C_BLUE};
      text-shadow: 0 0 20px rgba(88,166,255,0.4);
      font-family: monospace;
  }}
  .drift-sub {{
      font-size: 11px;
      color: {C_DIM};
      letter-spacing: 1px;
      margin-top: 2px;
  }}
  .live-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(63,185,80,0.12);
      border: 1px solid rgba(63,185,80,0.3);
      border-radius: 20px;
      padding: 4px 12px;
      font-size: 11px;
      font-weight: 600;
      color: {C_GREEN};
      letter-spacing: 1px;
  }}
  .live-dot {{
      width: 8px; height: 8px;
      background: {C_GREEN};
      border-radius: 50%;
      animation: pulse 2s infinite;
  }}
  @keyframes pulse {{
      0%   {{ box-shadow: 0 0 0 0 rgba(63,185,80,0.7); }}
      70%  {{ box-shadow: 0 0 0 8px rgba(63,185,80,0); }}
      100% {{ box-shadow: 0 0 0 0 rgba(63,185,80,0); }}
  }}

  /* ── KPI cards ── */
  .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 24px;
  }}
  .kpi-card {{
      background: {C_CARD};
      border: 1px solid {C_BORDER};
      border-radius: 10px;
      padding: 18px 20px;
      transition: border-color .2s, box-shadow .2s;
  }}
  .kpi-card:hover {{
      border-color: {C_BLUE};
      box-shadow: 0 0 16px rgba(88,166,255,0.12);
  }}
  .kpi-value {{
      font-size: 32px;
      font-weight: 700;
      font-family: monospace;
      line-height: 1;
  }}
  .kpi-label {{
      font-size: 11px;
      color: {C_DIM};
      letter-spacing: 1px;
      text-transform: uppercase;
      margin-top: 6px;
  }}

  /* ── Bot cards ── */
  .bot-card {{
      background: {C_CARD};
      border: 1px solid {C_BORDER};
      border-radius: 10px;
      padding: 16px 18px;
      margin-bottom: 12px;
      cursor: pointer;
      transition: border-color .2s, box-shadow .2s, transform .15s;
  }}
  .bot-card:hover {{
      border-color: {C_BLUE};
      box-shadow: 0 0 20px rgba(88,166,255,0.15);
      transform: translateY(-1px);
  }}
  .bot-card.active {{
      border-color: {C_BLUE};
      box-shadow: 0 0 20px rgba(88,166,255,0.2);
  }}
  .bot-name {{ font-weight: 700; font-size: 14px; color: {C_TEXT}; }}
  .bot-model {{ font-size: 11px; color: {C_DIM}; font-family: monospace; margin-top: 3px; }}
  .bot-env  {{ font-size: 10px; color: {C_PURPLE}; margin-top: 2px; }}

  /* ── Status badges ── */
  .badge {{
      display: inline-block;
      border-radius: 20px;
      padding: 2px 10px;
      font-size: 10px;
      font-weight: 600;
      letter-spacing: .5px;
  }}
  .badge-green  {{ background: rgba(63,185,80,.15);  color: {C_GREEN};  border: 1px solid rgba(63,185,80,.3);  }}
  .badge-red    {{ background: rgba(248,81,73,.15);  color: {C_RED};    border: 1px solid rgba(248,81,73,.3);  }}
  .badge-amber  {{ background: rgba(210,153,34,.15); color: {C_AMBER};  border: 1px solid rgba(210,153,34,.3); }}
  .badge-blue   {{ background: rgba(88,166,255,.15); color: {C_BLUE};   border: 1px solid rgba(88,166,255,.3); }}

  /* ── Section titles ── */
  .section-title {{
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 2px;
      text-transform: uppercase;
      color: {C_DIM};
      border-bottom: 1px solid {C_BORDER};
      padding-bottom: 8px;
      margin: 24px 0 16px;
  }}

  /* ── Analysis panel ── */
  .analysis-panel {{
      background: {C_CARD};
      border-left: 3px solid {C_PURPLE};
      border-radius: 0 10px 10px 0;
      padding: 18px 22px;
      margin-top: 8px;
      font-size: 14px;
      line-height: 1.7;
      color: {C_TEXT};
  }}
  .analysis-label {{
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 2px;
      color: {C_PURPLE};
      margin-bottom: 10px;
  }}

  /* ── Metric delta chips ── */
  .delta-up   {{ color: {C_GREEN}; font-weight: 700; }}
  .delta-down {{ color: {C_RED};   font-weight: 700; }}
  .delta-flat {{ color: {C_DIM};   font-weight: 400; }}

  /* ── Model version pill ── */
  .model-pill {{
      display: inline-block;
      background: rgba(188,140,255,.12);
      border: 1px solid rgba(188,140,255,.3);
      border-radius: 6px;
      padding: 3px 10px;
      font-size: 11px;
      font-family: monospace;
      color: {C_PURPLE};
  }}

  /* ── Empty state ── */
  .empty-state {{
      text-align: center;
      padding: 60px 20px;
      color: {C_DIM};
  }}
  .empty-icon {{ font-size: 48px; margin-bottom: 16px; }}
  .empty-title {{ font-size: 16px; font-weight: 600; color: {C_TEXT}; margin-bottom: 8px; }}

  /* ── Scrollbar ── */
  ::-webkit-scrollbar {{ width: 6px; }}
  ::-webkit-scrollbar-track {{ background: {C_BG}; }}
  ::-webkit-scrollbar-thumb {{ background: {C_BORDER}; border-radius: 3px; }}

  /* ── Hide Streamlit chrome ── */
  #MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; }}
  [data-testid="stHeader"] {{ display: none; }}
</style>
""", unsafe_allow_html=True)


# ── Data layer ────────────────────────────────────────────────────────────────
STORE_DIR = os.environ.get("STORE_DIR", "data")


def _load_json(path: str) -> dict:
    try:
        return json.loads(open(path).read())
    except Exception:
        return {}


def load_all_bots() -> list[dict]:
    bots = []
    if not os.path.exists(STORE_DIR):
        return bots
    for bot_id in os.listdir(STORE_DIR):
        bot_dir = os.path.join(STORE_DIR, bot_id)
        if not os.path.isdir(bot_dir):
            continue
        tracking = _load_json(os.path.join(bot_dir, "tracking.json"))
        if not tracking:
            continue
        runs = load_bot_runs(bot_id)
        last_run = runs[-1] if runs else {}
        bots.append({
            "botId":        bot_id,
            "botName":      tracking.get("botName", bot_id),
            "envName":      tracking.get("envName", "—"),
            "modelVersion": tracking.get("modelVersion", "unknown"),
            "updatedAt":    tracking.get("updatedAt", ""),
            "runCount":     len(runs),
            "lastRun":      last_run,
            "runs":         runs,
        })
    return sorted(bots, key=lambda b: b["updatedAt"], reverse=True)


def load_bot_runs(bot_id: str) -> list[dict]:
    runs_dir = os.path.join(STORE_DIR, bot_id, "runs")
    if not os.path.exists(runs_dir):
        return []
    files = sorted(f for f in os.listdir(runs_dir) if f.endswith(".json"))
    return [_load_json(os.path.join(runs_dir, f)) for f in files]


def extract_metrics(run: dict) -> dict:
    results = run.get("results", run)
    return _extract_metrics_from_run(results)


def extract_ai_reasons(run: dict) -> list[str]:
    reasons = []
    results = run.get("results", run)
    for case in results.get("testCasesResults", []):
        for m in case.get("metricsResults", []):
            r = m.get("aiResultReason", "")
            if r:
                reasons.append(r)
    return reasons


def composite_score(metrics: dict) -> float:
    if not metrics:
        return 0.0
    return round(sum(metrics.values()) / len(metrics), 4)


def _fmt_ts(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %H:%M UTC")
    except Exception:
        return iso or "—"


# ── Chart builders ────────────────────────────────────────────────────────────
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=C_TEXT, family="monospace", size=11),
    margin=dict(l=10, r=10, t=30, b=10),
    xaxis=dict(gridcolor=C_BORDER, linecolor=C_BORDER, zerolinecolor=C_BORDER),
    yaxis=dict(gridcolor=C_BORDER, linecolor=C_BORDER, zerolinecolor=C_BORDER),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=C_BORDER, borderwidth=1),
)


def chart_radar(prev_metrics: dict, curr_metrics: dict,
                prev_label: str, curr_label: str) -> go.Figure:
    keys = sorted(set(list(prev_metrics.keys()) + list(curr_metrics.keys())))
    if not keys:
        return go.Figure()
    short = [k.split(".")[-1][:18] for k in keys]
    fig = go.Figure()
    for vals, label, color in [
        ([prev_metrics.get(k, 0) for k in keys], prev_label, C_AMBER),
        ([curr_metrics.get(k, 0) for k in keys], curr_label, C_BLUE),
    ]:
        fig.add_trace(go.Scatterpolar(
            r=vals + [vals[0]], theta=short + [short[0]],
            fill="toself", name=label,
            line=dict(color=color, width=2),
            fillcolor=color.replace("#", "rgba(") + ",0.1)" if "#" in color else color,
        ))
    fig.update_layout(
        **CHART_LAYOUT,
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(visible=True, range=[0, 1],
                            gridcolor=C_BORDER, linecolor=C_BORDER,
                            tickfont=dict(size=9, color=C_DIM)),
            angularaxis=dict(gridcolor=C_BORDER, linecolor=C_BORDER),
        ),
        showlegend=True,
        height=360,
    )
    return fig


def chart_trend(runs: list[dict]) -> go.Figure:
    if len(runs) < 2:
        return go.Figure()
    all_keys: set = set()
    data: list[dict] = []
    for run in runs:
        m = extract_metrics(run)
        all_keys.update(m.keys())
        data.append({"label": run.get("modelVersion", "?")[:24], "metrics": m,
                     "ts": run.get("storedAt", "")})
    x = [d["label"] for d in data]
    fig = go.Figure()
    colors = [C_BLUE, C_GREEN, C_PURPLE, C_AMBER, C_RED, "#79c0ff", "#56d364"]
    for i, key in enumerate(sorted(all_keys)):
        y = [d["metrics"].get(key, None) for d in data]
        color = colors[i % len(colors)]
        fig.add_trace(go.Scatter(
            x=x, y=y, name=key.split(".")[-1],
            mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(color=color, size=7, line=dict(color=C_BG, width=2)),
        ))
    fig.update_layout(**CHART_LAYOUT, height=320,
                      yaxis=dict(range=[0, 1.05], gridcolor=C_BORDER,
                                 linecolor=C_BORDER, zerolinecolor=C_BORDER),
                      xaxis=dict(gridcolor=C_BORDER, linecolor=C_BORDER))
    return fig


def chart_box(runs: list[dict]) -> go.Figure:
    all_keys: set = set()
    model_metrics: dict = {}
    for run in runs:
        model = run.get("modelVersion", "unknown")[:24]
        results = run.get("results", run)
        per_case: dict = {}
        for case in results.get("testCasesResults", []):
            for m in case.get("metricsResults", []):
                mtype = m.get("type", "?")
                data  = m.get("result", {}).get("data", {})
                for field, val in data.items():
                    key = f"{mtype}.{field}"
                    all_keys.add(key)
                    if isinstance(val, (bool, int, float)):
                        per_case.setdefault(key, []).append(float(val))
        model_metrics[model] = per_case
    if not all_keys:
        return go.Figure()
    fig = go.Figure()
    colors = [C_BLUE, C_GREEN, C_PURPLE, C_AMBER]
    for i, (model, metrics) in enumerate(model_metrics.items()):
        for key, vals in metrics.items():
            fig.add_trace(go.Box(
                y=vals, name=model, legendgroup=model,
                showlegend=(key == list(metrics.keys())[0]),
                marker_color=colors[i % len(colors)],
                line_color=colors[i % len(colors)],
                fillcolor=colors[i % len(colors)] + "33",
                boxmean=True,
            ))
    fig.update_layout(**CHART_LAYOUT, height=320,
                      yaxis=dict(range=[-.05, 1.05], gridcolor=C_BORDER,
                                 linecolor=C_BORDER, zerolinecolor=C_BORDER))
    return fig


def chart_fleet_heatmap(bots: list[dict]) -> go.Figure:
    all_models: list[str] = []
    for bot in bots:
        for run in bot["runs"]:
            m = run.get("modelVersion", "unknown")[:20]
            if m not in all_models:
                all_models.append(m)
    all_models = sorted(set(all_models))
    z, y_labels = [], []
    for bot in bots:
        row = []
        model_score = {run.get("modelVersion", "?"): composite_score(extract_metrics(run))
                       for run in bot["runs"]}
        for model in all_models:
            row.append(model_score.get(model, None))
        z.append(row)
        y_labels.append(bot["botName"][:20])
    fig = go.Figure(go.Heatmap(
        z=z, x=[m[:16] for m in all_models], y=y_labels,
        colorscale=[[0, C_RED], [0.5, C_AMBER], [1, C_GREEN]],
        zmin=0, zmax=1,
        hovertemplate="<b>%{y}</b><br>Model: %{x}<br>Score: %{z:.2f}<extra></extra>",
        colorbar=dict(tickfont=dict(color=C_DIM), outlinecolor=C_BORDER,
                      outlinewidth=1, len=0.8),
    ))
    fig.update_layout(**CHART_LAYOUT, height=max(200, len(bots) * 44 + 60),
                      xaxis=dict(gridcolor=C_BORDER, linecolor=C_BORDER, side="bottom"))
    return fig


def chart_failure_clusters(runs: list[dict]) -> go.Figure:
    reasons = []
    for run in runs:
        reasons.extend(extract_ai_reasons(run))
    if not reasons:
        return go.Figure()
    clusters = {
        "Routing / Topic":     ["route", "topic", "intent", "trigger", "match"],
        "Response quality":    ["response", "answer", "relevant", "accurate", "content"],
        "Formatting":          ["format", "length", "verbose", "short", "paragraph"],
        "Safety / Guardrails": ["safety", "block", "refuse", "restrict", "guard"],
        "Fallback":            ["fallback", "escalat", "handoff", "unknown", "not understand"],
        "Other":               [],
    }
    counts = {k: 0 for k in clusters}
    for r in reasons:
        rl = r.lower()
        matched = False
        for cluster, kws in clusters.items():
            if cluster == "Other":
                continue
            if any(kw in rl for kw in kws):
                counts[cluster] += 1
                matched = True
                break
        if not matched:
            counts["Other"] += 1
    labels = [k for k, v in counts.items() if v > 0]
    values = [counts[k] for k in labels]
    color_map = {
        "Routing / Topic": C_BLUE, "Response quality": C_GREEN,
        "Formatting": C_PURPLE, "Safety / Guardrails": C_RED,
        "Fallback": C_AMBER, "Other": C_DIM,
    }
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=[color_map.get(l, C_BLUE) for l in labels],
        hovertemplate="%{x}: %{y} cases<extra></extra>",
    ))
    fig.update_layout(**CHART_LAYOUT, height=280,
                      yaxis=dict(gridcolor=C_BORDER, linecolor=C_BORDER,
                                 zerolinecolor=C_BORDER, title="failure count"),
                      showlegend=False)
    return fig


def chart_sankey(prev_run: dict, curr_run: dict,
                 prev_label: str, curr_label: str) -> go.Figure:
    prev_results = prev_run.get("results", prev_run)
    curr_results = curr_run.get("results", curr_run)
    prev_cases = {c.get("utterance", c.get("id", i)): c
                  for i, c in enumerate(prev_results.get("testCasesResults", []))}
    curr_cases = {c.get("utterance", c.get("id", i)): c
                  for i, c in enumerate(curr_results.get("testCasesResults", []))}
    pp = ff = pf = fp = 0
    for uid, prev_c in prev_cases.items():
        curr_c = curr_cases.get(uid)
        if not curr_c:
            continue
        def _pass(c):
            for m in c.get("metricsResults", []):
                for v in m.get("result", {}).get("data", {}).values():
                    if isinstance(v, bool):
                        return v
            return None
        pv, cv = _pass(prev_c), _pass(curr_c)
        if pv is True  and cv is True:  pp += 1
        if pv is False and cv is False: ff += 1
        if pv is True  and cv is False: pf += 1
        if pv is False and cv is True:  fp += 1
    if pp + ff + pf + fp == 0:
        return go.Figure()
    nodes  = [f"PASS\n{prev_label[:12]}", f"FAIL\n{prev_label[:12]}",
              f"PASS\n{curr_label[:12]}", f"FAIL\n{curr_label[:12]}"]
    colors = [C_GREEN, C_RED, C_GREEN, C_RED]
    fig = go.Figure(go.Sankey(
        node=dict(label=nodes, color=colors, pad=20, thickness=24,
                  line=dict(color=C_BORDER, width=1)),
        link=dict(
            source=[0, 0, 1, 1],
            target=[2, 3, 2, 3],
            value=[pp, pf, fp, ff],
            color=["rgba(63,185,80,.35)", "rgba(248,81,73,.35)",
                   "rgba(88,166,255,.35)", "rgba(210,153,34,.35)"],
        ),
    ))
    fig.update_layout(**CHART_LAYOUT, height=300)
    return fig


# ── UI helpers ────────────────────────────────────────────────────────────────
def status_badge(bot: dict) -> str:
    runs = bot["runs"]
    if len(runs) < 2:
        return '<span class="badge badge-blue">BASELINE</span>'
    curr = composite_score(extract_metrics(runs[-1]))
    prev = composite_score(extract_metrics(runs[-2]))
    delta = curr - prev
    if delta <= -0.05:
        return '<span class="badge badge-red">REGRESSED</span>'
    if delta >= 0.05:
        return '<span class="badge badge-green">IMPROVED</span>'
    return '<span class="badge badge-amber">STABLE</span>'


def delta_chip(val: float) -> str:
    if val > 0.02:
        return f'<span class="delta-up">▲ +{val:.3f}</span>'
    if val < -0.02:
        return f'<span class="delta-down">▼ {val:.3f}</span>'
    return f'<span class="delta-flat">● {val:+.3f}</span>'


# ── Pages ─────────────────────────────────────────────────────────────────────
def page_overview(bots: list[dict]):
    total_runs    = sum(b["runCount"] for b in bots)
    drift_events  = sum(1 for b in bots if len(b["runs"]) >= 2)
    last_scan     = max((b["updatedAt"] for b in bots), default="")

    # KPI row
    st.markdown(f"""
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-value" style="color:{C_BLUE}">{len(bots)}</div>
        <div class="kpi-label">Bots Monitored</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="color:{C_PURPLE}">{total_runs}</div>
        <div class="kpi-label">Eval Runs Total</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="color:{C_AMBER}">{drift_events}</div>
        <div class="kpi-label">Drift Events</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="color:{C_DIM}; font-size:16px">{_fmt_ts(last_scan)}</div>
        <div class="kpi-label">Last Activity</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not bots:
        st.markdown("""
        <div class="empty-state">
          <div class="empty-icon">🤖</div>
          <div class="empty-title">No bots tracked yet</div>
          <div>Tag a Copilot Studio bot with <code>#monitor</code> in its description<br>
          and run the agent to populate this dashboard.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    # Fleet heatmap
    if any(len(b["runs"]) > 0 for b in bots):
        st.markdown('<div class="section-title">Fleet Health — All Models</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(chart_fleet_heatmap(bots), use_container_width=True,
                        config={"displayModeBar": False})


def page_bot_detail(bot: dict):
    runs   = bot["runs"]
    name   = bot["botName"]
    env    = bot["envName"]
    model  = bot["modelVersion"]

    # Bot header
    badge = status_badge(bot)
    st.markdown(f"""
    <div style="display:flex; align-items:flex-start; justify-content:space-between;
                margin-bottom:20px">
      <div>
        <div style="font-size:22px; font-weight:700; color:{C_TEXT}">🤖 {name}</div>
        <div style="margin-top:6px">
          <span class="model-pill">{model}</span>
          &nbsp;
          <span style="font-size:11px; color:{C_PURPLE}">● {env}</span>
          &nbsp;&nbsp;{badge}
        </div>
      </div>
      <div style="text-align:right; font-size:11px; color:{C_DIM}">
        {len(runs)} eval run{'s' if len(runs) != 1 else ''}<br>
        Last: {_fmt_ts(runs[-1].get('storedAt','') if runs else '')}
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not runs:
        st.markdown('<div class="empty-state"><div class="empty-icon">📭</div>'
                    '<div class="empty-title">No eval runs yet</div></div>',
                    unsafe_allow_html=True)
        return

    # ── Run selector ──────────────────────────────────────────────────────────
    if len(runs) >= 2:
        st.markdown('<div class="section-title">Compare Two Runs</div>',
                    unsafe_allow_html=True)
        run_labels = [f"{r.get('modelVersion','?')[:30]}  ·  {_fmt_ts(r.get('storedAt',''))}"
                      for r in runs]
        col1, col2 = st.columns(2)
        with col1:
            idx_a = st.selectbox("Baseline run", range(len(runs)),
                                 format_func=lambda i: run_labels[i],
                                 index=max(0, len(runs) - 2), key="sel_a")
        with col2:
            idx_b = st.selectbox("Current run", range(len(runs)),
                                 format_func=lambda i: run_labels[i],
                                 index=len(runs) - 1, key="sel_b")
        run_a, run_b = runs[idx_a], runs[idx_b]
        m_a  = extract_metrics(run_a)
        m_b  = extract_metrics(run_b)
        lbl_a = run_a.get("modelVersion", "Baseline")[:24]
        lbl_b = run_b.get("modelVersion", "Current")[:24]
    else:
        run_a, run_b = runs[0], runs[0]
        m_a  = extract_metrics(run_a)
        m_b  = {}
        lbl_a = run_a.get("modelVersion", "Baseline")[:24]
        lbl_b = "—"

    # ── Metric comparison table ───────────────────────────────────────────────
    st.markdown('<div class="section-title">Metric Scorecard</div>',
                unsafe_allow_html=True)
    all_keys = sorted(set(list(m_a.keys()) + list(m_b.keys())))
    if all_keys:
        header = (f"<tr><th>Metric</th><th>{lbl_a}</th>"
                  f"<th>{lbl_b if m_b else '—'}</th><th>Delta</th></tr>")
        rows   = []
        for k in all_keys:
            va = m_a.get(k)
            vb = m_b.get(k) if m_b else None
            va_s = f"{va:.3f}" if va is not None else "—"
            vb_s = f"{vb:.3f}" if vb is not None else "—"
            if va is not None and vb is not None:
                d    = vb - va
                chip = delta_chip(d)
            else:
                chip = '<span class="delta-flat">—</span>'
            short = k.split(".")[-1]
            rows.append(f"<tr><td style='font-family:monospace;font-size:12px'>{short}</td>"
                        f"<td>{va_s}</td><td>{vb_s}</td><td>{chip}</td></tr>")
        table_html = f"""
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead style="color:{C_DIM};font-size:10px;letter-spacing:1px;
                        text-transform:uppercase;border-bottom:1px solid {C_BORDER}">
            {header}
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>"""
        st.markdown(table_html, unsafe_allow_html=True)

    # ── Charts ────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Visual Analysis</div>',
                unsafe_allow_html=True)

    if m_b:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Radar — {lbl_a} vs {lbl_b}**")
            st.plotly_chart(chart_radar(m_a, m_b, lbl_a, lbl_b),
                            use_container_width=True, config={"displayModeBar": False})
        with c2:
            st.markdown("**Test Case Flow (Sankey)**")
            fig_s = chart_sankey(run_a, run_b, lbl_a, lbl_b)
            if fig_s.data:
                st.plotly_chart(fig_s, use_container_width=True,
                                config={"displayModeBar": False})
            else:
                st.markdown(f'<div style="color:{C_DIM};padding:40px;text-align:center">'
                            'Not enough per-case data for Sankey</div>',
                            unsafe_allow_html=True)

    if len(runs) >= 2:
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**Metric Trends — All Runs**")
            st.plotly_chart(chart_trend(runs), use_container_width=True,
                            config={"displayModeBar": False})
        with c4:
            st.markdown("**Score Distribution (Box Plot)**")
            st.plotly_chart(chart_box(runs), use_container_width=True,
                            config={"displayModeBar": False})

    # ── Failure clusters ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Failure Mode Clusters — All Runs</div>',
                unsafe_allow_html=True)
    fig_fc = chart_failure_clusters(runs)
    if fig_fc.data:
        st.plotly_chart(fig_fc, use_container_width=True,
                        config={"displayModeBar": False})
    else:
        st.markdown(f'<div style="color:{C_DIM};padding:20px">'
                    'No aiResultReason data available yet.</div>',
                    unsafe_allow_html=True)

    # ── LLM analysis ─────────────────────────────────────────────────────────
    analysis = (run_b.get("analysis") or run_a.get("analysis") or "").strip()
    if analysis:
        st.markdown('<div class="section-title">LLM Drift Analysis</div>',
                    unsafe_allow_html=True)
        st.markdown(f"""
        <div class="analysis-panel">
          <div class="analysis-label">⚡ AI ANALYSIS</div>
          {analysis.replace(chr(10), '<br>')}
        </div>
        """, unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar(bots: list[dict]) -> str | None:
    with st.sidebar:
        st.markdown(f"""
        <div style="padding: 4px 0 16px">
          <div style="font-size:15px;font-weight:700;letter-spacing:2px;
                      color:{C_BLUE};font-family:monospace">⚡ DRIFT TRACKER</div>
          <div style="font-size:10px;color:{C_DIM};margin-top:2px">copilot-eval-agent · v1.0</div>
        </div>
        """, unsafe_allow_html=True)

        # Nav
        pages = {"overview": "🏠  Overview", "bots": "🤖  Bot Detail"}
        if "page" not in st.session_state:
            st.session_state.page = "overview"
        for key, label in pages.items():
            active = st.session_state.page == key or \
                     (key == "bots" and st.session_state.page not in pages)
            if st.button(label, key=f"nav_{key}",
                         use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.page = key
                st.rerun()

        st.markdown(f'<div style="border-top:1px solid {C_BORDER};margin:12px 0 16px"></div>',
                    unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:10px;color:{C_DIM};'
                    f'letter-spacing:1px;margin-bottom:10px">MONITORED BOTS</div>',
                    unsafe_allow_html=True)

        if not bots:
            st.markdown(f'<div style="color:{C_DIM};font-size:12px;padding:8px 0">'
                        'No bots yet — tag a bot with #monitor</div>',
                        unsafe_allow_html=True)
            return None

        selected = st.session_state.get("selected_bot")
        for bot in bots:
            badge = status_badge(bot)
            is_active = selected == bot["botId"]
            card_class = "bot-card active" if is_active else "bot-card"
            st.markdown(f"""
            <div class="{card_class}">
              <div style="display:flex;justify-content:space-between;align-items:flex-start">
                <div class="bot-name">{bot['botName']}</div>
                {badge}
              </div>
              <div class="bot-env">● {bot['envName']}</div>
              <div class="bot-model">{bot['modelVersion'][:28]}</div>
              <div style="font-size:10px;color:{C_DIM};margin-top:4px">
                {bot['runCount']} run{'s' if bot['runCount'] != 1 else ''}
                · {_fmt_ts(bot['updatedAt'])}
              </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"View {bot['botName']}", key=f"btn_{bot['botId']}",
                         use_container_width=True, type="secondary"):
                st.session_state.selected_bot = bot["botId"]
                st.session_state.page = "bots"
                st.rerun()

        return selected


# ── App header ────────────────────────────────────────────────────────────────
def render_header(bots: list[dict]):
    last_scan = max((b["updatedAt"] for b in bots), default="")
    ts_str    = _fmt_ts(last_scan) if last_scan else "no data yet"
    st.markdown(f"""
    <div class="drift-header">
      <div>
        <div class="drift-title">⚡ LLM DRIFT TRACKER</div>
        <div class="drift-sub">copilot-eval-agent · v1.0 · {len(bots)} bots monitored</div>
      </div>
      <div style="display:flex;align-items:center;gap:16px">
        <div style="font-size:11px;color:{C_DIM}">last activity: {ts_str}</div>
        <div class="live-pill"><div class="live-dot"></div>LIVE</div>
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
    else:
        bot = next((b for b in bots if b["botId"] == selected), None)
        if bot:
            page_bot_detail(bot)
        else:
            st.markdown(f'<div style="color:{C_DIM};padding:40px;text-align:center">'
                        'Select a bot from the sidebar.</div>',
                        unsafe_allow_html=True)


if __name__ == "__main__":
    main()
