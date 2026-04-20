"""dashboard/spinner.py — Shared loading animations for all dashboard pages."""
import random


def _hyperspace_html(label: str) -> str:
    """Stars stretching into light-streaks radiating from center."""
    streaks = []
    angles = [i * 30 for i in range(12)]  # 12 streaks every 30°
    for i, angle in enumerate(angles):
        delay  = round(i * 0.1, 1)
        length = random.randint(28, 44)
        streaks.append(
            f"<div style='position:absolute;top:50%;left:50%;height:1px;"
            f"width:{length}px;transform-origin:0 0;"
            f"transform:rotate({angle}deg);"
            f"background:linear-gradient(to right,rgba(0,240,255,0),rgba(0,240,255,0.85));"
            f"animation:hstreak 1.1s ease-out {delay}s infinite'></div>"
        )
    # counter-streaks (slight offset, magenta)
    for i, angle in enumerate(angles):
        delay  = round(i * 0.1 + 0.55, 1)
        length = random.randint(12, 24)
        streaks.append(
            f"<div style='position:absolute;top:50%;left:50%;height:1px;"
            f"width:{length}px;transform-origin:0 0;"
            f"transform:rotate({angle + 15}deg);"
            f"background:linear-gradient(to right,rgba(255,0,170,0),rgba(255,0,170,0.5));"
            f"animation:hstreak 1.1s ease-out {delay}s infinite'></div>"
        )
    return f"""
    <style>
      @keyframes hstreak {{
        0%   {{ transform-origin:0 0; opacity:0; width:2px; }}
        15%  {{ opacity:1; }}
        70%  {{ opacity:0.7; }}
        100% {{ opacity:0; width:var(--w,40px); }}
      }}
      @keyframes hpulse {{
        0%,100% {{ box-shadow:0 0 12px #00f0ff,0 0 28px rgba(0,240,255,0.4); }}
        50%      {{ box-shadow:0 0 20px #00f0ff,0 0 48px rgba(0,240,255,0.7); }}
      }}
    </style>
    <div style="display:flex;flex-direction:column;align-items:center;padding:28px 0">
      <div style="position:relative;width:90px;height:90px">
        {''.join(streaks)}
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                    width:10px;height:10px;border-radius:50%;background:#00f0ff;
                    animation:hpulse 1.1s ease-in-out infinite"></div>
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                    font-size:18px;line-height:1">🚀</div>
      </div>
      <div style="color:#00f0ff;font-size:0.7rem;letter-spacing:4px;margin-top:14px;
                  font-family:monospace;font-weight:700">{label}</div>
    </div>
    """


def _orbit_html(label: str) -> str:
    """🛸 traces a glowing orbit around a planet."""
    return f"""
    <style>
      @keyframes orb  {{ 0% {{ transform:rotate(0deg);   }} 100% {{ transform:rotate(360deg);  }} }}
      @keyframes orb2 {{ 0% {{ transform:rotate(0deg);   }} 100% {{ transform:rotate(-360deg); }} }}
      @keyframes pglow {{
        0%,100% {{ box-shadow:0 0 10px rgba(0,240,255,0.4),0 0 24px rgba(0,240,255,0.2); }}
        50%      {{ box-shadow:0 0 18px rgba(0,240,255,0.7),0 0 40px rgba(0,240,255,0.35); }}
      }}
    </style>
    <div style="display:flex;flex-direction:column;align-items:center;padding:28px 0">
      <div style="position:relative;width:90px;height:90px">
        <!-- orbit rings -->
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                    width:80px;height:80px;border-radius:50%;
                    border:1px solid rgba(0,240,255,0.18)"></div>
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                    width:56px;height:56px;border-radius:50%;
                    border:1px solid rgba(255,0,170,0.12)"></div>
        <!-- planet -->
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                    width:18px;height:18px;border-radius:50%;
                    background:radial-gradient(circle at 35% 35%,#2af,#0040a0);
                    animation:pglow 2s ease-in-out infinite"></div>
        <!-- outer orbiting ship -->
        <div style="position:absolute;top:50%;left:50%;width:0;height:0;
                    animation:orb 2.4s linear infinite">
          <div style="position:absolute;top:-40px;left:-9px;font-size:18px;line-height:1;
                      filter:drop-shadow(0 0 4px rgba(0,240,255,0.8))">🛸</div>
        </div>
        <!-- inner counter-orbiting dot -->
        <div style="position:absolute;top:50%;left:50%;width:0;height:0;
                    animation:orb2 1.6s linear infinite">
          <div style="position:absolute;top:-28px;left:-3px;
                      width:6px;height:6px;border-radius:50%;
                      background:rgba(255,0,170,0.8);
                      box-shadow:0 0 6px rgba(255,0,170,0.6)"></div>
        </div>
      </div>
      <div style="color:#00f0ff;font-size:0.7rem;letter-spacing:4px;margin-top:14px;
                  font-family:monospace;font-weight:700">{label}</div>
    </div>
    """


def spinner(placeholder, label: str = "PROCESSING"):
    """Render a randomly chosen spaceship animation into placeholder."""
    html = _hyperspace_html(label) if random.choice([True, False]) else _orbit_html(label)
    placeholder.markdown(html, unsafe_allow_html=True)
