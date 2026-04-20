"""
dashboard/pages/2_Data.py — Storage management.
Browse, inspect, and delete stored run data, event logs, and reports.
"""
import json
import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
from theme import C_BG, C_CARD, C_BORDER, C_CYAN, C_MAGENTA, C_GOLD, C_RED, C_GREEN, C_DIM, C_TEXT, FONT
from spinner import spinner as _spinner

STORE_DIR = os.environ.get("STORE_DIR", "data")

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  .data-card {{
    background:{C_CARD}; border:1px solid {C_BORDER};
    border-radius:10px; padding:20px 24px; margin-bottom:14px;
  }}
  .data-head {{
    font-size:0.85rem; font-weight:700; letter-spacing:2px;
    font-family:{FONT}; text-transform:uppercase;
    border-bottom:1px solid {C_BORDER}; padding-bottom:8px; margin-bottom:14px;
  }}
  .run-row {{
    display:flex; align-items:center; justify-content:space-between;
    padding:8px 0; border-bottom:1px solid {C_BORDER};
    font-size:0.85rem;
  }}
  .run-model  {{ color:{C_TEXT}; font-family:{FONT}; font-weight:600; }}
  .run-meta   {{ color:{C_DIM};  font-size:0.75rem; margin-top:2px; }}
  .run-forced {{ color:{C_GOLD}; font-size:0.7rem; font-family:{FONT};
                 letter-spacing:1px; margin-left:8px; }}
  .stat-row {{
    display:grid; grid-template-columns:repeat(4,1fr);
    gap:1px; background:{C_BORDER}; border:1px solid {C_BORDER};
    border-radius:8px; overflow:hidden; margin-bottom:24px;
  }}
  .stat-cell {{ background:{C_CARD}; padding:12px 16px; text-align:center; }}
  .stat-val  {{ font-size:1.6rem; font-weight:700; font-family:{FONT}; line-height:1; }}
  .stat-lbl  {{ font-size:0.65rem; color:{C_DIM}; letter-spacing:2px;
                text-transform:uppercase; margin-top:4px; }}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _fmt_ts(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y  %H:%M")
    except Exception:
        return iso[:16] if iso else "—"


def _dir_size(path: str) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except Exception:
                pass
    return total


def _fmt_size(n: int) -> str:
    if n < 1024:        return f"{n} B"
    if n < 1024**2:     return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.1f} MB"


def _load_run_meta(run_dir: str) -> dict:
    path = os.path.join(run_dir, "run.json")
    try:
        return json.loads(open(path).read())
    except Exception:
        pass
    path = os.path.join(run_dir, "meta.json")
    try:
        return json.loads(open(path).read())
    except Exception:
        return {}


def _load_all_bots():
    bots = []
    if not os.path.exists(STORE_DIR):
        return bots
    for bot_id in sorted(os.listdir(STORE_DIR)):
        bot_dir = os.path.join(STORE_DIR, bot_id)
        if not os.path.isdir(bot_dir):
            continue
        tracking_path = os.path.join(bot_dir, "tracking.json")
        try:
            tracking = json.loads(open(tracking_path).read())
        except Exception:
            continue
        runs_dir = os.path.join(bot_dir, "runs")
        runs = []
        if os.path.isdir(runs_dir):
            for folder in sorted(os.listdir(runs_dir)):
                folder_path = os.path.join(runs_dir, folder)
                if not os.path.isdir(folder_path):
                    continue
                meta  = _load_run_meta(folder_path)
                size  = _dir_size(folder_path)
                runs.append({
                    "folder":    folder,
                    "path":      folder_path,
                    "model":     meta.get("modelVersion", "unknown"),
                    "ts":        meta.get("triggeredAt", ""),
                    "forced":    meta.get("forced", False),
                    "testSets":  list(meta.get("testSets", {}).keys()),
                    "size":      size,
                })
        bots.append({
            "botId":    bot_id,
            "botName":  tracking.get("botName", bot_id),
            "envName":  tracking.get("envName", "—"),
            "model":    tracking.get("modelVersion", "unknown"),
            "path":     bot_dir,
            "runs":     runs,
            "size":     _dir_size(bot_dir),
        })
    return bots


def _load_reports():
    reports = []
    if not os.path.exists(STORE_DIR):
        return reports
    for fname in sorted(os.listdir(STORE_DIR), reverse=True):
        if not fname.startswith("report_") or not fname.endswith(".html"):
            continue
        path = os.path.join(STORE_DIR, fname)
        reports.append({
            "fname": fname,
            "path":  path,
            "size":  os.path.getsize(path),
            "ts":    fname[7:22],
        })
    return reports


def _events_path():
    return os.path.join(STORE_DIR, "events.jsonl")


def _events_size():
    p = _events_path()
    return os.path.getsize(p) if os.path.exists(p) else 0


def _events_count():
    p = _events_path()
    if not os.path.exists(p):
        return 0
    try:
        return sum(1 for line in open(p, encoding="utf-8") if line.strip())
    except Exception:
        return 0


# ── Summary stats ─────────────────────────────────────────────────────────────
def render_summary(bots, reports):
    total_runs    = sum(len(b["runs"]) for b in bots)
    total_size    = sum(b["size"] for b in bots)
    total_reports = len(reports)
    ev_count      = _events_count()

    st.markdown(f"""
    <div class='stat-row'>
      <div class='stat-cell'>
        <div class='stat-val' style='color:{C_CYAN}'>{len(bots)}</div>
        <div class='stat-lbl'>Agents</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-val' style='color:{C_TEXT}'>{total_runs}</div>
        <div class='stat-lbl'>Eval Runs</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-val' style='color:{C_DIM}'>{ev_count}</div>
        <div class='stat-lbl'>Events</div>
      </div>
      <div class='stat-cell'>
        <div class='stat-val' style='color:{C_MAGENTA}'>{_fmt_size(total_size)}</div>
        <div class='stat-lbl'>Total Size</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Confirmation guard ────────────────────────────────────────────────────────
def _confirm_key(key):
    return f"confirm_{key}"


def _delete_button(label, key, danger=True):
    """Two-click delete: first click arms, second click fires. Returns True on confirm."""
    ck = _confirm_key(key)
    if st.session_state.get(ck):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⚠ Confirm delete", key=f"{key}_yes",
                         type="primary", use_container_width=True):
                st.session_state.pop(ck, None)
                return True
        with col2:
            if st.button("Cancel", key=f"{key}_no",
                         type="secondary", use_container_width=True):
                st.session_state.pop(ck, None)
                st.rerun()
    else:
        color = C_RED if danger else C_DIM
        if st.button(label, key=key, use_container_width=True):
            st.session_state[ck] = True
            st.rerun()
    return False


# ── Bot data section ──────────────────────────────────────────────────────────
def render_bots(bots):
    st.markdown("<div class='data-head' style='font-size:0.85rem;font-weight:700;"
                f"letter-spacing:2px;font-family:{FONT};text-transform:uppercase;"
                f"color:{C_DIM};border-bottom:1px solid {C_BORDER};"
                f"padding-bottom:6px;margin-bottom:16px'>AGENT DATA</div>",
                unsafe_allow_html=True)

    if not bots:
        st.markdown(f"<div style='color:{C_DIM};font-size:0.85rem;padding:12px 0'>"
                    f"No agent data stored yet.</div>", unsafe_allow_html=True)
        return

    for bot in bots:
        with st.expander(
            f"{bot['botName']}  ·  {len(bot['runs'])} run{'s' if len(bot['runs'])!=1 else ''}  "
            f"·  {_fmt_size(bot['size'])}",
            expanded=False,
        ):
            st.markdown(
                f"<div style='font-size:0.75rem;color:{C_DIM};margin-bottom:12px'>"
                f"{bot['envName']} &nbsp;·&nbsp; current model: "
                f"<span style='color:{C_TEXT};font-family:{FONT}'>{bot['model']}</span></div>",
                unsafe_allow_html=True,
            )

            if bot["runs"]:
                # ── Individual run list ───────────────────────────────────────
                for run in reversed(bot["runs"]):
                    col_info, col_del = st.columns([5, 1])
                    with col_info:
                        forced_tag = (f"<span class='run-forced'>FORCED</span>"
                                      if run["forced"] else "")
                        ts_str = run["testSets"]
                        st.markdown(
                            f"<div class='run-row'>"
                            f"<div>"
                            f"<div class='run-model'>{run['model']}{forced_tag}</div>"
                            f"<div class='run-meta'>"
                            f"{_fmt_ts(run['ts'])} &nbsp;·&nbsp; "
                            f"{', '.join(ts_str) or '—'} &nbsp;·&nbsp; "
                            f"{_fmt_size(run['size'])}</div>"
                            f"</div></div>",
                            unsafe_allow_html=True,
                        )
                    with col_del:
                        if _delete_button("✕", key=f"run_{run['folder']}"):
                            shutil.rmtree(run["path"], ignore_errors=True)
                            st.rerun()

                st.divider()

            # ── Bot-level actions ─────────────────────────────────────────────
            col_a, col_b = st.columns(2)
            with col_a:
                if _delete_button("✕ Delete all runs", key=f"runs_{bot['botId']}"):
                    runs_dir = os.path.join(bot["path"], "runs")
                    if os.path.isdir(runs_dir):
                        shutil.rmtree(runs_dir, ignore_errors=True)
                    st.rerun()
            with col_b:
                if _delete_button("✕ Remove agent entirely", key=f"bot_{bot['botId']}"):
                    shutil.rmtree(bot["path"], ignore_errors=True)
                    st.rerun()


# ── Event log section ─────────────────────────────────────────────────────────
def render_events():
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
    ev_count = _events_count()
    ev_size  = _events_size()

    col_info, col_del = st.columns([5, 1])
    with col_info:
        st.markdown(
            f"<div class='data-head' style='font-size:0.85rem;font-weight:700;"
            f"letter-spacing:2px;font-family:{FONT};text-transform:uppercase;"
            f"color:{C_DIM};border-bottom:1px solid {C_BORDER};"
            f"padding-bottom:6px;margin-bottom:0'>EVENT LOG &nbsp;·&nbsp; "
            f"<span style='color:{C_TEXT}'>{ev_count} events</span> &nbsp;·&nbsp; "
            f"<span style='color:{C_DIM}'>{_fmt_size(ev_size)}</span></div>",
            unsafe_allow_html=True,
        )
    with col_del:
        if ev_count > 0:
            if _delete_button("✕ Clear", key="clear_events"):
                try:
                    os.remove(_events_path())
                except Exception:
                    pass
                st.rerun()


# ── Reports section ───────────────────────────────────────────────────────────
def render_reports(reports):
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
    total_size = sum(r["size"] for r in reports)

    st.markdown(
        f"<div class='data-head' style='font-size:0.85rem;font-weight:700;"
        f"letter-spacing:2px;font-family:{FONT};text-transform:uppercase;"
        f"color:{C_DIM};border-bottom:1px solid {C_BORDER};"
        f"padding-bottom:6px;margin-bottom:16px'>HTML REPORTS &nbsp;·&nbsp; "
        f"<span style='color:{C_TEXT}'>{len(reports)}</span> &nbsp;·&nbsp; "
        f"<span style='color:{C_DIM}'>{_fmt_size(total_size)}</span></div>",
        unsafe_allow_html=True,
    )

    if not reports:
        st.markdown(f"<div style='color:{C_DIM};font-size:0.85rem'>No reports yet.</div>",
                    unsafe_allow_html=True)
        return

    for r in reports:
        col_info, col_del = st.columns([5, 1])
        with col_info:
            st.markdown(
                f"<div style='padding:8px 0;border-bottom:1px solid {C_BORDER}'>"
                f"<span style='color:{C_TEXT};font-family:{FONT};font-size:0.85rem'>{r['fname']}</span>"
                f"<span style='color:{C_DIM};font-size:0.75rem;margin-left:10px'>{_fmt_size(r['size'])}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_del:
            if _delete_button("✕", key=f"report_{r['fname']}"):
                try:
                    os.remove(r["path"])
                except Exception:
                    pass
                st.rerun()

    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
    if _delete_button("✕ Delete all reports", key="delete_all_reports"):
        for r in reports:
            try:
                os.remove(r["path"])
            except Exception:
                pass
        st.rerun()


# ── Page ──────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='font-size:1.4rem;font-weight:700;letter-spacing:4px;"
    f"color:{C_CYAN};font-family:{FONT};margin-bottom:4px'>DATA</div>"
    f"<div style='font-size:0.7rem;color:{C_DIM};letter-spacing:1px;"
    f"margin-bottom:24px'>Manage stored eval runs, events, and reports</div>",
    unsafe_allow_html=True,
)

_load_ph = st.empty()
_spinner(_load_ph, "LOADING")
bots    = _load_all_bots()
reports = _load_reports()
_load_ph.empty()

render_summary(bots, reports)
render_bots(bots)
render_events()
render_reports(reports)
