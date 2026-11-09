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

import ui

CREDS = Path.home() / ".config" / "ops-dashboard" / "supabase.json"
BRANDS = {"natcho": "Natcho", "carina": "Carina", "genz": "GenZ"}
SEV_ICON = {"critical": "🔴", "warning": "🟠", "watch": "🟡", "win": "🟢"}

st.set_page_config(page_title="Konoz Ops", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")


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
SEV_ORDER = ["critical", "warning", "watch", "win"]
SEV_COLOR = {"critical": ui.RED, "warning": "#FF9F43", "watch": ui.YELLOW, "win": ui.GREEN}
PLATFORM_ICON = {"Google Ads": ("G", "#FFFFFF", "#4285F4"), "Meta": ("∞", "#0866FF", "#FFFFFF"),
                 "Snapchat": ("S", "#FFFC00", "#111111"), "TikTok": ("♪", "#000000", "#FFFFFF")}
PERIODS = {7: "7D", 14: "14D", 30: "1M", 90: "3M", 180: "6M", 365: "1Y"}

gate()
ui.inject()

h_logo, h_health, h_brand, h_period = st.columns([2.2, 3, 2.2, 3.4], vertical_alignment="center")
h_logo.markdown('<div class="k-logo"><i></i>Konoz Ops</div>', unsafe_allow_html=True)
days = h_period.segmented_control("Period", list(PERIODS), format_func=PERIODS.get, default=30,
                                  label_visibility="collapsed", key="period") or 30
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

brands_here = [b for b in BRANDS if b in set(kpi.brand)]
brand = h_brand.segmented_control("Brand", brands_here, format_func=BRANDS.get, default=brands_here[0],
                                  label_visibility="collapsed", key="brand") or brands_here[0]

if not ad.empty:
    ad["date"] = pd.to_datetime(ad["date"]).dt.date
    for col in ["spend_sar", "conv_value_sar", "conversions", "clicks", "impressions"]:
        ad[col] = pd.to_numeric(ad[col], errors="coerce")
    ad = ad[ad.brand == brand]
if not alerts.empty:
    alerts = alerts[alerts.brand == brand]

# health score = 100 minus the weight of the latest run's alerts
latest_alerts = alerts[alerts.run_date == alerts.run_date.max()] if not alerts.empty else alerts
health = max(0, 100 - sum({"critical": 15, "warning": 7, "watch": 3}.get(s, 0) for s in latest_alerts.get("severity", [])))
h_health.markdown(f'<div class="k-pill">{ui.ticks(health)}<b style="color:#fff">{health}</b>'
                  f'<span style="color:#aaa">Health Score</span></div>', unsafe_allow_html=True)

seo_all = nums(table("seo_daily", [("brand", f"eq.{brand}"), ("order", "date")]),
               ["published", "avg_score", "low_score", "missing_title", "missing_description", "missing_keywords",
                "no_images", "single_image", "duplicate_titles", "url_errors", "slow_pages", "merchant_disapproved"])
ps_all = nums(table("product_status", [("brand", f"eq.{brand}")]),
              ["stock", "units_7d", "units_30d", "revenue_30d", "velocity_day", "days_cover", "reorder_qty",
               "seo_score", "price_sar", "gsc_impressions", "gsc_clicks", "gsc_position"])

st.write("")
tab_over, tab_ads, tab_prod, tab_seo, tab_gsc, tab_content = st.tabs(
    ["Overview", "Ads & ROAS", "Products & Restock", "SEO health", "Search Console", "Content & Insights"])

# ---- overview ------------------------------------------------------------------
with tab_over:
    cb, pb = cur[cur.brand == brand], prev[prev.brand == brand]
    rev, prev_rev = cb.revenue_sar.sum(), pb.revenue_sar.sum()
    orders, prev_orders = cb.orders.sum(), pb.orders.sum()
    aov = rev / orders if orders else 0
    prev_aov = prev_rev / prev_orders if prev_orders else 0
    spend, prev_spend = cb.ad_spend_sar.sum(), pb.ad_spend_sar.sum()
    mer = rev / spend if spend else None
    prev_mer = prev_rev / prev_spend if prev_spend else None
    ch = lambda c, p: (c - p) / p if p else None

    left, right = st.columns([5, 7.4], gap="medium")
    with left.container(key="card_total", height=470, border=False):
        tiles = [ui.mini("Orders", f"{orders:,.0f}", ui.GREEN, ch(orders, prev_orders)),
                 ui.mini("AOV", f"{aov:,.0f} SAR", ui.ORANGE, ch(aov, prev_aov))]
        if spend:
            tiles += [ui.mini("Ad spend", money(spend), ui.YELLOW, ch(spend, prev_spend), inverse=True),
                      ui.mini("MER", f"{mer:.2f}", ui.WHITE, ch(mer, prev_mer) if prev_mer else None)]
        else:
            oos = int(((ps_all.stock <= 0) & (ps_all.infinite != True)).sum()) if not ps_all.empty else 0
            tiles += [ui.mini("Published", f"{len(ps_all):,}", ui.YELLOW),
                      ui.mini("Out of stock", f"{oos:,}", ui.WHITE)]
        ui.html(f'<div class="k-label">Total revenue · {BRANDS[brand]}</div>'
                f'<div class="k-big">{rev:,.0f} <span style="font-size:1.2rem;color:#aaa">SAR</span>'
                f'{ui.badge(ch(rev, prev_rev))}</div>'
                f'<div class="k-sub" style="margin-top:6px">{start:%b %d} → {end:%b %d} · vs previous {days} days</div>'
                f'<div class="k-grid">{"".join(tiles)}</div>')

    with right.container(key="hero", height=470, border=False):
        daily = cb.groupby("date", as_index=False).revenue_sar.sum()
        per_day = rev / days
        ui.html(f'<div class="k-hero-t">Revenue per day</div>'
                f'<div class="k-hero-v">{per_day:,.0f} SAR{ui.badge(ch(rev, prev_rev))}</div>')
        st.plotly_chart(ui.hero_chart(pd.to_datetime(daily.date), daily.revenue_sar), width="stretch",
                        config={"displayModeBar": False}, key="hero_chart")

    # watchlist row
    with st.container(key="card_watch", border=False):
        if not ad.empty and ad.spend_sar.sum() > 0:
            ca = ad[(ad.date >= start) & (ad.date <= end)]
            pa = ad[(ad.date >= prev_start) & (ad.date < start)]
            items = []
            # every known platform stays on the row: a paused one shows when it last spent
            for plat in [p for p in PLATFORM_ICON if p in set(ad.platform)] + \
                        [p for p in sorted(set(ad.platform)) if p not in PLATFORM_ICON]:
                g, pg = ca[ca.platform == plat], pa[pa.platform == plat]
                s_, v_ = g.spend_sar.sum(), g.conv_value_sar.sum()
                ic, bg, fg = PLATFORM_ICON.get(plat, (plat[:1], "#333", "#fff"))
                if not s_:
                    spent = table("ad_spend_daily", [("brand", f"eq.{brand}"), ("platform", f"eq.{plat}"),
                                                     ("spend_sar", "gt.0"), ("order", "date.desc"), ("limit", "1")])
                    since = (f"since {pd.to_datetime(spent.date.iloc[0]):%b %d}" if not spent.empty
                             else "no spend")
                    items.append(ui.watch_item(ic, bg, fg, f"{plat} · {since}", "Paused"))
                    continue
                d_ = g.groupby("date")[["spend_sar", "conv_value_sar", "conversions"]].sum()
                if not v_:
                    # no purchase value reported (TikTok today): ROAS can't be computed, show CPA instead
                    cpa = s_ / g.conversions.sum() if g.conversions.sum() else None
                    pcpa = pg.spend_sar.sum() / pg.conversions.sum() if pg.conversions.sum() else None
                    series = d_.spend_sar.rolling(3, min_periods=1).mean()
                    items.append(ui.watch_item(ic, bg, fg, f"{plat} · CPA (no value tracked)",
                                               f"{cpa:,.0f} SAR" if cpa else money(s_),
                                               ch(cpa, pcpa) if cpa and pcpa else None, list(series.tail(21)),
                                               inverse=True))
                    continue
                roas = v_ / s_
                proas = pg.conv_value_sar.sum() / pg.spend_sar.sum() if pg.spend_sar.sum() else None
                series = (d_.conv_value_sar / d_.spend_sar.where(d_.spend_sar > 0)).rolling(3, min_periods=1).mean()
                items.append(ui.watch_item(ic, bg, fg, f"{plat} · ROAS", f"{roas:.2f}",
                                           ch(roas, proas) if proas else None, list(series.tail(21))))
            ui.html(ui.watchlist("Ad platforms", items))
        else:
            seo_last = seo_all.iloc[-1] if not seo_all.empty else None
            od = cb.groupby("date").orders.sum()
            items = [ui.watch_item("◎", "#fff", "#111", "Orders / day", f"{orders / days:.1f}",
                                   ch(orders, prev_orders), list(od.tail(21))),
                     ui.watch_item("▣", ui.YELLOW, "#111", "Published", f"{len(ps_all):,}")]
            if seo_last is not None:
                items += [ui.watch_item("✦", ui.GREEN, "#111", "SEO score", f"{seo_last.avg_score:.0f}/100"),
                          ui.watch_item("≡", ui.ORANGE, "#fff", "Duplicate SEO titles", f"{int(seo_last.duplicate_titles):,}")]
            ui.html(ui.watchlist("Store", items))

    b1, b2, b3 = st.columns([2.35, 1.6, 1.6], gap="medium")
    with b1.container(key="card_alloc", height=360, border=False):
        if not ad.empty and ad.spend_sar.sum() > 0:
            ca = ad[(ad.date >= start) & (ad.date <= end)].groupby("platform").spend_sar.sum().sort_values(ascending=False)
            share = ca / ca.sum() if ca.sum() else ca
            colors = [(ui.ORANGE, "#fff"), (ui.YELLOW, "#111"), (ui.WHITE, "#111"), ("#5A5A5A", "#fff")]
            ui.html(f'<div class="k-head">Spend allocation<span class="k-sub">{money(ca.sum())}</span></div>'
                    + ui.bars([(p, f, *colors[i % 4]) for i, (p, f) in enumerate(share.items())]))
        else:
            n = len(ps_all) or 1
            stock_ok = ((ps_all.stock > 0) | (ps_all.infinite == True)).sum() / n if not ps_all.empty else 0
            seo_ok = (ps_all.seo_score >= 70).sum() / n if not ps_all.empty else 0
            img_ok = 1 - (seo_all.iloc[-1].single_image / n) if not seo_all.empty else 0
            uniq = 1 - (seo_all.iloc[-1].duplicate_titles / n) if not seo_all.empty else 0
            ui.html('<div class="k-head">Catalogue health<span class="k-sub">% of published products</span></div>'
                    + ui.bars([("In stock", stock_ok, ui.ORANGE, "#fff"), ("SEO ≥ 70", seo_ok, ui.YELLOW, "#111"),
                               ("2+ images", img_ok, ui.WHITE, "#111"), ("Unique title", uniq, "#5A5A5A", "#fff")]))

    with b2.container(key="card_gauge", height=360, border=False):
        if seo_all.empty:
            ui.html('<div class="k-head">SEO Health</div><div class="k-sub">مفيش داتا SEO لسه.</div>')
        else:
            last = seo_all.iloc[-1]
            note = (f"Score {last.avg_score - seo_all.iloc[-2].avg_score:+.1f} vs last check" if len(seo_all) > 1
                    else f"{int(last.low_score)} products below 70")
            ui.html(f'<div class="k-head">SEO Health<span class="k-arrow">↗</span></div>'
                    f'<div class="k-score">{last.avg_score:.0f} <small>/100</small></div>{ui.gauge(last.avg_score)}'
                    f'<div class="k-sub" style="text-align:center;margin-top:-8px">{note}</div>')

    with b3.container(key="cardlight_insight", height=360, border=False):
        if latest_alerts.empty:
            text = "مفيش تنبيهات في آخر تشغيل للـ Morning Ops."
        else:
            top = latest_alerts.assign(o=latest_alerts.severity.map(SEV_ORDER.index)).sort_values("o").iloc[0]
            act = top.action if isinstance(top.action, str) else ""
            text = f'<div dir="auto"><b>{top.message}</b><br>{act}</div>'
        counts = latest_alerts.severity.value_counts() if not latest_alerts.empty else pd.Series(dtype=int)
        chips = "".join(f'<div class="k-chip" style="background:{SEV_COLOR[s]}" title="{s}">{int(counts.get(s, 0))}</div>'
                        for s in SEV_ORDER)
        ui.html(f'<div class="k-head">✦ Today\'s insight<span class="k-arrow">↗</span></div>'
                f'<div class="k-insight">{text}</div><div class="k-chips">{chips}</div>')

    st.write("")
    with st.container(key="card_alerts", border=False):
        ui.html('<div class="k-head" style="margin-bottom:10px">Alerts</div>')
        if alerts.empty:
            st.caption("مفيش تنبيهات محفوظة لسه.")
        else:
            sev = st.multiselect("Severity", SEV_ORDER, default=["critical", "warning"], label_visibility="collapsed")
            a = alerts[alerts.severity.isin(sev)].copy()
            a["severity"] = a.severity.map(lambda s: f"{SEV_ICON[s]} {s}")
            st.dataframe(a[["run_date", "severity", "message", "action"]], hide_index=True, width="stretch")


# ---- ads & ROAS --------------------------------------------------------------
with tab_ads:
    if ad.empty or not ad.spend_sar.sum():
        st.caption(f"مفيش داتا إعلانات لـ {BRANDS[brand]}.")
    else:
        cur_ad = ad[(ad.date >= start) & (ad.date <= end)]
        prev_ad = ad[(ad.date >= prev_start) & (ad.date < start)]
        st.caption("ROAS = قيمة التحويلات اللي المنصة نفسها بتقولها ÷ الصرف (بيتعد مرتين بين المنصات). "
                   "MER = إيراد المتجر الفعلي ÷ كل الصرف — ده الرقم الحقيقي.")
        no_value = [p_ for p_, g_ in cur_ad.groupby("platform")
                    if g_.spend_sar.sum() > 0 and not g_.conv_value_sar.sum()]
        if no_value:
            st.warning(f"{'، '.join(no_value)}: فيه صرف بس مفيش قيمة مشتريات راجعة من المنصة — الـ ROAS مش محسوب. "
                       "اتأكد إن الـ pixel/Events API بيبعت value + currency مع الـ Purchase.")
        p = cur_ad.groupby("platform")[["spend_sar", "conv_value_sar", "conversions", "clicks", "impressions"]].sum()
        pp = prev_ad.groupby("platform")[["spend_sar", "conv_value_sar"]].sum()
        p["roas"] = p.conv_value_sar / p.spend_sar.where(p.spend_sar > 0)
        p["prev_roas"] = (pp.conv_value_sar / pp.spend_sar.where(pp.spend_sar > 0)).reindex(p.index)
        p["cpa_sar"] = p.spend_sar / p.conversions.where(p.conversions > 0)
        p["cpc_sar"] = p.spend_sar / p.clicks.where(p.clicks > 0)
        p["share_of_spend"] = p.spend_sar / p.spend_sar.sum()
        total_spend = p.spend_sar.sum()
        brand_rev = cur[cur.brand == brand].revenue_sar.sum()
        k = st.columns(4)
        k[0].metric("Total spend", money(total_spend), delta(total_spend, pp.spend_sar.sum()), delta_color="inverse")
        k[1].metric("Platform ROAS (all)", f"{p.conv_value_sar.sum() / total_spend:.2f}" if total_spend else "—")
        k[2].metric("MER (real)", f"{brand_rev / total_spend:.2f}" if total_spend else "—")
        k[3].metric("Best ROAS platform", p.roas.idxmax() if p.roas.notna().any() else "—")
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
            "share_of_spend": st.column_config.ProgressColumn("Share", format="percent", min_value=0, max_value=1),
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

        camp = nums(table("ad_campaign_daily", [("brand", f"eq.{brand}"), ("date", f"gte.{start}"),
                                                ("date", f"lte.{end}")]),
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
    b = ps_all
    if b.empty:
        st.caption("مفيش داتا منتجات لسه.")
    else:
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
                             "vs_avg": st.column_config.NumberColumn("vs avg", format="percent")})
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
        dead = b[(b.units_30d.fillna(0) == 0) & (b.stock > 0)] if brand == "natcho" else pd.DataFrame()
        if not dead.empty:
            with st.expander(f"🧊 Published with stock but 0 sales in 30 days ({len(dead)})"):
                st.dataframe(dead[["name", "sku", "stock", "price_sar", "seo_score", "gsc_impressions", "url"]]
                             .sort_values("stock", ascending=False), hide_index=True, width="stretch",
                             column_config={"url": st.column_config.LinkColumn("Link", display_text="open")})


# ---- SEO health ----------------------------------------------------------------
with tab_seo:
    if seo_all.empty or ps_all.empty:
        st.caption("مفيش داتا SEO لسه.")
    else:
        s = seo_all
        last = s.iloc[-1]
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

        b = ps_all.copy()
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
        fig = px.bar(counts.sort_values(), orientation="h", title="Issues across the catalogue",
                     labels={"value": "products", "index": ""})
        fig.update_traces(marker_color=ui.ORANGE, marker_cornerradius=6)
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, width="stretch")


# ---- Search Console ------------------------------------------------------------
with tab_gsc:
    gd = nums(table("gsc_daily", [("brand", f"eq.{brand}"), ("date", f"gte.{prev_start}"), ("order", "date")]),
              ["clicks", "impressions", "ctr", "position"])
    gq = nums(table("gsc_queries", [("brand", f"eq.{brand}")]),
              ["clicks", "impressions", "ctr", "position", "prev_clicks", "prev_impressions", "prev_position"])
    if gd.empty and gq.empty:
        st.caption(f"مفيش داتا Search Console لـ {BRANDS[brand]} لسه.")
    else:
        st.caption("Google Search Console (organic). جوجل بيتأخر يومين في الداتا.")
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
                    "ctr": st.column_config.NumberColumn("CTR", format="percent"),
                    "position": st.column_config.NumberColumn("Pos", format="%.1f"),
                    "prev_position": st.column_config.NumberColumn("Prev pos", format="%.1f"),
                    "action": st.column_config.TextColumn("Action", width="large")})
            c1, c2 = st.columns(2)
            nb = gq[~gq.is_brand.astype(bool)]
            c1.markdown("**Top non-brand queries (clicks)**")
            c1.dataframe(nb.nlargest(25, "clicks")[["query", "clicks", "impressions", "position"]], hide_index=True,
                         width="stretch")
            c2.markdown("**Brand vs non-brand clicks**")
            split = gq.assign(type=gq.is_brand.astype(bool).map({True: "Brand", False: "Non-brand"}))
            pie = px.pie(split.groupby("type", as_index=False).clicks.sum(), names="type", values="clicks", hole=0.6)
            c2.plotly_chart(pie, width="stretch")
            q = st.text_input("Search a keyword", key="gsc_q")
            if q:
                st.dataframe(gq[gq["query"].str.contains(q, case=False, regex=False)].sort_values("impressions", ascending=False)[
                    ["query", "clicks", "prev_clicks", "impressions", "ctr", "position", "prev_position", "action"]],
                    hide_index=True, width="stretch")


# ---- content plan & market insights ---------------------------------------------
PRIORITY_COLOR = {"high": ui.RED, "medium": "#FF9F43", "low": ui.YELLOW}
INSIGHT_TYPE = {"competitor_ad": "📣 إعلانات المنافسين", "customer_voice": "💬 كلام العملاء", "gap": "🕳️ فجوة في السوق",
                "moment": "📆 مناسبة", "positioning": "🧭 Positioning", "risk": "⚠️ مخاطرة",
                "competitor_social": "📱 سوشيال المنافسين"}

with tab_content:
    ins = table("content_insights", [("brand", f"eq.{brand}")])
    plan = table("content_plan", [("brand", f"eq.{brand}"), ("order", "date")])
    if ins.empty and plan.empty:
        st.caption(f"مفيش content plan ولا insights لـ {BRANDS[brand]} لسه.")
    else:
        today = date.today()
        if not plan.empty:
            plan["date"] = pd.to_datetime(plan.date).dt.date
        k = st.columns(4)
        k[0].metric("Insights", len(ins), f"{(ins.priority == 'high').sum()} high" if len(ins) else None,
                    delta_color="off")
        k[1].metric("Plan days", len(plan), f"{plan.date.min():%b %d} → {plan.date.max():%b %d}" if len(plan) else None,
                    delta_color="off")
        k[2].metric("Stronger hooks", int(plan.hook_alt.notna().sum()) if len(plan) else 0)
        if len(ins):
            k[3].metric("Last research", str(ins.updated.max()))

        # next posts: current hook vs the stronger alternative
        if len(plan):
            nxt = plan[plan.date >= today].head(3)
            if nxt.empty:
                nxt = plan.head(3)
            st.subheader("🪝 Next posts — الهوك الحالي vs الأقوى")
            for col, r in zip(st.columns(len(nxt)), nxt.itertuples()):
                with col.container(key=f"card_next_{r.day}", height=300, border=False):
                    ui.html(f'<div class="k-head"><span>{r.date:%a %d %b} · {r.content_type}</span>'
                            f'<span class="k-sub">{r.insight_ids or ""}</span></div>'
                            f'<div class="k-rtl" style="margin-top:14px">'
                            f'<div class="k-hook-old">{r.on_image or ""}</div>'
                            f'<div class="k-hook-new">{r.hook_alt or r.on_image or ""}</div>'
                            f'<div class="k-why">↑ {r.hook_alt_why or ""}</div>'
                            f'<div class="k-sub" style="margin-top:10px">{(r.product or "").split(" — ")[0]}</div></div>')

        # market insights: what competitors do, their weak spot, and what we do about it
        if len(ins):
            st.subheader("🔍 Market & competitor insights")
            st.caption("من إعلانات المنافسين الشغالة (Meta Ad Library)، ريفيوهات العملاء عند المنافسين، مواقعهم، وداتا GSC. "
                       "كل insight مربوط بأيام في الخطة.")
            types = [t for t in INSIGHT_TYPE if t in set(ins.type)]
            pick = st.segmented_control("Type", types, format_func=INSIGHT_TYPE.get, selection_mode="multi",
                                        default=types, label_visibility="collapsed", key="ins_type")
            f = ins[ins.type.isin(pick or types)].copy()
            f["rank"] = f.priority.map({"high": 0, "medium": 1, "low": 2})
            f = f.sort_values(["rank", "id"])
            cols = st.columns(3)
            for i, r in enumerate(f.itertuples()):
                c = PRIORITY_COLOR.get(r.priority, ui.YELLOW)
                days = f"أيام الخطة: {r.days}" if r.days else "استراتيجي (مش يوم محدد)"
                with cols[i % 3].container(key=f"card_ins_{r.id}", border=False):
                    ui.html(f'<div class="k-head"><span><span class="k-tag" style="background:{c};color:#111">{r.priority}</span>'
                            f'<span class="k-sub">{INSIGHT_TYPE.get(r.type, r.type)}</span></span>'
                            f'<span class="k-sub">{r.id}</span></div>'
                            f'<div class="k-rtl"><div class="k-ins-title">{r.finding}</div>'
                            f'<div class="k-ins-row"><b>نقطة الضعف:</b> {r.weakness}</div>'
                            f'<div class="k-ins-row"><b>هنعمل إيه:</b> {r.action}</div>'
                            f'<div class="k-sub" style="margin-top:8px">{r.competitor} · {days}</div></div>')

        # the competitors' posts that pulled the most views this week, with why and the format
        posts = table("competitor_posts", [("brand", f"eq.{brand}"), ("order", "week.desc,metric_value.desc")])
        if len(posts):
            st.subheader("🏆 Top competitor posts — الأعلى مشاهدات")
            weeks = list(dict.fromkeys(posts.week.astype(str)))
            wk = st.selectbox("Week", weeks, format_func=lambda w: f"أسبوع {w}", key="posts_week")
            w = posts[posts.week.astype(str) == wk]
            st.caption("Like-rate = لايكات ÷ مشاهدات. أقل من 0.1% مع ملايين المشاهدات = فيديو ممول، مش أورجانيك. "
                       "الأعلى في الـ like-rate هو اللي شغال فعلاً عند الجمهور. "
                       "Formats: " + " · ".join(f"{f} ({n})" for f, n in
                                             w.format.str.split(r" · | \(").str[0].value_counts().items()))
            cols = st.columns(3)
            for i, r in enumerate(w.itertuples()):
                with cols[i % 3].container(key=f"card_post_{r.id}", border=False):
                    if r.image_url:
                        st.image(r.image_url, width="stretch")
                    ui.html(f'<div class="k-head"><span>{r.competitor} · {r.platform}</span>'
                            f'<span class="k-sub">{r.id}</span></div>'
                            f'<div style="margin:6px 0"><span class="k-tag" style="background:{ui.ORANGE};color:#111">'
                            f'{r.format}</span></div>'
                            f'<div class="k-sub">{r.metric}</div>'
                            f'<div class="k-rtl"><div class="k-ins-title">{r.hook or ""}</div>'
                            f'<div class="k-ins-row"><b>جاب ترافيك ليه:</b> {r.why or ""}</div>'
                            f'<div class="k-ins-row"><b>ناخد منه إيه:</b> {r.takeaway or ""}</div>'
                            f'<div class="k-sub" style="margin-top:8px"><a href="{r.post_url}" target="_blank">افتح البوست ↗</a>'
                            f'</div></div>')

        # the plan itself, in the August v7 format + the hook columns
        if len(plan):
            st.subheader("📅 Content plan")
            weeks = list(dict.fromkeys(plan.week_theme.dropna()))
            wk = st.selectbox("Week", ["كل الشهر"] + weeks, key="plan_week")
            p = plan if wk == "كل الشهر" else plan[plan.week_theme == wk]
            st.dataframe(p[["date", "content_type", "hook_type", "product", "on_image", "hook_alt", "hook_alt_why",
                            "offer", "insight_ids", "visual_ref", "caption"]], hide_index=True, width="stretch",
                         column_config={
                             "date": st.column_config.DateColumn("Date", format="ddd DD MMM"),
                             "content_type": "Type", "hook_type": "Hook type", "product": "Product",
                             "on_image": st.column_config.TextColumn("Hook الحالي", width="medium"),
                             "hook_alt": st.column_config.TextColumn("Hook أقوى", width="medium"),
                             "hook_alt_why": "ليه أقوى", "offer": "العرض", "insight_ids": "Insight",
                             "visual_ref": "Visual", "caption": "Caption"})
            c1, c2 = st.columns(2)
            mix = p.content_type.value_counts().sort_values()
            fig = px.bar(mix, orientation="h", title="Content types", labels={"value": "posts", "index": ""})
            fig.update_traces(marker_color=ui.ORANGE, marker_cornerradius=6)
            fig.update_layout(showlegend=False)
            c1.plotly_chart(fig, width="stretch")
            hooks = p.hook_type.str.extract(r"\(([^)]+)\)")[0].fillna(p.hook_type).value_counts().sort_values()
            fig = px.bar(hooks, orientation="h", title="Hook types", labels={"value": "posts", "index": ""})
            fig.update_traces(marker_color=ui.YELLOW, marker_cornerradius=6)
            fig.update_layout(showlegend=False)
            c2.plotly_chart(fig, width="stretch")
            st.download_button("⬇️ Download plan (CSV)", p.drop(columns=["brand"]).to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"{brand}_content_plan.csv", mime="text/csv")
