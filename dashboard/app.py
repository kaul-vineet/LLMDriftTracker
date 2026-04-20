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
        llm_status_path = os.path.join(cfg.get("store_dir", "data"), "llm_status.json")
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


def render_readiness():
    ready, issues = _get_readiness()
    if ready:
        st.markdown(
            f"<div style='background:rgba(40,200,64,.08);border:1px solid rgba(40,200,64,.35);"
            f"border-radius:6px;padding:10px 14px;margin-bottom:8px;text-align:center'>"
            f"<div style='color:{C_GREEN};font-size:0.85rem;font-weight:700;letter-spacing:3px;"
            f"font-family:{FONT}'>● READY</div></div>",
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
    running = _agent_running()
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
        _ready, _ = _get_readiness()
        if st.button("▶ Start Agent", use_container_width=True, type="primary",
                     disabled=not _ready,
                     help=None if _ready else "Complete setup before starting the agent"):
            _start_agent()
            time.sleep(1)
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
    render_readiness()
    render_agent_controls()
    st.markdown(
        f"<div style='border-top:1px solid {C_BORDER};margin:10px 0'></div>",
        unsafe_allow_html=True,
    )

# ── Page routing ──────────────────────────────────────────────────────────────
pg = st.navigation([
    st.Page("pages/ashoka.py", title="ASHOKA", icon="⚡", default=True),
    st.Page("pages/1_Setup.py", title="Setup", icon="⚙"),
    st.Page("pages/2_Data.py", title="Data", icon="🗄"),
])
pg.run()
