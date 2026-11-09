"""Look & feel for the Ops Dashboard: dark rounded cards, orange hero, pill tabs.

Cards are st.container(key="card_…") / key="hero" — Streamlit adds a `st-key-<key>` class that
the CSS below styles. HTML fragments are built without leading spaces so markdown doesn't
turn them into code blocks.
"""
import math

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

ORANGE, YELLOW, GREEN, RED, WHITE = "#F0441A", "#FFD23F", "#3DDC84", "#FF5A3C", "#F4F4F4"
MUTED, CARD, CARD2, LINE = "#8B8B8B", "#141414", "#1C1C1C", "#262626"
SERIES = [ORANGE, YELLOW, WHITE, GREEN, "#7AA2FF", "#C084FC"]

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&display=swap');
html, body, .stApp, [class*="css"], .stMarkdown, button, input {{ font-family: 'Manrope', sans-serif !important; }}
.stApp {{ background: #0A0A0A; }}
header[data-testid="stHeader"] {{ background: transparent; pointer-events: none; }}
header[data-testid="stHeader"] button, header[data-testid="stHeader"] a {{ pointer-events: auto; }}
.block-container {{ max-width: 1440px; padding-top: 4.4rem; padding-bottom: 3rem; }}
h1, h2, h3 {{ font-weight: 600 !important; letter-spacing: -0.01em; }}

/* pill navigation */
.stTabs [role="tablist"], .stTabs [data-baseweb="tab-list"] {{ gap: 4px; background: #111; border: 1px solid {LINE};
  border-radius: 999px; padding: 6px; width: fit-content; margin-bottom: 18px; border-bottom: 1px solid {LINE}; }}
.stTabs [role="tab"] {{ border-radius: 999px; padding: 9px 22px !important; height: auto; color: #DADADA;
  background: transparent; border: none !important; box-shadow: none !important; margin: 0 !important; }}
.stTabs [role="tab"] p {{ font-size: 0.95rem; color: #DADADA; }}
.stTabs [role="tab"][aria-selected="true"] {{ background: #FFFFFF !important; }}
.stTabs [role="tab"][aria-selected="true"] p {{ color: #000 !important; font-weight: 600; }}
.stTabs [role="tab"]::after, .stTabs [role="tab"]::before {{ display: none !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}
.stTabs > div > hr, .stTabs [role="tablist"] + div[aria-hidden] {{ display: none; }}

/* segmented controls (brand / period) */
button[data-variant="segmented_control"] {{ border-radius: 999px !important; border: 1px solid {LINE} !important;
  background: #111 !important; padding: 4px 16px !important; margin-right: 4px; }}
button[data-variant="segmented_control"] p, button[data-variant="segmented_control"] span {{ color: #DADADA !important; }}
button[data-variant="segmented_control"][aria-checked="true"] {{ background: #FFFFFF !important; border-color: #fff !important; }}
button[data-variant="segmented_control"][aria-checked="true"] p,
button[data-variant="segmented_control"][aria-checked="true"] span {{ color: #000 !important; font-weight: 600; }}

/* cards */
div[class*="st-key-card"] {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 30px; padding: 24px 26px; }}
div[class*="st-key-cardlight"] {{ background: #222; }}
div[class*="st-key-hero"] {{ background: {ORANGE}; border-radius: 30px; padding: 24px 26px 10px; }}
[data-testid="stMetric"] {{ background: {CARD2}; border: 1px solid {LINE}; border-radius: 20px; padding: 16px 18px; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; }}
[data-testid="stDataFrame"], [data-testid="stPlotlyChart"] {{ border-radius: 20px; overflow: hidden; }}
[data-testid="stExpander"] details {{ border-radius: 20px; border-color: {LINE}; background: {CARD}; }}
.stTextInput input, .stSelectbox div[data-baseweb="select"] > div, .stDateInput input {{ border-radius: 14px !important; }}

/* building blocks */
.k-logo {{ display: flex; align-items: center; gap: 10px; font-size: 1.5rem; font-weight: 700; color: #fff; }}
.k-logo i {{ width: 30px; height: 30px; border-radius: 9px; background: linear-gradient(135deg, {GREEN}, #1fa463);
  display: inline-block; transform: skewX(-12deg); }}
.k-pill {{ display: inline-flex; align-items: center; gap: 12px; background: #111; border: 1px solid {LINE};
  border-radius: 999px; padding: 8px 16px; color: #ddd; }}
.k-ticks span {{ display: inline-block; width: 2px; height: 16px; margin-right: 3px; border-radius: 2px; background: #444; }}
.k-ticks span.on {{ background: {YELLOW}; }}
.k-label {{ color: #CFCFCF; font-size: 0.95rem; margin-bottom: 6px; }}
.k-big {{ font-size: 2.9rem; font-weight: 600; color: #fff; line-height: 1.1; letter-spacing: -0.02em; }}
.k-badge {{ display: inline-flex; align-items: center; gap: 4px; border-radius: 999px; padding: 4px 12px;
  font-size: 0.9rem; font-weight: 600; vertical-align: middle; margin-left: 10px; }}
.k-badge.up {{ background: {GREEN}; color: #062b16; }}
.k-badge.down {{ background: #fff; color: #222; }}
.k-badge.flat {{ background: #333; color: #ddd; }}
.k-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 26px; }}
.k-mini {{ background: {CARD2}; border-radius: 20px; padding: 16px 18px; }}
.k-mini .t {{ color: #BDBDBD; font-size: 0.9rem; border-left: 3px solid var(--c); padding-left: 8px; }}
.k-mini .v {{ color: #fff; font-size: 1.55rem; font-weight: 600; margin-top: 10px; }}
.k-mini .d {{ font-size: 0.8rem; margin-left: 6px; }}
.k-hero-t {{ color: #fff; font-size: 1rem; font-weight: 500; }}
.k-hero-v {{ color: #fff; font-size: 2.6rem; font-weight: 600; letter-spacing: -0.02em; }}
.k-watch {{ display: flex; align-items: center; }}
.k-watch .lbl {{ color: #ddd; padding-right: 22px; margin-right: 8px; border-right: 1px solid {LINE}; white-space: nowrap; }}
.k-witem {{ flex: 1; display: flex; align-items: center; gap: 14px; padding: 4px 18px; border-right: 1px solid {LINE}; min-width: 0; }}
.k-witem:last-child {{ border-right: none; }}
.k-ico {{ width: 52px; height: 52px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 1.3rem; flex: none; }}
.k-witem .n {{ color: #CFCFCF; font-size: 0.9rem; }}
.k-witem .v {{ color: #fff; font-weight: 600; font-size: 1.05rem; white-space: nowrap; }}
.k-up {{ color: {GREEN}; }} .k-down {{ color: {RED}; }}
.k-bars {{ display: flex; gap: 12px; height: 210px; margin-top: 14px; }}
.k-bar {{ flex: 1; display: flex; flex-direction: column; }}
.k-bar .track {{ flex: 1; border-radius: 16px; position: relative; overflow: hidden;
  background: repeating-linear-gradient(135deg, #1E1E1E 0 6px, #262626 6px 8px); }}
.k-bar .fill {{ position: absolute; left: 0; right: 0; bottom: 0; border-radius: 16px; padding: 10px 12px;
  font-weight: 600; font-size: 0.95rem; }}
.k-bar .name {{ text-align: center; color: #CFCFCF; font-size: 0.85rem; margin-top: 8px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }}
.k-head {{ display: flex; justify-content: space-between; align-items: center; color: #DDD; font-size: 1rem; }}
.k-arrow {{ width: 38px; height: 38px; border-radius: 50%; background: #1E1E1E; border: 1px solid {LINE};
  display: flex; align-items: center; justify-content: center; color: #ddd; }}
.k-score {{ font-size: 2.6rem; color: #fff; font-weight: 600; margin-top: 12px; }}
.k-score small {{ font-size: 1.3rem; color: {MUTED}; font-weight: 500; }}
.k-insight {{ unicode-bidi: plaintext; color: #D5D5D5; line-height: 1.65; margin-top: 26px; font-size: 0.98rem; min-height: 110px; }}
.k-insight b {{ color: #fff; }}
.k-chips {{ display: flex; gap: 8px; background: #161616; border-radius: 999px; padding: 8px; margin-top: 14px; width: fit-content; }}
.k-chip {{ width: 46px; height: 46px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-weight: 700; color: #111; }}
.k-sub {{ color: {MUTED}; font-size: 0.85rem; }}
.k-rtl {{ direction: rtl; text-align: right; unicode-bidi: plaintext; line-height: 1.7; }}
.k-tag {{ display: inline-block; border-radius: 999px; padding: 2px 10px; font-size: 0.75rem; font-weight: 700;
  margin-inline-end: 6px; }}
.k-ins-title {{ color: #fff; font-weight: 600; font-size: 1rem; margin: 10px 0 8px; }}
.k-ins-row {{ color: #CFCFCF; font-size: 0.9rem; margin-top: 6px; }}
.k-ins-row b {{ color: {ORANGE}; font-weight: 600; }}
.k-hook-old {{ color: {MUTED}; font-size: 0.95rem; text-decoration: line-through; text-decoration-color: #555; }}
.k-hook-new {{ color: #fff; font-size: 1.15rem; font-weight: 600; margin: 6px 0; }}
.k-why {{ color: {GREEN}; font-size: 0.85rem; }}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)
    t = go.layout.Template(pio.templates["plotly_dark"])
    t.layout.update(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", colorway=SERIES,
                    font=dict(family="Manrope, sans-serif", color="#CFCFCF"),
                    title=dict(font=dict(size=15, color="#E6E6E6")),
                    xaxis=dict(gridcolor="#1F1F1F", zeroline=False), yaxis=dict(gridcolor="#1F1F1F", zeroline=False),
                    legend=dict(orientation="h", y=1.12, x=0), margin=dict(l=10, r=10, t=50, b=10),
                    hoverlabel=dict(bgcolor="#111", bordercolor="#333", font=dict(color="#fff")))
    pio.templates["konoz"] = t
    pio.templates.default = "konoz"


def html(s):
    st.markdown(s, unsafe_allow_html=True)


def badge(change):
    """change is a fraction (0.047 = +4.7%) or None."""
    if change is None:
        return ""
    cls, arrow = ("up", "↗") if change > 0.0005 else ("down", "↙") if change < -0.0005 else ("flat", "→")
    return f'<span class="k-badge {cls}">{arrow} {abs(change):.1%}</span>'


def ticks(score, n=24):
    on = round(n * max(min(score, 100), 0) / 100)
    return '<span class="k-ticks">' + "".join(f'<span class="{"on" if i < on else ""}"></span>' for i in range(n)) + "</span>"


def mini(label, value, color, change=None, inverse=False):
    d = ""
    if change is not None:
        good = (change < 0) if inverse else (change > 0)
        d = f'<span class="d {"k-up" if good else "k-down"}">{change:+.1%}</span>'
    return f'<div class="k-mini" style="--c:{color}"><div class="t">{label}</div><div class="v">{value}{d}</div></div>'


def spark(values, color, w=96, h=36):
    v = [x for x in values if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    span = (hi - lo) or 1
    pts = [(i * (w - 8) / (len(v) - 1) + 4, h - 4 - (x - lo) / span * (h - 8)) for i, x in enumerate(v)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    ex, ey = pts[-1]
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="flex:none">'
            f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="7" fill="{color}" opacity=".25"/>'
            f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3.5" fill="{color}"/></svg>')


def watch_item(icon, bg, fg, name, value, change=None, series=None, inverse=False):
    d, color = "", MUTED
    if change is not None:
        good = (change < 0) if inverse else (change > 0)
        color = GREEN if good else RED
        d = f' <span class="{"k-up" if good else "k-down"}" style="font-size:.85rem">{change:+.2%}</span>'
    return (f'<div class="k-witem"><div class="k-ico" style="background:{bg};color:{fg}">{icon}</div>'
            f'<div style="min-width:0"><div class="n">{name}</div><div class="v">{value}{d}</div></div>'
            f'<div style="margin-left:auto">{spark(series or [], color)}</div></div>')


def watchlist(label, items):
    return f'<div class="k-watch"><div class="lbl">{label}</div>{"".join(items)}</div>'


def bars(items):
    """items: [(name, fraction 0-1, color, text_color)]"""
    out = []
    for name, frac, color, txt in items:
        h = max(min(frac, 1), 0) * 100
        fill = (f'<div class="fill" style="height:{h:.0f}%;background:{color};color:{txt}">{frac:.0%}</div>'
                if h >= 1 else "")
        out.append(f'<div class="k-bar"><div class="track">{fill}</div><div class="name">{name}</div></div>')
    return f'<div class="k-bars">{"".join(out)}</div>'


def gauge(score, w=300, h=170):
    r, cx, cy = 120, w / 2, h - 10
    s = max(min(score, 100), 0) / 100
    a = math.pi * (1 - s)
    kx, ky = cx + r * math.cos(a), cy - r * math.sin(a)
    arc = f"M {cx - r} {cy} A {r} {r} 0 0 1 {cx + r} {cy}"
    length = math.pi * r
    return (f'<svg width="100%" viewBox="0 0 {w} {h + 8}" style="display:block;margin-top:6px">'
            f'<defs><pattern id="hatch" width="6" height="6" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">'
            f'<rect width="6" height="6" fill="#1E1E1E"/><rect width="2" height="6" fill="#2A2A2A"/></pattern></defs>'
            f'<path d="{arc}" stroke="url(#hatch)" stroke-width="44" fill="none"/>'
            f'<path d="{arc}" stroke="{GREEN}" stroke-width="44" fill="none" stroke-linecap="round" '
            f'stroke-dasharray="{length * s:.1f} {length:.1f}"/>'
            f'<circle cx="{cx - r}" cy="{cy}" r="13" fill="#2A2A2A"/><circle cx="{cx - r}" cy="{cy}" r="6" fill="#111"/>'
            f'<line x1="{kx:.1f}" y1="{ky:.1f}" x2="{kx:.1f}" y2="{ky + 70:.1f}" stroke="#555" stroke-width="2"/>'
            f'<circle cx="{kx:.1f}" cy="{ky:.1f}" r="16" fill="{GREEN}"/><circle cx="{kx:.1f}" cy="{ky:.1f}" r="9" fill="#fff"/>'
            f'</svg>')


def hero_chart(x, y, height=300):
    fig = go.Figure(go.Scatter(x=x, y=y, mode="lines", line=dict(color=YELLOW, width=2.2, shape="spline", smoothing=0.4),
                               fill="tozeroy", fillcolor="rgba(255,255,255,0.10)",
                               hovertemplate="%{x|%b %d}<br><b>%{y:,.0f} SAR</b><extra></extra>"))
    fig.update_layout(template="plotly", height=height, margin=dict(l=0, r=0, t=6, b=0), showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Manrope, sans-serif", color="rgba(255,255,255,.85)"),
                      hoverlabel=dict(bgcolor="#111", bordercolor="#111", font=dict(color="#fff")))
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,.14)", zeroline=False, showline=False, tickformat="%b %d")
    fig.update_yaxes(showgrid=False, zeroline=False, showline=False, tickformat="~s", ticksuffix="")
    return fig
