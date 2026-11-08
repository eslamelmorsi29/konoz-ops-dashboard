# Konoz Ops Dashboard

Overview of Natcho, Carina and GenZ: daily KPIs, MER, ad spend by platform, catalogue/shipping snapshot and Morning Ops alerts.

- Data: Supabase (`schema.sql`), written daily by the Morning Ops Agent. Aggregates only, no customer personal data.
- Secrets (Streamlit Cloud → App settings → Secrets):
  ```toml
  app_password = "..."
  [supabase]
  url = "https://<project>.supabase.co"
  service_key = "sb_secret_..."
  ```
