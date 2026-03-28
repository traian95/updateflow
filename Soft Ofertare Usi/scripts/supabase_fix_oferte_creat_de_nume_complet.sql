-- Remediu pentru eroarea PostgREST PGRST204: coloana creat_de_nume_complet lipsește din tabela oferte
-- (trigger, policy sau cache de schemă vechi). Rulează o dată în Supabase → SQL Editor.

alter table public.oferte
  add column if not exists creat_de_nume_complet text;

comment on column public.oferte.creat_de_nume_complet is
  'Opțional: nume complet al utilizatorului care creează oferta; poate rămâne NULL.';

-- După rulare: în Dashboard, reîncarcă schema API dacă eroarea persistă (sau așteaptă câteva minute).
