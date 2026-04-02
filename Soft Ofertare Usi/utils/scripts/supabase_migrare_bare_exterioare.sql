-- =============================================================================
-- Tabel public.bare_exterioare — listă separată pentru bare trăgătoare (exterior)
-- Rulează în Supabase → SQL Editor (după migrarea usi_exterioare cu pret_baza, dacă o folosești).
-- Apoi: py utils/scripts/import_bare_usi_exterioare_supabase.py
-- =============================================================================

create table if not exists public.bare_exterioare (
  model text primary key,
  pret_baza double precision not null default 0
);

comment on table public.bare_exterioare is
  'Bare trăgătoare exterior: model = text complet «Bara tragatoare | cod | lungime | decor», pret_baza = EUR listă.';

create index if not exists idx_bare_exterioare_model on public.bare_exterioare (model);

alter table public.bare_exterioare enable row level security;

drop policy if exists "bare_exterioare_select_anon" on public.bare_exterioare;
create policy "bare_exterioare_select_anon"
  on public.bare_exterioare for select
  to anon, authenticated
  using (true);

-- Inserare/ștergere în bulk: service_role (scriptul de import) ocolește RLS.

-- Reîncarcă cache-ul API (evită PGRST205 imediat după CREATE TABLE):
notify pgrst, 'reload schema';

-- Verificări:
-- select count(*) from public.bare_exterioare;
-- select model, pret_baza from public.bare_exterioare order by model limit 5;
