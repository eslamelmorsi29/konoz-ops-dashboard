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
