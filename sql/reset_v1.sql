-- DESTRUCTIVE. Removes the v1 (single-user, no accounts) LodgeLedger tables
-- and EVERYTHING in them, so sql/schema.sql (v2, with accounts) can be applied.
--
-- Only run this on a project whose v1 tables hold data you are happy to lose
-- (for example the fictional [demo] rows from the old seed_demo.sql).
-- It does nothing to any other table, and nothing if the tables are absent.
--
-- Order: run this file, then run sql/schema.sql.

begin;

-- Refuse if this already looks like a v2 database (users table present), so a
-- mistaken re-run cannot wipe real accounts.
do $$
begin
  if exists (select 1 from information_schema.tables
             where table_schema = current_schema() and table_name = 'users') then
    raise exception 'A users table exists: this is already the v2 schema. Nothing was dropped.';
  end if;
end $$;

drop table if exists contributions;
drop table if exists goals;
drop table if exists budgets;
drop table if exists transactions;
drop table if exists categories;
drop table if exists settings;

commit;
