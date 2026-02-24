#!/usr/bin/env node
/**
 * Prompt Push Script
 *
 * Reads prompt files from prompts/ and upserts them into the Supabase
 * system_prompts table. Requires Node 18+ (built-in fetch).
 *
 * Usage:
 *   npm run prompts:push
 *   npm run prompts:push:dry
 */

import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");

// --- Parse .env manually (no dotenv dependency) ---
function loadEnv(envPath) {
  try {
    const lines = readFileSync(envPath, "utf8").split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eq = trimmed.indexOf("=");
      if (eq === -1) continue;
      const key = trimmed.slice(0, eq).trim();
      const val = trimmed.slice(eq + 1).trim().replace(/^["']|["']$/g, "");
      if (key && !(key in process.env)) process.env[key] = val;
    }
  } catch {
    // .env not found — rely on existing env vars
  }
}

loadEnv(resolve(ROOT, ".env"));

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.error("Missing SUPABASE_URL or SUPABASE_KEY in .env");
  process.exit(1);
}

const isDryRun = process.argv.includes("--dry-run");

// Slug mapping
const PROMPT_FILES = [
  { file: "prompts/evaluation.md",  slug: "arete.evaluation", version: "1.0.0" },
  { file: "prompts/arete-short.md", slug: "arete.short",       version: "1.0.0" },
  { file: "prompts/arete-long.md",  slug: "arete.long",        version: "1.1.0" },
];

console.log(isDryRun ? "DRY RUN — no changes will be written\n" : "Pushing prompts to Supabase...\n");

for (const { file, slug, version } of PROMPT_FILES) {
  let prompt_text;
  try {
    prompt_text = readFileSync(resolve(ROOT, file), "utf8").trim();
  } catch {
    console.error(`  SKIP  ${slug} — could not read ${file}`);
    continue;
  }

  console.log(`  ${isDryRun ? "WOULD PUSH" : "PUSHING"}  ${slug}  (${prompt_text.length} chars, v${version})`);
  if (isDryRun) continue;

  const res = await fetch(`${supabaseUrl}/rest/v1/system_prompts`, {
    method: "POST",
    headers: {
      "apikey": supabaseKey,
      "Authorization": `Bearer ${supabaseKey}`,
      "Content-Type": "application/json",
      "Prefer": "resolution=merge-duplicates",
    },
    body: JSON.stringify({ slug, prompt_text, version, is_active: true }),
  });

  if (!res.ok) {
    const err = await res.text();
    console.error(`  ERROR  ${slug}: ${res.status} ${err}`);
  } else {
    console.log(`  OK     ${slug}`);
  }
}

console.log("\nDone.");
