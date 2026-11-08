"""Ops Dashboard — Overview for all brands (Streamlit, reads Supabase).

Run locally:   streamlit run app.py
Data source:   Supabase via st.secrets["supabase"] (url, service_key) or
               ~/.config/ops-dashboard/supabase.json. With neither, it runs in demo mode
               on the Morning Ops cache (Natcho only) so the layout can be previewed.
Optional:      st.secrets["app_password"] gates the app behind one shared password.
"""
import hmac
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
    entered = st.text_input("Password", type="password", help="اكتب الباسورد واضغط Enter")
    if entered and hmac.compare_digest(entered, pw):
        st.session_state.ok = True
        st.rerun()
    if entered:
        st.error("الباسورد غلط.")
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


def table(name, params):
    """Optional v2 tables: an empty frame if Supabase isn't connected or the table is missing."""
    if creds() is None:
        return pd.DataFrame()
    try:
        return fetch(name, tuple(params))
    except Exception:
        return pd.DataFrame()


def nums(df, cols):
    for c in cols:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


RESTOCK_ICON = {"critical": "🔴 critical", "warning": "🟠 warning", "watch": "🟡 watch"}

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

tab_over, tab_ads, tab_prod, tab_seo, tab_gsc = st.tabs(
    ["📊 Overview", "💸 Ads & ROAS", "📦 Products & Restock", "🩺 SEO health", "🔎 Search Console"])

with tab_over:
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
                            labels={"revenue_sar": "SAR", "date": ""}), width="stretch")
    m = cur[cur.ad_spend_sar.fillna(0) > 0].assign(mer=lambda d: d.revenue_sar / d.ad_spend_sar)
    m["brand"] = m.brand.map(BRANDS)
    t2.plotly_chart(px.line(m, x="date", y="mer", color="brand", title="MER per day (revenue ÷ ad spend)",
                            labels={"mer": "MER", "date": ""}), width="stretch")

    if not ad.empty:
        ad["date"] = pd.to_datetime(ad["date"]).dt.date
        ad["spend_sar"] = pd.to_numeric(ad["spend_sar"], errors="coerce")
        a = ad[(ad.date >= start) & (ad.date <= end)].groupby(["date", "platform"], as_index=False).spend_sar.sum()
        st.plotly_chart(px.bar(a, x="date", y="spend_sar", color="platform", title="Ad spend by platform (SAR)",
                               labels={"spend_sar": "SAR", "date": ""}), width="stretch")

    # ---- catalogue & shipping snapshot -------------------------------------------
    snap_cols = ["published_products", "zero_sales_products", "out_of_stock_products", "stuck_shipments", "stuck_value_sar"]
    snap = kpi[kpi[[c for c in snap_cols if c in kpi]].notna().any(axis=1)] if any(c in kpi for c in snap_cols) else pd.DataFrame()
    if not snap.empty:
        st.divider()
        st.subheader("Catalogue & shipping (latest)")
        latest = snap.sort_values("date").groupby("brand").tail(1)
        latest = latest.assign(brand=latest.brand.map(BRANDS))[["brand", "date"] + [c for c in snap_cols if c in latest]]
        st.dataframe(latest, hide_index=True, width="stretch")

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
        st.dataframe(a[["run_date", "brand", "severity", "message", "action"]], hide_index=True, width="stretch")


# ---- ads & ROAS --------------------------------------------------------------
with tab_ads:
    if ad.empty:
        st.caption("مفيش داتا إعلانات.")
    else:
        for col in ["conv_value_sar", "conversions", "clicks", "impressions"]:
            ad[col] = pd.to_numeric(ad[col], errors="coerce")
        cur_ad = ad[(ad.date >= start) & (ad.date <= end)]
        prev_ad = ad[(ad.date >= prev_start) & (ad.date < start)]
        rev_by_brand = cur.groupby("brand").revenue_sar.sum()
        st.caption("ROAS = قيمة التحويلات اللي المنصة نفسها بتقولها ÷ الصرف (بيتعد مرتين بين المنصات). "
                   "MER = إيراد المتجر الفعلي ÷ كل الصرف — ده الرقم الحقيقي.")
        p = cur_ad.groupby("platform")[["spend_sar", "conv_value_sar", "conversions", "clicks", "impressions"]].sum()
        pp = prev_ad.groupby("platform")[["spend_sar", "conv_value_sar"]].sum()
        p["roas"] = p.conv_value_sar / p.spend_sar.where(p.spend_sar > 0)
        p["prev_roas"] = (pp.conv_value_sar / pp.spend_sar.where(pp.spend_sar > 0)).reindex(p.index)
        p["cpa_sar"] = p.spend_sar / p.conversions.where(p.conversions > 0)
        p["cpc_sar"] = p.spend_sar / p.clicks.where(p.clicks > 0)
        p["share_of_spend"] = p.spend_sar / p.spend_sar.sum()
        total_spend = p.spend_sar.sum()
        k = st.columns(4)
        k[0].metric("Total spend", money(total_spend), delta(total_spend, pp.spend_sar.sum()), delta_color="inverse")
        k[1].metric("Platform ROAS (all)", f"{p.conv_value_sar.sum() / total_spend:.2f}" if total_spend else "—")
        nat_rev = rev_by_brand.get("natcho", 0)
        k[2].metric("Natcho MER", f"{nat_rev / total_spend:.2f}" if total_spend else "—")
        best = p.roas.idxmax() if p.roas.notna().any() else "—"
        k[3].metric("Best ROAS platform", best)
        cols = st.columns(len(p) or 1)
        for i, (plat, r) in enumerate(p.iterrows()):
            cols[i].metric(plat, f"ROAS {r.roas:.2f}" if pd.notna(r.roas) else "ROAS —",
                           delta(r.roas, r.prev_roas) if pd.notna(r.roas) else None)
            cols[i].caption(f"صرف {money(r.spend_sar)} · CPA {r.cpa_sar:,.0f} SAR" if pd.notna(r.cpa_sar)
                            else f"صرف {money(r.spend_sar)}")
        show = p.reset_index()[["platform", "spend_sar", "share_of_spend", "conv_value_sar", "roas", "prev_roas",
                                "conversions", "cpa_sar", "clicks", "cpc_sar", "impressions"]]
        st.dataframe(show, hide_index=True, width="stretch", column_config={
            "spend_sar": st.column_config.NumberColumn("Spend SAR", format="%.0f"),
            "share_of_spend": st.column_config.ProgressColumn("Share", format="%.0f%%", min_value=0, max_value=1),
            "conv_value_sar": st.column_config.NumberColumn("Conv. value SAR", format="%.0f"),
            "roas": st.column_config.NumberColumn("ROAS", format="%.2f"),
            "prev_roas": st.column_config.NumberColumn("ROAS prev", format="%.2f"),
            "cpa_sar": st.column_config.NumberColumn("CPA", format="%.0f"),
            "cpc_sar": st.column_config.NumberColumn("CPC", format="%.2f")})
        r = cur_ad.groupby(["date", "platform"], as_index=False)[["spend_sar", "conv_value_sar"]].sum()
        r["roas"] = r.conv_value_sar / r.spend_sar.where(r.spend_sar > 0)
        c1, c2 = st.columns(2)
        c1.plotly_chart(px.line(r, x="date", y="roas", color="platform", title="ROAS per day",
                                labels={"date": ""}), width="stretch")
        c2.plotly_chart(px.bar(r, x="date", y="spend_sar", color="platform", title="Spend per day (SAR)",
                               labels={"spend_sar": "SAR", "date": ""}), width="stretch")

        camp = nums(table("ad_campaign_daily", [("date", f"gte.{start}"), ("date", f"lte.{end}")]),
                    ["spend_sar", "conv_value_sar", "conversions", "clicks"])
        if not camp.empty:
            st.subheader("Campaigns")
            c = camp.groupby(["platform", "campaign"], as_index=False)[["spend_sar", "conv_value_sar", "conversions"]].sum()
            c = c[c.spend_sar > 0]
            c["roas"] = c.conv_value_sar / c.spend_sar
            avg = c.conv_value_sar.sum() / c.spend_sar.sum() if c.spend_sar.sum() else 0
            c["action"] = c.apply(lambda x: "🔴 وقف/راجع — صرف بدون نتيجة" if x.conv_value_sar == 0 and x.spend_sar >= 300
                                  else "🟠 أقل من المتوسط بكتير — قلل الميزانية أو غيّر الكرييتف" if x.roas < avg * 0.6
                                  else "🟢 كسبان — زوّد الميزانية تدريجياً (20%)" if x.roas > avg * 1.3 and x.spend_sar >= 300
                                  else "", axis=1)
            st.caption(f"متوسط ROAS للكامبينز في الفترة: {avg:.2f}")
            st.dataframe(c.sort_values("spend_sar", ascending=False), hide_index=True, width="stretch",
                         column_config={"spend_sar": st.column_config.NumberColumn("Spend", format="%.0f"),
                                        "conv_value_sar": st.column_config.NumberColumn("Conv. value", format="%.0f"),
                                        "roas": st.column_config.NumberColumn("ROAS", format="%.2f")})


# ---- products & restock -------------------------------------------------------
with tab_prod:
    ps = nums(table("product_status", []), ["stock", "units_7d", "units_30d", "revenue_30d", "velocity_day",
                                            "days_cover", "reorder_qty", "seo_score", "price_sar"])
    if ps.empty:
        st.caption("مفيش داتا منتجات لسه.")
    else:
        brand = st.radio("Brand", [b for b in BRANDS if b in set(ps.brand)], format_func=BRANDS.get,
                         horizontal=True, key="prod_brand")
        b = ps[ps.brand == brand]
        st.caption(f"Snapshot: {b.snapshot_date.max()} · سرعة البيع = متوسط آخر 14 يوم · "
                   "الكمية المقترحة تكفي 30 يوم")
        rs = b[b.restock.notna()].copy()
        k = st.columns(4)
        k[0].metric("🔴 Restock now", int((rs.restock == "critical").sum()))
        k[1].metric("🟠 < 14 days", int((rs.restock == "warning").sum()))
        k[2].metric("🟡 < 21 days", int((rs.restock == "watch").sum()))
        k[3].metric("Out of stock (published)", int(((b.stock <= 0) & (b.infinite != True)).sum()))
        st.subheader("⚠️ Restock alerts — منتجات بتبيع ومحتاجة مخزون")
        if brand != "natcho":
            st.info("Carina لسه مفيش سرعة بيع لكل منتج (محتاج order lines من زد) — المخزون بس متاح.")
        if rs.empty:
            st.success("مفيش منتج بيبيع ومخزونه قرب يخلص.")
        else:
            rs["restock"] = rs.restock.map(RESTOCK_ICON)
            rs["lost_per_day"] = (rs.revenue_30d / 30).where(rs.stock <= 0)
            st.dataframe(rs.sort_values(["days_cover", "velocity_day"], ascending=[True, False])[
                ["restock", "name", "sku", "stock", "velocity_day", "days_cover", "reorder_qty", "units_30d",
                 "revenue_30d", "lost_per_day", "url"]], hide_index=True, width="stretch",
                column_config={"url": st.column_config.LinkColumn("Link", display_text="open"),
                               "velocity_day": st.column_config.NumberColumn("Units/day", format="%.2f"),
                               "days_cover": st.column_config.NumberColumn("Days left", format="%.1f"),
                               "reorder_qty": st.column_config.NumberColumn("Order qty"),
                               "lost_per_day": st.column_config.NumberColumn("SAR lost/day (OOS)", format="%.0f")})

        pdaily = nums(table("product_daily", [("brand", f"eq.{brand}"), ("date", f"gte.{prev_start}")]),
                      ["units", "revenue_sar"])
        if not pdaily.empty:
            pdaily["date"] = pd.to_datetime(pdaily.date).dt.date
            st.subheader("📈 Daily product analysis")
            day = st.date_input("Day", value=end, min_value=start, max_value=end, key="prod_day")
            d = pdaily[pdaily.date == day].groupby(["sku", "name"], as_index=False)[["units", "revenue_sar"]].sum()
            base = (pdaily[(pdaily.date < day) & (pdaily.date >= day - timedelta(days=28))]
                    .groupby("sku")[["units", "revenue_sar"]].sum() / 28).add_suffix("_avg28")
            d = d.join(base, on="sku")
            d["vs_avg"] = d.revenue_sar / d.revenue_sar_avg28.where(d.revenue_sar_avg28 > 0) - 1
            c1, c2, c3 = st.columns(3)
            c1.metric("Products sold", len(d))
            c2.metric("Units", f"{d.units.sum():,.0f}")
            c3.metric("Revenue", money(d.revenue_sar.sum()))
            st.dataframe(d.sort_values("revenue_sar", ascending=False).head(50), hide_index=True,
                         width="stretch", column_config={
                             "revenue_sar": st.column_config.NumberColumn("Revenue", format="%.0f"),
                             "units_avg28": st.column_config.NumberColumn("Units/day avg 28d", format="%.2f"),
                             "revenue_sar_avg28": st.column_config.NumberColumn("Rev/day avg 28d", format="%.0f"),
                             "vs_avg": st.column_config.NumberColumn("vs avg", format="%+.0f%%")})
            w = pdaily[(pdaily.date >= start) & (pdaily.date <= end)]
            pw = pdaily[(pdaily.date >= prev_start) & (pdaily.date < start)]
            m = (w.groupby(["sku", "name"]).revenue_sar.sum().rename("revenue").to_frame()
                 .join(pw.groupby("sku").revenue_sar.sum().rename("prev_revenue"), on="sku").fillna(0).reset_index())
            m["change"] = m.revenue - m.prev_revenue
            c1, c2 = st.columns(2)
            c1.markdown(f"**🚀 Rising** (last {days}d vs before)")
            c1.dataframe(m.nlargest(15, "change")[["name", "revenue", "prev_revenue", "change"]], hide_index=True,
                         width="stretch")
            c2.markdown("**📉 Falling**")
            c2.dataframe(m.nsmallest(15, "change")[["name", "revenue", "prev_revenue", "change"]], hide_index=True,
                         width="stretch")
            dead = b[(b.units_30d.fillna(0) == 0) & (b.stock > 0)]
            with st.expander(f"🧊 Published with stock but 0 sales in 30 days ({len(dead)})"):
                st.dataframe(dead[["name", "sku", "stock", "price_sar", "seo_score", "gsc_impressions", "url"]]
                             .sort_values("stock", ascending=False), hide_index=True, width="stretch",
                             column_config={"url": st.column_config.LinkColumn("Link", display_text="open")})


# ---- SEO health ----------------------------------------------------------------
with tab_seo:
    seo = nums(table("seo_daily", [("order", "date")]), ["published", "avg_score", "low_score", "missing_title",
                                                         "missing_description", "missing_keywords", "no_images",
                                                         "single_image", "duplicate_titles", "url_errors",
                                                         "slow_pages", "merchant_disapproved"])
    ps = table("product_status", [])
    if seo.empty or ps.empty:
        st.caption("مفيش داتا SEO لسه.")
    else:
        ps = nums(ps, ["seo_score", "units_30d", "revenue_30d", "gsc_impressions", "gsc_clicks", "gsc_position"])
        brand = st.radio("Brand", [b for b in BRANDS if b in set(seo.brand)], format_func=BRANDS.get,
                         horizontal=True, key="seo_brand")
        s = seo[seo.brand == brand].sort_values("date")
        last, first = s.iloc[-1], s.iloc[0]
        k = st.columns(5)
        k[0].metric("SEO score (avg)", f"{last.avg_score:.0f}/100",
                    f"{last.avg_score - s.iloc[-2].avg_score:+.1f}" if len(s) > 1 else None)
        k[1].metric("Products < 70", int(last.low_score))
        k[2].metric("No SEO title/desc", int(max(last.missing_title, last.missing_description)))
        k[3].metric("Single image", int(last.single_image))
        k[4].metric("Duplicate titles", int(last.duplicate_titles))
        if brand == "natcho":
            k = st.columns(3)
            k[0].metric("Broken / moved URLs", int(last.url_errors or 0))
            k[1].metric("Slow pages", int(last.slow_pages or 0))
            k[2].metric("Merchant Center disapproved", int(last.merchant_disapproved or 0))
        if len(s) > 1:
            st.plotly_chart(px.line(s, x="date", y="avg_score", title="SEO score trend"), width="stretch")

        b = ps[ps.brand == brand].copy()
        st.subheader("🛠️ Products to fix — مرتبة حسب الأهمية")
        st.caption("الأولوية = منتجات بتبيع أو بتظهر في جوجل ودرجتها ضعيفة. صلّح من زد ← المنتج ← تحسين محركات البحث.")
        b["priority"] = (100 - b.seo_score) * (1 + b.revenue_30d.fillna(0) / 500 + b.gsc_impressions.fillna(0) / 5000)
        issue = st.selectbox("Filter by issue", ["كل المشاكل", "مفيش SEO title", "مفيش meta description",
                                                 "SEO إنجليزي ناقص", "مفيش keywords", "مفيش صور", "صورة واحدة بس",
                                                 "الوصف المختصر", "مكرر", "الـ title طويل", "الـ description قصيرة",
                                                 "Google Merchant", "الصفحة:"], key="seo_issue")
        f = b[b.seo_issues.notna()]
        if issue != "كل المشاكل":
            f = f[f.seo_issues.str.contains(issue, regex=False)]
        st.caption(f"{len(f)} منتج")
        st.dataframe(f.sort_values("priority", ascending=False)[
            ["seo_score", "name", "seo_issues", "units_30d", "revenue_30d", "gsc_impressions", "gsc_position", "url"]],
            hide_index=True, width="stretch", column_config={
                "seo_score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
                "url": st.column_config.LinkColumn("Link", display_text="open")})
        counts = (b.seo_issues.dropna().str.split("، ").explode()
                  .str.replace(r"^الصفحة:.*", "مشكلة في الصفحة (URL health)", regex=True).value_counts())
        st.plotly_chart(px.bar(counts.sort_values(), orientation="h", title="Issues across the catalogue",
                               labels={"value": "products", "index": ""}), width="stretch")


# ---- Search Console ------------------------------------------------------------
with tab_gsc:
    gd = nums(table("gsc_daily", [("date", f"gte.{prev_start}"), ("order", "date")]),
              ["clicks", "impressions", "ctr", "position"])
    gq = nums(table("gsc_queries", []), ["clicks", "impressions", "ctr", "position", "prev_clicks",
                                         "prev_impressions", "prev_position"])
    if gd.empty and gq.empty:
        st.caption("مفيش داتا Search Console لسه.")
    else:
        st.caption("Natcho · Google Search Console (organic). جوجل بيتأخر يومين في الداتا.")
        if not gd.empty:
            gd["date"] = pd.to_datetime(gd.date).dt.date
            gc, gp = gd[(gd.date >= start) & (gd.date <= end)], gd[(gd.date >= prev_start) & (gd.date < start)]
            wpos = lambda x: (x.position * x.impressions).sum() / x.impressions.sum() if x.impressions.sum() else 0
            k = st.columns(4)
            k[0].metric("Clicks", f"{gc.clicks.sum():,.0f}", delta(gc.clicks.sum(), gp.clicks.sum()))
            k[1].metric("Impressions", f"{gc.impressions.sum():,.0f}", delta(gc.impressions.sum(), gp.impressions.sum()))
            ctr_c = gc.clicks.sum() / gc.impressions.sum() if gc.impressions.sum() else 0
            ctr_p = gp.clicks.sum() / gp.impressions.sum() if gp.impressions.sum() else 0
            k[2].metric("CTR", f"{ctr_c:.2%}", delta(ctr_c, ctr_p))
            k[3].metric("Avg position", f"{wpos(gc):.1f}", f"{wpos(gc) - wpos(gp):+.1f}" if len(gp) else None,
                        delta_color="inverse")
            st.plotly_chart(px.line(gc, x="date", y=["clicks", "impressions"], title="Organic clicks & impressions",
                                    labels={"date": "", "value": ""}), width="stretch")
        if not gq.empty:
            st.subheader("🎯 Keyword actions")
            st.caption(f"آخر 28 يوم لحد {gq.period_end.max()} مقارنة بالـ 28 يوم اللي قبلهم.")
            opp = gq[gq.opportunity.notna()]
            counts = opp.opportunity.value_counts()
            cols = st.columns(len(counts) or 1)
            for i, (o, n) in enumerate(counts.items()):
                cols[i].metric(o, n)
            pick = st.multiselect("Type", list(counts.index), default=list(counts.index), key="gsc_type")
            st.dataframe(opp[opp.opportunity.isin(pick)].sort_values("impressions", ascending=False)[
                ["opportunity", "query", "clicks", "prev_clicks", "impressions", "ctr", "position", "prev_position",
                 "action"]], hide_index=True, width="stretch", column_config={
                    "ctr": st.column_config.NumberColumn("CTR", format="%.3f"),
                    "position": st.column_config.NumberColumn("Pos", format="%.1f"),
                    "prev_position": st.column_config.NumberColumn("Prev pos", format="%.1f"),
                    "action": st.column_config.TextColumn("Action", width="large")})
            c1, c2 = st.columns(2)
            nb = gq[~gq.is_brand.astype(bool)]
            c1.markdown("**Top non-brand queries (clicks)**")
            c1.dataframe(nb.nlargest(25, "clicks")[["query", "clicks", "impressions", "position"]], hide_index=True,
                         width="stretch")
            c2.markdown("**Brand vs non-brand clicks**")
            split = gq.assign(type=gq.is_brand.astype(bool).map({True: "Brand (ناتشو)", False: "Non-brand"}))
            c2.plotly_chart(px.pie(split.groupby("type", as_index=False).clicks.sum(), names="type", values="clicks"),
                            width="stretch")
            q = st.text_input("Search a keyword", key="gsc_q")
            if q:
                st.dataframe(gq[gq["query"].str.contains(q, case=False, regex=False)].sort_values("impressions", ascending=False)[
                    ["query", "clicks", "prev_clicks", "impressions", "ctr", "position", "prev_position", "action"]],
                    hide_index=True, width="stretch")
