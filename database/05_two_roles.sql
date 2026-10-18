-- Needed if you created the tables with an OLDER schema that had five roles.
-- Moves everyone onto the two roles that remain, then tightens the rule.
--   master_admin -> manager,  operator and viewer -> engineer
-- Run it once in Supabase -> SQL Editor. It is safe to run twice.

alter table app_users drop constraint if exists app_users_role_check;
update app_users set role = 'manager'  where role = 'master_admin';
update app_users set role = 'engineer' where role in ('operator', 'viewer');
alter table app_users alter column role set default 'engineer';
alter table app_users add constraint app_users_role_check check (role in ('manager', 'engineer'));
