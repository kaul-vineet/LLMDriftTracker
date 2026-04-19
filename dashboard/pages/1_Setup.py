"""
dashboard/pages/1_Setup.py — 7-step configuration wizard.

Dynamically discovers Power Platform environments (BAPI) and bots (Dataverse)
using MSAL device-flow auth. Writes config.json to STORE_DIR on completion.

Steps:
  1  App Registration   (client ID, tenant ID)
  2  Connect            (MSAL device flow in-browser)
  3  Environments       (dynamic from BAPI)
  4  Bots               (dynamic from Dataverse per env)
  5  LLM                (endpoint, model; api_key via env var)
  6  Notifications      (SMTP; password via env var)
  7  Review + Save
"""
import json
import msal
import os
import time
from datetime import datetime, timezone

import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Setup — LLM Drift Tracker", page_icon="⚙️", layout="wide")

# ── Ouroboros tokens (copied so page is self-contained) ───────────────────────
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

TOTAL_STEPS    = 7
EVAL_SCOPES    = ["https://api.powerplatform.com/.default"]
BAPI_SCOPES    = ["https://service.powerapps.com/.default"]
STORE_DIR      = os.environ.get("STORE_DIR", "data")
CONFIG_PATH    = "config.json"

DEFAULT_CLIENT_ID = "774142ce-9070-446b-83ac-e2053c716879"

st.markdown(f"""
<style>
  html, body, [data-testid="stAppViewContainer"] {{
    background: {C_BG} !important; color: {C_TEXT}; font-family: {FONT};
  }}
  [data-testid="stSidebar"] {{ background: {C_CARD} !important; }}
  #MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; }}
  [data-testid="stHeader"] {{ display: none; }}
  .step-bar {{
    display: flex; align-items: center; gap: 0;
    margin-bottom: 28px; padding: 0;
  }}
  .step-node {{
    display: flex; flex-direction: column; align-items: center;
    min-width: 80px;
  }}
  .step-circle {{
    width: 32px; height: 32px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.8rem; font-family: {FONT};
    border: 2px solid {C_BORDER};
  }}
  .step-circle.done    {{ background: {C_GREEN}; color: #000; border-color: {C_GREEN}; }}
  .step-circle.active  {{ background: {C_CYAN};  color: #000; border-color: {C_CYAN};
                          box-shadow: 0 0 12px rgba(0,240,255,.4); }}
  .step-circle.pending {{ background: {C_BG};    color: {C_DIM}; }}
  .step-label {{
    font-size: 0.6rem; color: {C_DIM}; margin-top: 4px;
    letter-spacing: 1px; text-transform: uppercase; text-align: center;
  }}
  .step-label.active {{ color: {C_CYAN}; font-weight: 700; }}
  .step-connector {{
    flex: 1; height: 1px; background: {C_BORDER}; margin-bottom: 20px;
  }}
  .section-card {{
    background: {C_CARD}; border: 1px solid {C_BORDER};
    border-radius: 10px; padding: 24px 28px; margin-bottom: 20px;
  }}
  .probe-box {{
    background: {C_BG}; border: 1px solid {C_BORDER};
    border-radius: 6px; padding: 12px 16px;
    font-family: {FONT}; font-size: 0.72rem; color: {C_DIM};
    margin-top: 12px; max-height: 200px; overflow-y: auto;
  }}
  .device-code {{
    font-size: 2.5rem; font-weight: 700; letter-spacing: 8px;
    color: {C_CYAN}; font-family: {FONT}; text-align: center;
    padding: 20px; background: {C_BG}; border-radius: 8px;
    border: 1px solid {C_CYAN}; margin: 16px 0;
    box-shadow: 0 0 20px rgba(0,240,255,.15);
  }}
</style>
""", unsafe_allow_html=True)


# ── Session state init ────────────────────────────────────────────────────────
def _init():
    defaults = {
        "wiz_step":          1,
        "wiz_client_id":     DEFAULT_CLIENT_ID,
        "wiz_tenant_id":     "",
        "wiz_cache_file":    os.path.join(STORE_DIR, "msal_cache.json"),
        "wiz_token":         None,
        "wiz_account":       None,
        "wiz_envs":          [],
        "wiz_selected_envs": [],
        "wiz_bots":          {},   # {env_name: [bot, ...]}
        "wiz_bot_sel":       {},   # {env_name: [schemaname, ...]}  empty = all
        "wiz_llm_url":       "",
        "wiz_llm_model":     "gpt-4o",
        "wiz_poll":          20,
        "wiz_smtp_host":     "",
        "wiz_smtp_port":     587,
        "wiz_smtp_user":     "",
        "wiz_smtp_rcpt":     "",
        "wiz_device_flow":   None,
        "wiz_flow_started":  False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()
step = st.session_state.wiz_step


# ── Step indicator ────────────────────────────────────────────────────────────
STEP_LABELS = ["App Reg", "Connect", "Envs", "Bots", "LLM", "Notify", "Save"]

def render_step_bar(current: int):
    nodes = ""
    for i, label in enumerate(STEP_LABELS, 1):
        state = "done" if i < current else ("active" if i == current else "pending")
        sym   = "✓" if state == "done" else str(i)
        nodes += (
            f"<div class='step-node'>"
            f"<div class='step-circle {state}'>{sym}</div>"
            f"<div class='step-label {\"active\" if state == \"active\" else \"\"}'>{label}</div>"
            f"</div>"
        )
        if i < len(STEP_LABELS):
            nodes += "<div class='step-connector'></div>"
    st.markdown(f"<div class='step-bar'>{nodes}</div>", unsafe_allow_html=True)


# ── MSAL helpers ──────────────────────────────────────────────────────────────
def _msal_app(client_id: str, tenant_id: str, cache: msal.SerializableTokenCache):
    return msal.PublicClientApplication(
        client_id=client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=cache,
    )


def _load_cache(cache_file: str) -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if os.path.exists(cache_file):
        cache.deserialize(open(cache_file).read())
    return cache


def _save_cache(cache: msal.SerializableTokenCache, cache_file: str):
    if cache.has_state_changed:
        os.makedirs(os.path.dirname(cache_file) or ".", exist_ok=True)
        open(cache_file, "w").write(cache.serialize())


def _get_token_silent(scopes, client_id, tenant_id, cache_file) -> str | None:
    cache = _load_cache(cache_file)
    app   = _msal_app(client_id, tenant_id, cache)
    accs  = app.get_accounts()
    if accs:
        r = app.acquire_token_silent(scopes, account=accs[0])
        if r and "access_token" in r:
            _save_cache(cache, cache_file)
            return r["access_token"]
    return None


def _acquire_with_flow(scopes, client_id, tenant_id, cache_file) -> tuple[dict, msal.PublicClientApplication]:
    """Initiate device flow. Returns (flow_dict, app). Does NOT block."""
    cache = _load_cache(cache_file)
    app   = _msal_app(client_id, tenant_id, cache)
    flow  = app.initiate_device_flow(scopes=scopes)
    return flow, app, cache


def _poll_device_flow(app, flow, cache, cache_file) -> str | None:
    """Try one non-blocking poll. Returns token if ready, None if still waiting."""
    # Use a short timeout so we don't block Streamlit
    result = app.acquire_token_by_device_flow(flow, exit_condition=lambda r: True)
    if result and "access_token" in result:
        _save_cache(cache, cache_file)
        return result["access_token"]
    return None


# ── API probe helpers ─────────────────────────────────────────────────────────
def _probe_envs(token: str) -> dict:
    import requests
    try:
        r = requests.get(
            "https://api.bap.microsoft.com/providers/Microsoft.BusinessAppPlatform/environments",
            params={"api-version": "2020-10-01"},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        raw  = r.json()
        envs = []
        for item in raw.get("value", []):
            props = item.get("properties", {})
            url   = props.get("linkedEnvironmentMetadata", {}).get("instanceUrl", "")
            if url:
                envs.append({
                    "name":          props.get("displayName", item.get("name", "")),
                    "orgUrl":        url.rstrip("/"),
                    "environmentId": item.get("name", ""),
                })
        return {"ok": True, "envs": envs, "raw_count": len(raw.get("value", []))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _probe_bots(org_url: str, dv_token: str) -> dict:
    import requests
    try:
        r = requests.get(
            f"{org_url}/api/data/v9.2/bots",
            params={"$select": "botid,name,schemaname,statecode", "$filter": "statecode eq 0"},
            headers={"Authorization": f"Bearer {dv_token}", "OData-MaxVersion": "4.0",
                     "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        bots = r.json().get("value", [])
        return {"ok": True, "bots": bots}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _get_dv_token(org_url: str, client_id: str, tenant_id: str, cache_file: str) -> str | None:
    scopes = [org_url.rstrip("/") + "/.default"]
    return _get_token_silent(scopes, client_id, tenant_id, cache_file)


# ── Nav helpers ───────────────────────────────────────────────────────────────
def go_next():
    st.session_state.wiz_step = min(TOTAL_STEPS, st.session_state.wiz_step + 1)


def go_back():
    st.session_state.wiz_step = max(1, st.session_state.wiz_step - 1)


# ── RENDER ────────────────────────────────────────────────────────────────────
st.markdown(
    f"<h2 style='color:{C_CYAN};font-family:{FONT};letter-spacing:3px;margin-bottom:8px'>"
    f"⚡ SETUP WIZARD</h2>",
    unsafe_allow_html=True,
)

render_step_bar(step)

client_id  = st.session_state.wiz_client_id
tenant_id  = st.session_state.wiz_tenant_id
cache_file = st.session_state.wiz_cache_file


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — App Registration
# ═══════════════════════════════════════════════════════════════════════════════
if step == 1:
    st.markdown(f"<div class='section-card'>", unsafe_allow_html=True)
    st.markdown(f"<div style='color:{C_CYAN};font-weight:700;font-family:{FONT};"
                f"letter-spacing:1px;margin-bottom:16px'>STEP 1 — APP REGISTRATION</div>",
                unsafe_allow_html=True)
    st.caption("Azure AD app with CopilotStudio.MakerOperations delegated permission.")

    c1, c2 = st.columns(2)
    with c1:
        cid = st.text_input("Client (App) ID", value=st.session_state.wiz_client_id)
    with c2:
        tid = st.text_input("Tenant ID", value=st.session_state.wiz_tenant_id,
                            placeholder="8b7a11d9-6513-4d54-a468-f6630df73c8b")

    cache_f = st.text_input("Token cache path (on shared volume on Azure)",
                            value=st.session_state.wiz_cache_file)

    st.markdown("</div>", unsafe_allow_html=True)

    if st.button("Next →", type="primary", disabled=not (cid and tid)):
        st.session_state.wiz_client_id  = cid.strip()
        st.session_state.wiz_tenant_id  = tid.strip()
        st.session_state.wiz_cache_file = cache_f.strip() or cache_file
        go_next()
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Connect to Microsoft
# ═══════════════════════════════════════════════════════════════════════════════
elif step == 2:
    st.markdown(f"<div class='section-card'>", unsafe_allow_html=True)
    st.markdown(f"<div style='color:{C_CYAN};font-weight:700;font-family:{FONT};"
                f"letter-spacing:1px;margin-bottom:16px'>STEP 2 — CONNECT TO MICROSOFT</div>",
                unsafe_allow_html=True)

    # Try silent first
    existing = _get_token_silent(EVAL_SCOPES, client_id, tenant_id, cache_file)
    if existing and not st.session_state.get("wiz_force_reauth"):
        st.success("✓ Already authenticated — cached token found.")
        st.session_state.wiz_token = existing
        accs = msal.PublicClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=_load_cache(cache_file),
        ).get_accounts()
        st.session_state.wiz_account = accs[0].get("username", "unknown") if accs else "unknown"
        st.markdown("</div>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Back"):
                go_back(); st.rerun()
        with col2:
            if st.button("Next →", type="primary"):
                go_next(); st.rerun()
        if st.button("Re-authenticate", type="secondary"):
            st.session_state.wiz_force_reauth = True
            st.session_state.wiz_device_flow  = None
            st.session_state.wiz_flow_started  = False
            st.rerun()
    else:
        # Device flow
        if not st.session_state.wiz_flow_started:
            st.info("Click **Start Authentication** to open a Microsoft sign-in flow.")
            if st.button("Start Authentication", type="primary"):
                try:
                    flow, app, cache = _acquire_with_flow(
                        EVAL_SCOPES, client_id, tenant_id, cache_file
                    )
                    st.session_state.wiz_device_flow   = {
                        "flow": flow, "app": app, "cache": cache
                    }
                    st.session_state.wiz_flow_started   = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to start auth: {e}")
        else:
            flow_data = st.session_state.wiz_device_flow
            flow      = flow_data["flow"]
            code      = flow.get("user_code", "")

            st.markdown(
                f"<div style='margin-bottom:12px;color:{C_TEXT}'>"
                f"<b>1.</b> Open "
                f"<a href='https://microsoft.com/devicelogin' target='_blank' "
                f"style='color:{C_CYAN}'>microsoft.com/devicelogin</a> in your browser"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown(f"<b style='color:{C_TEXT}'>2.</b> Enter this code:", unsafe_allow_html=True)
            st.markdown(f"<div class='device-code'>{code}</div>", unsafe_allow_html=True)
            st.caption(f"Expires in {flow.get('expires_in', 900) // 60} minutes")

            # Show raw flow for diagnostics
            with st.expander("▸ Raw device flow response (diagnostics)"):
                safe_flow = {k: v for k, v in flow.items() if k != "access_token"}
                st.json(safe_flow)

            col1, col2 = st.columns(2)
            with col1:
                if st.button("← Back"):
                    st.session_state.wiz_flow_started = False
                    st.session_state.wiz_device_flow  = None
                    go_back(); st.rerun()
            with col2:
                if st.button("✓ I've authenticated — check status", type="primary"):
                    # Try silent acquire (non-blocking check)
                    token = _get_token_silent(EVAL_SCOPES, client_id, tenant_id, cache_file)
                    if token:
                        st.session_state.wiz_token         = token
                        st.session_state.wiz_flow_started  = False
                        st.session_state.wiz_device_flow   = None
                        st.session_state.wiz_force_reauth  = False
                        # Get account name
                        cache = _load_cache(cache_file)
                        app   = msal.PublicClientApplication(
                            client_id=client_id,
                            authority=f"https://login.microsoftonline.com/{tenant_id}",
                            token_cache=cache,
                        )
                        accs  = app.get_accounts()
                        # Try to complete the device flow to get token into cache
                        try:
                            r = app.acquire_token_by_device_flow(flow_data["flow"],
                                                                  exit_condition=lambda _: True)
                            if r and "access_token" in r:
                                st.session_state.wiz_token = r["access_token"]
                                _save_cache(app.token_cache, cache_file)
                                accs = app.get_accounts()
                        except Exception:
                            pass
                        st.session_state.wiz_account = accs[0].get("username","unknown") if accs else "unknown"
                        go_next(); st.rerun()
                    else:
                        # Try completing the blocking flow
                        try:
                            app   = flow_data["app"]
                            cache = flow_data["cache"]
                            result = app.acquire_token_by_device_flow(flow_data["flow"],
                                                                       exit_condition=lambda r: True)
                            if result and "access_token" in result:
                                _save_cache(app.token_cache, cache_file)
                                st.session_state.wiz_token    = result["access_token"]
                                st.session_state.wiz_account  = app.get_accounts()[0].get("username","?") if app.get_accounts() else "?"
                                st.session_state.wiz_flow_started = False
                                go_next(); st.rerun()
                            else:
                                st.warning("Not authenticated yet — complete sign-in in your browser first.")
                        except Exception as e:
                            st.warning(f"Waiting for authentication: {e}")

    st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Pick Environments
# ═══════════════════════════════════════════════════════════════════════════════
elif step == 3:
    st.markdown(f"<div class='section-card'>", unsafe_allow_html=True)
    st.markdown(f"<div style='color:{C_CYAN};font-weight:700;font-family:{FONT};"
                f"letter-spacing:1px;margin-bottom:16px'>STEP 3 — SELECT ENVIRONMENTS</div>",
                unsafe_allow_html=True)

    token = st.session_state.wiz_token
    if not token:
        st.error("No token — go back to Step 2 and authenticate.")
        if st.button("← Back"):
            go_back(); st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()

    if not st.session_state.wiz_envs:
        with st.spinner("Fetching environments from Power Platform BAPI…"):
            result = _probe_envs(token)

        if result["ok"]:
            st.session_state.wiz_envs = result["envs"]
        else:
            st.error(f"BAPI call failed: {result['error']}")
            with st.expander("▸ Diagnostics"):
                st.json(result)
            if st.button("← Back"):
                go_back(); st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            st.stop()

    envs = st.session_state.wiz_envs

    # Show raw API info
    with st.expander(f"▸ Raw BAPI response — {len(envs)} environments with Dataverse URL"):
        st.json(envs[:5])  # first 5 for diagnostics

    if not envs:
        st.warning("No environments with a Dataverse org URL found in your tenant.")
        if st.button("← Back"):
            go_back(); st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()

    st.caption(f"Found {len(envs)} environment(s). Select the ones to monitor:")
    sel_names = st.multiselect(
        "Environments to monitor",
        options=[e["name"] for e in envs],
        default=st.session_state.wiz_selected_envs or [e["name"] for e in envs[:1]],
    )

    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            go_back(); st.rerun()
    with col2:
        if st.button("Next →", type="primary", disabled=not sel_names):
            st.session_state.wiz_selected_envs = sel_names
            st.session_state.wiz_bots = {}
            go_next(); st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Pick Bots
# ═══════════════════════════════════════════════════════════════════════════════
elif step == 4:
    st.markdown(f"<div class='section-card'>", unsafe_allow_html=True)
    st.markdown(f"<div style='color:{C_CYAN};font-weight:700;font-family:{FONT};"
                f"letter-spacing:1px;margin-bottom:16px'>STEP 4 — SELECT BOTS</div>",
                unsafe_allow_html=True)

    token    = st.session_state.wiz_token
    sel_envs = st.session_state.wiz_selected_envs
    all_envs = {e["name"]: e for e in st.session_state.wiz_envs}

    bot_sel  = dict(st.session_state.wiz_bot_sel)

    for env_name in sel_envs:
        env = all_envs.get(env_name)
        if not env:
            continue

        st.markdown(
            f"<div style='font-weight:700;color:{C_MAGENTA};font-family:{FONT};"
            f"margin-bottom:8px;margin-top:14px'>{env_name}</div>",
            unsafe_allow_html=True,
        )

        # Fetch bots if not cached
        if env_name not in st.session_state.wiz_bots:
            with st.spinner(f"Fetching bots from {env_name}…"):
                dv_token = _get_dv_token(env["orgUrl"], client_id, tenant_id, cache_file)
                if not dv_token:
                    # Try BAPI token as fallback probe
                    result = {"ok": False, "error": "Could not acquire Dataverse token silently — try re-authenticating."}
                else:
                    result = _probe_bots(env["orgUrl"], dv_token)

            st.session_state.wiz_bots[env_name] = result

        result = st.session_state.wiz_bots[env_name]

        # Show raw response for diagnostics
        with st.expander(f"▸ Raw Dataverse /bots response — {env_name}"):
            st.json(result)

        if not result.get("ok"):
            st.error(f"Failed to fetch bots: {result.get('error')}")
            continue

        bots = result.get("bots", [])
        if not bots:
            st.caption("No active bots in this environment — all future bots will be monitored.")
            bot_sel[env_name] = []
            continue

        options  = [b["name"] for b in bots]
        schemas  = {b["name"]: b["schemaname"] for b in bots}
        current  = bot_sel.get(env_name, options)
        selected = st.multiselect(
            f"Bots to monitor ({env_name})",
            options=options,
            default=current,
            key=f"bots_{env_name}",
        )
        bot_sel[env_name] = [schemas[n] for n in selected]

    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            go_back(); st.rerun()
    with col2:
        if st.button("Next →", type="primary"):
            st.session_state.wiz_bot_sel = bot_sel
            go_next(); st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5 — LLM Settings
# ═══════════════════════════════════════════════════════════════════════════════
elif step == 5:
    st.markdown(f"<div class='section-card'>", unsafe_allow_html=True)
    st.markdown(f"<div style='color:{C_CYAN};font-weight:700;font-family:{FONT};"
                f"letter-spacing:1px;margin-bottom:16px'>STEP 5 — LLM SETTINGS</div>",
                unsafe_allow_html=True)
    st.caption("Used for drift analysis narration. API key is set via environment variable.")

    # Load existing config for defaults
    existing = {}
    try:
        existing = json.loads(open(CONFIG_PATH).read()).get("llm", {})
    except Exception:
        pass

    c1, c2 = st.columns(2)
    with c1:
        url   = st.text_input("LLM Base URL",
                              value=st.session_state.wiz_llm_url or existing.get("base_url", ""))
        model = st.text_input("Model name",
                              value=st.session_state.wiz_llm_model or existing.get("model", "gpt-4o"))
    with c2:
        poll  = st.number_input("Poll interval (minutes)", min_value=1, max_value=1440,
                                value=st.session_state.wiz_poll)

    st.markdown(
        f"<div style='background:{C_BG};border:1px solid {C_BORDER};border-radius:6px;"
        f"padding:12px 16px;margin-top:12px;font-size:0.75rem;color:{C_DIM}'>"
        f"<span style='color:{C_GOLD};font-weight:700'>LLM_API_KEY</span> — set this as an "
        f"environment variable on your container. Not stored in config.json.</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            go_back(); st.rerun()
    with col2:
        if st.button("Next →", type="primary"):
            st.session_state.wiz_llm_url   = url.strip()
            st.session_state.wiz_llm_model = model.strip()
            st.session_state.wiz_poll      = int(poll)
            go_next(); st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6 — Notifications
# ═══════════════════════════════════════════════════════════════════════════════
elif step == 6:
    st.markdown(f"<div class='section-card'>", unsafe_allow_html=True)
    st.markdown(f"<div style='color:{C_CYAN};font-weight:700;font-family:{FONT};"
                f"letter-spacing:1px;margin-bottom:16px'>STEP 6 — NOTIFICATIONS (SMTP)</div>",
                unsafe_allow_html=True)
    st.caption("Leave blank to skip email reports. Configure later in config.json.")

    existing_smtp = {}
    try:
        existing_smtp = json.loads(open(CONFIG_PATH).read()).get("smtp", {})
    except Exception:
        pass

    c1, c2 = st.columns(2)
    with c1:
        host = st.text_input("SMTP host", value=st.session_state.wiz_smtp_host or existing_smtp.get("host", ""))
        user = st.text_input("Sender email", value=st.session_state.wiz_smtp_user or existing_smtp.get("user", ""))
    with c2:
        port = st.number_input("SMTP port", min_value=1, max_value=65535,
                               value=st.session_state.wiz_smtp_port)
        rcpt = st.text_input("Recipient email", value=st.session_state.wiz_smtp_rcpt or existing_smtp.get("recipient", ""))

    st.markdown(
        f"<div style='background:{C_BG};border:1px solid {C_BORDER};border-radius:6px;"
        f"padding:12px 16px;margin-top:12px;font-size:0.75rem;color:{C_DIM}'>"
        f"<span style='color:{C_GOLD};font-weight:700'>SMTP_PASSWORD</span> — set as "
        f"environment variable. Not stored in config.json.</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            go_back(); st.rerun()
    with col2:
        if st.button("Next →", type="primary"):
            st.session_state.wiz_smtp_host = host.strip()
            st.session_state.wiz_smtp_port = int(port)
            st.session_state.wiz_smtp_user = user.strip()
            st.session_state.wiz_smtp_rcpt = rcpt.strip()
            go_next(); st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7 — Review + Save
# ═══════════════════════════════════════════════════════════════════════════════
elif step == 7:
    st.markdown(f"<div class='section-card'>", unsafe_allow_html=True)
    st.markdown(f"<div style='color:{C_CYAN};font-weight:700;font-family:{FONT};"
                f"letter-spacing:1px;margin-bottom:16px'>STEP 7 — REVIEW & SAVE</div>",
                unsafe_allow_html=True)

    # Build environments list
    all_envs = {e["name"]: e for e in st.session_state.wiz_envs}
    bot_sel  = st.session_state.wiz_bot_sel
    envs_cfg = []
    for env_name in st.session_state.wiz_selected_envs:
        env = all_envs.get(env_name, {})
        if not env:
            continue
        envs_cfg.append({
            "name":          env_name,
            "orgUrl":        env.get("orgUrl", ""),
            "environmentId": env.get("environmentId", ""),
            "monitoredBots": bot_sel.get(env_name, []),
        })

    cfg = {
        "environments":             envs_cfg,
        "eval_app_client_id":       st.session_state.wiz_client_id,
        "eval_app_tenant_id":       st.session_state.wiz_tenant_id,
        "token_cache_file":         st.session_state.wiz_cache_file,
        "store_dir":                STORE_DIR,
        "poll_interval_minutes":    st.session_state.wiz_poll,
        "eval_poll_timeout_seconds": 1200,
        "eval_poll_interval_seconds": 20,
        "llm": {
            "base_url": st.session_state.wiz_llm_url,
            "api_key":  "",
            "model":    st.session_state.wiz_llm_model,
        },
        "smtp": {
            "host":      st.session_state.wiz_smtp_host,
            "port":      st.session_state.wiz_smtp_port,
            "user":      st.session_state.wiz_smtp_user,
            "password":  "",
            "recipient": st.session_state.wiz_smtp_rcpt,
        },
    }

    st.json(cfg)

    st.markdown(
        f"<div style='background:{C_BG};border:1px solid {C_GOLD};border-radius:6px;"
        f"padding:12px 16px;margin-top:12px;font-size:0.75rem;color:{C_DIM}'>"
        f"Secrets not in this file: "
        f"<span style='color:{C_GOLD};font-weight:700'>LLM_API_KEY  SMTP_PASSWORD</span> "
        f"— set as container environment variables.</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            go_back(); st.rerun()
    with col2:
        if st.button("💾 Save config.json", type="primary"):
            try:
                open(CONFIG_PATH, "w").write(json.dumps(cfg, indent=2))
                st.success(
                    f"✓ config.json saved. Agent will pick up the new configuration on its next poll cycle."
                )
                st.markdown(
                    f"<div style='color:{C_GREEN};font-family:{FONT};font-size:0.8rem;"
                    f"margin-top:8px'>ALL SYSTEMS GO ⚡</div>",
                    unsafe_allow_html=True,
                )
                # Reset wizard state
                st.session_state.wiz_step = 1
                for k in list(st.session_state.keys()):
                    if k.startswith("wiz_"):
                        del st.session_state[k]
            except Exception as e:
                st.error(f"Failed to save: {e}")
