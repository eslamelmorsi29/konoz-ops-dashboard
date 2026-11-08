"""Ops Dashboard — Overview for all brands (Streamlit, reads Supabase).

Run locally:   streamlit run app.py
Data source:   Supabase via st.secrets["supabase"] (url, service_key) or
               ~/.config/ops-dashboard/supabase.json. With neither, it runs in demo mode
               on the Morning Ops cache (Natcho only) so the layout can be previewed.
Optional:      st.secrets["app_password"] gates the app behind one shared password.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

CREDS = Path.home() / ".config" / "ops-dashboard" / "supabase.json"
BRANDS = {"natcho": "Natcho", "carina": "Carina", "genz": "GenZ"}
SEV_ICON = {"critical": "🔴", "warning": "🟠", "watch": "🟡", "win": "🟢"}

st.set_page_config(page_title="Ops Dashboard", page_icon="📊", layout="wide")


def creds():
    try:
        if "supabase" in st.secrets:
            return dict(st.secrets["supabase"])
    except Exception:
        pass
    return json.loads(CREDS.read_text()) if CREDS.exists() else None


def gate():
    try:
        pw = st.secrets.get("app_password")
    except Exception:
        pw = None
    if not pw or st.session_state.get("ok"):
        return
    entered = st.text_input("Password", type="password")
    if entered == pw:
        st.session_state.ok = True
        st.rerun()
    st.stop()


@st.cache_data(ttl=900)
def fetch(table, params):
    c = creds()
    k = c["service_key"]
    # new-style keys (sb_secret_…) are not JWTs and go in `apikey` only; legacy JWT keys also need Bearer
    h = {"apikey": k} if k.startswith("sb_") else {"apikey": k, "Authorization": f"Bearer {k}"}
    out, start = [], 0
    while True:   # PostgREST caps responses (1000 rows by default): page with Range
        r = requests.get(f"{c['url'].rstrip('/')}/rest/v1/{table}", params=dict(params),
                         headers={**h, "Range": f"{start}-{start + 999}"}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        out += rows
        if len(rows) < 1000:
            return pd.DataFrame(out)
        start += 1000


@st.cache_data(ttl=900)
def demo_data():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "morning-ops"))
    import morning_ops as m
    import supabase_sync as ss
    C = m.CACHE
    yday = (date.today() - timedelta(days=1)).isoformat()
    kpi, ad = ss.natcho_rows(pd.read_parquet(C / "orders.parquet"), pd.read_parquet(C / "df_adspend.parquet"),
                             pd.read_parquet(C / "ga4_daily_traffic.parquet"), yday)
    return pd.DataFrame(kpi), pd.DataFrame(ad), pd.DataFrame(columns=["brand", "run_date", "severity", "message", "action"])


def load(since):
    if creds() is None:
        kpi, ad, alerts = demo_data()
        return kpi, ad, alerts, True
    s = since.isoformat()
    kpi = fetch("kpi_daily", (("date", f"gte.{s}"), ("order", "date")))
    ad = fetch("ad_spend_daily", (("date", f"gte.{s}"), ("order", "date")))
    alerts = fetch("alerts", (("run_date", f"gte.{s}"), ("order", "run_date.desc")))
    return kpi, ad, alerts, False


def money(v):
    # compact so the metric cards don't truncate ("85.1K SAR" instead of "85,092 S…")
    return f"{v / 1_000_000:.2f}M SAR" if v >= 1_000_000 else f"{v / 1000:.1f}K SAR" if v >= 10_000 else f"{v:,.0f} SAR"


def delta(cur, prev):
    if prev in (0, None) or pd.isna(prev):
        return None
    return f"{(cur - prev) / prev:+.0%}"


gate()
st.title("📊 Ops Dashboard")

c1, c2 = st.columns([1, 3])
days = c1.selectbox("Period", [7, 14, 30, 90, 180, 365], index=2, format_func=lambda d: f"Last {d} days")
end = date.today() - timedelta(days=1)
start = end - timedelta(days=days - 1)
prev_start = start - timedelta(days=days)

kpi, ad, alerts, demo = load(prev_start)
if demo:
    st.info("Demo mode — Supabase مش متوصل لسه، الأرقام دي Natcho بس من cache الـ Morning Ops.")
if kpi.empty:
    st.warning("مفيش داتا لسه.")
    st.stop()

kpi["date"] = pd.to_datetime(kpi["date"]).dt.date
num = ["orders", "revenue_sar", "ad_spend_sar", "cancelled_orders", "sessions", "ga4_conversions"]
for col in num:
    if col in kpi:
        kpi[col] = pd.to_numeric(kpi[col], errors="coerce")
cur = kpi[(kpi.date >= start) & (kpi.date <= end)]
prev = kpi[(kpi.date >= prev_start) & (kpi.date < start)]
c2.caption(f"{start} → {end} · compared with {prev_start} → {start - timedelta(days=1)}")

# ---- brand cards -------------------------------------------------------------
for brand in [b for b in BRANDS if b in set(kpi.brand)]:
    cb, pb = cur[cur.brand == brand], prev[prev.brand == brand]
    st.subheader(BRANDS[brand])
    cols = st.columns(5)
    rev, prev_rev = cb.revenue_sar.sum(), pb.revenue_sar.sum()
    cols[0].metric("Revenue", money(rev), delta(rev, prev_rev))
    cols[1].metric("Orders", f"{cb.orders.sum():,.0f}", delta(cb.orders.sum(), pb.orders.sum()))
    aov = rev / cb.orders.sum() if cb.orders.sum() else 0
    prev_aov = prev_rev / pb.orders.sum() if pb.orders.sum() else 0
    cols[2].metric("AOV", f"{aov:,.0f} SAR", delta(aov, prev_aov))
    spend = cb.ad_spend_sar.sum() if "ad_spend_sar" in cb else 0
    if spend:
        mer, prev_mer = rev / spend, (prev_rev / pb.ad_spend_sar.sum() if pb.ad_spend_sar.sum() else None)
        cols[3].metric("Ad spend", money(spend), delta(spend, pb.ad_spend_sar.sum()), delta_color="inverse")
        cols[4].metric("MER", f"{mer:.2f}", delta(mer, prev_mer))
    else:
        cols[3].metric("Ad spend", "—")
        cols[4].metric("MER", "—")

# ---- trends ------------------------------------------------------------------
st.divider()
t1, t2 = st.columns(2)
daily = cur.groupby(["date", "brand"], as_index=False).revenue_sar.sum()
daily["brand"] = daily.brand.map(BRANDS)
t1.plotly_chart(px.line(daily, x="date", y="revenue_sar", color="brand", title="Revenue per day (SAR)",
                        labels={"revenue_sar": "SAR", "date": ""}), use_container_width=True)
m = cur[cur.ad_spend_sar.fillna(0) > 0].assign(mer=lambda d: d.revenue_sar / d.ad_spend_sar)
m["brand"] = m.brand.map(BRANDS)
t2.plotly_chart(px.line(m, x="date", y="mer", color="brand", title="MER per day (revenue ÷ ad spend)",
                        labels={"mer": "MER", "date": ""}), use_container_width=True)

if not ad.empty:
    ad["date"] = pd.to_datetime(ad["date"]).dt.date
    ad["spend_sar"] = pd.to_numeric(ad["spend_sar"], errors="coerce")
    a = ad[(ad.date >= start) & (ad.date <= end)].groupby(["date", "platform"], as_index=False).spend_sar.sum()
    st.plotly_chart(px.bar(a, x="date", y="spend_sar", color="platform", title="Ad spend by platform (SAR)",
                           labels={"spend_sar": "SAR", "date": ""}), use_container_width=True)

# ---- catalogue & shipping snapshot -------------------------------------------
snap_cols = ["published_products", "zero_sales_products", "out_of_stock_products", "stuck_shipments", "stuck_value_sar"]
snap = kpi[kpi[[c for c in snap_cols if c in kpi]].notna().any(axis=1)] if any(c in kpi for c in snap_cols) else pd.DataFrame()
if not snap.empty:
    st.divider()
    st.subheader("Catalogue & shipping (latest)")
    latest = snap.sort_values("date").groupby("brand").tail(1)
    latest = latest.assign(brand=latest.brand.map(BRANDS))[["brand", "date"] + [c for c in snap_cols if c in latest]]
    st.dataframe(latest, hide_index=True, use_container_width=True)

# ---- alerts ------------------------------------------------------------------
st.divider()
st.subheader("Alerts")
if alerts.empty:
    st.caption("مفيش تنبيهات محفوظة لسه.")
else:
    sev = st.multiselect("Severity", list(SEV_ICON), default=["critical", "warning"])
    a = alerts[alerts.severity.isin(sev)].copy()
    a["severity"] = a.severity.map(lambda s: f"{SEV_ICON[s]} {s}")
    a["brand"] = a.brand.map(BRANDS)
    st.dataframe(a[["run_date", "brand", "severity", "message", "action"]], hide_index=True, use_container_width=True)
