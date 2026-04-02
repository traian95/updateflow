-- =============================================================================
-- Migrare Supabase — tabel public.usi_exterioare (uși exterior + bare trăgătoare)
-- Proiect: ingtefnrfjjribocqtgy (Naturen Flow / Soft Ofertare Usi)
--
-- Rulează O SINGURĂ DATĂ: Supabase Dashboard → SQL Editor → lipsește totul aici → Run
-- După succes: din PC rulezi importul barelor:
--   py utils/scripts/import_bare_usi_exterioare_supabase.py
-- =============================================================================

-- 1) Coloană necesară pentru prețul barelor (aplicația citește pret_baza pentru kit bară)
alter table public.usi_exterioare
  add column if not exists pret_baza double precision;

comment on column public.usi_exterioare.pret_baza is
  'Preț EUR listă pentru rânduri care nu folosesc adaos pe toc (ex. bară trăgătoare). Ușile metalice: prețurile pe tip toc rămân în pret_thermo_64 / pret_thermo_78 / pret_thermo_hot_78 / pret_thermo_hot_88.';

-- 2) Index pentru listări și ștergeri după prefix model (import bare)
create index if not exists idx_usi_exterioare_model on public.usi_exterioare (model);

-- 3) RLS: aplicația folosește cheia «anon» pentru citire. Nu dezactivăm RLS aici.
--    Dacă după migrare nu se încarcă rânduri în app, în Dashboard verifică:
--    Authentication → Policies pe «usi_exterioare» — trebuie SELECT permis pentru rolul folosit de client.
--    Exemplu politică (doar dacă lipsește și e acceptabil pentru tine):
--
--    create policy "usi_exterioare_select_public"
--      on public.usi_exterioare for select to anon, authenticated
--      using (true);

-- =============================================================================
-- VERIFICĂRI (rulează după migrare; opțional după import bare)
-- =============================================================================
-- select column_name, data_type
--   from information_schema.columns
--  where table_schema = 'public' and table_name = 'usi_exterioare'
--  order by ordinal_position;
--
-- select count(*) as total_usi_exterior from public.usi_exterioare;
--
-- select count(*) as bare from public.usi_exterioare
--  where model ilike 'bara tragatoare |%';
--
-- select model, pret_baza from public.usi_exterioare
--  where model ilike 'bara tragatoare |%'
--  order by model limit 10;
--
-- 5) Liste separate bare: vezi supabase_migrare_bare_exterioare.sql + import_bare_usi_exterioare_supabase.py
