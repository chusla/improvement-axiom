/**
 * Prompt Push Script
 *
 * Reads prompt files from prompts/ and upserts them into the Supabase
 * system_prompts table. Run this after editing any prompt file.
 *
 * Usage:
 *   deno run --allow-env --allow-net --allow-read scripts/prompts-push.ts
 *   deno run --allow-env --allow-net --allow-read scripts/prompts-push.ts --dry-run
 *
 * Env vars (from .env):
 *   AXIOM_SUPABASE_URL
 *   AXIOM_SUPABASE_SERVICE_ROLE_KEY
 */

import { load } from "https://deno.land/std@0.168.0/dotenv/mod.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// Load .env from project root
const env = await load({ envPath: ".env", export: false });
const supabaseUrl = env["AXIOM_SUPABASE_URL"] || Deno.env.get("AXIOM_SUPABASE_URL");
const supabaseKey =
  env["AXIOM_SUPABASE_SERVICE_ROLE_KEY"] ||
  Deno.env.get("AXIOM_SUPABASE_SERVICE_ROLE_KEY");

if (!supabaseUrl || !supabaseKey) {
  console.error("Missing AXIOM_SUPABASE_URL or AXIOM_SUPABASE_SERVICE_ROLE_KEY");
  Deno.exit(1);
}

const isDryRun = Deno.args.includes("--dry-run");
const supabase = createClient(supabaseUrl, supabaseKey);

// Slug mapping: file path (relative to prompts/) -> slug
const PROMPT_FILES: Array<{ file: string; slug: string; version: string }> = [
  { file: "prompts/evaluation.md",  slug: "arete.evaluation", version: "1.0.0" },
  { file: "prompts/arete-short.md", slug: "arete.short",       version: "1.0.0" },
  { file: "prompts/arete-long.md",  slug: "arete.long",        version: "1.1.0" },
];

console.log(isDryRun ? "DRY RUN — no changes will be written\n" : "Pushing prompts to Supabase...\n");

for (const { file, slug, version } of PROMPT_FILES) {
  let prompt_text: string;
  try {
    prompt_text = await Deno.readTextFile(file);
  } catch {
    console.error(`  SKIP  ${slug} — could not read ${file}`);
    continue;
  }

  const charCount = prompt_text.length;
  console.log(`  ${isDryRun ? "WOULD PUSH" : "PUSHING"}  ${slug}  (${charCount} chars, v${version})`);

  if (isDryRun) continue;

  const { error } = await supabase
    .from("system_prompts")
    .upsert(
      { slug, prompt_text, version, is_active: true, updated_at: new Date().toISOString() },
      { onConflict: "slug" }
    );

  if (error) {
    console.error(`  ERROR  ${slug}: ${error.message}`);
  } else {
    console.log(`  OK     ${slug}`);
  }
}

console.log("\nDone.");
