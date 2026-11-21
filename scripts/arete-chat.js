#!/usr/bin/env node
/**
 * Arete Chat REPL
 *
 * Talks to Arete directly from the terminal, using the same prompt files the
 * edge function ships. For prompt tuning and model A/B, outside the app.
 *
 * Defaults to Kimi K2.6 via Moonshot's Anthropic-compatible endpoint, so the
 * wire format matches supabase/functions/evaluate-tweet exactly. Requires
 * Node 18+ (built-in fetch).
 *
 * Usage:
 *   npm run arete                          # kimi-k2.6, short mode
 *   npm run arete -- --mode long
 *   npm run arete -- --model claude-sonnet-4-5   # A/B against Claude
 *   npm run arete -- --once "AI will replace all engineers by 2027"
 *
 * Env vars (from .env):
 *   MOONSHOT_API_KEY    -- for kimi-* models
 *   ANTHROPIC_API_KEY   -- for claude-* models
 */

import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import readline from "readline/promises";
import { stdin, stdout } from "process";

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
      if (!process.env[key]) process.env[key] = val;
    }
  } catch {
    // no .env — fall back to real environment
  }
}
loadEnv(resolve(ROOT, ".env"));

// --- Modes map to the prompt files, same slugs as prompts-push.js ---
const MODES = {
  short: { file: "prompts/arete-short.md", maxTokens: 350,  limit: 260 },
  long:  { file: "prompts/arete-long.md",  maxTokens: 8192, limit: 4000 },
  eval:  { file: "prompts/evaluation.md",  maxTokens: 512,  limit: null },
};

// --- Providers ---
const PROVIDERS = {
  kimi: {
    baseUrl: "https://api.moonshot.ai/anthropic/v1/messages",
    envKey: "MOONSHOT_API_KEY",
  },
  anthropic: {
    baseUrl: "https://api.anthropic.com/v1/messages",
    envKey: "ANTHROPIC_API_KEY",
  },
};

const providerFor = (model) => (model.startsWith("kimi-") ? "kimi" : "anthropic");

// --- Args ---
function parseArgs(argv) {
  const out = { mode: "short", model: "kimi-k2.6", wrap: false, once: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--mode") out.mode = argv[++i];
    else if (a === "--model") out.model = argv[++i];
    else if (a === "--once") out.once = argv[++i];
    else if (a === "--wrap") out.wrap = true;
  }
  return out;
}

const args = parseArgs(process.argv.slice(2));
if (!MODES[args.mode]) {
  console.error(`Unknown mode "${args.mode}". Use: ${Object.keys(MODES).join(", ")}`);
  process.exit(1);
}

let mode = args.mode;
let model = args.model;
let wrap = args.wrap;
let showRaw = false;
let history = [];

function systemPrompt() {
  return readFileSync(resolve(ROOT, MODES[mode].file), "utf8");
}

// --- Mirror how evaluate-tweet frames a reply request ---
function wrapInput(text) {
  if (!wrap) return text;
  if (mode === "eval") return `"${text}"\n\nby @testuser`;
  return `You are replying to this tweet by @testuser:\n"${text}"\n\nDraft a reply.`;
}

async function send(text) {
  const provider = providerFor(model);
  const { baseUrl, envKey } = PROVIDERS[provider];
  const apiKey = process.env[envKey];

  if (!apiKey) {
    console.error(`\n  Missing ${envKey} — add it to .env or the environment.\n`);
    return;
  }

  history.push({ role: "user", content: wrapInput(text) });

  const res = await fetch(baseUrl, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model,
      max_tokens: MODES[mode].maxTokens,
      system: systemPrompt(),
      messages: history,
    }),
  });

  if (!res.ok) {
    const body = await res.text();
    console.error(`\n  HTTP ${res.status}: ${body.slice(0, 600)}\n`);
    history.pop();
    return;
  }

  const data = await res.json();
  const reply = (data.content || []).filter((b) => b.type === "text").map((b) => b.text).join("");
  history.push({ role: "assistant", content: reply });

  report(reply, data.usage);
}

// --- Output: show the draft plus the adherence signals worth tuning on ---
function report(reply, usage) {
  if (showRaw) {
    console.log(`\n${reply}\n`);
  } else {
    const parsed = tryParse(reply);
    if (parsed && parsed.draft) {
      console.log(`\n${parsed.draft}\n`);
      if (parsed.tone) console.log(`  tone: ${parsed.tone}`);
    } else if (parsed) {
      console.log(`\n${JSON.stringify(parsed, null, 2)}\n`);
    } else {
      console.log(`\n${reply}\n`);
    }
    flagViolations(parsed?.draft ?? reply);
  }

  if (usage) {
    console.log(`  tokens: ${usage.input_tokens} in / ${usage.output_tokens} out`);
  }
  console.log();
}

function tryParse(raw) {
  const text = raw.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "").trim();
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

// The rules the edge function post-processes away — surfaced here instead,
// because for prompt tuning you want to see what the model actually did.
function flagViolations(text) {
  if (typeof text !== "string") return;
  const limit = MODES[mode].limit;
  const flags = [];

  if (limit) {
    const over = text.length > limit;
    flags.push(`${over ? "OVER" : "ok"}  ${text.length}/${limit} chars`);
  }
  if (/[—–]/.test(text)) flags.push("BANNED  em/en dash present");
  if (/#\w/.test(text)) flags.push("BANNED  hashtag present");

  if (flags.length) console.log(`  ${flags.join("   ")}`);
}

// --- REPL ---
const HELP = `
Commands:
  /mode <short|long|eval>   switch prompt file
  /model <id>               switch model (kimi-* or claude-*)
  /wrap                     toggle app-style tweet framing
  /raw                      toggle raw output (no JSON parsing)
  /reset                    clear conversation history
  /help                     this
  /exit                     quit
`;

function banner() {
  console.log(
    `\nArete  |  ${model}  |  mode: ${mode}  |  wrap: ${wrap ? "on" : "off"}  |  ${MODES[mode].file}`
  );
  console.log(`Type /help for commands.\n`);
}

async function runRepl() {
  const rl = readline.createInterface({ input: stdin, output: stdout });
  banner();

  while (true) {
    let line;
    try {
      line = (await rl.question("> ")).trim();
    } catch {
      break; // ctrl-c / ctrl-d
    }
    if (!line) continue;

    if (line.startsWith("/")) {
      const [cmd, arg] = line.split(/\s+/, 2);
      if (cmd === "/exit" || cmd === "/quit") break;
      else if (cmd === "/help") console.log(HELP);
      else if (cmd === "/reset") {
        history = [];
        console.log("  history cleared\n");
      } else if (cmd === "/raw") {
        showRaw = !showRaw;
        console.log(`  raw output ${showRaw ? "on" : "off"}\n`);
      } else if (cmd === "/wrap") {
        wrap = !wrap;
        console.log(`  tweet framing ${wrap ? "on" : "off"}\n`);
      } else if (cmd === "/mode") {
        if (!MODES[arg]) console.log(`  unknown mode. use: ${Object.keys(MODES).join(", ")}\n`);
        else {
          mode = arg;
          history = [];
          banner();
        }
      } else if (cmd === "/model") {
        if (!arg) console.log("  usage: /model <id>\n");
        else {
          model = arg;
          history = [];
          banner();
        }
      } else console.log(`  unknown command: ${cmd}\n`);
      continue;
    }

    try {
      await send(line);
    } catch (err) {
      console.error(`\n  Request failed: ${err.message}\n`);
    }
  }

  rl.close();
}

// One-shot: send a single message and exit. For scripted A/B runs.
if (args.once) {
  banner();
  console.log(`> ${args.once}`);
  await send(args.once);
} else {
  await runRepl();
}
