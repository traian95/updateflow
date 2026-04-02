-- DEPRECAT pentru fluxul curent: barele se pun în public.usi_exterioare (pret_baza + model).
-- Vezi Soft Ofertare Usi/utils/scripts/supabase_migrare_usi_exterioare_complet.sql + import_bare_usi_exterioare_supabase.py
--
-- Tabel exemplu (opțional) pentru datele extrase cu scripts/extract_bare.py
-- Rulare in SQL Editor Supabase, apoi import CSV din Studio sau insert din aplicatie.

create table if not exists public.bare_preturi (
  id uuid primary key default gen_random_uuid(),
  categorie text not null,
  cod_model text not null,
  lungime_text text not null,
  lungime_cm integer,
  decor text not null,
  pret_eur numeric(12, 2) not null,
  moneda text not null default 'EUR',
  tva_inclus boolean not null default false,
  sursa_pret text,
  created_at timestamptz not null default now(),
  unique (cod_model, lungime_text, decor)
);

comment on table public.bare_preturi is 'Preturi lista bare (Naturen EUR fara TVA), import din bare.xlsx.';

alter table public.bare_preturi enable row level security;

-- Policy minim: inlocuieste cu regulile tale (ex. read pentru authenticated).
-- create policy "bare_preturi_read" on public.bare_preturi for select using (true);
