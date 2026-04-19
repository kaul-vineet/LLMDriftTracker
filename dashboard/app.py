"""
dashboard/app.py — LLM Drift Tracker · entry point & router
Runs on every page load: sets config, applies CSS, renders shared sidebar, then routes.
"""
import json
import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

import streamlit as st

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dashboard.theme import (
    C_BG, C_CARD, C_BORDER, C_CYAN, C_MAGENTA, C_GOLD,
    C_RED, C_GREEN, C_DIM, C_TEXT, FONT,
)

STORE_DIR = os.environ.get("STORE_DIR", "data")
PID_FILE  = os.path.join(STORE_DIR, "agent.pid")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LLM Drift Tracker",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={},
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;600;700&display=swap');
  html, body, [data-testid="stAppViewContainer"] {{
    background: {C_BG} !important; color: {C_TEXT}; font-family: {FONT};
  }}
  [data-testid="stSidebar"] {{
    background: {C_CARD} !important; border-right: 1px solid {C_BORDER};
  }}
  [data-testid="stSidebar"] * {{ color: {C_TEXT} !important; }}
  .block-container {{ padding-top: 1rem; padding-bottom: 2rem; }}
  section[data-testid="stSidebar"] > div {{ padding-top: 1rem; }}
  #MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; }}
  [data-testid="stHeader"] {{ display: none; }}
  [data-testid="stSidebarCollapsed"],
  [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
  .stPlotlyChart {{ background: transparent !important; }}
  ::-webkit-scrollbar {{ width: 5px; }}
  ::-webkit-scrollbar-track {{ background: {C_BG}; }}
  ::-webkit-scrollbar-thumb {{ background: {C_BORDER}; border-radius: 3px; }}

  /* Stat bar */
  .stat-bar {{
    display: grid; grid-template-columns: repeat(5, 1fr);
    gap: 1px; background: {C_BORDER}; border: 1px solid {C_BORDER};
    border-radius: 8px; overflow: hidden; margin-bottom: 24px;
  }}
  .stat-cell {{ background: {C_CARD}; padding: 16px 20px; text-align: center; }}
  .stat-value {{
    font-size: 2rem; font-weight: 700; font-family: {FONT}; line-height: 1;
  }}
  .stat-label {{
    font-size: 0.65rem; color: {C_DIM}; letter-spacing: 2px;
    text-transform: uppercase; margin-top: 5px;
  }}

  /* Section label */
  .sec-label {{
    font-size: 0.65rem; font-weight: 700; letter-spacing: 2px;
    text-transform: uppercase; color: {C_DIM};
    border-bottom: 1px solid {C_BORDER}; padding-bottom: 6px;
    margin: 20px 0 14px; font-family: {FONT};
  }}

  /* Verdict badge */
  .vbadge {{
    display: inline-block; border-radius: 3px; padding: 2px 8px;
    font-size: 0.65rem; font-weight: 700; letter-spacing: 1px; font-family: {FONT};
  }}

  /* Analysis panel */
  .analysis-panel {{
    background: {C_BG}; border-left: 3px solid {C_MAGENTA};
    border-radius: 0 8px 8px 0; padding: 16px 20px;
    font-size: 0.875rem; line-height: 1.75; color: {C_TEXT}; margin-bottom: 20px;
  }}
  .analysis-label {{
    font-size: 0.65rem; font-weight: 700; color: {C_MAGENTA};
    letter-spacing: 2px; margin-bottom: 8px; font-family: {FONT};
  }}

  /* Run timeline */
  .timeline {{ padding: 8px 0; }}
  .tl-item {{
    display: flex; gap: 16px; padding: 12px 0;
    border-bottom: 1px solid {C_BORDER}; align-items: flex-start;
  }}
  .tl-dot {{ width: 10px; height: 10px; border-radius: 50%; margin-top: 4px; flex-shrink: 0; }}
  .tl-content {{ flex: 1; }}
  .tl-guid {{ font-family:{FONT}; font-size:0.7rem; color:{C_DIM}; }}
  .tl-model {{ font-size:0.78rem; color:{C_TEXT}; font-family:{FONT}; }}
  .tl-ts {{ font-size:0.68rem; color:{C_DIM}; }}
</style>
<style>
  html, body, [data-testid="stAppViewContainer"] {{
    background-image:
      radial-gradient(circle, rgba(0,240,255,0.035) 1px, transparent 1px),
      radial-gradient(circle at 80% 20%, rgba(255,0,170,0.04) 0%, transparent 50%),
      radial-gradient(circle at 20% 80%, rgba(0,240,255,0.04) 0%, transparent 50%) !important;
    background-size: 28px 28px, 100% 100%, 100% 100% !important;
  }}
  @keyframes hline {{
    0%   {{ transform: translateY(-100vh); opacity: 0; }}
    10%  {{ opacity: 0.4; }}
    90%  {{ opacity: 0.4; }}
    100% {{ transform: translateY(100vh); opacity: 0; }}
  }}
  .scan-line {{
    position: fixed; left: 0; width: 100%; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(0,240,255,0.15), transparent);
    pointer-events: none; z-index: 0;
    animation: hline 8s linear infinite;
  }}
  .scan-line:nth-child(2) {{ animation-delay: 3s; }}
</style>
<div class="scan-line"></div>
<div class="scan-line"></div>
""", unsafe_allow_html=True)


# ── PID / agent helpers ───────────────────────────────────────────────────────
def _read_pid():
    try:
        return int(open(PID_FILE).read().strip())
    except Exception:
        return None


def _is_pid_alive(pid):
    import sys as _sys
    try:
        if _sys.platform == "win32":
            import subprocess as _sp
            r = _sp.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                        capture_output=True, text=True, timeout=3)
            return str(pid) in r.stdout
        else:
            import os as _os
            _os.kill(pid, 0)
            return True
    except Exception:
        return False


def _agent_running():
    pid = _read_pid()
    return pid is not None and _is_pid_alive(pid)


def _start_agent():
    import subprocess as _sp
    import sys as _sys
    kwargs = {"stdout": _sp.DEVNULL, "stderr": _sp.DEVNULL}
    if _sys.platform == "win32":
        kwargs["creationflags"] = _sp.CREATE_NO_WINDOW
    proc = _sp.Popen([_sys.executable, "-m", "agent.main"], **kwargs)
    os.makedirs(STORE_DIR, exist_ok=True)
    open(PID_FILE, "w").write(str(proc.pid))


def _stop_agent():
    pid = _read_pid()
    if not pid:
        return
    import sys as _sys
    try:
        if _sys.platform == "win32":
            import subprocess as _sp
            _sp.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)
        else:
            import os as _os, signal as _sig
            _os.kill(pid, _sig.SIGTERM)
    except Exception:
        pass
    try:
        os.remove(PID_FILE)
    except Exception:
        pass


def render_auth_status():
    from agent.auth import get_auth_state
    try:
        cfg   = json.loads(open("config.json").read()) if os.path.exists("config.json") else {}
        state = get_auth_state(cfg) if cfg else {"status": "UNKNOWN"}
    except Exception:
        state = {"status": "UNKNOWN"}
    status  = state.get("status", "UNKNOWN")
    account = state.get("account", "")
    if status == "AUTHENTICATED":
        st.markdown(
            f"<div style='background:rgba(40,200,64,.08);border:1px solid rgba(40,200,64,.3);"
            f"border-radius:6px;padding:8px 12px;margin-bottom:8px'>"
            f"<div style='color:{C_GREEN};font-size:0.65rem;font-weight:700;letter-spacing:1px;"
            f"font-family:{FONT}'>● TOKEN VALID</div>"
            f"<div style='color:{C_DIM};font-size:0.65rem;margin-top:2px'>{account}</div></div>",
            unsafe_allow_html=True,
        )
    elif status == "PENDING_DEVICE_FLOW":
        code = state.get("user_code", "")
        st.markdown(
            f"<div style='background:rgba(255,68,68,.08);border:1px solid {C_RED};"
            f"border-radius:6px;padding:10px 12px;margin-bottom:8px'>"
            f"<div style='color:{C_RED};font-size:0.65rem;font-weight:700;letter-spacing:1px;"
            f"font-family:{FONT}'>⚠ ACTION REQUIRED</div>"
            f"<div style='color:{C_DIM};font-size:0.68rem;margin-top:4px'>microsoft.com/devicelogin</div>"
            f"<div style='color:{C_CYAN};font-size:1.4rem;font-weight:700;letter-spacing:6px;"
            f"font-family:{FONT};margin-top:6px;text-align:center'>{code}</div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='background:{C_CARD};border:1px solid {C_BORDER};"
            f"border-radius:6px;padding:8px 12px;margin-bottom:8px'>"
            f"<div style='color:{C_DIM};font-size:0.65rem;font-weight:700;letter-spacing:1px;"
            f"font-family:{FONT}'>● AUTH UNKNOWN</div></div>",
            unsafe_allow_html=True,
        )


def render_agent_controls():
    running      = _agent_running()
    trigger_path = os.path.join(STORE_DIR, "force_eval.trigger")
    if running:
        pid = _read_pid()
        st.markdown(
            f"<div style='background:rgba(40,200,64,.06);border:1px solid rgba(40,200,64,.25);"
            f"border-radius:6px;padding:8px 12px;margin-bottom:8px'>"
            f"<div style='color:{C_GREEN};font-size:0.65rem;font-weight:700;letter-spacing:1px;"
            f"font-family:{FONT}'>● AGENT RUNNING &nbsp;·&nbsp; PID {pid}</div></div>",
            unsafe_allow_html=True,
        )
        if st.button("■ Stop Agent", use_container_width=True, type="secondary"):
            _stop_agent()
            st.rerun()
    else:
        st.markdown(
            f"<div style='background:{C_CARD};border:1px solid {C_BORDER};"
            f"border-radius:6px;padding:8px 12px;margin-bottom:8px'>"
            f"<div style='color:{C_DIM};font-size:0.65rem;font-weight:700;letter-spacing:1px;"
            f"font-family:{FONT}'>○ AGENT STOPPED</div></div>",
            unsafe_allow_html=True,
        )
        if st.button("▶ Start Agent", use_container_width=True, type="primary"):
            _start_agent()
            time.sleep(1)
            st.rerun()
    pending = os.path.exists(trigger_path)
    if pending:
        st.markdown(
            f"<div style='color:{C_GOLD};font-size:0.7rem;font-family:{FONT};"
            f"text-align:center;padding:6px'>⏳ Eval queued</div>",
            unsafe_allow_html=True,
        )
    else:
        if st.button("▶ Force Eval Now", use_container_width=True, type="secondary"):
            os.makedirs(STORE_DIR, exist_ok=True)
            open(trigger_path, "w").write(datetime.now(timezone.utc).isoformat())
            st.rerun()


# ── Shared sidebar (appears on every page) ────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"<div style='padding:4px 0 14px'>"
        f"<div style='font-size:16px;font-weight:700;letter-spacing:3px;"
        f"color:{C_CYAN};font-family:{FONT}'>⚡ DRIFT TRACKER</div>"
        f"<div style='font-size:0.6rem;color:{C_DIM};margin-top:2px;letter-spacing:1px'>"
        f"copilot-eval-agent · v1.1</div></div>",
        unsafe_allow_html=True,
    )
    render_auth_status()
    render_agent_controls()
    st.markdown(
        f"<div style='border-top:1px solid {C_BORDER};margin:10px 0'></div>",
        unsafe_allow_html=True,
    )

# ── Page routing ──────────────────────────────────────────────────────────────
pg = st.navigation([
    st.Page("pages/ashoka.py", title="ASHOKA", icon="⚡", default=True),
    st.Page("pages/events.py", title="Events", icon="📋"),
    st.Page("pages/1_Setup.py", title="Setup", icon="⚙"),
])
pg.run()
