-- ===========================================================================
-- OpEx - database tables (Supabase / Postgres 15+)
-- Run this first in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run twice: every statement uses IF NOT EXISTS.
-- The app also runs this automatically on first start if the tables are missing.
-- ===========================================================================

create extension if not exists pgcrypto;   -- gen_random_uuid()

-- People who can sign in. Passwords are bcrypt hashes, never plain text.
create table if not exists app_users (
    id              uuid primary key default gen_random_uuid(),
    email           varchar(255) not null unique,
    full_name       varchar(120) not null,
    role            varchar(20)  not null default 'viewer'
                    check (role in ('manager', 'engineer', 'operator', 'viewer')),
    password_hash   varchar(255) not null,
    is_active       boolean      not null default true,
    preferences     jsonb        not null default '{}'::jsonb,   -- accessibility settings
    created_at      timestamptz  not null default now(),
    last_login_at   timestamptz
);

-- One open alert per machine and kind; resolved automatically when the condition clears.
create table if not exists alerts (
    id               uuid primary key default gen_random_uuid(),
    machine_id       varchar(10)  not null,
    kind             varchar(30)  not null check (kind in ('failure_risk', 'breakdown', 'quality', 'energy', 'data_health')),
    severity         varchar(10)  not null check (severity in ('critical', 'high', 'medium', 'low')),
    title            varchar(200) not null,
    message          text         not null,
    status           varchar(15)  not null default 'open' check (status in ('open', 'acknowledged', 'resolved')),
    plant_time       varchar(20)  not null,
    created_at       timestamptz  not null default now(),
    acknowledged_by  varchar(255),
    acknowledged_at  timestamptz
);
create index if not exists ix_alerts_machine on alerts (machine_id);
create index if not exists ix_alerts_status on alerts (status);

-- Critical risks and breakdowns, with a snapshot of everything the AI saw.
create table if not exists incidents (
    id                   uuid primary key default gen_random_uuid(),
    machine_id           varchar(10)  not null,
    title                varchar(200) not null,
    status               varchar(15)  not null default 'open' check (status in ('open', 'resolved')),
    severity             varchar(10)  not null,
    component            varchar(20),
    root_cause           varchar(120),
    started_plant_time   varchar(20)  not null,
    resolved_plant_time  varchar(20),
    opened_at            timestamptz  not null default now(),
    snapshot             jsonb        not null default '{}'::jsonb,
    report               text                                   -- investigation write-up
);
create index if not exists ix_incidents_machine on incidents (machine_id);
create index if not exists ix_incidents_status on incidents (status);

-- Priced options and the recommended action for a machine at a moment in time.
create table if not exists recommendations (
    id                  uuid primary key default gen_random_uuid(),
    incident_id         uuid references incidents (id) on delete set null,
    machine_id          varchar(10)  not null,
    plant_time          varchar(20)  not null,
    cause_key           varchar(40)  not null,
    cause_name          varchar(120) not null,
    component           varchar(20),
    preset              varchar(30)  not null default 'balanced',
    weights             jsonb        not null default '{}'::jsonb,
    options             jsonb        not null default '[]'::jsonb,
    recommended_action  varchar(40)  not null,
    summary             jsonb        not null default '{}'::jsonb,
    confidence          double precision not null,
    agent_trace         jsonb        not null default '[]'::jsonb,   -- AI incident-room output
    created_at          timestamptz  not null default now()
);
create index if not exists ix_recommendations_machine on recommendations (machine_id);

-- What a person decided, and what happened afterwards (closed-loop learning).
create table if not exists decisions (
    id                  uuid primary key default gen_random_uuid(),
    recommendation_id   uuid references recommendations (id) on delete set null,
    machine_id          varchar(10)  not null,
    cause_key           varchar(40)  not null,
    recommended_action  varchar(40),
    action_key          varchar(40)  not null,
    decision            varchar(15)  not null check (decision in ('approved', 'rejected', 'modified')),
    note                text,
    decided_by          varchar(255),
    decided_at          timestamptz  not null default now(),
    plant_minute        integer      not null default 0,
    plant_time          varchar(20)  not null default '',
    predicted           jsonb        not null default '{}'::jsonb,
    before              jsonb        not null default '{}'::jsonb,
    after               jsonb        not null default '{}'::jsonb,
    outcome_status      varchar(15)  not null default 'pending' check (outcome_status in ('pending', 'success', 'failure')),
    outcome             jsonb        not null default '{}'::jsonb,
    evaluated_at        timestamptz,
    source              varchar(20)  not null default 'live' check (source in ('live', 'pilot_history'))
);
create index if not exists ix_decisions_machine on decisions (machine_id);
create index if not exists ix_decisions_cause on decisions (cause_key);
create index if not exists ix_decisions_outcome on decisions (outcome_status);

-- Documents people add to factory memory (SOPs, notes). Built-in SOPs live in data/knowledge/.
create table if not exists knowledge_documents (
    id          uuid primary key default gen_random_uuid(),
    kind        varchar(30)  not null default 'sop',
    title       varchar(200) not null,
    body        text         not null,
    source      varchar(200) not null default 'uploaded',
    created_by  varchar(255),
    created_at  timestamptz  not null default now()
);

-- Every 5-year simulation run: inputs, results, the day-by-day replay data and events.
create table if not exists simulation_runs (
    id          uuid primary key default gen_random_uuid(),
    created_by  varchar(255),
    created_at  timestamptz  not null default now(),
    params      jsonb        not null default '{}'::jsonb,
    summary     jsonb        not null default '{}'::jsonb,
    player      jsonb        not null default '{}'::jsonb,
    events      jsonb        not null default '[]'::jsonb,
    duration_s  double precision not null default 0
);

-- Who did what, for traceability of every human decision and setting change.
create table if not exists audit_log (
    id          uuid primary key default gen_random_uuid(),
    at          timestamptz  not null default now(),
    user_email  varchar(255),
    action      varchar(60)  not null,
    target      varchar(120),
    details     jsonb        not null default '{}'::jsonb
);
create index if not exists ix_audit_at on audit_log (at);

-- Plant-wide settings a manager can change (priorities, economics).
create table if not exists app_settings (
    key         varchar(60) primary key,
    value       jsonb       not null default '{}'::jsonb,
    updated_by  varchar(255),
    updated_at  timestamptz not null default now()
);
