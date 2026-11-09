-- Ops Dashboard schema (Supabase / Postgres).
-- Run once in Supabase → SQL Editor. Safe to re-run.
-- Only de-identified, aggregated data lives here: no customer names, phones or addresses.

create table if not exists brands (
  id   text primary key,          -- 'natcho', 'carina', 'genz'
  name text not null
);
insert into brands (id, name) values
  ('natcho', 'Natcho'), ('carina', 'Carina'), ('genz', 'GenZ')
on conflict (id) do nothing;

-- one row per brand per day; null = not measured for that brand
create table if not exists kpi_daily (
  brand                 text not null references brands(id),
  date                  date not null,
  orders                integer,
  revenue_sar           numeric(12,2),
  cancelled_orders      integer,
  ad_spend_sar          numeric(12,2),
  mer                   numeric(8,3),
  sessions              integer,
  ga4_conversions       integer,
  published_products    integer,
  zero_sales_products   integer,
  out_of_stock_products integer,
  stuck_shipments       integer,
  stuck_value_sar       numeric(12,2),
  updated_at            timestamptz not null default now(),
  primary key (brand, date)
);

-- ad spend split by platform (Natcho today)
create table if not exists ad_spend_daily (
  brand          text not null references brands(id),
  date           date not null,
  platform       text not null,
  spend_sar      numeric(12,2),
  conv_value_sar numeric(12,2),
  conversions    numeric(10,2),
  clicks         integer,
  impressions    integer,
  primary key (brand, date, platform)
);

-- every alert the Morning Ops Agent raised; key = hash of brand+date+message so re-runs don't duplicate
create table if not exists alerts (
  key        text primary key,
  brand      text not null references brands(id),
  run_date   date not null,
  severity   text not null check (severity in ('critical', 'warning', 'watch', 'win')),
  message    text not null,
  action     text,
  resolved   boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists alerts_brand_date on alerts (brand, run_date desc);

-- Row Level Security on: nothing is readable with the public anon key.
-- The agent and the Streamlit app use the service_role key server-side only.
alter table brands         enable row level security;
alter table kpi_daily      enable row level security;
alter table ad_spend_daily enable row level security;
alter table alerts         enable row level security;

-- ===== v2: SEO, Search Console, products, campaigns (2026-11-08) =====

-- daily units/revenue per product (from order lines, valid orders only)
create table if not exists product_daily (
  brand       text not null references brands(id),
  date        date not null,
  sku         text not null,
  name        text,
  units       numeric(10,2),
  revenue_sar numeric(12,2),
  primary key (brand, date, sku)
);

-- latest snapshot per published product: stock, sales velocity, restock need, SEO score
create table if not exists product_status (
  brand           text not null references brands(id),
  sku             text not null,
  snapshot_date   date not null,
  name            text,
  url             text,
  category        text,
  price_sar       numeric(12,2),
  stock           numeric(10,2),
  infinite        boolean,
  units_7d        numeric(10,2),
  units_30d       numeric(10,2),
  revenue_30d     numeric(12,2),
  velocity_day    numeric(10,3),
  days_cover      numeric(10,1),
  restock         text,            -- critical / warning / watch / null
  reorder_qty     integer,
  seo_score       integer,
  seo_issues      text,
  gsc_clicks      integer,
  gsc_impressions integer,
  gsc_position    numeric(6,2),
  primary key (brand, sku)
);

-- site-level SEO health per day (trend)
create table if not exists seo_daily (
  brand                text not null references brands(id),
  date                 date not null,
  published            integer,
  avg_score            numeric(5,1),
  low_score            integer,
  missing_title        integer,
  missing_description  integer,
  missing_keywords     integer,
  no_images            integer,
  single_image         integer,
  duplicate_titles     integer,
  url_errors           integer,
  slow_pages           integer,
  merchant_disapproved integer,
  primary key (brand, date)
);

-- Search Console totals per day
create table if not exists gsc_daily (
  brand       text not null references brands(id),
  date        date not null,
  clicks      integer,
  impressions integer,
  ctr         numeric(8,5),
  position    numeric(6,2),
  primary key (brand, date)
);

-- latest 28-day query report vs the previous 28 days, with the action to take
create table if not exists gsc_queries (
  brand            text not null references brands(id),
  query            text not null,
  period_end       date not null,
  clicks           integer,
  impressions      integer,
  ctr              numeric(8,5),
  position         numeric(6,2),
  prev_clicks      integer,
  prev_impressions integer,
  prev_position    numeric(6,2),
  is_brand         boolean,
  opportunity      text,
  action           text,
  primary key (brand, query)
);

-- ad spend per campaign per day
create table if not exists ad_campaign_daily (
  brand          text not null references brands(id),
  date           date not null,
  platform       text not null,
  campaign       text not null,
  campaign_type  text,
  spend_sar      numeric(12,2),
  conv_value_sar numeric(12,2),
  conversions    numeric(10,2),
  clicks         integer,
  impressions    integer,
  primary key (brand, date, platform, campaign)
);

alter table product_daily     enable row level security;
alter table product_status    enable row level security;
alter table seo_daily         enable row level security;
alter table gsc_daily         enable row level security;
alter table gsc_queries       enable row level security;
alter table ad_campaign_daily enable row level security;

-- ---- v3: content plan & market insights (2026-11-09) --------------------------
create table if not exists content_insights (
  brand      text not null,
  id         text not null,
  updated    date,
  type       text,            -- competitor_ad | customer_voice | gap | moment | positioning | risk | competitor_social
  competitor text,
  priority   text,            -- high | medium | low
  finding    text,
  weakness   text,
  action     text,
  evidence   text,
  days       text,            -- plan days that act on it, "4,20,29"
  primary key (brand, id)
);

create table if not exists content_plan (
  brand        text not null,
  date         date not null,
  day          integer,
  week_theme   text,
  content_type text,
  hook_type    text,
  product      text,
  visual_ref   text,
  on_image     text,          -- current hook (text on the image)
  caption      text,
  offer        text,
  hook_alt     text,          -- stronger alternative hook
  hook_alt_why text,
  insight_ids  text,
  primary key (brand, date)
);

alter table content_insights enable row level security;
alter table content_plan     enable row level security;
