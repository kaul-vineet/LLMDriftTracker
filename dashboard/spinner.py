"""dashboard/spinner.py — Shared loading animations for all dashboard pages."""
import random


def _hyperspace_html(label: str) -> str:
    """Rotating conic sweep + static radial streaks + pulsing rocket."""
    lines = "".join(
        f"<div style='position:absolute;top:50%;left:50%;height:1px;width:38px;"
        f"background:linear-gradient(to right,rgba(0,240,255,0.65),transparent);"
        f"transform-origin:0 50%;transform:rotate({i * 30}deg)'></div>"
        for i in range(12)
    )
    mag_lines = "".join(
        f"<div style='position:absolute;top:50%;left:50%;height:1px;width:22px;"
        f"background:linear-gradient(to right,rgba(255,0,170,0.45),transparent);"
        f"transform-origin:0 50%;transform:rotate({i * 30 + 15}deg)'></div>"
        for i in range(12)
    )
    return f"""
    <style>
      @keyframes warp {{
        from {{ transform:rotate(0deg); }}
        to   {{ transform:rotate(360deg); }}
      }}
      @keyframes rpulse {{
        0%,100% {{ transform:translate(-50%,-50%) scale(1);   opacity:0.9; }}
        50%      {{ transform:translate(-50%,-50%) scale(1.2); opacity:1;   }}
      }}
    </style>
    <div style="display:flex;flex-direction:column;align-items:center;padding:28px 0">
      <div style="position:relative;width:90px;height:90px">
        {lines}{mag_lines}
        <div style="position:absolute;top:0;left:0;width:90px;height:90px;
                    border-radius:50%;
                    background:conic-gradient(
                      rgba(0,240,255,0) 0deg, rgba(0,240,255,0) 220deg,
                      rgba(0,240,255,0.08) 270deg, rgba(0,240,255,0.55) 345deg,
                      rgba(0,240,255,0.85) 358deg, rgba(0,240,255,0) 360deg);
                    animation:warp 1.3s linear infinite"></div>
        <div style="position:absolute;top:50%;left:50%;font-size:22px;line-height:1;
                    animation:rpulse 1.3s ease-in-out infinite">🚀</div>
      </div>
      <div style="color:#00f0ff;font-size:0.7rem;letter-spacing:4px;margin-top:14px;
                  font-family:monospace;font-weight:700">{label}</div>
    </div>
    """


def _orbit_html(label: str) -> str:
    """🛸 traces a glowing circular orbit around a planet."""
    return f"""
    <style>
      @keyframes orb {{
        from {{ transform:rotate(0deg);   }}
        to   {{ transform:rotate(360deg); }}
      }}
      @keyframes corb {{
        from {{ transform:rotate(0deg);    }}
        to   {{ transform:rotate(-360deg); }}
      }}
      @keyframes pglow {{
        0%,100% {{ box-shadow:0 0 8px  rgba(0,240,255,0.5); }}
        50%      {{ box-shadow:0 0 20px rgba(0,240,255,0.9); }}
      }}
    </style>
    <div style="display:flex;flex-direction:column;align-items:center;padding:28px 0">
      <div style="position:relative;width:90px;height:90px">
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                    width:78px;height:78px;border-radius:50%;
                    border:1px solid rgba(0,240,255,0.22)"></div>
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                    width:52px;height:52px;border-radius:50%;
                    border:1px dashed rgba(255,0,170,0.15)"></div>
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                    width:16px;height:16px;border-radius:50%;
                    background:radial-gradient(circle at 35% 35%,#55aaff,#0040a0);
                    animation:pglow 2s ease-in-out infinite"></div>
        <div style="position:absolute;top:50%;left:50%;width:0;height:0;
                    animation:orb 2.2s linear infinite">
          <div style="position:absolute;top:-39px;left:-10px;
                      font-size:18px;line-height:1;
                      filter:drop-shadow(0 0 5px rgba(0,240,255,0.9))">🛸</div>
        </div>
        <div style="position:absolute;top:50%;left:50%;width:0;height:0;
                    animation:corb 1.5s linear infinite">
          <div style="position:absolute;top:-26px;left:-3px;
                      width:6px;height:6px;border-radius:50%;
                      background:rgba(255,0,170,0.85);
                      box-shadow:0 0 6px rgba(255,0,170,0.7)"></div>
        </div>
      </div>
      <div style="color:#00f0ff;font-size:0.7rem;letter-spacing:4px;margin-top:14px;
                  font-family:monospace;font-weight:700">{label}</div>
    </div>
    """


def spinner(placeholder, label: str = "PROCESSING"):
    """Render a randomly chosen spaceship animation into a Streamlit placeholder."""
    html = _hyperspace_html(label) if random.choice([True, False]) else _orbit_html(label)
    placeholder.markdown(html, unsafe_allow_html=True)
