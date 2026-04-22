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
ENV_SCOPES  = ["https://api.powerplatform.com/EnvironmentManagement.Environments.Read"]
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
    # Maps ok state to CSS class (ok/err) and status symbol (✓/✗/·)
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






def _fetch_bots_inventory(env_id, token):
    """List Copilot Studio agents via Power Platform Inventory API.
    Same EVAL token as environment discovery — no Dataverse needed.
    env_id must be lowercased; inventory API filter is case-sensitive."""
    import requests
    try:
        r = requests.post(
            "https://api.powerplatform.com/resourcequery/resources/query",
            params={"api-version": "2024-10-01"},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "Accept": "application/json"},
            json={"TableName": "PowerPlatformResources",
                  "Clauses": [
                      {"$type": "where", "FieldName": "type",
                       "Operator": "==", "Values": ["'microsoft.copilotstudio/agents'"]},
                      {"$type": "where", "FieldName": "properties.environmentId",
                       "Operator": "==", "Values": [f"'{env_id.lower()}'"]}
                  ]},
            timeout=15,
        )
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}: {r.text[:300]}"
        bots = []
        for item in r.json().get("data", []):
            p = item.get("properties", {})
            bots.append({
                "botId":      item.get("name", ""),
                "name":       p.get("displayName", ""),
                "schemaname": p.get("schemaName", ""),
                "statecode":  0,
            })
        return bots, None
    except Exception as e:
        return [], str(e)


def _fetch_envs(token):
    import requests
    try:
        r = requests.get(
            "https://api.powerplatform.com/environmentmanagement/environments",
            params={"api-version": "2022-03-01-preview"},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}: {r.text[:300]}"
        envs = []
        for item in r.json().get("value", []):
            org_url = item.get("url", "")
            name    = item.get("displayName") or item.get("name") or ""
            env_id  = item.get("id", "")
            if org_url and name:
                envs.append({"name": name, "orgUrl": org_url.rstrip("/"), "environmentId": env_id})
        return envs, None
    except Exception as e:
        return [], str(e)


def _test_llm(base_url, model, api_key, api_version=""):
    import requests
    try:
        params = {"api-version": api_version} if api_version.strip() else {}
        r = requests.post(
            base_url.rstrip("/") + "/chat/completions",
            params=params,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
            timeout=10,
        )
        r.raise_for_status()
        return True, None
    except Exception as e:
        return False, str(e)


def _llm_status_path():
    return os.path.join(STORE_DIR, "agent", "llm_status.json")


def _llm_validated():
    try:
        ls = json.loads(open(_llm_status_path()).read())
        return ls.get("ok", False)
    except Exception:
        return False




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
    "s_cache_file":    _cfg.get("token_cache_file", os.path.join(STORE_DIR, "agent", "msal_token_cache.json")),
    "s_token":         None,
    "s_account":       "",
    "s_flow":          None,
    "s_flow_started":  False,
    "s_envs":          list(_envs_cfg),
    "s_sel_envs":      [e["name"] for e in _envs_cfg],
    "s_bots":          {},
    "s_bot_sel":       {e["name"]: e.get("monitoredBots", []) for e in _envs_cfg},
    "s_env_verified":  {},
    "s_bot_verified":  {},
    "s_llm_url":        _llm.get("base_url", ""),
    "s_llm_model":      _llm.get("model", "gpt-4o"),
    "s_llm_api_ver":    _llm.get("api_version", ""),
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
    # Auth is valid only if cache has accounts AND user hasn't clicked Re-authenticate
    s2 = bool(_cache_accounts(
        st.session_state.s_client_id,
        st.session_state.s_tenant_id,
        st.session_state.s_cache_file,
    )) and not st.session_state.get("s_force_reauth")
    s3 = s2 and bool(st.session_state.s_sel_envs)  # environments only meaningful when auth is valid
    s4 = True  # empty bot list = monitor all, always valid
    s5 = bool(st.session_state.s_llm_url) and _llm_validated()  # URL alone isn't enough; test must pass
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
st.caption("The Entra ID (Azure AD) app registration used to authenticate with Power Platform.")

c1, c2 = st.columns(2)
with c1:
    client_id = st.text_input("Client (App) ID *", value=st.session_state.s_client_id,
                               key="in_client_id",
                               help="The Application (client) ID of your Entra app registration. "
                                    "Must have CopilotStudio.MakerOperations.Read and "
                                    "EnvironmentManagement.Environments.Read delegated permissions.")
with c2:
    tenant_id = st.text_input("Tenant ID *", value=st.session_state.s_tenant_id,
                               placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                               key="in_tenant_id",
                               help="Your Microsoft Entra tenant ID. "
                                    "Found in Entra ID → Overview → Directory (tenant) ID.")
st.markdown("</div>", unsafe_allow_html=True)

# Persist immediately
st.session_state.s_client_id  = client_id.strip()
st.session_state.s_tenant_id  = tenant_id.strip()


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
        if st.button("Switch Account", key="btn_reauth", type="secondary"):
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
    _loading_envs = st.session_state.get("_op_loading_envs", False)
    col_e1, col_e2 = st.columns([1, 4])
    with col_e1:
        if st.button("Load Environments", key="btn_load_envs", disabled=_loading_envs):
            st.session_state["_op_loading_envs"] = True
            st.rerun()
    with col_e2:
        if st.session_state.s_envs:
            st.markdown(
                f"<div style='color:{C_CYAN};font-family:{FONT};font-size:0.78rem;"
                f"font-weight:700;letter-spacing:1px;margin-top:8px'>"
                f"✓ {len(st.session_state.s_envs)} environment(s) found</div>",
                unsafe_allow_html=True,
            )

    if _loading_envs:
        with st.spinner("Scanning environments…"):
            # Use explicit ENV_SCOPES so MSAL picks the token that contains
            # EnvironmentManagement.Environments.Read, not the older CopilotStudio-only token.
            tok, tok_err = _token_silent(ENV_SCOPES, st.session_state.s_client_id,
                                         st.session_state.s_tenant_id, st.session_state.s_cache_file)
            if not tok:
                st.session_state["_env_load_err"] = tok_err or "Token acquisition failed — sign in first (Section 2)."
            else:
                envs, err = _fetch_envs(tok)
                if err:
                    st.session_state["_env_load_err"] = err
                else:
                    st.session_state["_env_load_err"] = None
                    # Preserve manually-added envs and cross-check their IDs
                    manual_envs = [e for e in st.session_state.s_envs if e.get("manual")]
                    discovered_ids   = {e["environmentId"] for e in envs}
                    discovered_names = {e["name"] for e in envs}
                    ev = dict(st.session_state.s_env_verified)
                    for me in manual_envs:
                        ev[me["name"]] = bool(me.get("environmentId")) and me["environmentId"] in discovered_ids
                    st.session_state.s_env_verified = ev
                    # Merge: auto-discovered + manual envs not already in the list
                    merged = list(envs)
                    for me in manual_envs:
                        if me["name"] not in discovered_names:
                            merged.append(me)
                    st.session_state.s_envs = merged
        st.session_state["_op_loading_envs"] = False
        st.rerun()

    if st.session_state.get("_env_load_err"):
        st.error(st.session_state["_env_load_err"])

    if st.session_state.s_envs:
        sel = st.multiselect(
            "Environments to monitor",
            options=[e["name"] for e in st.session_state.s_envs],
            default=[n for n in st.session_state.s_sel_envs
                     if n in [e["name"] for e in st.session_state.s_envs]],
            key="ms_envs",
            help="Power Platform environments the agent will watch. Only agents inside these "
                 "environments are evaluated and reported. Deselect to exclude an environment."
        )
        st.session_state.s_sel_envs = sel
        # Lazy-validation badges for manually-added environments
        for _e in st.session_state.s_envs:
            if not _e.get("manual") or _e["name"] not in st.session_state.s_sel_envs:
                continue
            _vs = st.session_state.s_env_verified.get(_e["name"])
            if _vs is True:
                st.markdown(
                    f"<div class='status-ok' style='font-size:0.72rem;margin-top:2px'>"
                    f"✓ {_e['name']} — environment ID verified against tenant</div>",
                    unsafe_allow_html=True,
                )
            elif _vs is False:
                st.markdown(
                    f"<div class='status-err' style='font-size:0.72rem;margin-top:2px'>"
                    f"⚠ {_e['name']} — environment ID not found in tenant · verify the ID</div>",
                    unsafe_allow_html=True,
                )
    elif st.session_state.s_sel_envs:
        chips = "".join(
            f"<span style='display:inline-block;background:rgba(0,240,255,0.07);"
            f"border:1px solid rgba(0,240,255,0.25);border-radius:4px;"
            f"padding:4px 12px;margin:3px 4px 3px 0;color:{C_CYAN};"
            f"font-family:{FONT};font-size:0.78rem;letter-spacing:1px'>{n}</span>"
            for n in st.session_state.s_sel_envs
        )
        st.markdown(
            f"<div style='margin-bottom:6px'>{chips}</div>"
            f"<div style='color:{C_DIM};font-size:0.7rem;font-family:{FONT};"
            f"letter-spacing:1px'>Saved config · click Load Environments to refresh</div>",
            unsafe_allow_html=True,
        )

    def _env_form():
        m1, m2 = st.columns(2)
        with m1:
            m_name = st.text_input("Friendly name *", key="m_env_name",
                                   placeholder="Contoso (default)",
                                   help="Display label used throughout the dashboard.")
            m_url  = st.text_input("Org URL *", key="m_env_url",
                                   placeholder="https://orgXXXXX.crm.dynamics.com",
                                   help="Dataverse instance URL. Found in make.powerapps.com → "
                                        "Settings → Session details → Instance url.")
        with m2:
            m_id   = st.text_input("Environment ID *", key="m_env_id",
                                   placeholder="00000000-0000-0000-0000-000000000000",
                                   help="Required for agent discovery. Found in make.powerapps.com → "
                                        "Settings → Session details → Environment ID.")
            st.markdown(
                f"<div style='color:{C_DIM};font-size:0.68rem;margin-top:4px'>"
                f"make.powerapps.com → Settings → Session details</div>",
                unsafe_allow_html=True,
            )
        if st.button("Add environment", key="btn_add_env"):
            if m_name.strip() and m_url.strip():
                new_env = {"name": m_name.strip(), "orgUrl": m_url.strip().rstrip("/"),
                           "environmentId": m_id.strip(), "manual": True}
                existing_names = [e["name"] for e in st.session_state.s_envs]
                if new_env["name"] not in existing_names:
                    st.session_state.s_envs.append(new_env)
                if new_env["name"] not in st.session_state.s_sel_envs:
                    st.session_state.s_sel_envs.append(new_env["name"])
                st.rerun()
            else:
                st.warning("Friendly name and Org URL are required.")

    st.markdown(
        f"<div style='color:{C_DIM};font-size:0.72rem;font-family:{FONT};"
        f"letter-spacing:1px;margin:14px 0 8px'>ADD ENVIRONMENT MANUALLY</div>",
        unsafe_allow_html=True,
    )
    _env_form()

st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Bots
# ═══════════════════════════════════════════════════════════════════════════════
_sec("4 · Agents to Monitor", ok4)
st.caption("Agents discovered via the Power Platform Inventory API — same sign-in as above, no extra permissions needed.")

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
            bots_raw    = st.session_state.s_bots.get(env_name, [])
            saved_bots  = bot_sel.get(env_name, [])
            loading_key = f"_op_loading_bots_{env_name}"
            _loading_bots = st.session_state.get(loading_key, False)

            col_b1, col_b2 = st.columns([1, 4])
            with col_b1:
                if st.button("Load Bots", key=f"btn_bots_{env_name}", disabled=_loading_bots):
                    st.session_state[loading_key] = True
                    st.rerun()
            with col_b2:
                if bots_raw:
                    st.markdown(
                        f"<div style='color:{C_CYAN};font-family:{FONT};font-size:0.78rem;"
                        f"font-weight:700;letter-spacing:1px;margin-top:8px'>"
                        f"✓ {len(bots_raw)} agent(s) found</div>",
                        unsafe_allow_html=True,
                    )

            env_id = env.get("environmentId", "")

            if _loading_bots:
                with st.spinner("Scanning agents…"):
                    if not env_id:
                        st.session_state[f"_bots_err_{env_name}"] = (
                            "Environment ID is missing — edit this environment in Section 3 to add it."
                        )
                    else:
                        tok, _ = _token_silent(EVAL_SCOPES, st.session_state.s_client_id,
                                               st.session_state.s_tenant_id,
                                               st.session_state.s_cache_file)
                        if tok:
                            bots, err = _fetch_bots_inventory(env_id, tok)
                            if err:
                                st.session_state[f"_bots_err_{env_name}"] = err
                            else:
                                st.session_state.pop(f"_bots_err_{env_name}", None)
                                # Preserve manually-added agents; cross-check their schema names
                                manual_bots     = [b for b in st.session_state.s_bots.get(env_name, [])
                                                   if not b.get("botId")]
                                fetched_schemas = {b["schemaname"] for b in bots}
                                bv = dict(st.session_state.s_bot_verified)
                                bv[env_name] = {mb["schemaname"]: mb["schemaname"] in fetched_schemas
                                                for mb in manual_bots}
                                st.session_state.s_bot_verified = bv
                                # Merge: fetched + manual agents not found in inventory
                                merged_bots = list(bots)
                                for mb in manual_bots:
                                    if mb["schemaname"] not in fetched_schemas:
                                        merged_bots.append(mb)
                                st.session_state.s_bots[env_name] = merged_bots
                        else:
                            st.session_state[f"_bots_err_{env_name}"] = "Token acquisition failed — sign in first (Section 2)."
                st.session_state[loading_key] = False
                st.rerun()

            if st.session_state.get(f"_bots_err_{env_name}"):
                st.error(st.session_state[f"_bots_err_{env_name}"])

            # Bot list display
            if bots_raw:
                names   = [b["name"] for b in bots_raw]
                schemas = {b["name"]: b["schemaname"] for b in bots_raw}
                cur_schemas = bot_sel.get(env_name, [])
                cur_names   = [b["name"] for b in bots_raw if b["schemaname"] in cur_schemas]
                sel_names   = st.multiselect(
                    f"Agents ({env_name}) — leave empty to monitor all",
                    options=names, default=cur_names or names,
                    key=f"ms_bots_{env_name}",
                    help="Select which agents in this environment to monitor. "
                         "Leave empty to monitor all agents.",
                )
                bot_sel[env_name] = [schemas[n] for n in sel_names]
            elif saved_bots:
                chips = "".join(
                    f"<span style='display:inline-block;background:rgba(255,0,170,0.07);"
                    f"border:1px solid rgba(255,0,170,0.25);border-radius:4px;"
                    f"padding:3px 10px;margin:3px 4px 3px 0;color:{C_MAGENTA};"
                    f"font-family:monospace;font-size:0.72rem'>{s}</span>"
                    for s in saved_bots
                )
                st.markdown(
                    f"<div style='margin:4px 0'>{chips}</div>"
                    f"<div style='color:{C_DIM};font-size:0.7rem;font-family:{FONT};"
                    f"letter-spacing:1px'>Saved config · click Load Bots to refresh</div>",
                    unsafe_allow_html=True,
                )

            # Lazy-validation badges for manually-added agents
            _abv = st.session_state.s_bot_verified.get(env_name, {})
            for _schema, _ok in _abv.items():
                _label = next((b["name"] for b in bots_raw if b["schemaname"] == _schema), _schema)
                if _ok:
                    st.markdown(
                        f"<div class='status-ok' style='font-size:0.72rem;margin-top:2px'>"
                        f"✓ {_label} ({_schema}) — found in inventory</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"<div class='status-err' style='font-size:0.72rem;margin-top:2px'>"
                        f"⚠ {_label} ({_schema}) — schema name not found in inventory · verify spelling</div>",
                        unsafe_allow_html=True,
                    )

            # Manual agent entry
            st.markdown(
                f"<div style='color:{C_DIM};font-size:0.72rem;font-family:{FONT};"
                f"letter-spacing:1px;margin:14px 0 6px'>ADD AGENT MANUALLY</div>",
                unsafe_allow_html=True,
            )
            ma1, ma2 = st.columns(2)
            with ma1:
                m_bot_name = st.text_input(
                    "Display name *", key=f"m_bot_name_{env_name}",
                    placeholder="My Copilot Agent",
                    help="Friendly label shown in the dashboard.",
                )
            with ma2:
                m_bot_schema = st.text_input(
                    "Schema name *", key=f"m_bot_schema_{env_name}",
                    placeholder="myorg_MyCopilotAgent",
                    help="Unique logical name of the agent. Found in Copilot Studio → "
                         "Settings → Advanced → Schema name.",
                )
            if st.button("Add agent", key=f"btn_add_bot_{env_name}"):
                if m_bot_name.strip() and m_bot_schema.strip():
                    new_bot = {
                        "botId": "", "name": m_bot_name.strip(),
                        "schemaname": m_bot_schema.strip(), "statecode": 0,
                    }
                    existing = st.session_state.s_bots.get(env_name, [])
                    if new_bot["schemaname"] not in [b["schemaname"] for b in existing]:
                        st.session_state.s_bots.setdefault(env_name, []).append(new_bot)
                    if new_bot["schemaname"] not in bot_sel.get(env_name, []):
                        bot_sel.setdefault(env_name, []).append(new_bot["schemaname"])
                    st.session_state.s_bot_sel = bot_sel
                    st.rerun()
                else:
                    st.warning("Both display name and schema name are required.")

        else:
            cur = bot_sel.get(env_name, [])
            st.caption(f"Existing config: {len(cur)} agent(s) selected. Load bots to change.")

    st.session_state.s_bot_sel = bot_sel

st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — LLM
# ═══════════════════════════════════════════════════════════════════════════════
_sec("5 · LLM (Response Analysis)", ok5)
st.caption("Any OpenAI-compatible endpoint. API key goes in .env as LLM_API_KEY.")

c1, c2, c3 = st.columns([3, 2, 1])
with c1:
    llm_url   = st.text_input(
        "Base URL", value=st.session_state.s_llm_url, key="in_llm_url",
        placeholder="https://api.openai.com/v1",
        help="OpenAI: https://api.openai.com/v1\n\n"
             "Azure AI Foundry project endpoint: "
             "https://{resource}.services.ai.azure.com/api/projects/{project}"
             "/openai/deployments/{deployment-name}\n\n"
             "/chat/completions is appended automatically.",
    )
with c2:
    llm_model = st.text_input(
        "Model / Deployment", value=st.session_state.s_llm_model, key="in_llm_model",
        help="OpenAI model name (e.g. gpt-4o) or Azure deployment name. "
             "For Azure AI Foundry, this must match the deployment name in the Base URL.",
    )
with c3:
    poll      = st.number_input("Poll (min)", min_value=1, max_value=1440,
                                 value=int(st.session_state.s_poll), key="in_poll")

c4, _ = st.columns([2, 3])
with c4:
    llm_api_ver = st.text_input(
        "API Version (Azure only)", value=st.session_state.s_llm_api_ver, key="in_llm_api_ver",
        placeholder="2024-12-01-preview",
        help="Required for Azure AI Foundry / Azure OpenAI endpoints. "
             "Leave blank for OpenAI. Common value: 2024-12-01-preview.",
    )

st.session_state.s_llm_url     = llm_url.strip()
st.session_state.s_llm_model   = llm_model.strip()
st.session_state.s_llm_api_ver = llm_api_ver.strip()
st.session_state.s_poll        = int(poll)

# LLM validation
_api_key = os.environ.get("LLM_API_KEY", "")
_loading_llm = st.session_state.get("_op_loading_llm", False)
col_t1, col_t2 = st.columns([1, 4])
with col_t1:
    if st.button("Test LLM", key="btn_test_llm",
                 disabled=_loading_llm or not llm_url.strip()):
        st.session_state["_op_loading_llm"] = True
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

if _loading_llm:
    with st.spinner("Pinging LLM…"):
        ok, err = _test_llm(llm_url.strip(), llm_model.strip(), _api_key, llm_api_ver.strip())
        os.makedirs(os.path.join(STORE_DIR, "agent"), exist_ok=True)
        import json as _json
        open(_llm_status_path(), "w").write(_json.dumps({"ok": ok, "error": err or ""}))
    st.session_state["_op_loading_llm"] = False
    st.rerun()

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
        "base_url":    st.session_state.s_llm_url,
        "api_key":     "",
        "model":       st.session_state.s_llm_model,
        "api_version": st.session_state.s_llm_api_ver,
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

# ── Agent maintenance ─────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    f"<div style='font-size:0.85rem;font-weight:700;letter-spacing:3px;"
    f"text-transform:uppercase;color:{C_DIM};margin-bottom:12px;font-family:{FONT}'>"
    f"AGENT MAINTENANCE</div>",
    unsafe_allow_html=True,
)

def _stale_files():
    import glob
    agent_dir = os.path.join(STORE_DIR, "agent")
    patterns  = [
        os.path.join(agent_dir, "force_eval*.trigger"),
        os.path.join(agent_dir, "eval_active_*.lock"),
        os.path.join(agent_dir, "eval_progress_*.json"),
    ]
    found = []
    for p in patterns:
        found.extend(glob.glob(p))
    return found

stale = _stale_files()
if stale:
    st.warning(f"{len(stale)} stale agent file(s) found: trigger, lock, or progress files left from a previous session.")
    st.caption("  \n".join(os.path.basename(f) for f in stale))
    if st.button("🗑 Clear stale agent files", type="secondary"):
        removed, failed = 0, 0
        for f in stale:
            try:
                os.remove(f)
                removed += 1
            except Exception:
                failed += 1
        if failed:
            st.error(f"Removed {removed}, failed to remove {failed}.")
        else:
            st.success(f"Cleared {removed} stale file(s). Dashboard state reset.")
        st.rerun()
else:
    st.caption("No stale agent files found.")
