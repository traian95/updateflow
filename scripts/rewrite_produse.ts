/**
 * Oglindă completă: golește tabelele aplicației din Supabase și le reîncarcă
 * din SQLite (aceleași nume de tabele și coloane ca în sursă).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Database from "better-sqlite3";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import dotenv from "dotenv";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = path.resolve(__dirname, "..");

for (const envPath of [
  path.join(PROJECT_ROOT, ".env"),
  path.join(PROJECT_ROOT, "Soft Ofertare Usi", ".env"),
  path.join(process.cwd(), ".env"),
]) {
  if (fs.existsSync(envPath)) {
    dotenv.config({ path: envPath });
  }
}

const BATCH_SIZE = 500;

/** Ștergere: mai întâi `oferte` (FK către `clienti`). */
const DELETE_ORDER = [
  "oferte",
  "clienti",
  "users",
  "produse",
  "izolatiile",
  "sync_state",
  "schema_version",
] as const;

/** Inserare: `clienti` înainte de `oferte`. */
const INSERT_ORDER = [
  "schema_version",
  "sync_state",
  "clienti",
  "users",
  "produse",
  "izolatiile",
  "oferte",
] as const;

function requireEnv(name: string): string {
  const v = process.env[name]?.trim();
  if (!v) {
    throw new Error(`Lipsește variabila de mediu obligatorie: ${name}`);
  }
  return v;
}

function resolveSqliteDbPath(): string {
  const fromEnv = process.env.SQLITE_DB_PATH?.trim();
  if (fromEnv) {
    if (!fs.existsSync(fromEnv)) {
      throw new Error(`SQLITE_DB_PATH nu indică un fișier existent: ${fromEnv}`);
    }
    return path.resolve(fromEnv);
  }

  const candidates = [
    path.join(PROJECT_ROOT, "date ofertare.db"),
    path.join(PROJECT_ROOT, "date_ofertare.db"),
    path.join(process.cwd(), "date ofertare.db"),
    path.join(process.cwd(), "date_ofertare.db"),
  ];

  for (const p of candidates) {
    if (fs.existsSync(p)) {
      return p;
    }
  }

  throw new Error(
    "Nu am găsit baza SQLite. Pune `date ofertare.db` sau `date_ofertare.db` în rădăcina proiectului sau setează SQLITE_DB_PATH.",
  );
}

function quoteIdent(table: string): string {
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(table)) {
    throw new Error(`Nume de tabel nepermis: ${table}`);
  }
  return table;
}

function listSqliteUserTables(db: Database.Database): Set<string> {
  const rows = db
    .prepare(
      "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'",
    )
    .all() as { name: string }[];
  return new Set(rows.map((r) => r.name));
}

function getColumnNames(db: Database.Database, table: string): string[] {
  const cols = db.prepare(`PRAGMA table_info(${quoteIdent(table)})`).all() as {
    name: string;
  }[];
  if (!cols.length) {
    throw new Error(`Tabelul SQLite „${table}” nu are coloane (sau nu există).`);
  }
  return cols.map((c) => c.name);
}

/** Prima coloană marcată PK în PRAGMA (pentru filtru delete tautologic). */
function getPrimaryKeyColumn(db: Database.Database, table: string): string {
  const cols = db.prepare(`PRAGMA table_info(${quoteIdent(table)})`).all() as {
    name: string;
    pk: number;
  }[];
  const pk = cols.filter((c) => c.pk > 0).sort((a, b) => a.pk - b.pk);
  if (pk.length) {
    return pk[0]!.name;
  }
  return cols[0]!.name;
}

function valueForSupabase(v: unknown): unknown {
  if (v === null || v === undefined) {
    return v;
  }
  if (Buffer.isBuffer(v)) {
    return v.toString("base64");
  }
  return v;
}

function rowToRecord(
  row: Record<string, unknown>,
  columnNames: string[],
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const col of columnNames) {
    out[col] = valueForSupabase(row[col]);
  }
  return out;
}

async function deleteAllRows(
  supabase: SupabaseClient,
  table: string,
  pkColumn: string,
): Promise<void> {
  const { error } = await supabase
    .from(table)
    .delete()
    .or(`${pkColumn}.is.null,${pkColumn}.not.is.null`);

  if (error) {
    throw new Error(`Ștergere „${table}” eșuată: ${error.message}`);
  }
}

async function insertBatches(
  supabase: SupabaseClient,
  table: string,
  records: Record<string, unknown>[],
): Promise<void> {
  for (let i = 0; i < records.length; i += BATCH_SIZE) {
    const chunk = records.slice(i, i + BATCH_SIZE);
    const { error } = await supabase.from(table).insert(chunk);
    if (error) {
      throw new Error(
        `Insert „${table}” eșuat (lot ${Math.floor(i / BATCH_SIZE) + 1}): ${error.message}`,
      );
    }
  }
}

function loadTableRecords(
  db: Database.Database,
  table: string,
): Record<string, unknown>[] {
  const columnNames = getColumnNames(db, table);
  const stmt = db.prepare(`SELECT * FROM ${quoteIdent(table)}`);
  const rawRows = stmt.all() as Record<string, unknown>[];
  return rawRows.map((row) => rowToRecord(row, columnNames));
}

async function main(): Promise<void> {
  const url = requireEnv("SUPABASE_URL").replace(/\/+$/, "");
  const serviceKey = requireEnv("SUPABASE_SERVICE_ROLE_KEY");

  const dbPath = resolveSqliteDbPath();
  console.log(`SQLite: ${dbPath}`);

  const db = new Database(dbPath, { readonly: true, fileMustExist: true });
  try {
    const sqliteTables = listSqliteUserTables(db);

    const supabase = createClient(url, serviceKey, {
      auth: { persistSession: false, autoRefreshToken: false },
    });

    console.log("— Golește Supabase (ordine FK) —");
    for (const table of DELETE_ORDER) {
      if (!sqliteTables.has(table)) {
        console.log(`  [omit] ${table}: lipsește din SQLite`);
        continue;
      }
      const pk = getPrimaryKeyColumn(db, table);
      console.log(`  șterg ${table} (PK: ${pk})…`);
      await deleteAllRows(supabase, table, pk);
    }

    let totalImported = 0;
    console.log("— Inserează din SQLite —");
    for (const table of INSERT_ORDER) {
      if (!sqliteTables.has(table)) {
        console.log(`  [omit] ${table}: lipsește din SQLite`);
        continue;
      }
      const records = loadTableRecords(db, table);
      if (records.length === 0) {
        console.log(`  ${table}: 0 rânduri`);
        continue;
      }
      console.log(`  ${table}: ${records.length} rânduri…`);
      await insertBatches(supabase, table, records);
      totalImported += records.length;
    }

    console.log(`Import finalizat. Total rânduri importate: ${totalImported}`);
  } finally {
    db.close();
  }
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
