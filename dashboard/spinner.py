"""dashboard/spinner.py — Full-screen blocking overlay spinner for all pages."""
import random


def _overlay(label: str, animation_html: str, keyframes_css: str) -> str:
    return f"""
    <style>{keyframes_css}</style>
    <div style="
      position:fixed; top:0; left:0; width:100vw; height:100vh;
      background:rgba(0,4,12,0.90);
      z-index:99999;
      display:flex; flex-direction:column; align-items:center; justify-content:center;
      cursor:wait;
    ">
      <div style="display:flex;flex-direction:column;align-items:center;margin-left:500px">
        {animation_html}
        <div style="color:#00f0ff;font-size:0.75rem;letter-spacing:5px;
                    margin-top:22px;font-family:monospace;font-weight:700;
                    text-shadow:0 0 12px rgba(0,240,255,0.6)">
          {label}
        </div>
      </div>
    </div>
    """


def _hyperspace_html(label: str) -> str:
    lines = "".join(
        f"<div style='position:absolute;top:50%;left:50%;height:1px;width:42px;"
        f"background:linear-gradient(to right,rgba(0,240,255,0.7),transparent);"
        f"transform-origin:0 50%;transform:rotate({i * 30}deg)'></div>"
        for i in range(12)
    )
    mag_lines = "".join(
        f"<div style='position:absolute;top:50%;left:50%;height:1px;width:24px;"
        f"background:linear-gradient(to right,rgba(255,0,170,0.45),transparent);"
        f"transform-origin:0 50%;transform:rotate({i * 30 + 15}deg)'></div>"
        for i in range(12)
    )
    anim = f"""
    <div style="position:relative;width:100px;height:100px">
      {lines}{mag_lines}
      <div style="position:absolute;top:0;left:0;width:100px;height:100px;
                  border-radius:50%;
                  background:conic-gradient(
                    rgba(0,240,255,0) 0deg, rgba(0,240,255,0) 220deg,
                    rgba(0,240,255,0.08) 270deg, rgba(0,240,255,0.55) 345deg,
                    rgba(0,240,255,0.85) 358deg, rgba(0,240,255,0) 360deg);
                  animation:sp-warp 1.3s linear infinite"></div>
      <div style="position:absolute;top:50%;left:50%;font-size:24px;line-height:1;
                  animation:sp-pulse 1.3s ease-in-out infinite">🚀</div>
    </div>
    """
    css = """
      @keyframes sp-warp  { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
      @keyframes sp-pulse {
        0%,100%{transform:translate(-50%,-50%) scale(1);   opacity:0.85;}
        50%     {transform:translate(-50%,-50%) scale(1.2); opacity:1;}
      }
    """
    return _overlay(label, anim, css)


def _orbit_html(label: str) -> str:
    anim = """
    <div style="position:relative;width:100px;height:100px">
      <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                  width:88px;height:88px;border-radius:50%;
                  border:1px solid rgba(0,240,255,0.22)"></div>
      <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                  width:58px;height:58px;border-radius:50%;
                  border:1px dashed rgba(255,0,170,0.15)"></div>
      <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                  width:18px;height:18px;border-radius:50%;
                  background:radial-gradient(circle at 35% 35%,#55aaff,#0040a0);
                  animation:sp-pglow 2s ease-in-out infinite"></div>
      <div style="position:absolute;top:50%;left:50%;width:0;height:0;
                  animation:sp-orb 2.2s linear infinite">
        <div style="position:absolute;top:-44px;left:-11px;
                    font-size:20px;line-height:1;
                    filter:drop-shadow(0 0 6px rgba(0,240,255,0.9))">🛸</div>
      </div>
      <div style="position:absolute;top:50%;left:50%;width:0;height:0;
                  animation:sp-corb 1.5s linear infinite">
        <div style="position:absolute;top:-29px;left:-3px;
                    width:6px;height:6px;border-radius:50%;
                    background:rgba(255,0,170,0.85);
                    box-shadow:0 0 6px rgba(255,0,170,0.7)"></div>
      </div>
    </div>
    """
    css = """
      @keyframes sp-orb   { from{transform:rotate(0deg)}   to{transform:rotate(360deg)}  }
      @keyframes sp-corb  { from{transform:rotate(0deg)}   to{transform:rotate(-360deg)} }
      @keyframes sp-pglow {
        0%,100%{box-shadow:0 0 8px  rgba(0,240,255,0.5);}
        50%    {box-shadow:0 0 22px rgba(0,240,255,0.95);}
      }
    """
    return _overlay(label, anim, css)


def spinner(placeholder, label: str = "PROCESSING"):
    """Full-screen blocking overlay — clears when placeholder.empty() is called."""
    html = _hyperspace_html(label) if random.choice([True, False]) else _orbit_html(label)
    placeholder.markdown(html, unsafe_allow_html=True)
