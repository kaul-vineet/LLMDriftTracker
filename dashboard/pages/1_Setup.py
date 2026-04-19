"""
dashboard/pages/1_Setup.py — Single-screen configuration.
All parameters on one page. Authenticate → load envs → pick bots → save.
"""
import json
import msal
import os

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from theme import C_BG, C_CARD, C_BORDER, C_CYAN, C_MAGENTA, C_GOLD, C_RED, C_GREEN, C_DIM, C_TEXT, FONT

EVAL_SCOPES = ["https://api.powerplatform.com/.default"]
STORE_DIR   = os.environ.get("STORE_DIR", "data")
CONFIG_PATH = "config.json"
DEFAULT_CLIENT_ID = "774142ce-9070-446b-83ac-e2053c716879"

st.markdown(f"""
<style>
  .cfg-section {{
    border-radius:10px; padding:20px 24px; margin-bottom:18px;
    border:1px solid {C_BORDER}; background:{C_CARD};
  }}
  .cfg-section.ok  {{ border-color:rgba(40,200,64,.4); }}
  .cfg-section.err {{ border-color:rgba(255,68,68,.4); }}
  .cfg-head {{
    font-size:0.85rem; font-weight:700; letter-spacing:2px;
    font-family:{FONT}; text-transform:uppercase; margin-bottom:16px;
    border-bottom:1px solid {C_BORDER}; padding-bottom:8px;
  }}
  .device-code {{
    font-size:2.2rem; font-weight:700; letter-spacing:8px;
    color:{C_CYAN}; font-family:{FONT}; text-align:center;
    padding:18px; background:{C_BG}; border-radius:8px;
    border:1px solid {C_CYAN}; margin:12px 0;
    box-shadow:0 0 20px rgba(0,240,255,.15);
  }}
  .status-ok  {{ color:{C_GREEN}; font-size:0.78rem; font-weight:700; font-family:{FONT}; }}
  .status-err {{ color:{C_RED};   font-size:0.78rem; font-weight:700; font-family:{FONT}; }}
  .status-dim {{ color:{C_DIM};   font-size:0.78rem; font-family:{FONT}; }}
</style>
""", unsafe_allow_html=True)


def _sec(title, ok: bool | None = None):
    """Render a section opening div with coloured border + ✓/✗ in the heading."""
    if ok is True:
        border = "ok";  sym = f"<span style='color:{C_GREEN}'>✓</span>"
    elif ok is False:
        border = "err"; sym = f"<span style='color:{C_RED}'>✗</span>"
    else:
        border = "";    sym = f"<span style='color:{C_DIM}'>·</span>"
    st.markdown(
        f"<div class='cfg-section {border}'>"
        f"<div class='cfg-head'>{sym}&nbsp; {title}</div>",
        unsafe_allow_html=True,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────
def _load_cache(path):
    c = msal.SerializableTokenCache()
    if os.path.exists(path):
        c.deserialize(open(path).read())
    return c

def _save_cache(c, path):
    if c.has_state_changed:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        open(path, "w").write(c.serialize())

def _msal_app(client_id, tenant_id, cache):
    return msal.PublicClientApplication(
        client_id, authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=cache,
    )

def _cache_accounts(client_id, tenant_id, cache_file):
    """Local-only check — no network call. Returns list of accounts in cache."""
    try:
        cache = _load_cache(cache_file)
        app   = _msal_app(client_id, tenant_id, cache)
        return app.get_accounts()
    except Exception:
        return []

def _token_silent(scopes, client_id, tenant_id, cache_file):
    """Full silent acquisition — may make a network call to refresh the token."""
    cache = _load_cache(cache_file)
    app   = _msal_app(client_id, tenant_id, cache)
    accs  = app.get_accounts()
    if accs:
        r = app.acquire_token_silent(scopes, account=accs[0])
        if r and "access_token" in r:
            _save_cache(cache, cache_file)
            return r["access_token"], app.get_accounts()
    return None, []

def _fetch_envs(token):
    import requests
    try:
        r = requests.get(
            "https://api.bap.microsoft.com/providers/Microsoft.BusinessAppPlatform/environments",
            params={"api-version": "2020-10-01"},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        envs = []
        for item in r.json().get("value", []):
            props = item.get("properties", {})
            url   = props.get("linkedEnvironmentMetadata", {}).get("instanceUrl", "")
            if url:
                envs.append({
                    "name":          props.get("displayName", item.get("name", "")),
                    "orgUrl":        url.rstrip("/"),
                    "environmentId": item.get("name", ""),
                })
        return envs, None
    except Exception as e:
        return [], str(e)

def _test_llm(base_url, model, api_key):
    import requests
    try:
        r = requests.post(
            base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
            timeout=10,
        )
        r.raise_for_status()
        return True, None
    except Exception as e:
        return False, str(e)


def _llm_status_path():
    return os.path.join(STORE_DIR, "llm_status.json")


def _llm_validated():
    try:
        ls = json.loads(open(_llm_status_path()).read())
        return ls.get("ok", False)
    except Exception:
        return False


def _fetch_bots(org_url, client_id, tenant_id, cache_file):
    import requests
    scopes = [org_url.rstrip("/") + "/.default"]
    token, _ = _token_silent(scopes, client_id, tenant_id, cache_file)
    if not token:
        return [], "Could not acquire Dataverse token — try re-authenticating."
    try:
        r = requests.get(
            f"{org_url}/api/data/v9.2/bots",
            params={"$select": "botid,name,schemaname,statecode", "$filter": "statecode eq 0"},
            headers={"Authorization": f"Bearer {token}", "OData-MaxVersion": "4.0",
                     "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("value", []), None
    except Exception as e:
        return [], str(e)


# ── Load existing config ──────────────────────────────────────────────────────
_cfg = {}
try:
    _cfg = json.loads(open(CONFIG_PATH).read())
except Exception:
    pass

_llm  = _cfg.get("llm", {})
_smtp = _cfg.get("smtp", {})
_envs_cfg = _cfg.get("environments", [])

# ── Session defaults ──────────────────────────────────────────────────────────
_defs = {
    "s_client_id":     _cfg.get("eval_app_client_id", DEFAULT_CLIENT_ID),
    "s_tenant_id":     _cfg.get("eval_app_tenant_id", ""),
    "s_cache_file":    _cfg.get("token_cache_file", os.path.join(STORE_DIR, "msal_cache.json")),
    "s_token":         None,
    "s_account":       "",
    "s_flow":          None,
    "s_flow_started":  False,
    "s_envs":          [],
    "s_sel_envs":      [e["name"] for e in _envs_cfg],
    "s_bots":          {},
    "s_bot_sel":       {e["name"]: e.get("monitoredBots", []) for e in _envs_cfg},
    "s_llm_url":       _llm.get("base_url", ""),
    "s_llm_model":     _llm.get("model", "gpt-4o"),
    "s_poll":          _cfg.get("poll_interval_minutes", 20),
    "s_smtp_host":     _smtp.get("host", ""),
    "s_smtp_port":     _smtp.get("port", 587),
    "s_smtp_user":     _smtp.get("user", ""),
    "s_smtp_rcpt":     _smtp.get("recipient", ""),
}
for k, v in _defs.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Section completion status (computed once before any rendering) ─────────────
def _sec_status():
    s1 = bool(st.session_state.s_client_id and st.session_state.s_tenant_id)
    s2 = bool(_cache_accounts(
        st.session_state.s_client_id,
        st.session_state.s_tenant_id,
        st.session_state.s_cache_file,
    ))
    s3 = bool(st.session_state.s_sel_envs)
    s4 = True  # empty bot list = monitor all, always valid
    s5 = bool(st.session_state.s_llm_url) and _llm_validated()
    return s1, s2, s3, s4, s5

ok1, ok2, ok3, ok4, ok5 = _sec_status()


# ── Page header ───────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='font-size:1.4rem;font-weight:700;letter-spacing:4px;"
    f"color:{C_CYAN};font-family:{FONT};margin-bottom:4px'>⚡ SETUP</div>"
    f"<div style='font-size:0.78rem;color:{C_DIM};margin-bottom:24px'>"
    f"Fill all required fields and click Save at the bottom.</div>",
    unsafe_allow_html=True,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — App Registration
# ═══════════════════════════════════════════════════════════════════════════════
_sec("1 · App Registration", ok1)
st.caption("Azure AD app with CopilotStudio.MakerOperations delegated permission.")

c1, c2 = st.columns(2)
with c1:
    client_id = st.text_input("Client (App) ID *", value=st.session_state.s_client_id,
                               key="in_client_id")
with c2:
    tenant_id = st.text_input("Tenant ID *", value=st.session_state.s_tenant_id,
                               placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                               key="in_tenant_id")
cache_file = st.text_input("Token cache path", value=st.session_state.s_cache_file,
                            key="in_cache_file")
st.markdown("</div>", unsafe_allow_html=True)

# Persist immediately
st.session_state.s_client_id  = client_id.strip()
st.session_state.s_tenant_id  = tenant_id.strip()
st.session_state.s_cache_file = cache_file.strip() or st.session_state.s_cache_file


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Authentication
# ═══════════════════════════════════════════════════════════════════════════════
_sec("2 · Authentication", ok2)

_can_auth = bool(st.session_state.s_client_id and st.session_state.s_tenant_id)

if not _can_auth:
    st.markdown("<div class='status-dim'>Enter Client ID and Tenant ID above first.</div>",
                unsafe_allow_html=True)
else:
    # Local cache check only — consistent with sidebar, no network call
    _cached_accs = _cache_accounts(
        st.session_state.s_client_id,
        st.session_state.s_tenant_id,
        st.session_state.s_cache_file,
    )
    _has_cache = bool(_cached_accs) and not st.session_state.get("s_force_reauth")

    if _has_cache:
        _cached_user = _cached_accs[0].get("username", "—")
        st.session_state.s_account = _cached_user
        st.markdown(
            f"<div class='status-ok'>● TOKEN VALID — {_cached_user}</div>",
            unsafe_allow_html=True,
        )
        if st.button("Re-authenticate", key="btn_reauth", type="secondary"):
            st.session_state.s_force_reauth = True
            st.session_state.s_flow = None
            st.session_state.s_flow_started = False
            st.rerun()
    else:
        if not st.session_state.s_flow_started:
            st.markdown("<div class='status-dim'>Not authenticated.</div>", unsafe_allow_html=True)
            if st.button("Sign In (device flow)", key="btn_signin", type="primary"):
                try:
                    cache = _load_cache(st.session_state.s_cache_file)
                    app   = _msal_app(st.session_state.s_client_id,
                                      st.session_state.s_tenant_id, cache)
                    flow  = app.initiate_device_flow(scopes=EVAL_SCOPES)
                    st.session_state.s_flow         = {"flow": flow, "app": app, "cache": cache}
                    st.session_state.s_flow_started = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to start sign-in: {e}")
        else:
            flow_data = st.session_state.s_flow
            code      = flow_data["flow"].get("user_code", "")
            st.markdown(
                f"Open <a href='https://microsoft.com/devicelogin' target='_blank' "
                f"style='color:{C_CYAN}'>microsoft.com/devicelogin</a> and enter:",
                unsafe_allow_html=True,
            )
            st.markdown(f"<div class='device-code'>{code}</div>", unsafe_allow_html=True)
            st.caption(f"Expires in {flow_data['flow'].get('expires_in', 900) // 60} min")

            if st.button("✓ I've signed in — verify", key="btn_verify", type="primary"):
                app   = flow_data["app"]
                cache = flow_data["cache"]
                try:
                    result = app.acquire_token_by_device_flow(
                        flow_data["flow"], exit_condition=lambda _: True
                    )
                except Exception:
                    result = None
                if result and "access_token" in result:
                    _save_cache(app.token_cache, st.session_state.s_cache_file)
                    accs = app.get_accounts()
                    st.session_state.s_token        = result["access_token"]
                    st.session_state.s_account      = accs[0].get("username","—") if accs else "—"
                    st.session_state.s_flow_started = False
                    st.session_state.s_flow         = None
                    st.session_state.s_force_reauth = False
                    st.rerun()
                else:
                    # Silent fallback
                    tok, accs = _token_silent(
                        EVAL_SCOPES, st.session_state.s_client_id,
                        st.session_state.s_tenant_id, st.session_state.s_cache_file,
                    )
                    if tok:
                        st.session_state.s_token        = tok
                        st.session_state.s_account      = accs[0].get("username","—") if accs else "—"
                        st.session_state.s_flow_started = False
                        st.session_state.s_force_reauth = False
                        st.rerun()
                    else:
                        st.warning("Not signed in yet — complete sign-in in your browser first.")

st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Environments
# ═══════════════════════════════════════════════════════════════════════════════
_sec("3 · Environments", ok3)

if not _can_auth:
    st.markdown("<div class='status-dim'>Enter Client ID and Tenant ID above first.</div>",
                unsafe_allow_html=True)
else:
    col_e1, col_e2 = st.columns([1, 4])
    with col_e1:
        if st.button("Load Environments", key="btn_load_envs"):
            with st.spinner("Acquiring token…"):
                tok, _ = _token_silent(
                    EVAL_SCOPES, st.session_state.s_client_id,
                    st.session_state.s_tenant_id, st.session_state.s_cache_file,
                )
            if not tok:
                st.error("Token acquisition failed — sign in first (Section 2).")
            else:
                st.session_state.s_token = tok
                with st.spinner("Fetching from Power Platform BAPI…"):
                    envs, err = _fetch_envs(tok)
                if err:
                    st.error(f"BAPI error: {err}")
                else:
                    st.session_state.s_envs = envs
    with col_e2:
        if st.session_state.s_envs:
            st.caption(f"{len(st.session_state.s_envs)} environment(s) found")

    if st.session_state.s_envs:
        sel = st.multiselect(
            "Environments to monitor",
            options=[e["name"] for e in st.session_state.s_envs],
            default=[n for n in st.session_state.s_sel_envs
                     if n in [e["name"] for e in st.session_state.s_envs]],
            key="ms_envs",
        )
        st.session_state.s_sel_envs = sel

st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Bots
# ═══════════════════════════════════════════════════════════════════════════════
_sec("4 · Bots to Monitor", ok4)

if not st.session_state.s_sel_envs:
    st.markdown("<div class='status-dim'>Select at least one environment above.</div>",
                unsafe_allow_html=True)
else:
    env_map = {e["name"]: e for e in st.session_state.s_envs}
    bot_sel = dict(st.session_state.s_bot_sel)

    for env_name in st.session_state.s_sel_envs:
        env = env_map.get(env_name)
        st.markdown(
            f"<div style='color:{C_MAGENTA};font-weight:700;font-family:{FONT};"
            f"font-size:0.85rem;margin:14px 0 6px'>{env_name}</div>",
            unsafe_allow_html=True,
        )
        if env:
            col_b1, col_b2 = st.columns([1, 4])
            with col_b1:
                if st.button("Load Bots", key=f"btn_bots_{env_name}"):
                    with st.spinner(f"Fetching bots from {env_name}…"):
                        bots, err = _fetch_bots(
                            env["orgUrl"], st.session_state.s_client_id,
                            st.session_state.s_tenant_id, st.session_state.s_cache_file,
                        )
                    if err:
                        st.error(f"{err}")
                    else:
                        st.session_state.s_bots[env_name] = bots
            with col_b2:
                nb = len(st.session_state.s_bots.get(env_name, []))
                if nb:
                    st.caption(f"{nb} bot(s) found")

            bots_raw = st.session_state.s_bots.get(env_name, [])
            if bots_raw:
                names   = [b["name"] for b in bots_raw]
                schemas = {b["name"]: b["schemaname"] for b in bots_raw}
                cur_schemas = bot_sel.get(env_name, [])
                cur_names   = [b["name"] for b in bots_raw if b["schemaname"] in cur_schemas]
                sel_names   = st.multiselect(
                    f"Bots ({env_name}) — leave empty to monitor all",
                    options=names,
                    default=cur_names or names,
                    key=f"ms_bots_{env_name}",
                )
                bot_sel[env_name] = [schemas[n] for n in sel_names]
        else:
            # env came from existing config, not freshly loaded
            cur = bot_sel.get(env_name, [])
            st.caption(f"Existing config: {len(cur)} bot(s) selected. Load bots to change.")

    st.session_state.s_bot_sel = bot_sel

st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — LLM
# ═══════════════════════════════════════════════════════════════════════════════
_sec("5 · LLM (Drift Analysis)", ok5)
st.caption("Any OpenAI-compatible endpoint. API key goes in .env as LLM_API_KEY.")

c1, c2, c3 = st.columns([3, 2, 1])
with c1:
    llm_url   = st.text_input("Base URL", value=st.session_state.s_llm_url, key="in_llm_url",
                               placeholder="https://api.openai.com/v1")
with c2:
    llm_model = st.text_input("Model", value=st.session_state.s_llm_model, key="in_llm_model")
with c3:
    poll      = st.number_input("Poll (min)", min_value=1, max_value=1440,
                                 value=int(st.session_state.s_poll), key="in_poll")

st.session_state.s_llm_url   = llm_url.strip()
st.session_state.s_llm_model = llm_model.strip()
st.session_state.s_poll      = int(poll)

# LLM validation
_api_key = os.environ.get("LLM_API_KEY", "")
col_t1, col_t2 = st.columns([1, 4])
with col_t1:
    if st.button("Test LLM", key="btn_test_llm", disabled=not llm_url.strip()):
        with st.spinner("Calling LLM…"):
            ok, err = _test_llm(llm_url.strip(), llm_model.strip(), _api_key)
        os.makedirs(STORE_DIR, exist_ok=True)
        import json as _json
        open(_llm_status_path(), "w").write(_json.dumps({"ok": ok, "error": err or ""}))
        st.rerun()
with col_t2:
    if _llm_validated():
        st.markdown(f"<div class='status-ok'>✓ LLM responded</div>", unsafe_allow_html=True)
    elif os.path.exists(_llm_status_path()):
        try:
            _ls = json.loads(open(_llm_status_path()).read())
            st.markdown(f"<div class='status-err'>✗ {_ls.get('error','failed')}</div>",
                        unsafe_allow_html=True)
        except Exception:
            pass
    elif llm_url.strip():
        st.markdown(f"<div class='status-dim'>· Not tested yet</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Notifications (optional)
# ═══════════════════════════════════════════════════════════════════════════════
with st.expander("6 · Notifications (SMTP) — optional"):
    st.caption("Leave blank to disable email reports. SMTP_PASSWORD goes in .env.")
    c1, c2 = st.columns(2)
    with c1:
        smtp_host = st.text_input("SMTP host", value=st.session_state.s_smtp_host,
                                   placeholder="smtp.office365.com", key="in_smtp_host")
        smtp_user = st.text_input("Sender email", value=st.session_state.s_smtp_user,
                                   key="in_smtp_user")
    with c2:
        smtp_port = st.number_input("SMTP port", min_value=1, max_value=65535,
                                     value=int(st.session_state.s_smtp_port), key="in_smtp_port")
        smtp_rcpt = st.text_input("Recipient email", value=st.session_state.s_smtp_rcpt,
                                   key="in_smtp_rcpt")
    st.session_state.s_smtp_host = smtp_host.strip()
    st.session_state.s_smtp_port = int(smtp_port)
    st.session_state.s_smtp_user = smtp_user.strip()
    st.session_state.s_smtp_rcpt = smtp_rcpt.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — Save
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
st.divider()

_ready = bool(st.session_state.s_client_id and st.session_state.s_tenant_id)

# Build config preview
all_envs_map = {e["name"]: e for e in st.session_state.s_envs}
envs_cfg = []
for env_name in st.session_state.s_sel_envs:
    env = all_envs_map.get(env_name)
    if env:
        envs_cfg.append({
            "name":          env_name,
            "orgUrl":        env["orgUrl"],
            "environmentId": env.get("environmentId", ""),
            "monitoredBots": st.session_state.s_bot_sel.get(env_name, []),
        })
    else:
        # Keep existing config entry if env wasn't reloaded
        for e in _envs_cfg:
            if e["name"] == env_name:
                envs_cfg.append(e)
                break

cfg_out = {
    "environments":               envs_cfg,
    "eval_app_client_id":         st.session_state.s_client_id,
    "eval_app_tenant_id":         st.session_state.s_tenant_id,
    "token_cache_file":           st.session_state.s_cache_file,
    "store_dir":                  STORE_DIR,
    "poll_interval_minutes":      st.session_state.s_poll,
    "eval_poll_timeout_seconds":  1200,
    "eval_poll_interval_seconds": 20,
    "llm": {
        "base_url": st.session_state.s_llm_url,
        "api_key":  "",
        "model":    st.session_state.s_llm_model,
    },
    "smtp": {
        "host":      st.session_state.s_smtp_host,
        "port":      st.session_state.s_smtp_port,
        "user":      st.session_state.s_smtp_user,
        "password":  "",
        "recipient": st.session_state.s_smtp_rcpt,
    },
}

with st.expander("Preview config.json"):
    st.json(cfg_out)

col_s1, col_s2 = st.columns([3, 1])
with col_s2:
    if st.button("💾 Save config.json", type="primary", disabled=not _ready,
                 use_container_width=True):
        try:
            open(CONFIG_PATH, "w").write(json.dumps(cfg_out, indent=2))
            st.success("✓ config.json saved. Agent picks up changes on next poll cycle.")
            st.markdown(
                f"<div style='color:{C_GREEN};font-family:{FONT};font-size:0.85rem;"
                f"margin-top:6px;letter-spacing:2px'>ALL SYSTEMS GO ⚡</div>",
                unsafe_allow_html=True,
            )
        except Exception as e:
            st.error(f"Failed to save: {e}")

if not _ready:
    st.caption("⚠ Client ID and Tenant ID are required to save.")
