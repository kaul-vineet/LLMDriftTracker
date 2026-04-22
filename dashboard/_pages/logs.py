"""dashboard/pages/logs.py — Live log viewer for the āshokā agent."""
import json
import os
import time

import streamlit as st

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from theme import C_BG, C_CARD, C_BORDER, C_CYAN, C_MAGENTA, C_GOLD, C_RED, C_GREEN, C_DIM, C_TEXT, FONT

STORE_DIR = os.environ.get("STORE_DIR", "data")
LOG_PATH  = os.path.join(STORE_DIR, "agent", "agent.log")
MAX_LINES = 500

LEVEL_COLOR = {
    "ERROR":   C_RED,
    "WARNING": C_GOLD,
    "WARN":    C_GOLD,
    "INFO":    C_CYAN,
    "DEBUG":   C_DIM,
}

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='font-size:1.4rem;font-weight:700;letter-spacing:4px;"
    f"color:{C_CYAN};font-family:{FONT};margin-bottom:4px'>⚡ LOGS</div>"
    f"<div style='font-size:0.78rem;color:{C_DIM};margin-bottom:20px'>"
    f"Operational log · last {MAX_LINES} lines · newest first · auto-refreshes every 5s</div>",
    unsafe_allow_html=True,
)

# ── Controls ──────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns([2, 3, 1])
with c1:
    level_filter = st.selectbox(
        "Level", ["ALL", "ERROR", "WARNING", "INFO", "DEBUG"],
        key="log_level", label_visibility="collapsed",
    )
with c2:
    search = st.text_input(
        "Search", placeholder="filter by text or thread…",
        key="log_search", label_visibility="collapsed",
    )
with c3:
    if os.path.exists(LOG_PATH):
        if st.session_state.get("_confirm_clear_log"):
            if st.button("⚠ Confirm", key="btn_clear_log_yes",
                         type="primary", use_container_width=True):
                try:
                    open(LOG_PATH, "w").close()
                except Exception:
                    pass
                st.session_state.pop("_confirm_clear_log", None)
                st.rerun()
        else:
            if st.button("🗑 Clear", key="btn_clear_log",
                         type="secondary", use_container_width=True):
                st.session_state["_confirm_clear_log"] = True
                st.rerun()

# ── Auto-refresh every 5 s permanently ───────────────────────────────────────
@st.fragment(run_every=5)
def _render_logs():
    if not os.path.exists(LOG_PATH):
        st.info("No log file yet — start the agent to begin writing logs.")
        return

    size_kb = os.path.getsize(LOG_PATH) / 1024
    mtime   = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(LOG_PATH)))
    st.markdown(
        f"<div style='font-size:0.65rem;color:{C_DIM};font-family:{FONT};"
        f"border-bottom:1px solid {C_BORDER};padding-bottom:6px;margin-bottom:14px'>"
        f"data/agent.log &nbsp;·&nbsp; {size_kb:.1f} KB &nbsp;·&nbsp; last written {mtime}"
        f"</div>",
        unsafe_allow_html=True,
    )

    try:
        with open(LOG_PATH, encoding="utf-8") as f:
            raw_lines = f.readlines()
    except Exception:
        raw_lines = []

    parsed = []
    for raw in raw_lines[-MAX_LINES:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            parsed.append(json.loads(raw))
        except Exception:
            parsed.append({"ts": "", "level": "INFO", "thread": "main", "msg": raw})

    if level_filter != "ALL":
        parsed = [e for e in parsed if e.get("level", "").upper() == level_filter]
    if search.strip():
        q = search.strip().lower()
        parsed = [e for e in parsed
                  if q in e.get("msg", "").lower() or q in e.get("thread", "").lower()]

    if not parsed:
        st.markdown(
            f"<div style='color:{C_DIM};font-size:0.8rem;padding:12px 0'>No matching entries.</div>",
            unsafe_allow_html=True,
        )
        return

    rows = []
    for e in reversed(parsed):
        level  = e.get("level", "INFO").upper()
        color  = LEVEL_COLOR.get(level, C_DIM)
        ts     = e.get("ts", "")
        try:
            from datetime import datetime, timezone, timedelta
            _IST = timezone(timedelta(hours=5, minutes=30))
            _dt  = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(_IST)
            ts_fmt = _dt.strftime("%H:%M:%S")
        except Exception:
            ts_fmt = ts[11:19] if len(ts) >= 19 else ts or "—"
        thread = e.get("thread", "")[:10]
        msg    = e.get("msg", "").replace("<", "&lt;").replace(">", "&gt;")
        rows.append(
            f"<div style='display:grid;"
            f"grid-template-columns:64px 58px 80px 1fr;"
            f"gap:0 10px;padding:4px 0;"
            f"border-bottom:1px solid rgba(255,255,255,0.04);"
            f"font-family:monospace;font-size:0.72rem;align-items:baseline'>"
            f"<span style='color:{C_DIM}'>{ts_fmt}</span>"
            f"<span style='color:{color};font-weight:700'>{level}</span>"
            f"<span style='color:{C_DIM}'>{thread}</span>"
            f"<span style='color:{C_TEXT}'>{msg}</span>"
            f"</div>"
        )

    st.markdown(
        f"<div style='background:{C_CARD};border:1px solid {C_BORDER};"
        f"border-radius:8px;padding:12px 16px;"
        f"max-height:620px;overflow-y:auto'>"
        + "".join(rows)
        + "</div>",
        unsafe_allow_html=True,
    )

_render_logs()
