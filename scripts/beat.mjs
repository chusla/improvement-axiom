// A station's hands on the Bridge.
//
// Every station is a Claude Code thread, and a thread cannot be pushed to — so it pulls on a loop
// and says it is alive on the way past. This is the deterministic part of that loop, for the same
// reason normalise.mjs exists: the model should not be re-deriving an HTTP call and an auth dance
// every thirty minutes. It calls this, reads the answer, and spends its thinking on the work.
//
//   node beat.mjs beat  --station itk --state working --chit ITK-STG-1248 --note "…" --eta 25m
//   node beat.mjs fires --station itk
//   node beat.mjs say   --station itk --kind HANDS --chit ITK-STG-1248 --text "needs Julia's OK"
//   node beat.mjs calls --station itk
//   node beat.mjs heard --station itk --ids <id>,<id>
//   node beat.mjs watch --station itk                     # under Monitor: one line per new call, wakes you mid-work
//   node beat.mjs line
//   node beat.mjs brief --station itk                     # how to work this station, read when a beat says so
//   node beat.mjs publish-brief --file station-brief.md   # owners only; every station reads it next beat
//
// Tickets (bridge/0007):
//
//   node beat.mjs mirror  --station itk [--full]        # own board → Bridge copy, every beat
//   node beat.mjs ticket  --station nu --title "…" --request "…" [--type bug] [--priority critical]
//                         [--from "Julia"] [--from-email j@x.io] [--tags a,b] [--page "Settings"]
//   node beat.mjs ticket  --station nu --file new-tickets.json    # an array of the same fields
//   node beat.mjs tickets --station nu [--all]
//   node beat.mjs comment --station nu --number 12 --text "…"
//   node beat.mjs status  --station nu --number 12 --to needs_dev
//   node beat.mjs status  --station nu --number 12 --to pr_open --pr 562   # pr_open needs its PR linked (bridge/0058)
//   node beat.mjs link    --station nu --number 12 --pr 562 [--url <pull URL>]   # link the ticket to its PR, so "Preview this change" has it
//   node beat.mjs go      --station nu --ticket NU-12 --said "build it and merge"   # Andrew said go in this session: record his words (bridge/0059)
//   node beat.mjs stale   --station nu                      # open tickets whose PR has merged or closed: move them, with a comment
//   node beat.mjs carried --station msc [--branch sandbox] [--dry]   # tickets at merged a sync carried, ones resting; 30 days untouched closes
//   node beat.mjs commitments --station msc [--by G4 --order G0,G1,G2,D1,D2,D3,D4,G3,D5,D6,D7,G4,D8,D9,D10,D11,G5]   # launch commitments; exits 1 while one due is open
//   node beat.mjs consolidate --station msc [--apply]      # put an existing board in order around its tickets: asks, document links, a todo list
//   node beat.mjs doc-link --station msc --id <document id> --ticket MSC-DEV-344 [--parent]   # link; --parent: the ticket it supports (bridge/0063)
//   node beat.mjs ask     --station msc --number 388 --on client --file ask.json   # the questions, answers to pick, steps, who (bridge/0062)
//   node beat.mjs answer  --station msc --number 388 --choice "…" --as "Rachael (WhatsApp)"   # an answer given elsewhere, on the ticket
//   node beat.mjs ask     --station msc --number 388 --on client --ask "Approve Emails 1 and 2"   # who it waits on, and what's asked (bridge/0061); --clear
//   node beat.mjs park    --station nu --number 12 [--unpark] [--note "after launch"]   # off Andrew's waiting list (bridge/0051)
//   node beat.mjs unexplained --station itk                 # open tickets not written up in plain words
//   node beat.mjs fresh   --station itk [--seen]          # tickets filed since you last looked (bridge/0041)
//   node beat.mjs doc     --station msc --title "…" --type spec --file doc.md [--ticket MSC-DEV-12]   # post a document
//   node beat.mjs doc     --station msc --id <document id> --file doc.md [--title "…"]                # a new revision
//   node beat.mjs docs    --station msc                                                              # what's there
//   node beat.mjs doc-comments --station msc [--all]   # what people wrote on them, and where (bridge/0047)
//   node beat.mjs doc-resolve --station msc --comment <id> [--reopen]   # mark a comment seen (a checklist answer goes back)
//   node beat.mjs doc-answer --station msc --comment <id> --answer "<text or link>" [--clear]   # answered: stays listed, answer under it (bridge/0057)
//   node beat.mjs may-merge --station itk --pr 1100 [--ticket ITK-DEV-12]   # may I merge this myself? (bridge/0038)
//   node beat.mjs explain --station itk --file plain.json   # write them up (bridge/0010)
//
// Talk on a ticket (bridge/0009): `calls` includes SAY, words from Andrew on one ticket; answer with
//   node beat.mjs say --station nu --kind REPLY --chit NU-3 --re <call id> --text "…"
// A SAY with no chit is on your line (bridge/0015); answer it with --re and no --chit.
//
// `--kitchen <slug>` (or LODESTAR_KITCHEN) picks the kitchen when the station account cooks in
// more than one.
//
// Credentials come from the environment, never a flag — a password in argv is a password in the
// shell history and in every process listing:
//
//   BRIDGE_URL, BRIDGE_ANON_KEY, BRIDGE_EMAIL, BRIDGE_PASSWORD
//
// `mirror` also needs a key for the project's own database, and only an own-board station has one:
//
//   BOARD_KEY_<STATION>       one line each in ~/.lodestar/boards.env (BOARD_KEY_ITK=…)
//
// The URL is not configured anywhere: the Bridge knows which database each project's board is in,
// so a key on the wrong line fails to sign in rather than copying the wrong client.
//
// No service-role key, deliberately. A station signs in as the operator and RLS gates it exactly
// as it gates The Pass — one posture for the whole system, and nothing here can reach further
// than the person running it could.

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { askProgress, consolidatePlan, copyBoard, normalizeAsk, optionsFromFlag, docComments, documentLink, documentRow, explainerRow, freshTickets, hostedTicket, kitBehind, managedFiles, mergeVerdict, refIn, refOf, STATUSES, taggedRef, ticketNumber, ticketTarget, WAITING_ON } from './board.mjs'

const REQUIRED = ['BRIDGE_URL', 'BRIDGE_ANON_KEY', 'BRIDGE_EMAIL', 'BRIDGE_PASSWORD']

/**
 * Which station kit this is. Bump it (date.n) whenever beat.mjs or board.mjs changes in a way a
 * brief depends on. Every beat reports it, and a brief names the kit it expects, so a station on
 * an older kit knows to ask for the update instead of failing on a command it doesn't have.
 */
// Bumped 2026-09-26 (UTC) after four changes to the kit landed without moving it: `fresh`
// (#209), the domain-word fix for "policy" (#204), kit-from-the-lock (#197) and
// package.json-that-is-code (#195). A station comparing its version against this one was told it
// was current while missing all four — a check that passes while being wrong, which is worse than
// no check, because it stops anyone looking.
// Bumped 2026-10-01: `roll` (answer a roll call, #268), the `roll:` and `clear:` hints on `calls`
// (#268, #269) and `doc-comments` (#259) all landed since. O2A answered the first roll call by
// hand, saying "no roll yet" — which is the version doing its job, once it moves.
// Bumped 2026-10-07: `doc-resolve` (mark a document comment seen; the Daily Checklist hands an item
// back that way).
// Bumped 2026-10-13: `park` (bridge/0051), so triage can take a ticket off Andrew's waiting list.
// Bumped 2026-10-20, one consolidated release (Andrew via MSC): pictures in documents and their
// comments (picture button, paste, the assistant's {{screenshot}}; MSC-SAND-254), screenshots and
// clips open in place with a strip to step through, the checklist's thread fixes since 10-13, and
// the claim check that no longer argues with "development closed it".
// Bumped 2026-10-23: `doc-answer` (an answered document comment is marked and stays listed, bridge/0057),
// the migration-edit guard, and the kit grants as their own migration (0004).
export const KIT_VERSION = '2026-11-23.1'

// kitBehind lives in board.mjs now, shared with The Pass; re-exported so existing importers hold.
export { kitBehind }

/**
 * What a beat tells the station about itself, and what to do before anything else. The first
 * thing a station reads every tick, so it is short and says the action outright.
 */
export function briefStatus(hello, kit = KIT_VERSION) {
  const b = hello?.brief ?? {}
  const latest = b.latest ?? null
  const yours = b.yours ?? null
  const out = {
    you: hello?.you ?? null,
    brief: { latest, yours, do: 'nothing — your brief is current' },
    kit: { yours: kit, expected: b.kit ?? null, do: 'nothing' },
  }
  if (!out.you) {
    out.brief.do = 'STOP — this station key is not a project in your kitchen. Tell Andrew; do not guess another key.'
  } else if (out.you.renamed_from) {
    out.brief.do = `YOUR KEY IS NOW ${out.you.key} (was ${out.you.renamed_from}): set station.key to "${out.you.key}" in lodestar.config.json, use --station ${out.you.key} and the ${out.you.prefix} prefix from now on, then read the brief: node scripts/beat.mjs brief --station ${out.you.key}`
  } else if (latest != null && (yours == null || yours < latest)) {
    out.brief.do = `READ THE BRIEF FIRST: node scripts/beat.mjs brief --station ${out.you.key}`
  }
  if (kitBehind(kit, b.kit)) {
    out.kit.do = `your kit is older than the brief expects — say HANDS "kit update needed", and follow the brief's update steps`
  }
  return out
}

/** A brief is written once for every station; these are filled in for the one reading it. */
export function fillBrief(body, you) {
  const vals = {
    key: you?.key ?? '<key>',
    prefix: you?.prefix ?? '<PREFIX>',
    label: you?.label ?? '<LABEL>',
    project: you?.project ?? '<project>',
    tickets: you?.tickets ?? '<own|hosted>',
    kitchen: you?.kitchen ?? '<kitchen>',
  }
  return String(body).replace(/\{\{\s*(key|prefix|label|project|tickets|kitchen)\s*\}\}/g, (_, k) => vals[k])
}

/** "25m" · "2h" · "1h30m" · "90s" → a Postgres interval. Null when nothing was said. */
export function parseEta(v) {
  if (!v) return null
  const s = String(v).trim().toLowerCase()
  if (!s) return null
  const m = s.match(/^(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?$/)
  if (!m || (!m[1] && !m[2] && !m[3])) {
    // A bare number is minutes, which is what a person says out loud.
    const n = s.match(/^(\d+)$/)
    if (n) return `${n[1]} minutes`
    return null
  }
  const parts = []
  if (m[1]) parts.push(`${m[1]} hours`)
  if (m[2]) parts.push(`${m[2]} minutes`)
  if (m[3]) parts.push(`${m[3]} seconds`)
  return parts.join(' ')
}

/** --flag value pairs. Bare --flag is true. */
export function parseArgs(argv) {
  const out = {}
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (!a.startsWith('--')) continue
    const key = a.slice(2)
    const next = argv[i + 1]
    if (next === undefined || next.startsWith('--')) { out[key] = true; continue }
    out[key] = next
    i++
  }
  return out
}

/** What `beat` sends. Anything not named is left alone by station_beat, so undefined is a value. */
export function beatPayload(args) {
  if (!args.station) throw new Error('--station is required: a key from the roster in docs/stations.md (itk | msc | nu | ws | wsweb | o2a | q2c)')
  const p = { p_key: String(args.station).toLowerCase() }
  if (args.label) p.p_label = args.label
  if (args.state) p.p_state = args.state
  if (args.chit) p.p_chit = args.chit
  if (args.note) p.p_note = args.note
  if (args.project) p.p_project = args.project
  if (args.session) p.p_session_ref = args.session
  const eta = parseEta(args.eta)
  if (eta) p.p_eta = eta
  const kitchen = kitchenSlug(args)
  if (kitchen) p.p_kitchen = kitchen
  return p
}

/** The heartbeat as sent: beatPayload plus which kit is beating. */
export function beatBody(args) {
  return { ...beatPayload(args), p_kit: KIT_VERSION }
}

/** `--kitchen` wins over LODESTAR_KITCHEN. Null leaves it to the Bridge, which knows your only one. */
export function kitchenSlug(args, envVars = process.env) {
  const v = args.kitchen === true ? '' : args.kitchen
  return String(v || envVars.LODESTAR_KITCHEN || '').trim().toLowerCase() || null
}

/** The station key every ticket command needs. */
function stationKey(args) {
  const key = String(args.station === true ? '' : args.station || '').trim().toLowerCase()
  if (!key) throw new Error('--station is required: a key from the roster in docs/stations.md (itk | msc | nu | ws | wsweb | o2a | q2c)')
  return key
}

/**
 * KEY=value lines from an env file. Comments and blanks are skipped and one layer of matching quotes
 * is removed. Deliberately small: this reads four Bridge values, not a general dotenv dialect.
 */
export function parseEnvFile(text) {
  const out = {}
  for (const raw of String(text || '').split(/\r?\n/)) {
    const line = raw.trim()
    if (!line || line.startsWith('#')) continue
    const m = line.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/)
    if (!m) continue
    let v = m[2]
    if (v.length >= 2 && (v[0] === '"' || v[0] === "'") && v.at(-1) === v[0]) v = v.slice(1, -1)
    out[m[1]] = v
  }
  return out
}

/**
 * Fill `target` from an env file without overriding what is already set, and never with an empty
 * value — an unfilled `BRIDGE_PASSWORD=` must still read as missing. Returns the keys it set.
 * A station runs this on every tick, so the file is read here instead of being sourced first.
 */
export function loadEnvFile(file, target = process.env) {
  let text
  try { text = fs.readFileSync(file, 'utf8') } catch { return [] }
  const set = []
  for (const [k, v] of Object.entries(parseEnvFile(text))) {
    if (v === '' || target[k]) continue
    target[k] = v
    set.push(k)
  }
  return set
}

/**
 * Where a station's Bridge credentials are read from, first match per key wins:
 *
 *   1. LODESTAR_BRIDGE_ENV, when set — an explicit path
 *   2. .env.bridge.local in the working directory — a per-repo override, gitignored
 *   3. ~/.lodestar/bridge.env — the one file every repo and every worktree shares
 *
 * The user-level file is the default, for two reasons. A git worktree does not get gitignored
 * files, so a station running in one (and most of them do) would never see a per-repo file. And a
 * password copied into five repos is five places to leak it and five places to rotate it.
 */
export function envFiles(cwd = process.cwd(), home = os.homedir(), override = process.env.LODESTAR_BRIDGE_ENV) {
  return [override, path.join(cwd, '.env.bridge.local'), path.join(home, '.lodestar', 'bridge.env')].filter(Boolean)
}

function env() {
  for (const f of envFiles()) loadEnvFile(f)
  const missing = REQUIRED.filter(k => !process.env[k])
  if (missing.length) {
    // Fail loudly. A station that cannot reach the Bridge must say so here, not go quiet and be
    // diagnosed fifteen minutes later from a light that never went green.
    throw new Error(`missing ${missing.join(', ')} — set them in ${path.join(os.homedir(), '.lodestar', 'bridge.env')} (shared by every repo and worktree), or in .env.bridge.local in this repo`)
  }
  return {
    url: process.env.BRIDGE_URL.replace(/\/$/, ''),
    key: process.env.BRIDGE_ANON_KEY,
    email: process.env.BRIDGE_EMAIL,
    password: process.env.BRIDGE_PASSWORD,
  }
}

/**
 * Where the Bridge session is kept between commands: `~/.lodestar/bridge-session.json`, beside
 * bridge.env, outside every repo. Every station runs on one machine, and every command used to sign
 * in with the password, so a wake round was some forty sign-ins in a few minutes and the Bridge's
 * auth answered 429 over_request_rate_limit (O2A's watch, 2026-11-11). Now one session is shared:
 * reused while it has five minutes left, refreshed when it's close, and the password only when
 * there's no session or the refresh fails.
 */
export function sessionFile(home = os.homedir()) {
  return path.join(home, '.lodestar', 'bridge-session.json')
}

const SESSION_MARGIN_S = 300
const RATE_WAITS_MS = [20_000, 60_000]

function readSessions(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')) || {} } catch { return {} }
}

function saveSession(file, key, s) {
  try {
    const all = readSessions(file)
    all[key] = s
    fs.mkdirSync(path.dirname(file), { recursive: true })
    const tmp = `${file}.${process.pid}.tmp`
    fs.writeFileSync(tmp, JSON.stringify(all), { mode: 0o600 })
    fs.renameSync(tmp, file)
  } catch { /* another command wrote it at the same moment; the next one saves */ }
}

/**
 * An access token for the Bridge: the kept one, a refreshed one, or a new sign-in. A 429 waits and
 * tries again twice before it's said. `deps` lets tests stand in for the clock, the file and fetch.
 */
export async function sessionToken(e, deps = {}) {
  const file = deps.file ?? sessionFile()
  const fetchFn = deps.fetch ?? fetch
  const nowS = () => (deps.now ? deps.now() : Date.now()) / 1000
  const wait = deps.wait ?? ((ms) => new Promise((r) => setTimeout(r, ms)))
  const key = `${e.url}|${e.email}`
  const kept = readSessions(file)[key]
  if (kept?.access_token && kept.expires_at - nowS() > SESSION_MARGIN_S) return kept.access_token

  const grant = async (type, body) => {
    for (let i = 0; ; i++) {
      const r = await fetchFn(`${e.url}/auth/v1/token?grant_type=${type}`, {
        method: 'POST',
        headers: { apikey: e.key, 'content-type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (r.status === 429 && i < RATE_WAITS_MS.length) { await wait(RATE_WAITS_MS[i]); continue }
      if (!r.ok) throw new Error(`sign-in failed ${r.status}: ${(await r.text()).slice(0, 200)}`)
      const j = await r.json()
      if (!j.access_token) throw new Error('sign-in returned no access token')
      return j
    }
  }
  let j = null
  if (kept?.refresh_token) j = await grant('refresh_token', { refresh_token: kept.refresh_token }).catch(() => null)
  if (!j) j = await grant('password', { email: e.email, password: e.password })
  const expires_at = Number(j.expires_at) || Math.floor(nowS()) + (Number(j.expires_in) || 3600)
  saveSession(file, key, { access_token: j.access_token, refresh_token: j.refresh_token ?? null, expires_at })
  return j.access_token
}

const token = (e) => sessionToken(e)

async function rest(e, tok, path, init = {}) {
  const r = await fetch(`${e.url}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: e.key,
      authorization: `Bearer ${tok}`,
      'content-type': 'application/json',
      ...(init.headers || {}),
    },
  })
  const body = await r.text()
  if (!r.ok) throw new Error(`${init.method || 'GET'} ${path} → ${r.status}: ${body.slice(0, 300)}`)
  return body ? JSON.parse(body) : null
}

export async function beat(args) {
  const e = env()
  const tok = await token(e)
  const body = beatBody(args)
  const rows = await rest(e, tok, 'rpc/station_beat', { method: 'POST', body: JSON.stringify(body) })
  const row = Array.isArray(rows) ? rows[0] : rows
  // Who you are and what to read, on every beat — so a station never works from a stale picture
  // of itself. An older Bridge without station_hello still beats; it just has nothing to add.
  const hello = await rest(e, tok, 'rpc/station_hello', {
    method: 'POST', body: JSON.stringify({ p_key: body.p_key, p_kitchen: body.p_kitchen ?? null }),
  }).catch(() => null)
  const { you, brief, kit } = briefStatus(hello)
  return {
    you, brief, kit,
    line: { state: row?.state, chit: row?.chit, note: row?.note, eta_at: row?.eta_at, last_seen_at: row?.last_seen_at },
  }
}

/**
 * The brief: how to work this station, filled in for it. Reading it records that you have, so
 * the next beat stops asking and The Pass stops showing this station as behind.
 */
export async function brief(args) {
  const e = env()
  const tok = await token(e)
  const station = stationKey(args)
  const kitchen = kitchenSlug(args)
  const hello = await rest(e, tok, 'rpc/station_hello', {
    method: 'POST', body: JSON.stringify({ p_key: station, p_kitchen: kitchen }),
  })
  if (!hello?.you) throw new Error(`"${station}" is not a project in your kitchen — check lodestar.config.json station.key, and tell Andrew`)
  const latest = hello.brief?.latest
  if (latest == null) return `No brief has been published yet. Work from .claude/skills/station/SKILL.md.\n`
  const kid = await rest(e, tok, 'rpc/current_kitchen', { method: 'POST', body: JSON.stringify({ p_slug: kitchen }) })
  const [row] = await rest(e, tok, `station_briefs?kitchen_id=eq.${kid}&version=eq.${latest}&select=body,kit,published_at`)
  await rest(e, tok, 'rpc/station_beat', {
    method: 'POST',
    body: JSON.stringify({ p_key: station, p_brief_version: latest, p_kit: KIT_VERSION, ...(kitchen ? { p_kitchen: kitchen } : {}) }),
  })
  const head = `<!-- station brief v${latest} · published ${row.published_at} · for ${hello.you.prefix} -->\n`
  const warn = kitBehind(KIT_VERSION, row.kit)
    ? `\n> Your station kit is ${KIT_VERSION}; this brief expects ${row.kit}. Some commands below may not exist yet — see "Keeping the kit current".\n`
    : ''
  return head + warn + '\n' + fillBrief(row.body, hello.you)
}

/** The file types the line takes, and what they are called. */
const PHOTO_TYPES = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', gif: 'image/gif', pdf: 'application/pdf' }

/**
 * Send a picture: a screenshot of what you see, or what a person sent you (bridge/0019).
 *
 * It goes in the line's private store — only your kitchen can read it — and the callback names it
 * as `line:<path>`. With --text it posts the callback for you; without, it just gives the ref back.
 */
export async function photo(args) {
  const e = env()
  const tok = await token(e)
  const station = stationKey(args)
  const file = String(args.file === true ? '' : args.file || '')
  if (!file) throw new Error('--file is required: the picture to send')
  const bytes = fs.readFileSync(file)
  const ext = (file.match(/\.([A-Za-z0-9]+)$/)?.[1] || '').toLowerCase()
  const type = PHOTO_TYPES[ext]
  if (!type) throw new Error(`--file must be one of: ${Object.keys(PHOTO_TYPES).join(", ")}`)
  const kitchen = await rest(e, tok, 'rpc/current_kitchen', { method: 'POST', body: JSON.stringify({ p_slug: kitchenSlug(args) }) })
  const path = `${kitchen}/${station}/${crypto.randomUUID()}.${ext}`
  const up = await fetch(`${e.url}/storage/v1/object/line/${path}`, {
    method: 'POST',
    headers: { apikey: e.key, authorization: `Bearer ${tok}`, 'content-type': type },
    body: bytes,
  })
  if (!up.ok) throw new Error(`upload → ${up.status}: ${(await up.text()).slice(0, 200)}`)
  const ref = `line:${path}`
  if (!args.text) return { ref }
  const kind = String(args.kind || 'NOTE').toUpperCase()
  const [event] = await say({ ...args, station, kind, ref })
  return { ref, event: event?.id ?? null }
}

/**
 * Look at a picture someone sent you: saves it next to your repo so you can open it.
 * `--ref line:<path>` comes from the message. Gives back the file's path.
 */
export async function look(args) {
  const e = env()
  const tok = await token(e)
  const ref = String(args.ref === true ? '' : args.ref || '')
  if (!ref.startsWith('line:')) throw new Error('--ref is required: the line:<path> on the message')
  const key = ref.slice('line:'.length)
  const signed = await fetch(`${e.url}/storage/v1/object/sign/line/${key}`, {
    method: 'POST',
    headers: { apikey: e.key, authorization: `Bearer ${tok}`, 'content-type': 'application/json' },
    body: JSON.stringify({ expiresIn: 600 }),
  })
  if (!signed.ok) throw new Error(`link → ${signed.status}: ${(await signed.text()).slice(0, 200)}`)
  const { signedURL } = await signed.json()
  const r = await fetch(`${e.url}/storage/v1${signedURL}`)
  if (!r.ok) throw new Error(`download → ${r.status}`)
  const dir = path.join('.lodestar', 'line')
  fs.mkdirSync(dir, { recursive: true })
  const out = path.join(dir, key.split('/').pop())
  fs.writeFileSync(out, Buffer.from(await r.arrayBuffer()))
  return { file: out }
}

/** Publish a new brief from a file. Owners only; every station reads it on its next beat. */
export async function publishBrief(args) {
  if (typeof args.file !== 'string') throw new Error('--file is required: the brief to publish')
  const body = fs.readFileSync(args.file, 'utf8')
  if (!body.trim()) throw new Error(`${args.file} is empty`)
  const e = env()
  const tok = await token(e)
  const kit = typeof args.kit === 'string' ? args.kit : KIT_VERSION
  const kitchen = kitchenSlug(args)
  const row = { body, kit }
  if (kitchen) {
    row.kitchen_id = await rest(e, tok, 'rpc/current_kitchen', { method: 'POST', body: JSON.stringify({ p_slug: kitchen }) })
  }
  const [made] = await rest(e, tok, 'station_briefs?select=version,kit,published_at', {
    method: 'POST', headers: { prefer: 'return=representation' }, body: JSON.stringify(row),
  })
  return { published: made.version, kit: made.kit, at: made.published_at }
}

/**
 * What the pass has dispatched to this station: expeditor tickets for this project that he has
 * actually chosen an option on. `chosen_at` is the authorization — a station never acts on a
 * ticket nobody marked.
 */
export async function fires(args) {
  const e = env()
  const tok = await token(e)
  const station = String(args.station || '').toLowerCase()
  if (!station) throw new Error('--station is required')
  const cols = 'ref,title,eli5,criticality,kind,why_now,options,prep,chosen_option,chosen_note,chosen_at,state,board_ref,board_url'
  return rest(e, tok,
    `expeditor_tickets?project=eq.${encodeURIComponent(station)}` +
    `&state=in.(chosen,doing)&select=${cols}&order=chosen_at.asc`)
}

/**
 * Where a station's unheard calls are read from: behind / push / in the weeds / fire (bridge/0004).
 * Oldest first, because "in the weeds" then "out of the weeds" only means something in order.
 */
export function callsPath(station, all = false) {
  const key = String(station || '').trim().toLowerCase()
  if (!key) throw new Error('--station is required')
  const cols = '&select=id,station,chit,kind,text,env,option,ref,at,heard_at'
  // --all looks back over what you have already heard, for a photo or a detail you need again.
  return all
    ? `station_calls?station=eq.${encodeURIComponent(key)}${cols}&order=at.desc&limit=30`
    : `station_calls?station=eq.${encodeURIComponent(key)}&heard_at=is.null${cols}&order=at.asc`
}

/**
 * Which calls a station is acknowledging. Ids are checked here, not left to PostgREST: a stray
 * comma or a pasted word must be refused, never widened into "every call".
 */
export function heardIds(v) {
  const ids = String(v === true ? '' : v || '').split(',').map(x => x.trim()).filter(Boolean)
  if (!ids.length) throw new Error('--ids is required — the calls you are acknowledging')
  const bad = ids.filter(x => !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(x))
  if (bad.length) throw new Error(`not a call id: ${bad.join(', ')}`)
  return ids
}

/**
 * What the pass has CALLED to this station that is not a ticket decision. Unheard only.
 *
 * A call can carry a photo (bridge/0019): `ref` names it, and `do` says how to look at it, so a
 * picture is never missed for want of knowing the command.
 */
export async function calls(args) {
  const e = env()
  const tok = await token(e)
  const rows = await rest(e, tok, callsPath(args.station, args.all === true || args.all === 'true'))
  return (rows ?? []).map(c => {
    if (typeof c.ref !== 'string') return c
    if (c.ref.startsWith('line:')) return { ...c, do: `a photo came with this — look at it: node scripts/beat.mjs look --ref ${c.ref}` }
    // Someone wrote on a document (bridge/0047). The call is the nudge; this reads the words.
    if (c.ref.startsWith('doc:')) return { ...c, do: `read the comments: node scripts/beat.mjs doc-comments --station ${c.station}` }
    // Andrew cleared an old ask of yours from his move. Nothing is owed either way.
    if (c.ref.startsWith('clear:')) return { ...c, do: 'nothing — mark it heard and move on; your earlier ask is closed without an answer' }
    // The expeditor called the line: sync, then call back with where you are.
    if (c.ref.startsWith('roll:')) return { ...c, do: `ONE tick, not a loop: sync (lodestar update, or git pull), beat, then: node scripts/beat.mjs roll --station ${c.station} --note "one line: what you are on, what is waiting on Andrew"` }
    return c
  })
}

/** "Heard" — the station has read these calls. Only this station's calls can be acknowledged. */
export async function heard(args) {
  const ids = heardIds(args.ids)
  const station = String(args.station || '').trim().toLowerCase()
  if (!station) throw new Error('--station is required')
  const e = env()
  const tok = await token(e)
  return rest(e, tok,
    `station_calls?id=in.(${ids.join(',')})&station=eq.${encodeURIComponent(station)}&heard_at=is.null`, {
      method: 'PATCH',
      headers: { prefer: 'return=representation' },
      body: JSON.stringify({ heard_at: new Date().toISOString() }),
    })
}

/** A callback. WALKING when done, HANDS when stuck, REFIRE? when you disagree with the call. */
export async function say(args) {
  const e = env()
  const tok = await token(e)
  const KINDS = ['WALKING', 'HANDS', 'REFIRE?', 'BUILDING', 'DEPLOYED', 'HEARD', 'NOTE', 'ERROR', 'REPLY']
  const kind = String(args.kind || '').toUpperCase()
  if (!KINDS.includes(kind)) throw new Error(`--kind must be one of: ${KINDS.join(', ')}`)
  if (!args.text) throw new Error('--text is required — a callback with no words is not a callback')
  const row = { station: String(args.station || '').toLowerCase(), kind, text: String(args.text) }
  if (args.chit) row.chit = args.chit
  if (args.ref) row.ref = args.ref
  // A REPLY is words on one ticket, and says which SAY it answers when it answers one (bridge/0009).
  // A REPLY names its ticket, or the call it answers (a message on your line has no ticket, bridge/0015).
  if (kind === 'REPLY' && !row.chit && args.re === undefined) throw new Error('a REPLY needs --chit (the ticket) or --re (the call it answers)')
  if (args.re !== undefined) row.re = heardIds(args.re)[0]
  return rest(e, tok, 'station_events', {
    method: 'POST',
    headers: { prefer: 'return=representation' },
    body: JSON.stringify(row),
  })
}

/** The report a roll call gets: the kit, the branch and commit, the counts, and your one line. */
export function rollText({ kit, branch, head, open, fired, note }) {
  const parts = [`kit ${kit}`, `${branch}@${head}`, `${open} open`, `${fired} fired`]
  const words = String(note || '').trim()
  return parts.join(' · ') + (words ? ` · ${words}` : '')
}

/**
 * Answer the roll call: the newest unheard `roll:` call gets a REPLY with the report and is marked
 * heard. The counts come from the board and the fires; the commit from git; the kit from this file.
 * Sync BEFORE calling this — the point of a roll call is that every station reports from current.
 */
export async function roll(args) {
  const station = String(args.station || '').trim().toLowerCase()
  if (!station) throw new Error('--station is required')
  const e = env()
  const tok = await token(e)
  const unheard = await rest(e, tok, callsPath(station))
  const call = [...(unheard ?? [])].reverse().find(c => typeof c.ref === 'string' && c.ref.startsWith('roll:'))
  if (!call) throw new Error('no roll call waiting — nothing to answer (node scripts/beat.mjs calls shows what is)')
  const git = (a) => { const r = spawnSync('git', a, { encoding: 'utf8' }); return r.status === 0 ? r.stdout.trim() : '?' }
  const branch = git(['rev-parse', '--abbrev-ref', 'HEAD'])
  const head = git(['rev-parse', '--short', 'HEAD'])
  let open = '?', fired = '?'
  try { open = (await tickets({ ...args, station })).length } catch { /* a station without a board still reports */ }
  try { fired = (await fires({ station })).length } catch { /* likewise */ }
  const text = rollText({ kit: KIT_VERSION, branch, head, open, fired, note: args.note })
  const [posted] = await rest(e, tok, 'station_events', {
    method: 'POST',
    headers: { prefer: 'return=representation' },
    body: JSON.stringify({ station, kind: 'REPLY', text, re: call.id, ref: call.ref }),
  })
  await heard({ station, ids: call.id })
  return { answered: call.id, text, id: posted?.id ?? null }
}

/**
 * Which stations have calls nobody has rung them for. Unheard calls, grouped by station, leaving
 * out any already rung for inside `quietMs` — so a station that is mid-turn is not rung again
 * every minute, but one that never answers is rung again once the quiet runs out.
 */
export function ringsFrom(rows, rung = {}, now = Date.now(), quietMs = 10 * 60_000) {
  const out = {}
  for (const c of rows ?? []) {
    const at = rung[c.id]
    if (at && now - at < quietMs) continue
    ;(out[c.station] ??= []).push(c)
  }
  // A station rung a moment ago is left alone for what other people wrote: a tester's assistant
  // comments on a ticket every few minutes while it works, and ringing for each one woke HQ and
  // interrupted the station nine times in an hour (MSC, 2026-10-02). Their comments gather and ring
  // together when the quiet runs out. Andrew's own calls ring at once, whatever was rung before.
  for (const [station, list] of Object.entries(out)) {
    const last = rung[`@${station}`]
    if (last && now - last < quietMs && !list.some((c) => ringKind(c).from === 'Andrew')) delete out[station]
  }
  return out
}

/**
 * What one waiting call is, and who it is from. A call on a line is not always Andrew: the Bridge
 * relays every ticket comment and document comment as a SAY (bridge/0039, 0047), and those are
 * written by testers, or by a host's own assistant in a tester's session. HQ relayed six of them to
 * MSC as "a message from Andrew" in one evening; they were Nathan's assistant noting PRs it had
 * opened and merged (2026-10-02). So the ring says which it is, and names the author.
 */
export function ringKind(c) {
  const text = String(c.text || '')
  const ref = typeof c.ref === 'string' ? c.ref : ''
  const from = (text.match(/\bfrom ([^:\n]{1,60}):/) || [])[1]?.trim() ?? null
  if (ref.startsWith('roll:')) return { what: 'roll call', from: 'Andrew' }
  if (ref.startsWith('clear:')) return { what: 'cleared', from: 'Andrew' }
  if (ref.startsWith('doc:') || text.startsWith('COMMENT on the document')) return { what: 'document comment', from }
  if (text.startsWith('COMMENT on')) return { what: 'ticket comment', from }
  if (c.kind === 'START') return { what: 'start development', from }
  if (text.startsWith('RECHECK')) return { what: 'take another look', from: 'Andrew' }
  if (text.startsWith('CLEAN PLATE')) return { what: 'clean plate', from: 'Andrew' }
  if (c.kind === 'SAY') return { what: 'message', from: 'Andrew' }
  return { what: String(c.kind || 'call').toLowerCase(), from: 'Andrew' }
}

/** What a ring says about one station's waiting calls: how many, since when, of what kind, from whom. */
export function ringSummary(list) {
  const kinds = {}
  const from = new Set()
  for (const c of list) {
    const k = ringKind(c)
    kinds[k.what] = (kinds[k.what] ?? 0) + 1
    from.add(k.from ?? 'someone on the board')
  }
  return { waiting: list.length, oldest: list[0]?.at ?? null, kinds, from: [...from] }
}

/**
 * Calls the bell does not ring for: comments written by the named authors. A station's own test
 * admin comments on tickets while a replay runs, and each one woke HQ to tell the station about
 * its own test (MSC, 2026-10-02). `--mute "Station Test,Another Name"`. Only relayed comments can
 * be muted, by their author; anything from Andrew or The Pass always rings.
 */
export function unmuted(rows, mute) {
  const names = String(mute === true ? '' : mute || '').split(',').map((n) => n.trim().toLowerCase()).filter(Boolean)
  if (!names.length) return rows ?? []
  return (rows ?? []).filter((c) => {
    const k = ringKind(c)
    return !(k.what.endsWith('comment') && k.from && names.includes(k.from.toLowerCase()))
  })
}

/**
 * HQ's bell. The Pass can write a call onto a station's line, but it cannot reach into a desktop
 * session, and a station whose loop is not running never reads its line: the first roll call went
 * to seven stations and sat unheard, and a "take another look" would have done the same
 * (2026-10-01). HQ can message a station's session, so HQ listens for the Pass.
 *
 *   node apps/pass/bridge/beat.mjs bell                 # what is waiting now, and mark it rung
 *   node apps/pass/bridge/beat.mjs bell --every 45      # wait until something is, then say so
 *   node apps/pass/bridge/beat.mjs bell --every 45 --mute "Station Test"   # but not for a test admin's comments
 *
 * It signs in once and asks one question per poll, for every station at once. What it has rung for
 * is kept in ~/.lodestar/bell.json, so re-arming it does not ring twice for the same call.
 */
export async function bell(args) {
  const e = env()
  const every = Math.max(0, Number(args.every) || 0) * 1000
  const quiet = (Number(args.quiet) || 600) * 1000
  const file = path.join(os.homedir(), '.lodestar', 'bell.json')
  const read = () => { try { return JSON.parse(fs.readFileSync(file, 'utf8')) } catch { return {} } }
  let tok = await token(e)
  for (;;) {
    // A token lasts an hour; a wait can last all day. The kept session is read each round, and
    // refreshed only when it's close to running out.
    tok = await token(e).catch(() => tok)
    let rows = []
    try {
      rows = await rest(e, tok, 'station_calls?heard_at=is.null&select=id,station,chit,kind,text,ref,at&order=at.asc&limit=500')
    } catch (err) {
      if (!every) throw err
      // One failed poll must not end the watch: try on the next round.
    }
    const now = Date.now()
    const rung = read()
    const rings = ringsFrom(unmuted(rows, args.mute), rung, now, quiet)
    if (Object.keys(rings).length || !every) {
      const keep = Object.fromEntries(Object.entries(rung).filter(([, at]) => now - at < 24 * 3600_000))
      for (const [station, list] of Object.entries(rings)) { keep[`@${station}`] = now; for (const c of list) keep[c.id] = now }
      fs.mkdirSync(path.dirname(file), { recursive: true })
      fs.writeFileSync(file, JSON.stringify(keep))
      return Object.fromEntries(Object.entries(rings).map(([station, list]) => [station, ringSummary(list)]))
    }
    await new Promise((r) => setTimeout(r, every))
  }
}

/**
 * One line per call this watch hasn't printed yet, and remembers it. Calls already waiting when the
 * watch starts are printed too, marked as such: nobody has heard them either.
 */
export function watchLines(rows, seen, first = false) {
  const out = []
  for (const c of rows ?? []) {
    if (!c?.id || seen.has(c.id)) continue
    seen.add(c.id)
    const k = ringKind(c)
    const text = String(c.text ?? '').replace(/\s+/g, ' ').trim().slice(0, 200)
    out.push(`NEW CALL ${String(c.id).slice(0, 8)}${first ? ' (already waiting)' : ''}: ${k.what}${k.from ? ` from ${k.from}` : ''}${c.chit ? ` on ${c.chit}` : ''}${text ? ` · ${text}` : ''}`)
  }
  return out
}

/**
 * A station's own ear on its line. The tick only reads calls every thirty minutes, and long work
 * pushes it later, so a client's comment sat 20 to 40 minutes (MSC, 2026-11-09). Run this under
 * Monitor: it prints one line per new call, and each line wakes the session mid-work. Quiet costs
 * nothing. It never returns; Monitor ends it, and the next tick arms it again.
 *
 *   node scripts/beat.mjs watch --station msc [--every 120]
 */
export async function watch(args) {
  const station = String(args.station || '').trim().toLowerCase()
  if (!station) throw new Error('--station is required')
  const every = Math.max(30, Number(args.every) || 120) * 1000
  const e = env()
  // A sign-in that fails at the start is said and tried again next round, not the end of the watch.
  let tok = null
  const seen = new Set()
  let first = true
  for (;;) {
    tok = await token(e).catch((err) => { console.error(`watch: sign-in failed, trying again: ${err.message || err}`); return tok })
    try {
      const rows = await rest(e, tok, callsPath(station))
      for (const l of watchLines(rows, seen, first)) console.log(l)
      first = false
    } catch (err) {
      // One failed poll must not end the watch: say so, sign in again, try next round.
      console.error(`watch: poll failed, trying again: ${err.message || err}`)
    }
    await new Promise((r) => setTimeout(r, every))
  }
}

/** Every station, for when a thread wants to know what the rest of the line is doing. */
export async function line() {
  const e = env()
  const tok = await token(e)
  return rest(e, tok, 'stations?select=key,label,state,chit,note,eta_at,last_seen_at&order=key')
}

// ── Tickets ────────────────────────────────────────────────────────────────

/** Signed in, kitchen resolved, and this station's project row — everything a ticket command needs. */
async function onBoard(args) {
  // Which station first: a command missing --station says so without signing in (the suite's
  // `doc({})` signed in to the real Bridge on every run).
  const station = stationKey(args)
  const e = env()
  const tok = await token(e)
  const call = (p, init) => rest(e, tok, p, init)
  const kitchen = await call('rpc/current_kitchen', {
    method: 'POST', body: JSON.stringify({ p_slug: kitchenSlug(args) }),
  })
  const [project] = await call(
    `projects?kitchen_id=eq.${kitchen}&key=eq.${encodeURIComponent(station)}&select=key,name,board_mode,supabase_ref,tags_required,env_by_source,databases,env_tags`)
  if (!project) throw new Error(`"${station}" is not a project in this kitchen — add it to public.projects first`)
  // Whether this board numbers a series per environment, asked of the board rather than guessed
  // from a row's source (see refIn): ITK carried `hosted` as a fourth series and echoed ITK-1.
  const envRefs = Array.isArray(project.env_tags) && project.env_tags.length > 0
  return { e, call, station, kitchen, project, envRefs }
}

/**
 * Where board keys live: one file, `~/.lodestar/boards.env`, one line per own-board station
 * (`BOARD_KEY_ITK=…`). Outside every repo so worktrees see it and nothing can commit it. A station
 * reads only its own line. The URL is never in it: the Bridge knows each project's database.
 */
export function boardsFile(home = os.homedir()) {
  return path.join(home, '.lodestar', 'boards.env')
}

/** `itk` → `BOARD_KEY_ITK`; `ws-web` → `BOARD_KEY_WS_WEB`. */
export function boardKeyName(station) {
  if (!/^[a-z0-9][a-z0-9-]*$/.test(station)) throw new Error(`not a station key: ${station}`)
  return `BOARD_KEY_${station.toUpperCase().replace(/-/g, '_')}`
}

/**
 * This station's board key: the environment first, then its line in boards.env. The older
 * per-station file (`~/.lodestar/boards/<key>.env`, `BOARD_KEY=`) still works, so nothing breaks
 * while it is moved over.
 */
export function boardKey(station, envVars = process.env, home = os.homedir(), name = boardKeyName(station)) {
  if (envVars[name]) return envVars[name]
  const read = (f) => { try { return parseEnvFile(fs.readFileSync(f, 'utf8')) } catch { return {} } }
  return read(boardsFile(home))[name] || read(path.join(home, '.lodestar', 'boards', `${station}.env`)).BOARD_KEY || null
}

/** Which boards.env line holds the key for a project's board database. */
export function boardLine(project) {
  const board = (project.databases ?? []).find((d) => d.role === 'board' && d.ref === project.supabase_ref)
  return board?.key || boardKeyName(project.key)
}

/** A project's own database, from the ref the Bridge holds for it. */
export const boardUrl = (ref) => `https://${ref}.supabase.co`

/** Copy this project's own board to the Bridge. Run it on every beat; it only copies what moved. */
export async function mirror(args) {
  const { e, call, station, kitchen, project } = await onBoard(args)
  if (project.board_mode !== 'own') {
    throw new Error(`${station}'s board is hosted on the Bridge — there is nothing to copy. File tickets with: beat.mjs ticket --station ${station}`)
  }
  if (!project.supabase_ref) throw new Error(`the Bridge has no database recorded for ${station} — set projects.supabase_ref first`)
  // The URL comes from the Bridge, never from a file, so a key on the wrong line can only fail to
  // sign in; it can never copy the wrong client.
  const url = boardUrl(project.supabase_ref)
  // The Bridge names the key line for the board database (projects.databases); BOARD_KEY_<STATION>
  // is the default when it doesn't.
  const line = boardLine(project)
  const key = boardKey(station, process.env, os.homedir(), line)
  if (!key) {
    throw new Error(`missing ${line} — add that line to ${boardsFile()} with the secret key for project ${project.supabase_ref}`)
  }
  try {
    return await copyBoard({ rest: call, kitchen, station }, { url, key }, { full: args.full === true })
  } catch (err) {
    // Say it on the Bridge too, so The Pass can show a copy that is failing rather than one that is
    // merely quiet. Best effort: if the Bridge is the thing that is down, the throw below still tells.
    await call('board_sync?on_conflict=kitchen_id,project', {
      method: 'POST',
      headers: { prefer: 'resolution=merge-duplicates,return=minimal' },
      body: JSON.stringify({ kitchen_id: kitchen, project: station, ok: false, synced_at: new Date().toISOString(), note: String(err.message || err).slice(0, 300) }),
    }).catch(() => {})
    throw err
  }
}

/** File one ticket, or a file of them, on a hosted board. Returns the refs, e.g. NU-12. */
export async function ticket(args) {
  const { call, station, kitchen, project, envRefs } = await onBoard(args)
  if (project.board_mode !== 'hosted') {
    throw new Error(`${station} keeps its tickets in its own database — create them in its admin, and \`beat.mjs mirror\` brings them here`)
  }
  let inputs
  if (typeof args.file === 'string') {
    const parsed = JSON.parse(fs.readFileSync(args.file, 'utf8'))
    inputs = Array.isArray(parsed) ? parsed : [parsed]
  } else {
    inputs = [args]
  }
  // Every entry is checked before any is filed, so a bad fifth entry doesn't leave four behind.
  const rows = inputs.map((i) => ({ ...hostedTicket(i, station), kitchen_id: kitchen }))
  // `source` back too: the trigger decides which series this lands in, so it is the only place
  // that knows, and a station that files a ticket should be told the ref it can go and use.
  const made = await call('board_tickets?select=id,ticket_number,source,title,status', {
    method: 'POST',
    headers: { prefer: 'return=representation' },
    body: JSON.stringify(rows),
  })
  return made.map((t) => ({ ref: refIn(station, t.ticket_number, t.source, envRefs), title: t.title, status: t.status, id: t.id }))
}

/**
 * What was filed on this board since this station last looked (bridge/0041).
 *
 * Neither `fires` nor `calls` shows a ticket somebody filed — a guest through the app's assistant, a
 * tester, the expeditor's intake — so one could sit unread until Andrew fired it. This is the third
 * thing a tick reads.
 *
 * `--seen` advances the watermark, and only then: a tick that dies halfway shows the same tickets
 * again rather than losing them. Seeing is not acting — a proposed ticket still waits for Andrew.
 */
export async function fresh(args) {
  const { call, station, kitchen, project, envRefs } = await onBoard(args)
  const [row] = await call(`stations?kitchen_id=eq.${kitchen}&key=eq.${encodeURIComponent(station)}&select=tickets_seen_at`)
    .catch(() => [])
  const seenAt = row?.tickets_seen_at ?? null
  const rows = await call(
    `board_tickets?kitchen_id=eq.${kitchen}&project=eq.${encodeURIComponent(station)}` +
    '&select=ticket_number,source,title,status,priority_flag,request_type,requester,created_at' +
    '&order=created_at.asc&limit=200')
  const { since, tickets, nextSeenAt } = freshTickets(rows)
  const out = tickets.map((t) => ({ ref: refIn(station, t.ticket_number, t.source, envRefs), ...t }))
  if (args.seen && nextSeenAt) {
    await call(`stations?kitchen_id=eq.${kitchen}&key=eq.${encodeURIComponent(station)}`, {
      method: 'PATCH', body: JSON.stringify({ tickets_seen_at: nextSeenAt }),
    })
  }
  return {
    since, count: out.length, tickets: out,
    ...(args.seen ? { seen_to: nextSeenAt } : { do: out.length ? `read these, then run the same command with --seen` : 'nothing new' }),
  }
}

/** This station's tickets: open ones, or `--all`. Works for copies too, read-only. */
export async function tickets(args) {
  const { call, station, kitchen, envRefs } = await onBoard(args)
  const open = args.all === true ? '' : `&is_backlog=eq.false&status=not.in.(merged,promoted,closed)`
  const rows = await call(
    `board_tickets?kitchen_id=eq.${kitchen}&project=eq.${encodeURIComponent(station)}${open}` +
    '&select=ticket_number,source,title,status,priority_flag,request_type,requester,updated_at&order=updated_at.desc&limit=200')
  return rows.map((t) => ({ ref: refIn(station, t.ticket_number, t.source, envRefs), ...t }))
}

/**
 * The one ticket with this number, or a refusal naming the candidates.
 *
 * It used to filter `origin=eq.hosted` and take the first row. That separated a station's ticket
 * from an imported one right up until a board HAD an import — and then origin='hosted' was on all
 * 1,313 of ITK's, so a station asking for number 1 got a ticket from June. Both of ITK's by-number
 * writes landed on it: a comment about something else, and a status change that closed a verified
 * ticket (2026-09-21).
 *
 * So: match on the number, take the series when the caller named one, and REFUSE when more than one
 * row answers — naming each, because the caller is the only one who knows which they meant. Picking
 * the first is what did the damage, and it did it while reporting success.
 */
const ASK_COLUMNS = 'waiting_on,ask,ask_detail,ask_answers'
async function hostedByNumber(ctx, n, source = null, more = null) {
  const rows = await ctx.call(
    `board_tickets?kitchen_id=eq.${ctx.kitchen}&project=eq.${encodeURIComponent(ctx.station)}` +
    `&ticket_number=eq.${n}${source ? `&source=eq.${encodeURIComponent(source)}` : ''}` +
    `&select=id,ticket_number,source,status,title,pr_number${more ? `,${more}` : ''}&order=created_at`)
  if (!rows?.length) {
    throw new Error(source
      ? `no ticket ${refIn(ctx.station, n, source, ctx.envRefs)}`
      : `no ticket ${refOf(ctx.station, n)}`)
  }
  if (rows.length > 1) {
    const which = rows.map((t) => `${refIn(ctx.station, t.ticket_number, t.source, ctx.envRefs)} (${t.status}) ${String(t.title || '').slice(0, 40)}`)
    throw new Error(`${rows.length} tickets are numbered ${n} on this board — say which:\n  ${which.join('\n  ')}`)
  }
  return rows[0]
}

/** Add a comment to a hosted ticket. */
export async function comment(args) {
  const ctx = await onBoard(args)
  const { n, source } = ticketTarget(args.number, ctx.station)
  if (!args.text || args.text === true) throw new Error('--text is required')
  const t = await hostedByNumber(ctx, n, source)
  await ctx.call('rpc/board_comment', {
    method: 'POST',
    // WHO WROTE THIS WAS THE STATION, and the record should say so. Left null, board_actor falls
    // back to the JWT's email — and a station signs in as Andrew, so his name went on a comment he
    // never wrote, on a ticket he has never seen (ITK, 2026-09-21). A station's mistake should not
    // be indistinguishable from a decision he made.
    body: JSON.stringify({ p_project: ctx.station, p_id: t.id, p_body: String(args.text), p_who: args.as ? String(args.as) : `the ${ctx.station} station` }),
  })
  // The ref of the ticket it actually wrote to, not the one that was asked for.
  return { ref: refIn(ctx.station, t.ticket_number, t.source, ctx.envRefs), commented: true }
}

/**
 * The PR to link: `--pr <n>`, and its URL from `--url` or from `gh pr view` in this checkout. A ticket marked
 * pr_open without its PR left the tester's "Preview this change" with nothing to open (MSC-SAND-273, 2026-10-24).
 */
export function prLink(args, ghUrl = ghPrUrl) {
  const pr = Number(args.pr)
  if (!Number.isInteger(pr) || pr <= 0) throw new Error('--pr must be the PR number, like --pr 562')
  const url = String(typeof args.url === 'string' && args.url ? args.url : ghUrl(pr)).trim().replace(/\/+$/, '')
  if (!new RegExp(`^https://github\\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/${pr}$`).test(url)) {
    throw new Error(`that isn't the GitHub URL of PR #${pr}: ${url || '(none)'}. Pass --url https://github.com/<owner>/<repo>/pull/${pr}`)
  }
  return { pr, url }
}

function ghPrUrl(pr) {
  const r = spawnSync('gh', ['pr', 'view', String(pr), '--json', 'url', '--jq', '.url'], { encoding: 'utf8' })
  if (r.status !== 0) throw new Error(`couldn't read PR #${pr} with gh here (${String(r.stderr || r.error?.message || '').trim().slice(0, 160)}). Pass --url`)
  return r.stdout.trim()
}

/** Through board_link_pr (bridge/0058): it says who linked it, and raises when there's no such ticket. */
async function linkPr(ctx, t, { pr, url }, args) {
  const [row] = await ctx.call('rpc/board_link_pr', {
    method: 'POST',
    body: JSON.stringify({ p_project: ctx.station, p_id: t.id, p_pr_number: pr, p_pr_url: url, p_who: args.as ? String(args.as) : `the ${ctx.station} station` }),
  }).then((r) => [r].flat())
  if (row?.pr_number !== pr) throw new Error(`asked to link PR #${pr}, the board says ${row?.pr_number ?? 'nothing'}`)
  return row
}

/** Link a hosted ticket to its PR, so the tester's "Preview this change" can open it. */
export async function link(args) {
  const ctx = await onBoard(args)
  const { n, source } = ticketTarget(args.number, ctx.station)
  const l = prLink(args)
  const t = await hostedByNumber(ctx, n, source)
  await linkPr(ctx, t, l, args)
  return { ref: refIn(ctx.station, t.ticket_number, t.source, ctx.envRefs), pr: l.pr, url: l.url }
}

/** Andrew's words for a go, or the reason they can't be recorded. */
export function goWords(args) {
  const words = String(args.said === true ? '' : args.said ?? '').trim()
  if (!words) throw new Error("--said is required: Andrew's own words, as he said them in this session")
  if (words.length > 1000) throw new Error(`--said is ${words.length} characters; the limit is 1000. Quote the part that says go`)
  return words
}

/**
 * Record that Andrew said go on a ticket, in this station's own session. It's what may-merge reads
 * when there was no fire on The Pass: a go in a chat otherwise leaves no record (MSC, 2026-10-31).
 * Never on a relay: a peer saying he said it isn't his word. The line it leaves on the ticket's thread
 * is how he sees what was recorded in his name.
 */
export async function go(args) {
  const ctx = await onBoard(args)
  const { n, source } = ticketTarget(args.ticket ?? args.number, ctx.station)
  const words = goWords(args)
  const t = await hostedByNumber(ctx, n, source)
  const ref = refIn(ctx.station, t.ticket_number, t.source, ctx.envRefs)
  const [row] = await ctx.call('rpc/board_go', {
    method: 'POST',
    body: JSON.stringify({ p_project: ctx.station, p_id: t.id, p_words: words, p_who: `the ${ctx.station} station` }),
  }).then((r) => [r].flat())
  if (!row?.go_at) throw new Error(`asked to record a go on ${ref}, and the board shows none`)
  await ctx.call('station_events', {
    method: 'POST',
    body: JSON.stringify({ station: ctx.station, kind: 'NOTE', chit: ref, text: `Recorded Andrew's go: "${words}"` }),
  }).catch(() => null)
  return { ref, go_at: row.go_at, said: words }
}

/**
 * Andrew's word on a ticket, if it's on record: the go on the ticket, or a proposal he chose that
 * names it. Null otherwise, and null from a Bridge without bridge/0059, so a kit that lands first
 * says no rather than yes.
 */
export async function goOnRecord(ctx, t, ref) {
  let row = null
  try {
    ;[row] = await ctx.call(`board_tickets?id=eq.${t.id}&select=go_at,go_by,go_note`)
  } catch (err) {
    if (!/go_at/.test(String(err.message))) throw err
  }
  if (row?.go_at) return { at: row.go_at, by: row.go_by ?? null, note: row.go_note ?? null }
  const [chosen] = await ctx.call(
    `expeditor_tickets?project=eq.${encodeURIComponent(ctx.station)}&board_ref=eq.${encodeURIComponent(ref)}` +
    '&chosen_at=not.is.null&select=ref,chosen_at&order=chosen_at.desc&limit=1')
  return chosen ? { at: chosen.chosen_at, by: 'The Pass', note: chosen.ref } : null
}

/** Move a hosted ticket. The status comes from the same closed list The Pass uses. */
export async function status(args) {
  const ctx = await onBoard(args)
  const { n, source } = ticketTarget(args.number, ctx.station)
  const to = String(args.to === true ? '' : args.to || '').toLowerCase()
  if (!STATUSES.includes(to)) throw new Error(`--to must be one of: ${STATUSES.join(', ')}`)
  const l = args.pr != null && args.pr !== true ? prLink(args) : null
  const t = await hostedByNumber(ctx, n, source)
  // pr_open means "here is the PR": never without one linked, or the preview has nothing to open.
  if (to === 'pr_open' && !l && !t.pr_number) throw new Error(`${refIn(ctx.station, t.ticket_number, t.source, ctx.envRefs)} has no PR linked: add --pr <number>`)
  if (l) await linkPr(ctx, t, l, args)
  // Through board_status (bridge/0035), not a PATCH on the table. Two reasons, both learned the
  // hard way on 2026-09-21:
  //
  //   WHO. The history trigger asks board_actor() who moved it, and board_actor prefers the
  //   `lodestar.actor` setting over the signed-in email. A PostgREST client cannot set a setting,
  //   so a station's every move was written down under Andrew's address — including the one that
  //   closed a verified ticket while he was asleep. Only a function can set it, so this is one.
  //
  //   WHETHER. A PATCH that matches nothing and a PATCH that worked look identical when nothing
  //   comes back, and this reported "verified → closed" about a row it never touched. The function
  //   raises instead, so there is no silence left to misread.
  const [moved] = await ctx.call('rpc/board_status', {
    method: 'POST',
    body: JSON.stringify({
      p_project: ctx.station, p_id: t.id, p_to: to,
      p_who: args.as ? String(args.as) : `the ${ctx.station} station`,
      p_note: typeof args.note === 'string' ? args.note : null,
    }),
  }).then((r) => [r].flat())
  if (moved?.status !== to) throw new Error(`asked for ${to}, the board says ${moved?.status ?? 'nothing'}`)
  return { ref: refIn(ctx.station, t.ticket_number, t.source, ctx.envRefs), from: t.status, to, ...(l ? { pr: l.pr, url: l.url } : {}) }
}

/** Tickets still waiting on work, which a merged or closed PR should have moved on. */
export const STALE_CHECKED = ['needs_dev', 'pr_open', 'proposed', 'awaiting_confirmation']
const PULL_URL = /^https:\/\/github\.com\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)\/pull\/(\d+)\/?$/

/** The PR a ticket links to, as owner/repo and number, or null when the link isn't a GitHub pull URL. */
export function prOf(ticket) {
  const m = PULL_URL.exec(String(ticket.pr_url || '').trim())
  return m ? { repo: `${m[1]}/${m[2]}`, number: Number(m[3]) } : null
}

/**
 * The open tickets whose PR has merged or been closed without merging, with what to do (Andrew via MSC,
 * 2026-10-28: MSC found a ticket at needs_dev though its PR was closed as superseded, and five merged PRs with no
 * ticket at all). A ticket's status moves in the same step as the work; this finds the ones that didn't.
 * `states` maps "owner/repo#number" to 'merged', 'closed' or 'open'. A PR it couldn't read is left out, not guessed.
 */
export function staleFrom(tickets, states, envRefs = {}, station = '') {
  const out = []
  for (const t of tickets) {
    if (!STALE_CHECKED.includes(t.status)) continue
    const pr = prOf(t)
    const state = pr && states[`${pr.repo}#${pr.number}`]
    if (state !== 'merged' && state !== 'closed') continue
    const ref = refIn(station, t.ticket_number, t.source, envRefs)
    out.push({
      ref, status: t.status, pr: pr.number, pr_state: state, title: t.title,
      do: state === 'merged'
        ? `status --number ${ref} --to testing (on sandbox, waiting for a tester) or verified, then a comment saying how to try it`
        : `status --number ${ref} --to closed if superseded or dropped (say why), or reopen the work and link its new PR`,
    })
  }
  return out
}

function ghPrState(repo, number) {
  const r = spawnSync('gh', ['api', `repos/${repo}/pulls/${number}`, '--jq', '{state: .state, merged: .merged}'], { encoding: 'utf8' })
  if (r.status !== 0) return null
  try {
    const p = JSON.parse(r.stdout)
    return p.merged ? 'merged' : p.state === 'closed' ? 'closed' : 'open'
  } catch { return null }
}

/** Open tickets whose PR has already merged or closed. Reads each PR with gh, so it needs gh signed in here. */
export async function stale(args, prState = ghPrState) {
  const ctx = await onBoard(args)
  const p = encodeURIComponent(ctx.station)
  const tickets = await ctx.call(
    `board_tickets?kitchen_id=eq.${ctx.kitchen}&project=eq.${p}&is_backlog=eq.false` +
    `&status=in.(${STALE_CHECKED.join(',')})&pr_url=not.is.null` +
    '&select=ticket_number,source,title,status,pr_number,pr_url&order=updated_at.desc&limit=200')
  const states = {}
  const unread = []
  for (const t of tickets) {
    const pr = prOf(t)
    if (!pr) continue
    const key = `${pr.repo}#${pr.number}`
    if (key in states) continue
    states[key] = prState(pr.repo, pr.number)
    if (states[key] == null) unread.push(key)
  }
  const todo = staleFrom(tickets, states, ctx.envRefs, ctx.station)
  return { count: todo.length, todo, ...(unread.length ? { unread: `couldn't read ${unread.join(', ')} with gh here` } : {}) }
}

/** A ticket left at `merged` longer than this is flagged: `merged` only means "on dev". */
export const MERGED_REST_MS = 24 * 60 * 60 * 1000
/**
 * A ticket at `merged` this long clears itself (Andrew in ITK's session, 2026-11-11: "there should be a half life
 * on those to self clear in our kits (30 days?)"). ITK had 249 there, every one over 30 days old.
 */
export const MERGED_HALF_LIFE_MS = 30 * 24 * 60 * 60 * 1000
export const HALF_LIFE_NOTE = 'No issue reported in 30 days, so this is closed. Reply here to reopen it.'
const CARRIED_DO = 'status --to testing with a one-line "what to try" comment if a client will try it; awaiting_confirmation if it waits on a client decision; verified if it is internal and you checked it on the running site'

/**
 * Tickets at `merged` that a sync carried to `branch`, and the ones resting at `merged` too long
 * (Andrew via MSC, 2026-11-10). The board reads `merged` as "Andrew, ship this", so MSC's 36 tickets
 * left there, some since September, showed on his Daily Checklist as release cards, while the
 * testers' list missed work already on sandbox. `merged` only means "on dev"; the sync moves them on.
 * Untouched for 30 days at `merged`, a ticket is `expired`: it closes itself with HALF_LIFE_NOTE.
 * `onBranch` maps "owner/repo#number" to true, false, or null when it couldn't be read; null for the whole
 * map when no branch was named.
 */
export function carriedFrom(tickets, onBranch, envRefs = {}, station = '', now = Date.now()) {
  const carried = []
  const resting = []
  const expired = []
  const held = []
  const answered = []
  const tasks = []
  for (const t of tickets) {
    const ref = refIn(station, t.ticket_number, t.source, envRefs)
    const since = Date.parse(t.updated_at || '')
    const age = Number.isFinite(since) ? now - since : 0
    const comments = Array.isArray(t.comments) ? t.comments : []
    if (t.status === 'testing') {
      // Built and with the testers, and nobody has said a word in 30 days: it clears the same way, unless the last
      // person to speak reported a problem (MSC, 2026-11-12: 147 at testing or waiting, 6 of them real).
      if (age <= MERGED_HALF_LIFE_MS) continue
      // A task isn't something a client tries, so silence doesn't mean it passed: NU-LIVE-146 to 151 are "Launch:"
      // work left at testing (NU, 2026-11-12). The same rule the Pass uses to tell a task from a card (list.ts).
      if (isTask(t)) { tasks.push({ ref, title: t.title, since: t.updated_at, do: 'a task, not something to try: finish it, move it to where it really is, or close it saying why' }); continue }
      const w = comments[comments.length - 1]
      if (w && isPersonWord(w) && !WORK_REPORT.test(String(w.body ?? '')) && PROBLEM_WORDS.test(String(w.body ?? ''))) held.push({ ref, title: t.title, since: t.updated_at, why: `${w.who} reported a problem: "${oneLine(w.body, 100)}"` })
      else expired.push({ ref, id: t.id, title: t.title, since: t.updated_at })
      continue
    }
    if (t.status === 'awaiting_confirmation') {
      // The client answered and nobody moved it on (MSC's SAND-389 and 390): say so after a day.
      const last = comments[comments.length - 1]
      const at = Date.parse(last?.at || '')
      if (last && isPersonWord(last) && Number.isFinite(at) && now - at >= ANSWERED_AFTER_MS) {
        answered.push({ ref, title: t.title, who: last.who, at: last.at, said: oneLine(last.body, 100), do: 'they answered: move it on (testing, verified, needs_dev or closed) with a reply' })
      }
      continue
    }
    if (t.status !== 'merged') continue
    const pr = prOf(t)
    if (age > MERGED_HALF_LIFE_MS) { expired.push({ ref, id: t.id, title: t.title, since: t.updated_at }); continue }
    const on = !pr ? false : onBranch ? onBranch[`${pr.repo}#${pr.number}`] : undefined
    if (on === true) { carried.push({ ref, pr: pr.number, title: t.title, do: CARRIED_DO }); continue }
    if (age > MERGED_REST_MS) {
      const why = !pr ? 'no PR linked' : on === false ? 'not on the branch yet' : on === undefined ? 'no --branch named' : "couldn't read its PR"
      resting.push({ ref, ...(pr ? { pr: pr.number } : {}), title: t.title, since: t.updated_at, why })
    }
  }
  return { carried, resting, expired, held, answered, tasks }
}

const TASK_KINDS = ['task', 'chore', 'question']
const TASK_TITLE = /^(launch|after launch|before launch|decide|to-?do)\s*:/i
/** A task rather than a change to try: the Pass's own rule (apps/pass/src/list.ts kindOf). */
export const isTask = (t) => TASK_KINDS.includes(t?.request_type) || TASK_TITLE.test(String(t?.title ?? ''))

/** A client who answered on a waiting ticket is listed after this long. */
export const ANSWERED_AFTER_MS = 24 * 60 * 60 * 1000
/** A station's own word on a ticket ("the msc station"), not a person's. */
export const isStationWord = (c) => /^the [\w-]+ station$/i.test(String(c?.who ?? '').trim())
// The steps the assistant writes on a ticket in the admin's name (stepWords in admin-assistant/board.ts): what
// happened, never someone's report.
const STEP_WORDS = /^(SERVED\b|Approved and merged|Merged (PR|the change)|Opened (PR|a PR|revert)|PR #\d+ (waits|is open)|Rejected:|Handed to the dev team|The change couldn't be applied|Revert PR|Diagnosis and proposed fix)/i
// How a development write-up opens ("Fixed + browser-validated", "ROOT CAUSE", "TEST THIS ON SAND"): a report of
// work, posted from a person's login on older boards, never a problem someone is waiting on. ITK's dry run held 41
// such notes as "a problem" because they name the bug they fixed.
const WORK_REPORT = /^[\s*_#>-]*(fixed|fix (is|was)|shipped|deployed|built|merged|added|done|complete|completed|ready for testing|browser[- ]validated|validated|test this|correction|root cause|false alarm|on (stage|staging|dev|sand|sandbox|live)|live on|substrate|resolved|pushed|released)\b/i
/** Words that say something is wrong. A guess, so a match only holds a ticket back; it never closes one. */
export const PROBLEM_WORDS = /\b(doesn'?t work|does not work|not working|isn'?t working|broken|broke|bug|error|fail(s|ed|ing|ures?)?|wrong|issue|problem|still (shows|see|seeing|get|getting|happens|broken|not)|can'?t|cannot|won'?t|didn'?t|missing|crash(es|ed)?)\b/i
export const isPersonWord = (c) => !!c && !isStationWord(c) && !STEP_WORDS.test(String(c.body ?? '').trim())
/** The last thing a person (not a station, not an assistant step) said on a ticket. */
export function lastPersonWord(comments) {
  for (let i = comments.length - 1; i >= 0; i--) if (isPersonWord(comments[i])) return comments[i]
  return null
}
const oneLine = (s, n) => String(s ?? '').replace(/\s+/g, ' ').trim().slice(0, n)

/** Whether a merged PR's commit is on `branch`: the branch is behind or equal to it, never ahead only. */
function ghOnBranch(repo, number, branch) {
  const pr = spawnSync('gh', ['api', `repos/${repo}/pulls/${number}`, '--jq', '{merged: .merged, sha: .merge_commit_sha}'], { encoding: 'utf8' })
  if (pr.status !== 0) return null
  let p
  try { p = JSON.parse(pr.stdout) } catch { return null }
  if (!p.merged || !p.sha) return false
  const cmp = spawnSync('gh', ['api', `repos/${repo}/compare/${branch}...${p.sha}`, '--jq', '.status'], { encoding: 'utf8' })
  if (cmp.status !== 0) return null
  const s = cmp.stdout.trim()
  return s === 'behind' || s === 'identical'
}

/**
 * Tickets at `merged` whose PR reached `--branch`, to move on in the same step as the sync (reads PRs with gh),
 * and the ones resting there. Any untouched for 30 days close themselves, with a note saying how to reopen,
 * unless `--dry`. Without `--branch` it only clears and lists what's resting: run it so once a day.
 * One sign-in for the whole batch (ITK, 2026-11-11: closing 249 one `status` at a time hit the auth limit).
 */
export async function carried(args, onBranchOf = ghOnBranch) {
  const branch = typeof args.branch === 'string' ? args.branch : null
  const dry = args.dry === true || args.dry === 'true'
  const ctx = await onBoard(args)
  const p = encodeURIComponent(ctx.station)
  const tickets = await ctx.call(
    `board_tickets?kitchen_id=eq.${ctx.kitchen}&project=eq.${p}&is_backlog=eq.false&status=in.(merged,testing,awaiting_confirmation)` +
    '&select=id,ticket_number,source,title,status,request_type,pr_number,pr_url,updated_at,comments&order=updated_at.asc&limit=1000')
  const now = Date.now()
  const onBranch = branch ? {} : null
  const unread = []
  for (const t of branch ? tickets.filter((x) => x.status === 'merged') : []) {
    const pr = prOf(t)
    if (!pr) continue
    if (now - Date.parse(t.updated_at || '') > MERGED_HALF_LIFE_MS) continue
    const key = `${pr.repo}#${pr.number}`
    if (key in onBranch) continue
    onBranch[key] = onBranchOf(pr.repo, pr.number, branch)
    if (onBranch[key] == null) unread.push(key)
  }
  const { carried: moved, resting, expired, held, answered, tasks } = carriedFrom(tickets, onBranch, ctx.envRefs, ctx.station, now)
  const closed = []
  for (const x of dry ? [] : expired) {
    const [row] = await ctx.call('rpc/board_status', {
      method: 'POST',
      body: JSON.stringify({ p_project: ctx.station, p_id: x.id, p_to: 'closed', p_who: `the ${ctx.station} station`, p_note: HALF_LIFE_NOTE }),
    }).then((r) => [r].flat())
    if (row?.status !== 'closed') throw new Error(`closing ${x.ref}: the board says ${row?.status ?? 'nothing'} (closed ${closed.length} before it)`)
    closed.push(x.ref)
  }
  return {
    branch, at_merged: tickets.filter((t) => t.status === 'merged').length, at_testing: tickets.filter((t) => t.status === 'testing').length,
    carried: moved, resting, held, answered, tasks,
    ...(dry ? { would_close: expired.map((x) => x.ref) } : { closed }),
    ...(unread.length ? { unread: `couldn't read ${unread.join(', ')} with gh here` } : {}),
  }
}

// ── Launch commitments (MSC, 2026-11-11) ──────────────────────────────────

/**
 * A promise to a client about launch is a ticket the same day, titled "Launch commitment [<step>]: …", where the
 * step is the gate or launch-day step it's due by (G0…G5, D6…). MSC found promises made in chat ("we'll turn X on
 * at launch") that existed nowhere enforceable. Only `verified` keeps a commitment; `closed` means it was dropped
 * and is said separately, so someone answers for it.
 */
export const COMMITMENT_TITLE = /^\s*Launch commitment\s*\[([A-Za-z]+\d+)\]\s*:\s*(.+)$/i

/** Steps in launch order: as given, or G0…Gn by number when every step is a gate. */
export function stepOrder(steps, order = null) {
  if (order) return order.map((s) => s.toUpperCase())
  const all = [...new Set(steps.map((s) => s.toUpperCase()))]
  if (all.every((s) => /^G\d+$/.test(s))) return all.sort((a, b) => Number(a.slice(1)) - Number(b.slice(1)))
  return null
}

/**
 * Every launch commitment on a board, by step, and with `by` the ones due by that step and not yet verified:
 * a gate can't pass while one is open. `order` lists the steps in launch order; it's needed once D-steps sit
 * between the gates, because only the project knows where they fall.
 */
export function commitmentsFrom(tickets, { by = null, order = null } = {}, envRefs = {}, station = '') {
  const rows = []
  for (const t of tickets) {
    const m = COMMITMENT_TITLE.exec(String(t.title || ''))
    if (!m) continue
    rows.push({ ref: refIn(station, t.ticket_number, t.source, envRefs), step: m[1].toUpperCase(), what: m[2].trim(), status: t.status })
  }
  const steps = stepOrder(rows.map((r) => r.step), order)
  const rank = (s) => (steps ? steps.indexOf(s) : -1)
  rows.sort((a, b) => rank(a.step) - rank(b.step) || a.ref.localeCompare(b.ref, undefined, { numeric: true }))
  const out = { count: rows.length, kept: rows.filter((r) => r.status === 'verified').length, commitments: rows }
  if (!by) return out
  const at = String(by).toUpperCase()
  if (!steps) throw new Error('these commitments name launch-day steps as well as gates: say the launch order with --order G0,G1,G2,D1,…,G3,…')
  if (!steps.includes(at)) throw new Error(`${at} isn't in the launch order (${steps.join(', ')})`)
  const unplaced = [...new Set(rows.map((r) => r.step).filter((s) => !steps.includes(s)))]
  const due = rows.filter((r) => steps.includes(r.step) && rank(r.step) <= rank(at))
  const open = due.filter((r) => r.status !== 'verified' && r.status !== 'closed')
  const dropped = due.filter((r) => r.status === 'closed')
  return {
    ...out, by: at, go: open.length === 0 && unplaced.length === 0,
    open, dropped,
    ...(unplaced.length ? { unplaced: `${unplaced.join(', ')} isn't in --order: place it, or the gate can't be judged` } : {}),
  }
}

/**
 * `beat commitments --station msc [--by G4 --order G0,G1,G2,D1,D2,D3,D4,G3,D5,D6,D7,G4,D8,D9,D10,D11,G5]`. With `--by`, it exits 1
 * while any commitment due by that step isn't verified, so a launch preflight can run it as one of its checks.
 */
export async function commitments(args) {
  const order = typeof args.order === 'string' ? args.order.split(',').map((s) => s.trim()).filter(Boolean) : null
  const out = await readCommitments({ station: args.station, by: typeof args.by === 'string' ? args.by : null, order })
  if (out.go === false) process.exitCode = 1
  return out
}

/** The same read for a launch preflight's commitments row (scripts/lodestar/launch-preflight.mjs), without the exit code. */
export async function readCommitments({ station, by = null, order = null }) {
  const ctx = await onBoard({ station })
  const tickets = await ctx.call(
    `board_tickets?kitchen_id=eq.${ctx.kitchen}&project=eq.${encodeURIComponent(ctx.station)}` +
    '&title=ilike.*launch%20commitment*&select=ticket_number,source,title,status&limit=500')
  return commitmentsFrom(tickets, { by, order }, ctx.envRefs, ctx.station)
}

/**
 * Say who a ticket waits on and what's asked of them (bridge/0061; Andrew via MSC, 2026-11-12: "sprawl between
 * PR's, tickets, docs and checklist"). The ask lives on the ticket, beside its status, so an ask on a merged
 * ticket still reaches the client. Rachael approved MSC's Emails 1 and 2 in WhatsApp because the ask rode on a
 * ticket at `merged` and never reached her list.
 *
 *   beat ask --station msc --number 388 --on client --ask "Approve Emails 1 and 2"
 *   beat ask --station msc --number 388 --on development          # back with development, no question
 *   beat ask --station msc --number 388 --clear
 */
export async function ask(args) {
  const clear = args.clear === true || args.clear === 'true'
  const on = clear ? null : typeof args.on === 'string' ? args.on.trim().toLowerCase() : null
  if (!clear && !WAITING_ON.includes(on)) throw new Error(`--on must be one of: ${WAITING_ON.join(', ')} (or --clear)`)
  // The questions (bridge/0062): from --file, or the quick form --ask "…" --options "A*|B" --why "…".
  let text = clear ? null : typeof args.ask === 'string' ? args.ask.replace(/\s+/g, ' ').trim() : null
  let detail = null
  if (!clear && typeof args.file === 'string') {
    ;({ ask: text, detail } = normalizeAsk(JSON.parse(fs.readFileSync(args.file, 'utf8'))))
  } else if (!clear && text && (typeof args.options === 'string' || typeof args.why === 'string')) {
    ;({ ask: text, detail } = normalizeAsk({ questions: [{ text, why: typeof args.why === 'string' ? args.why : undefined, options: optionsFromFlag(args.options) }] }))
  }
  if (text && text.length > 200) throw new Error(`an ask is one line: ${text.length} characters, at most 200`)
  const ctx = await onBoard(args)
  const { n, source } = ticketTarget(args.number, ctx.station)
  const t = await hostedByNumber(ctx, n, source, ASK_COLUMNS)
  const who = args.as ? String(args.as) : `the ${ctx.station} station`
  // Asking a ticket whose ask is fully answered asks again, from no answers. The board keeps answers when the same
  // ask is sent twice, so a re-run mid-way loses nothing; MSC's trial (2026-11-13) re-asked an answered ticket and the
  // card read "Answered. Development has it." while it waited on the client.
  const again = !clear && on === 'client' && (t.ask_answers?.length ?? 0) > 0 && askProgress(t.ask_detail, t.ask_answers).done
  if (again) {
    await ctx.call('rpc/board_ask', { method: 'POST', body: JSON.stringify({ p_project: ctx.station, p_id: t.id, p_on: null, p_ask: null, p_who: who }) })
  }
  const [row] = await ctx.call('rpc/board_ask', {
    method: 'POST',
    body: JSON.stringify({ p_project: ctx.station, p_id: t.id, p_on: on, p_ask: text, p_who: who, ...(detail ? { p_detail: detail } : {}) }),
  }).then((r) => [r].flat())
  if ((row?.waiting_on ?? null) !== on || (row?.ask ?? null) !== (text || null)) {
    throw new Error(`asked for ${on ?? 'nobody'}${text ? `: "${text}"` : ''}, the board says ${row?.waiting_on ?? 'nobody'}${row?.ask ? `: "${row.ask}"` : ''}`)
  }
  return {
    ref: refIn(ctx.station, t.ticket_number, t.source, ctx.envRefs), status: t.status, waiting_on: row.waiting_on ?? null, ask: row.ask ?? null,
    ...(again ? { asked_again: 'its earlier answers were complete, so this asks again with none' } : {}),
    ...(row.ask_detail ? { questions: row.ask_detail.questions.map((q) => `${q.text} [${[...q.options.map((o) => o.label + (o.recommended ? '*' : '')), ...(q.other === false ? [] : [q.other])].join(' | ')}]`) } : {}),
  }
}

/**
 * Record an answer given somewhere else, a message or a call, on the ticket, under the person's name (bridge/0062).
 * Only the ticket counts (Andrew via MSC, 2026-11-12: an approval given in WhatsApp lived nowhere enforceable).
 *
 *   beat answer --station msc --number 388 --choice "Three days before launch" --as "Rachael (WhatsApp)"
 *   beat answer --station msc --number 388 --question pages --choice "Another number" --value 12 --as "Nathan (call)"
 *   beat answer --station msc --number 388 --text "Yes, it reads 30 June 2027" --as "Rachael (WhatsApp)"
 */
export async function answer(args) {
  const as = typeof args.as === 'string' ? args.as.trim() : ''
  if (!as) throw new Error('say whose answer this is and where it came from: --as "Rachael (WhatsApp)"')
  const choice = typeof args.choice === 'string' ? args.choice.split('|').map((x) => x.trim()).filter(Boolean) : []
  const ctx = await onBoard(args)
  const { n, source } = ticketTarget(args.number, ctx.station)
  const t = await hostedByNumber(ctx, n, source)
  const [row] = await ctx.call('rpc/board_answer', {
    method: 'POST',
    body: JSON.stringify({
      p_project: ctx.station, p_id: t.id, p_question: typeof args.question === 'string' ? args.question : null, p_choice: choice,
      p_value: typeof args.value === 'string' ? args.value : null, p_text: typeof args.text === 'string' ? args.text : null, p_who: as,
    }),
  }).then((r) => [r].flat())
  if (!row?.id) throw new Error('the board did not return the ticket; check `ticket` before answering again')
  return { ref: refIn(ctx.station, t.ticket_number, t.source, ctx.envRefs), waiting_on: row.waiting_on ?? null, said: row.comments?.at(-1)?.body ?? null }
}

/**
 * The consolidate pass: put an existing board in order around its tickets (Andrew, 2026-11-12: "we'll need a way to
 * backfill and do a consolidate pass on existing boards to organize stuff"). Reads the whole board and says what it
 * would do (consolidatePlan in board.mjs). With --apply it does the unambiguous part in one sign-in: the asks, and
 * the links from a document to the one to three tickets it names. What needs judgement comes back as `todo`, each
 * with its command. Run `beat carried` first: a write restarts a ticket's 30-day clock.
 *
 *   beat consolidate --station msc            # the plan
 *   beat consolidate --station msc --apply    # do the asks and links
 */
export async function consolidate(args) {
  const apply = args.apply === true || args.apply === 'true'
  const ctx = await onBoard(args)
  const p = encodeURIComponent(ctx.station)
  const [tickets, docs, links] = await Promise.all([
    ctx.call(`board_tickets?kitchen_id=eq.${ctx.kitchen}&project=eq.${p}&select=id,ticket_number,source,title,status,is_backlog,waiting_on,ask,updated_at&limit=5000`),
    ctx.call(`board_documents?kitchen_id=eq.${ctx.kitchen}&project=eq.${p}&select=id,title,doc_type,body_md,ticket_id&limit=2000`),
    ctx.call(`board_document_links?kitchen_id=eq.${ctx.kitchen}&project=eq.${p}&select=document_id,ticket_id&limit=10000`),
  ])
  const plan = consolidatePlan({ tickets, docs, links, station: ctx.station, envRefs: ctx.envRefs })
  const out = {
    station: ctx.station, applied: apply,
    asks: plan.asks.map(({ id, ...a }) => a),
    links: plan.links.map(({ document_id, ticket_id, ...l }) => l),
    todo: plan.todo,
    ...(plan.skipped.length ? { skipped: `${plan.skipped.length} ticket(s) the 30-day clear would close; run \`beat carried\` first: ${plan.skipped.slice(0, 10).join(', ')}${plan.skipped.length > 10 ? ', …' : ''}` } : {}),
  }
  if (!apply) return out
  const who = args.as ? String(args.as) : `the ${ctx.station} station`
  let asked = 0
  for (const a of plan.asks) {
    const [row] = await ctx.call('rpc/board_ask', {
      method: 'POST', body: JSON.stringify({ p_project: ctx.station, p_id: a.id, p_on: a.on, p_ask: a.ask, p_who: who }),
    }).then((r) => [r].flat())
    if (row?.ask !== a.ask) throw new Error(`asking on ${a.ref}: the board says ${row?.ask ?? 'nothing'} (${asked} asked before it)`)
    asked++
  }
  let linked = 0
  for (const l of plan.links) {
    await ctx.call('board_document_links', {
      method: 'POST', headers: { prefer: 'resolution=ignore-duplicates,return=minimal' },
      body: JSON.stringify({ kitchen_id: ctx.kitchen, project: ctx.station, document_id: l.document_id, ticket_id: l.ticket_id, linked_by: who }),
    })
    linked++
  }
  return { ...out, asked, linked }
}

/**
 * Link a document to a ticket: `beat doc-link --station msc --id <document id> --ticket MSC-DEV-344`. With `--parent`, that
 * ticket is the one the document supports (bridge/0063): its comments land on that ticket's thread.
 */
export async function docLink(args) {
  const ctx = await onBoard(args)
  const id = String(args.id ?? '')
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) throw new Error(`--id is a document id (a uuid), not ${id || 'nothing'}`)
  const [doc] = await ctx.call(`board_documents?kitchen_id=eq.${ctx.kitchen}&project=eq.${encodeURIComponent(ctx.station)}&id=eq.${id}&select=id,title`)
  if (!doc) throw new Error(`no document ${id} on ${ctx.station}'s board`)
  const { n, source } = ticketTarget(args.ticket, ctx.station)
  const t = await hostedByNumber(ctx, n, source)
  await ctx.call('board_document_links', {
    method: 'POST', headers: { prefer: 'resolution=ignore-duplicates,return=minimal' },
    body: JSON.stringify({ kitchen_id: ctx.kitchen, project: ctx.station, document_id: doc.id, ticket_id: t.id, linked_by: args.as ? String(args.as) : `the ${ctx.station} station` }),
  })
  // --parent: this is the ticket the document supports (bridge/0063), where its comments land.
  const parent = args.parent === true || args.parent === 'true'
  if (parent) {
    const [set] = await ctx.call(`board_documents?kitchen_id=eq.${ctx.kitchen}&project=eq.${encodeURIComponent(ctx.station)}&id=eq.${doc.id}&select=ticket_id`, {
      method: 'PATCH', headers: { prefer: 'return=representation' }, body: JSON.stringify({ ticket_id: t.id }),
    })
    if (set?.ticket_id !== t.id) throw new Error(`asked to stand ${doc.title} on ${refIn(ctx.station, t.ticket_number, t.source, ctx.envRefs)}; the Bridge says ${set?.ticket_id ?? 'nothing'}`)
  }
  return { document: doc.title, ticket: refIn(ctx.station, t.ticket_number, t.source, ctx.envRefs), link: documentLink(doc.id), ...(parent ? { parent: true } : {}) }
}

/**
 * Park a ticket: keep it, but take it off Andrew's waiting list (his daily email and the Pass skip
 * backlog, bridge/0050c). `--unpark` brings it back. Through board_backlog (bridge/0051), for the same
 * two reasons `status` goes through board_status: a function can say who did it, and it raises when
 * there's no such ticket instead of a PATCH that silently matched nothing (NU, 2026-10-13).
 */
export async function park(args) {
  const ctx = await onBoard(args)
  const { n, source } = ticketTarget(args.number, ctx.station)
  const t = await hostedByNumber(ctx, n, source)
  const parked = !(args.unpark === true || args.unpark === 'true')
  const [row] = await ctx.call('rpc/board_backlog', {
    method: 'POST',
    body: JSON.stringify({
      p_project: ctx.station, p_id: t.id, p_backlog: parked,
      p_who: args.as ? String(args.as) : `the ${ctx.station} station`,
      p_note: typeof args.note === 'string' ? args.note : null,
    }),
  }).then((r) => [r].flat())
  if (row?.is_backlog !== parked) throw new Error(`asked to ${parked ? 'park' : 'unpark'} it, the board says is_backlog = ${row?.is_backlog}`)
  return { ref: refIn(ctx.station, t.ticket_number, t.source, ctx.envRefs), parked, status: row.status }
}

// ── Plain words (bridge/0010) ──────────────────────────────────────────────

/**
 * Write tickets up in plain words: one from flags, or many from a JSON file (an array of
 * { ref | number, issue, blocking, risk, options: [{ id, label, gain, cost }], recommend, detail,
 * ticket_updated_at }). Every entry is checked before any is written.
 */
export async function explain(args) {
  const { call, station, kitchen } = await onBoard(args)
  const inputs = typeof args.file === 'string'
    ? [JSON.parse(fs.readFileSync(args.file, 'utf8'))].flat()
    : [args]
  const rows = inputs.map((i) => ({
    ...explainerRow(i, station),
    kitchen_id: kitchen,
    written_by: `station:${station}`,
    written_at: new Date().toISOString(),
  }))
  await call('ticket_explainers?on_conflict=kitchen_id,project,ref', {
    method: 'POST',
    headers: { prefer: 'resolution=merge-duplicates,return=minimal' },
    body: JSON.stringify(rows),
  })
  return { explained: rows.map((r) => r.ref) }
}

/**
 * Open tickets with no explainer, or one written before the ticket last changed. Decisions first.
 * Reads the Bridge's copy of the board; an own board that isn't copied yet has to be listed from
 * the app instead, and this says so.
 */
export async function unexplained(args) {
  const { call, station, kitchen, project } = await onBoard(args)
  const p = encodeURIComponent(station)
  const [tickets, done] = await Promise.all([
    call(`board_tickets?kitchen_id=eq.${kitchen}&project=eq.${p}&is_backlog=eq.false` +
      '&status=in.(proposed,awaiting_confirmation,needs_dev,pr_open,testing,testing_failed,discuss,verified,pending_review,ready_to_merge,error)' +
      '&select=ticket_number,source,title,status,priority_flag,updated_at&order=updated_at.desc&limit=1000'),
    call(`ticket_explainers?kitchen_id=eq.${kitchen}&project=eq.${p}&select=ref,ticket_updated_at`),
  ])
  const have = new Map(done.map((e) => [e.ref, e.ticket_updated_at]))
  const QUEUE = new Set(['testing', 'verified'])
  const todo = tickets
    .map((t) => {
      // With its tag where the project names environments (ITK-STG-1240); an older untagged
      // explainer still counts where tags are optional.
      const tagged = taggedRef(station, t.ticket_number, t.source, project.env_by_source ?? {})
      const plain = refOf(station, t.ticket_number)
      const ref = tagged
      const key = have.has(tagged) ? tagged : !project.tags_required && have.has(plain) ? plain : null
      const at = key ? have.get(key) : undefined
      const why = !key ? 'not explained' : at && Date.parse(t.updated_at) > Date.parse(at) + 1000 ? 'ticket changed since' : null
      return why ? { ref, status: t.status, priority: t.priority_flag, title: t.title, updated_at: t.updated_at, why } : null
    })
    .filter(Boolean)
    .sort((a, b) => (QUEUE.has(a.status) - QUEUE.has(b.status)) || (!!b.priority - !!a.priority))
  const note = !tickets.length && project.board_mode === 'own'
    ? `No copy of ${station}'s board is on the Bridge yet. List your own open tickets from the app (anything needing a decision first) and explain those.`
    : undefined
  return { count: todo.length, todo: todo.slice(0, Number(args.limit) || 20), ...(note ? { note } : {}) }
}

// ── Documents (bridge/0022) ────────────────────────────────────────────────

/**
 * Post a document to this station's Documents tab, or with --id, write a new revision of one. The
 * Bridge keeps every revision itself (board_documents_revise), so replacing the text loses nothing.
 */
export async function doc(args) {
  const ctx = await onBoard(args)
  const { call, station, kitchen } = ctx
  const body = typeof args.file === 'string' ? fs.readFileSync(args.file, 'utf8') : undefined
  if (args.id && args.id !== true) {
    const id = String(args.id)
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) throw new Error(`not a document id: ${id}`)
    const [was] = await call(`board_documents?kitchen_id=eq.${kitchen}&project=eq.${encodeURIComponent(station)}&id=eq.${id}&select=title,doc_type,body_md`)
    if (!was) throw new Error(`no document ${id} on ${station}'s board`)
    const row = documentRow({ title: args.title && args.title !== true ? args.title : was.title, type: args.type && args.type !== true ? args.type : was.doc_type, body_md: body ?? was.body_md, as: args.as }, station)
    const [made] = await call(`board_documents?kitchen_id=eq.${kitchen}&project=eq.${encodeURIComponent(station)}&id=eq.${id}&select=id,title,doc_type,updated_at`, {
      method: 'PATCH', headers: { prefer: 'return=representation' },
      body: JSON.stringify({ title: row.title, doc_type: row.doc_type, body_md: row.body_md }),
    })
    if (!made) throw new Error(`the Bridge did not update document ${id}; nothing changed`)
    return { updated: made.id, title: made.title, type: made.doc_type, link: documentLink(made.id), at: made.updated_at }
  }
  const row = { ...documentRow({ ...args, body_md: body }, station), kitchen_id: kitchen }
  // The ticket first (Andrew via MSC, 2026-11-12: "ticket first then document to support"): a ref that doesn't
  // resolve stops the post. The document is posted standing on it (bridge/0063), which links it in the same write.
  let ticket = null
  if (args.ticket && args.ticket !== true) {
    const { n, source } = ticketTarget(args.ticket, station)
    ticket = await hostedByNumber(ctx, n, source)
    row.ticket_id = ticket.id
  }
  const [made] = await call('board_documents?select=id,title,doc_type,created_at', {
    method: 'POST', headers: { prefer: 'return=representation' }, body: JSON.stringify(row),
  })
  if (!made) throw new Error('the Bridge did not return the document; check `docs` before posting again')
  // With no ticket named, the Bridge made one for it as the write committed: say which, so it can be used.
  if (!ticket) {
    const [after] = await call(`board_documents?kitchen_id=eq.${kitchen}&project=eq.${encodeURIComponent(station)}&id=eq.${made.id}&select=ticket_id`)
    if (after?.ticket_id) {
      ;[ticket] = await call(`board_tickets?kitchen_id=eq.${kitchen}&project=eq.${encodeURIComponent(station)}&id=eq.${after.ticket_id}&select=id,ticket_number,source,status,title`)
    }
  }
  return {
    posted: made.id, title: made.title, type: made.doc_type, link: documentLink(made.id),
    ...(ticket ? { ticket: refIn(station, ticket.ticket_number, ticket.source, ctx.envRefs), ...(args.ticket && args.ticket !== true ? {} : { made: 'the Bridge made this ticket for it: give it the plain words of what the document is for' }) } : {}),
  }
}

/** This station's documents, newest first. */
/**
 * What people have written ON this station's documents: author, the passage, and the words.
 *
 * Waiting by default: neither answered (bridge/0057) nor resolved. `--all` includes the rest.
 * Testers are told to answer through documents, so this is a real inbox, not a curiosity: four of
 * Nathan's answers and 32 older comments sat unread because nothing listed them (MSC, 2026-09-27).
 * A new comment also calls (bridge/0047), so `calls` says a document is waiting and this says what.
 *
 * Answer one with a REPLY on the call, or by commenting on the document in the app.
 */
export async function docComments_(args) {
  const { call, station, kitchen } = await onBoard(args)
  const all = args.all === true || args.all === 'true'
  const rows = await call(`board_document_comments?kitchen_id=eq.${kitchen}&project=eq.${encodeURIComponent(station)}` +
    (all ? '' : '&resolved_at=is.null&answered_at=is.null') +
    '&select=id,document_id,author,author_email,body,anchor_text,resolved_at,resolved_by,answer,answered_at,answered_by,created_at' +
    '&order=created_at.desc&limit=300')
  const docRows = await call(`board_documents?kitchen_id=eq.${kitchen}&project=eq.${encodeURIComponent(station)}&select=id,title&limit=200`)
    .catch(() => [])
  const out = docComments(rows, docRows)
  return { ...out, ...(all ? {} : { do: out.count ? 'answer each one where the person will see it: doc-answer --comment <id> --answer "<the answer, or a link to it>" (it stays listed, with the answer under it); never resolve an answered comment, that hides it' : 'nothing waiting' }) }
}

const COMMENT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Marking a document comment seen: the patch, and who it says did it. On the Daily Checklist a
 * comment is an answer; resolving it hands the item back to the people who test, so development
 * marks it once it has acted (MSC, 2026-10-07). `--reopen` undoes it.
 */
export function resolvePatch({ reopen = false, station, now = new Date() } = {}) {
  return reopen ? { resolved_at: null, resolved_by: null } : { resolved_at: now.toISOString(), resolved_by: `${String(station).toUpperCase()} station` }
}

/**
 * Marking a document comment answered (bridge/0057): the answer, or a link to where it is, sits under the
 * question and the comment stays listed. Resolving hides a comment, which is why MSC's answers to a client's
 * seven comments vanished from beside them (Andrew, 2026-10-23: "just mark don't hide answered comments").
 * `--clear` takes the mark off.
 */
export function answerPatch({ answer = '', clear = false, station, now = new Date() } = {}) {
  const text = String(answer ?? '').trim()
  if (clear) return { answer: null, answered_at: null, answered_by: null }
  if (!text) throw new Error('say what the answer is, or where: --answer "<text or link>"')
  if (text.length > 50000) throw new Error(`that answer is ${text.length} characters; the limit is 50000. Put it in a document and link it`)
  return { answer: text, answered_at: now.toISOString(), answered_by: `${String(station).toUpperCase()} station` }
}

export async function docAnswer(args) {
  const id = String(args.comment ?? '')
  if (!COMMENT_ID.test(id)) throw new Error('name the comment: --comment <id> (doc-comments lists them)')
  const clear = args.clear === true || args.clear === 'true'
  const { call, station, kitchen } = await onBoard(args)
  const patch = answerPatch({ answer: args.answer === true ? '' : args.answer, clear, station })
  const rows = await call(`board_document_comments?kitchen_id=eq.${kitchen}&project=eq.${encodeURIComponent(station)}&id=eq.${id}` +
    '&select=id,document_id,author,body,answer,answered_at,answered_by', {
    method: 'PATCH', headers: { prefer: 'return=representation' }, body: JSON.stringify(patch),
  })
  if (!rows?.length) throw new Error(`no comment ${id} on the ${station.toUpperCase()} board`)
  const c = rows[0]
  return { id: c.id, document: c.document_id, from: c.author, said: String(c.body).slice(0, 120), answered: Boolean(c.answered_at), answer: c.answer, by: c.answered_by }
}

export async function docResolve(args) {
  const id = String(args.comment ?? '')
  if (!COMMENT_ID.test(id)) throw new Error('name the comment: --comment <id> (doc-comments --all lists them)')
  const { call, station, kitchen } = await onBoard(args)
  const reopen = args.reopen === true || args.reopen === 'true'
  const rows = await call(`board_document_comments?kitchen_id=eq.${kitchen}&project=eq.${encodeURIComponent(station)}&id=eq.${id}` +
    '&select=id,document_id,author,body,resolved_at,resolved_by', {
    method: 'PATCH', headers: { prefer: 'return=representation' }, body: JSON.stringify(resolvePatch({ reopen, station })),
  })
  if (!rows?.length) throw new Error(`no comment ${id} on the ${station.toUpperCase()} board`)
  const c = rows[0]
  return { id: c.id, document: c.document_id, from: c.author, said: String(c.body).slice(0, 120), resolved: Boolean(c.resolved_at), by: c.resolved_by }
}

export async function docs(args) {
  const { call, station, kitchen } = await onBoard(args)
  const rows = await call(`board_documents?kitchen_id=eq.${kitchen}&project=eq.${encodeURIComponent(station)}` +
    '&select=id,title,doc_type,created_by,updated_at&order=updated_at.desc&limit=100')
  return rows.map((d) => ({ ...d, link: documentLink(d.id) }))
}

// ── Merging on your own (bridge/0038) ─────────────────────────────────────

/** Runs gh in this repo and returns its stdout; says what failed when it does. */
export function gh(argv, run = spawnSync) {
  const r = run('gh', argv, { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
  if (r.error) throw new Error(`could not run gh: ${r.error.message}`)
  if (r.status !== 0) throw new Error(`gh ${argv.slice(0, 2).join(' ')} failed: ${String(r.stderr || '').trim().slice(0, 300)}`)
  return r.stdout
}

/** This project's merge list. Null, never a guess, when the Bridge has none or predates 0038. */
async function mergePolicy(ctx) {
  try {
    const [row] = await ctx.call(`projects?kitchen_id=eq.${ctx.kitchen}&key=eq.${encodeURIComponent(ctx.station)}&select=merge_policy`)
    return row?.merge_policy ?? null
  } catch (err) {
    if (/merge_policy/.test(String(err.message))) return null
    throw err
  }
}

/**
 * May this station merge PR <n> itself? Reads the PR from GitHub and the merge list from the
 * Bridge, and answers with mergeVerdict. It never merges: the station runs the command it's given.
 */
export async function mayMerge(args, run = spawnSync) {
  const n = Number(args.pr)
  if (!Number.isInteger(n) || n <= 0) throw new Error('--pr <number> is required')
  const ctx = await onBoard(args)
  const repo = args.repo && args.repo !== true ? ['--repo', String(args.repo)] : []
  const pr = JSON.parse(gh(['pr', 'view', String(n), ...repo, '--json',
    'number,state,isDraft,baseRefName,mergeStateStatus,isCrossRepository,changedFiles,statusCheckRollup,url'], run))
  const where = args.repo && args.repo !== true ? String(args.repo) : '{owner}/{repo}'
  const files = gh(['api', `repos/${where}/pulls/${n}/files`, '--paginate', '--jq', '.[] | {filename, previous_filename, patch}'], run)
    .split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l))
  let ticket = null
  if (args.ticket && args.ticket !== true) {
    const { n: tn, source } = ticketTarget(args.ticket, ctx.station)
    const t = await hostedByNumber(ctx, tn, source)
    const ref = refIn(ctx.station, t.ticket_number, t.source, ctx.envRefs)
    ticket = { ref, status: t.status, go: await goOnRecord(ctx, t, ref) }
  }
  // The host's own lock says which files Lodestar writes here, so `kit` isn't guessed from a list
  // that can fall behind the manifest (MSC, 2026-09-22). Missing or unreadable: the list answers.
  let managed = null
  try { managed = managedFiles(JSON.parse(fs.readFileSync('lodestar.lock', 'utf8'))) } catch { managed = null }
  // A host's own words, so "policy" on an insurance board isn't read as an RLS policy (MSC).
  let domainWords = null
  try { domainWords = JSON.parse(fs.readFileSync('lodestar.config.json', 'utf8'))?.merge?.domainWords ?? null } catch { domainWords = null }
  return { url: pr.url, ...mergeVerdict({ policy: await mergePolicy(ctx), pr, files, ticket, managed, domainWords }) }
}

// ── CLI ────────────────────────────────────────────────────────────────────
// pathToFileURL, not `file://${argv[1]}` — the latter never matches import.meta.url on Windows,
// so the block silently never ran and the script exited 0 having done nothing. argv[1] is
// undefined under `node -e`, where pathToFileURL would throw on an ordinary import.
const entrypoint = process.argv[1]
  ? (await import('node:url')).pathToFileURL(process.argv[1]).href
  : null

/**
 * `--dry` on a command that has no dry run is refused before anything happens. MSC ran `beat comment … --dry` expecting
 * a preview, and the comment posted on MSC-DEV-364 (2026-11-13). `consolidate` previews unless `--apply`.
 */
export const DRY_RUNS = ['carried']
export function dryRefusal(cmd, args) {
  if (args.dry === undefined || args.dry === false || DRY_RUNS.includes(cmd)) return null
  return `${cmd} has no --dry, so nothing was done. Dry runs: ${DRY_RUNS.join(', ')}; consolidate shows its plan unless --apply.`
}

if (entrypoint && import.meta.url === entrypoint) {
  const [cmd, ...rest] = process.argv.slice(2)
  const args = parseArgs(rest)
  const refused = dryRefusal(cmd, args)
  if (refused) {
    console.error(refused)
    process.exitCode = 2
  }
  const COMMANDS = { beat, brief, fires, calls, heard, say, roll, bell, watch, line, photo, look, mirror, ticket, tickets, comment, go, status, link, stale, carried, commitments, ask, answer, consolidate, 'doc-link': docLink, park, explain, unexplained, fresh, doc, docs, 'doc-comments': docComments_, 'doc-resolve': docResolve, 'doc-answer': docAnswer, 'may-merge': mayMerge, 'publish-brief': publishBrief }
  const run = refused ? null : COMMANDS[cmd]
  if (refused) {
    // said above; nothing runs
  } else if (!run) {
    console.error(`usage: node beat.mjs <${Object.keys(COMMANDS).join('|')}> [--flags]`)
    // exitCode rather than exit(): process.exit() while fetch's socket is still tearing down
    // aborts Node on Windows with a libuv assertion, which turns a clear error message into an
    // unreadable crash. Setting the code lets the event loop drain and exit on its own.
    process.exitCode = 2
  } else {
    try {
      const out = await run(args)
      // The brief is prose for the thread to read; everything else is data.
      process.stdout.write(typeof out === 'string' ? out : JSON.stringify(out, null, 2) + '\n')
    } catch (err) {
      // Say what happened, loudly. A station whose heartbeat fails silently is exactly the
      // failure the whole `last_seen_at` design exists to make visible — do not hide it here.
      console.error(String(err.message || err))
      process.exitCode = 1
    }
  }
}
