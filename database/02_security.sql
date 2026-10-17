-- ===========================================================================
-- OpEx - lock the tables down (run after 01_schema.sql).
--
-- Supabase publishes every table in the "public" schema through its REST API to
-- anyone holding the project's anon key. OpEx never uses that API: the backend
-- connects directly with the database password and checks roles itself.
-- So we switch on Row Level Security with NO policies, which blocks the anon and
-- authenticated API roles completely. The backend's connection (the postgres
-- owner role) is not affected by RLS.
-- ===========================================================================

alter table app_users            enable row level security;
alter table alerts               enable row level security;
alter table incidents            enable row level security;
alter table recommendations      enable row level security;
alter table decisions            enable row level security;
alter table knowledge_documents  enable row level security;
alter table simulation_runs      enable row level security;
alter table audit_log            enable row level security;
alter table app_settings         enable row level security;

-- Belt and braces: no direct table rights for the public API roles either.
revoke all on app_users, alerts, incidents, recommendations, decisions,
              knowledge_documents, simulation_runs, audit_log, app_settings
       from anon, authenticated;
