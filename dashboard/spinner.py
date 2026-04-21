"""dashboard/spinner.py — Inline branded loading indicator.

The original position:fixed full-screen overlay was stripped by Streamlit 1.56's
HTML sanitizer, causing the label div to appear as raw text. Replaced with a simple
single-div indicator that renders reliably via st.markdown(unsafe_allow_html=True).
Keyframes remain in app.py global CSS (unused now but harmless).
"""


def spinner(placeholder, label: str = "PROCESSING"):
    """Inline branded loading indicator. Clears when placeholder.empty() is called."""
    placeholder.markdown(
        f"<div style='margin-top:40vh;margin-left:550px'>"
        f"<div style='"
        f"display:inline-flex;align-items:center;gap:10px;"
        f"color:#00f0ff;font-size:0.8rem;letter-spacing:3px;"
        f"font-family:monospace;font-weight:700;"
        f"padding:12px 20px;border-radius:6px;"
        f"border:1px solid rgba(0,240,255,0.3);"
        f"background:rgba(0,4,12,0.6);"
        f"text-shadow:0 0 10px rgba(0,240,255,0.5)'>"
        f"⚡ {label}"
        f"</div></div>",
        unsafe_allow_html=True,
    )
