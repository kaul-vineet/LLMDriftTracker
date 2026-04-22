"""
dashboard/app.py — VARION · entry point & router
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
PID_FILE  = os.path.join(STORE_DIR, "agent", "agent.pid")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VARION",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={},
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  /* system monospace stack — avoids external HTTP round-trip on every load */
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

  /* Hide nav until our CSS is applied — prevents flash of default Streamlit styles */
  @keyframes nav-appear {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
  [data-testid="stSidebarNav"] {{
    opacity: 0;
    animation: nav-appear 0.15s ease-out 0.12s forwards;
  }}

  /* Nav link base — themed from the start so the reveal looks correct */
  [data-testid="stSidebarNavLink"] {{
    background: transparent !important;
    border-radius: 6px !important;
    padding: 5px 10px !important;
    text-decoration: none !important;
    border: none !important;
  }}
  [data-testid="stSidebarNavLink"] p,
  [data-testid="stSidebarNavLink"] span,
  [data-testid="stSidebarNavLink"] div {{
    font-family: {FONT} !important;
    font-size: 0.78rem !important;
    letter-spacing: 1px !important;
    color: {C_DIM} !important;
  }}
  [data-testid="stSidebarNavLink"]:hover {{
    background: rgba(0,240,255,0.07) !important;
  }}
  [data-testid="stSidebarNavLink"]:hover p,
  [data-testid="stSidebarNavLink"]:hover span,
  [data-testid="stSidebarNavLink"]:hover div {{
    color: {C_CYAN} !important;
  }}
  [data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: rgba(0,240,255,0.09) !important;
    border-left: 2px solid {C_CYAN} !important;
  }}
  [data-testid="stSidebarNavLink"][aria-current="page"] p,
  [data-testid="stSidebarNavLink"][aria-current="page"] span,
  [data-testid="stSidebarNavLink"][aria-current="page"] div {{
    color: {C_CYAN} !important;
  }}
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
  @keyframes sp-warp  {{ from{{transform:rotate(0deg)}} to{{transform:rotate(360deg)}} }}
  @keyframes sp-pulse {{
    0%,100%{{transform:translate(-50%,-50%) scale(1);   opacity:0.85;}}
    50%    {{transform:translate(-50%,-50%) scale(1.2); opacity:1;}}
  }}
  @keyframes sp-orb   {{ from{{transform:rotate(0deg)}}   to{{transform:rotate(360deg)}}  }}
  @keyframes sp-corb  {{ from{{transform:rotate(0deg)}}   to{{transform:rotate(-360deg)}} }}
  @keyframes sp-pglow {{
    0%,100%{{box-shadow:0 0 8px  rgba(0,240,255,0.5);}}
    50%    {{box-shadow:0 0 22px rgba(0,240,255,0.95);}}
  }}
</style>
""", unsafe_allow_html=True)


# ── PID / agent helpers ───────────────────────────────────────────────────────
def _read_pid():
    try:
        return int(open(PID_FILE).read().strip())
    except Exception:
        return None


def _is_pid_alive(pid):
    try:
        import psutil as _ps
        p = _ps.Process(pid)
        return p.is_running() and p.status() != _ps.STATUS_ZOMBIE
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


def _get_readiness():
    """Returns (ready: bool, issues: list[str])."""
    issues = []

    if not os.path.exists("config.json"):
        return False, ["No config.json — complete Setup"]

    try:
        cfg = json.loads(open("config.json").read())
    except Exception:
        return False, ["config.json unreadable"]

    if not cfg.get("eval_app_client_id") or not cfg.get("eval_app_tenant_id"):
        issues.append("App registration incomplete")

    # Offline cache inspection only — no network call; stale tokens surface on the first agent run
    try:
        import msal as _msal
        cp = cfg.get("token_cache_file", "msal_token_cache.json")
        if os.path.exists(cp):
            _c = _msal.SerializableTokenCache(); _c.deserialize(open(cp).read())
            _a = _msal.PublicClientApplication(
                cfg.get("eval_app_client_id", "x"),
                authority=f"https://login.microsoftonline.com/{cfg.get('eval_app_tenant_id','x')}",
                token_cache=_c,
            )
            if not _a.get_accounts():
                issues.append("Not authenticated — sign in via Setup")
        else:
            issues.append("Not authenticated — sign in via Setup")
    except Exception:
        issues.append("Auth check failed")

    if not cfg.get("environments"):
        issues.append("No environments configured")

    llm = cfg.get("llm", {})
    if not llm.get("base_url"):
        issues.append("LLM endpoint not configured")
    else:
        llm_status_path = os.path.join(cfg.get("store_dir", "data"), "agent", "llm_status.json")
        if not os.path.exists(llm_status_path):
            issues.append("LLM not validated — click Test in Setup")
        else:
            try:
                ls = json.loads(open(llm_status_path).read())
                if not ls.get("ok"):
                    issues.append(f"LLM error: {ls.get('error', 'unknown')}")
            except Exception:
                issues.append("LLM status unreadable")

    return len(issues) == 0, issues


def _get_readiness_cached():
    """_get_readiness with 30-second cache to avoid MSAL init on every rerun."""
    now = time.time()
    if now - st.session_state.get("_ready_ts", 0) > 30:
        st.session_state["_ready_cache"] = _get_readiness()
        st.session_state["_ready_ts"] = now
    return st.session_state["_ready_cache"]


def _agent_running_cached():
    """_agent_running with 10-second cache — psutil is fast but no need to poll every rerun."""
    now = time.time()
    if now - st.session_state.get("_agent_ts", 0) > 10:
        st.session_state["_agent_cache"] = _agent_running()
        st.session_state["_agent_ts"] = now
    return st.session_state["_agent_cache"]


def render_readiness():
    ready, issues = _get_readiness_cached()
    if ready:
        st.markdown(
            f"<div style='background:rgba(40,200,64,.08);border:1px solid rgba(40,200,64,.35);"
            f"border-radius:6px;padding:10px 14px;margin-bottom:8px;text-align:center'>"
            f"<div style='color:{C_GREEN};font-size:0.85rem;font-weight:700;letter-spacing:3px;"
            f"font-family:{FONT}'>● READY TO START</div></div>",
            unsafe_allow_html=True,
        )
    else:
        items = "".join(
            f"<div style='color:{C_DIM};font-size:0.62rem;margin-top:3px;padding-left:4px'>"
            f"· {iss}</div>"
            for iss in issues
        )
        st.markdown(
            f"<div style='background:rgba(255,68,68,.06);border:1px solid rgba(255,68,68,.3);"
            f"border-radius:6px;padding:10px 14px;margin-bottom:8px'>"
            f"<div style='color:{C_RED};font-size:0.75rem;font-weight:700;letter-spacing:2px;"
            f"font-family:{FONT}'>○ SETUP NOT COMPLETE</div>"
            f"{items}</div>",
            unsafe_allow_html=True,
        )


def render_agent_controls():
    running = _agent_running_cached()
    if running:
        pid = _read_pid()
        st.markdown(
            f"<div style='background:rgba(40,200,64,.06);border:1px solid rgba(40,200,64,.25);"
            f"border-radius:6px;padding:8px 12px;margin-bottom:8px'>"
            f"<div style='color:{C_GREEN};font-size:0.65rem;font-weight:700;letter-spacing:1px;"
            f"font-family:{FONT}'>● AGENT RUNNING &nbsp;·&nbsp; PID {pid}</div></div>",
            unsafe_allow_html=True,
        )
        st.markdown("""<style>
          [data-testid="stSidebar"] button[kind="secondary"] {
            border-color:#e53e3e !important; color:#e53e3e !important;
          }
          [data-testid="stSidebar"] button[kind="secondary"]:hover {
            background:rgba(229,62,62,0.12) !important;
          }
        </style>""", unsafe_allow_html=True)
        if st.button("■ Stop Agent", use_container_width=True, type="secondary"):
            with st.spinner("Shutting down…"):
                _stop_agent()
                time.sleep(1)
            st.session_state["_agent_ts"] = 0
            st.rerun()
    else:
        st.markdown(
            f"<div style='background:rgba(255,68,68,.06);border:1px solid rgba(255,68,68,.3);"
            f"border-radius:6px;padding:10px 14px;margin-bottom:8px;text-align:center'>"
            f"<div style='color:{C_RED};font-size:0.85rem;font-weight:700;letter-spacing:3px;"
            f"font-family:{FONT}'>○ AGENT STOPPED</div></div>",
            unsafe_allow_html=True,
        )
        _ready, _ = _get_readiness_cached()
        if st.button("▶ Start Agent", use_container_width=True, type="primary",
                     disabled=not _ready,
                     help=None if _ready else "Complete setup before starting the agent"):
            with st.spinner("Starting…"):
                _start_agent()
                time.sleep(2)
            st.session_state["_agent_ts"] = 0
            st.rerun()


# ── Shared sidebar (appears on every page) ────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"<div style='padding:4px 0 14px'>"
        f"<div style='font-size:16px;font-weight:700;letter-spacing:3px;"
        f"color:{C_CYAN};font-family:{FONT}'>⚡ VARION</div>"
        f"<div style='font-size:0.6rem;color:{C_DIM};margin-top:2px;letter-spacing:1px'>"
        f"copilot-eval-agent · v1.1</div></div>",
        unsafe_allow_html=True,
    )
    render_readiness()
    render_agent_controls()
    st.markdown(
        f"<div style='border-top:1px solid {C_BORDER};margin:10px 0'></div>",
        unsafe_allow_html=True,
    )

# ── Auth error banner (shown on every page when agent stopped due to auth failure) ──
_auth_err_path = os.path.join(STORE_DIR, "agent", "auth_error.json")
if os.path.exists(_auth_err_path):
    try:
        _auth_err = json.loads(open(_auth_err_path).read())
        _auth_msg = _auth_err.get("error", "Unknown auth error")
    except Exception:
        _auth_msg = "Unknown auth error"
    st.markdown(f"""
<div style="background:#2a0a0a;border:2px solid {C_RED};border-radius:8px;
            padding:16px 20px;margin-bottom:16px">
  <div style="font-size:0.9rem;font-weight:700;color:{C_RED};letter-spacing:3px;
              font-family:{FONT};margin-bottom:6px">⛔ CRITICAL AUTH ERROR — AGENT STOPPED</div>
  <div style="font-size:0.82rem;color:#ffaaaa;margin-bottom:10px">{_auth_msg}</div>
  <div style="font-size:0.78rem;color:{C_DIM}">
    All Power Platform APIs must be accessible with the existing token.
    Go to <b style="color:{C_CYAN}">Setup</b> → re-authenticate → restart the agent.
  </div>
</div>""", unsafe_allow_html=True)

# ── Page routing ──────────────────────────────────────────────────────────────
pg = st.navigation([
    st.Page("_pages/ashoka.py", title="ASHOKA", icon="⚡", default=True),
    st.Page("_pages/setup.py",  title="Setup",  icon="⚙"),
    st.Page("_pages/data.py",   title="Data",   icon="🗄"),
    st.Page("_pages/logs.py",   title="Logs",   icon="📋"),
])
pg.run()
