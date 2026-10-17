-- ===========================================================================
-- OpEx - optional read-only views for reporting (Supabase table editor,
-- Looker Studio, Metabase...). Run after 01 and 02. Safe to run again.
-- ===========================================================================

-- How often each action worked for each problem (the closed-loop learning table).
create or replace view v_action_success as
select cause_key,
       action_key,
       count(*) filter (where outcome_status = 'success') as successes,
       count(*) filter (where outcome_status in ('success', 'failure')) as trials,
       round(100.0 * count(*) filter (where outcome_status = 'success')
             / nullif(count(*) filter (where outcome_status in ('success', 'failure')), 0), 1) as success_pct
from decisions
where decision <> 'rejected'
group by cause_key, action_key
order by cause_key, success_pct desc nulls last;

-- How often people follow the AI's recommendation.
create or replace view v_ai_agreement as
select date_trunc('week', decided_at) as week,
       count(*) as decisions,
       count(*) filter (where action_key = recommended_action and decision <> 'rejected') as followed_ai,
       count(*) filter (where decision = 'rejected') as rejected
from decisions
where source = 'live'
group by 1
order by 1 desc;

-- Headline numbers of every simulation run.
create or replace view v_simulation_results as
select id,
       created_at,
       created_by,
       (params ->> 'years')::int                       as years,
       (params ->> 'adoption_rate')::numeric            as adoption_rate,
       (summary -> 'delta' ->> 'net_benefit_inr')::numeric   as net_benefit_inr,
       (summary -> 'delta' ->> 'roi_multiple')::numeric      as roi_multiple,
       (summary -> 'delta' ->> 'downtime_avoided_h')::numeric as downtime_avoided_h,
       (summary -> 'delta' ->> 'failures_avoided')::numeric   as failures_avoided
from simulation_runs
order by created_at desc;

-- The views inherit the lock-down: only the backend's owner role can read them.
revoke all on v_action_success, v_ai_agreement, v_simulation_results from anon, authenticated;
