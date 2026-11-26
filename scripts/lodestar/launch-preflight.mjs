#!/usr/bin/env node
// Launch preflight: one read-only check per go/no-go gate (Andrew via MSC, 2026-11-11: "launch protocol is
// critical for successful app hygiene and deployments"). Lifted from MSC's scripts/launch-preflight.mjs
// (MSC-DEV-333, 899), which exists because on 9 Nov a new environment ran production crons against the live
// database and emailed 36 real customers, and the old checklist, followed as written, would have done it again.
//
//   node scripts/lodestar/launch-preflight.mjs --gate G2 [--mode disarmed|armed] [--config launch/preflight.config.mjs]
//
// The kit owns the runner and the checks every app needs. Your project owns its gates and its table, in
// launch/preflight.config.mjs (start from launch/preflight.example.mjs). Exit 0 when nothing fails (MANUAL rows
// still need their owner), 1 when anything fails, 2 on a usage error.
//
// READ-ONLY. GET requests only (Vercel REST, Supabase Management API, Stripe, DNS-over-HTTPS, the sites); database
// reads go through Supabase's read-only query endpoint and a SELECT-only guard. Nothing is written, no email is
// sent, and no secret is printed: Vercel settings are judged by name, and only the plain-text switches a check
// names are read.
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import tls from 'node:tls'
import { pathToFileURL } from 'node:url'

export const TIMEOUT_MS = 20_000
export const MODES = ['disarmed', 'armed']
const ok = (detail) => ({ status: 'PASS', detail })
const fail = (detail) => ({ status: 'FAIL', detail })
const warn = (detail) => ({ status: 'WARN', detail })

// ── The table ──────────────────────────────────────────────────────────────

/** Gate names in launch order: the order the config writes them in. */
export function gateOrder(config) {
  const g = Object.keys(config?.gates ?? {})
  if (!g.length) throw new Error('the config names no gates: export default { gates: { G0: { title, when, mode }, … }, checks: [ … ] }')
  return g
}

/** Which gates a check runs at: 'all', a list, or { from, to } in launch order. */
export function gatesOf(spec, order) {
  if (spec === 'all' || spec == null) return [...order]
  if (Array.isArray(spec)) {
    const bad = spec.filter((g) => !order.includes(g))
    if (bad.length) throw new Error(`unknown gate ${bad.join(', ')} (gates: ${order.join(', ')})`)
    return order.filter((g) => spec.includes(g))
  }
  const from = spec.from ? order.indexOf(spec.from) : 0
  const to = spec.to ? order.indexOf(spec.to) : order.length - 1
  if (from < 0 || to < 0) throw new Error(`unknown gate in ${JSON.stringify(spec)} (gates: ${order.join(', ')})`)
  return order.slice(from, to + 1)
}

/** The checks for one gate, in table order. A check is automated (run) or manual (who), never neither. */
export function checksFor(config, gate) {
  const order = gateOrder(config)
  if (!order.includes(gate)) throw new Error(`${gate} isn't a gate here (gates: ${order.join(', ')})`)
  const ids = new Set()
  for (const c of config.checks ?? []) {
    if (!c.id || !c.name) throw new Error(`a check needs an id and a name: ${JSON.stringify(c).slice(0, 80)}`)
    if (ids.has(c.id)) throw new Error(`two checks are called ${c.id}`)
    ids.add(c.id)
    if (!c.who && typeof c.run !== 'function') throw new Error(`${c.id} has neither a run() nor a who: say how it's checked`)
  }
  return (config.checks ?? []).filter((c) => gatesOf(c.gates, order).includes(gate))
}

/** What a run is judging: the gate, its mode (the gate's own unless --mode says otherwise), and launch order. */
export function contextFor(config, gate, mode = null, now = new Date()) {
  const order = gateOrder(config)
  if (!order.includes(gate)) throw new Error(`${gate || 'no gate'} isn't a gate here (gates: ${order.join(', ')})`)
  const own = config.gates[gate]?.mode ?? 'disarmed'
  const m = mode ?? own
  if (!MODES.includes(m)) throw new Error(`--mode is ${MODES.join(' or ')}`)
  const at = order.indexOf(gate)
  return { gate, mode: m, ownMode: own, now, order, info: config.gates[gate], atOrAfter: (g) => at >= order.indexOf(g), before: (g) => at < order.indexOf(g) }
}

// ── Judges (pure, tested) ──────────────────────────────────────────────────

/** One SELECT, nothing else: a guard on everything this sends to the database. */
export function assertSelect(sql) {
  const s = String(sql).trim().replace(/;\s*$/, '')
  if (!/^(select|with)\b/i.test(s) || s.includes(';')) throw new Error('the preflight only sends a single SELECT')
  if (/\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|call|do|copy|vacuum|refresh|comment|security)\b/i.test(s.replace(/'[^']*'/g, "''"))) {
    throw new Error('the preflight only sends a single SELECT')
  }
  return s
}

const targetsOf = (v) => (Array.isArray(v.target) ? v.target : v.target ? [v.target] : [])

/** The Vercel settings one environment sees: 'production', 'preview', 'development', or a custom environment id. */
export function varsFor(all, target = 'production') {
  return (all ?? []).filter((v) => targetsOf(v).includes(target) || (Array.isArray(v.customEnvironmentIds) && v.customEnvironmentIds.includes(target)))
}

/** A plain-text value, or undefined: an encrypted or sensitive setting is judged by name only. */
export function plainValue(vars, key) {
  const v = vars.find((x) => x.key === key)
  return v && v.type === 'plain' && typeof v.value === 'string' ? v.value.trim().toLowerCase() : undefined
}

/**
 * Disarmed: no cron secret, crons switched off, customer email not on. Armed: the cron secret set, the off switch
 * gone, email on. `switches` names your app's settings: { cronSecret, cronsEnabled, emailLive, emailLiveValue, allowlist }.
 */
export const DEFAULT_SWITCHES = { cronSecret: 'CRON_SECRET', cronsEnabled: 'CRONS_ENABLED', emailLive: 'EMAIL_LIVE_ENV', emailLiveValue: 'production', allowlist: 'EMAIL_ALLOWLIST' }
export function evalArming(vars, mode, switches = {}) {
  const s = { ...DEFAULT_SWITCHES, ...switches }
  const has = (k) => k && vars.some((v) => v.key === k)
  const crons = plainValue(vars, s.cronsEnabled)
  const email = plainValue(vars, s.emailLive)
  const emailOn = email !== undefined ? email === s.emailLiveValue : has(s.emailLive) ? null : false
  const bad = []
  if (mode === 'disarmed') {
    if (has(s.cronSecret)) bad.push(`${s.cronSecret} is set (remove it until launch)`)
    if (crons !== 'false') bad.push(`${s.cronsEnabled} should be "false"${crons === undefined ? (has(s.cronsEnabled) ? ' (stored encrypted: make it plain)' : ' (missing)') : `, is "${crons}"`}`)
    if (emailOn === true) bad.push(`${s.emailLive} is ${s.emailLiveValue}: customer email is on`)
    if (emailOn === null) bad.push(`${s.emailLive} is stored encrypted, so it can't be read: make it plain`)
    if (s.allowlist && !has(s.allowlist)) bad.push(`${s.allowlist} is missing (staff-only email until launch)`)
    return bad.length ? fail(bad.join('; ')) : ok(`disarmed: no ${s.cronSecret}, ${s.cronsEnabled}=false, email held`)
  }
  if (!has(s.cronSecret)) bad.push(`${s.cronSecret} is missing`)
  if (crons === 'false') bad.push(`${s.cronsEnabled} is still "false"`)
  if (emailOn === false) bad.push(`${s.emailLive} isn't ${s.emailLiveValue}`)
  if (emailOn === null) bad.push(`${s.emailLive} is stored encrypted, so it can't be read: make it plain`)
  if (bad.length) return fail(bad.join('; '))
  const line = `armed: ${s.cronSecret} set, crons on, email ${s.emailLiveValue}`
  return s.allowlist && has(s.allowlist) ? warn(`${line}; ${s.allowlist} is still set, so only staff get email`) : ok(line)
}

/** Settings that must exist on an environment, by name. */
export function evalRequired(vars, names) {
  const missing = names.filter((n) => !vars.some((v) => v.key === n))
  return missing.length ? fail(`missing: ${missing.join(', ')}`) : ok(`all ${names.length} present`)
}

/** Cron jobs: listed while disarmed; when armed, every job in vercel.json registered and not disabled. */
export function evalCrons(crons, expectedPaths, mode) {
  const defs = crons?.definitions ?? []
  const registered = defs.map((d) => d.path)
  if (mode === 'disarmed') return ok(`${registered.length} job(s) registered${crons?.disabledAt ? ', all disabled' : ''}; they run only once armed`)
  if (crons?.disabledAt) return fail('cron jobs are disabled on the project')
  const missing = expectedPaths.filter((p) => !registered.includes(p))
  return missing.length ? fail(`not registered: ${missing.join(', ')}`) : ok(`all ${expectedPaths.length} job(s) registered and enabled`)
}

export function evalMigrations({ files, ledger, pending }) {
  return pending.length ? fail(`${pending.length} pending: ${pending.slice(0, 5).join(', ')}${pending.length > 5 ? ', …' : ''}`) : ok(`${files} file(s), ${ledger} recorded, none pending`)
}

export function evalPgCron(extensions, jobs, expected = []) {
  if (!extensions.includes('pg_cron')) return ok('pg_cron not installed')
  const unexpected = jobs.map((j) => j.jobname ?? '(unnamed)').filter((n) => !expected.includes(n))
  return unexpected.length ? fail(`unexpected job(s): ${unexpected.join(', ')}`) : ok(`${jobs.length} job(s), all expected`)
}

export function evalBackups(backups, now, maxHours = 26) {
  const done = (backups ?? []).filter((b) => b.status === 'COMPLETED' && b.inserted_at).map((b) => Date.parse(b.inserted_at)).filter(Number.isFinite)
  if (!done.length) return fail('no completed backup listed')
  const latest = Math.max(...done)
  const hours = (now.getTime() - latest) / 3_600_000
  const line = `latest ${new Date(latest).toISOString().slice(0, 16).replace('T', ' ')} UTC, ${hours.toFixed(1)} h old`
  return hours < maxHours ? ok(line) : fail(`${line} (want under ${maxHours} h)`)
}

export function evalUrl(actual, want, label = 'it') {
  const trim = (u) => String(u ?? '').replace(/\/+$/, '')
  const wants = [want].flat().map(trim)
  return wants.includes(trim(actual)) ? ok(`${label} is ${trim(actual)}`) : fail(`${label} is ${trim(actual) || 'unset'}, want ${wants.join(' or ')}`)
}

const VERCEL_A = [/^76\.76\.21\.\d+$/, /^66\.33\.60\.\d+$/, /^216\.198\.79\.\d+$/, /^64\.29\.17\.\d+$/]
/** Where a name points: 'vercel', 'none', or the first answer as written. */
export function classifyDns(answers) {
  if (!answers?.length) return 'none'
  const cnames = answers.filter((a) => a.type === 5).map((a) => a.data.toLowerCase())
  const as = answers.filter((a) => a.type === 1).map((a) => a.data)
  if (cnames.some((c) => /vercel-dns(-\d+)?\.com\.?$/.test(c)) || (as.length && as.every((a) => VERCEL_A.some((re) => re.test(a))))) return 'vercel'
  return (cnames[0] ?? as[0] ?? 'unknown').replace(/\.$/, '')
}

/** Every resolver must agree with `want` ('vercel', a name, or a RegExp); `maxTtl` warns when a record would linger. */
export function evalDns(byResolver, want, maxTtl = null) {
  const parts = []
  const bad = []
  let ttl = 0
  for (const [resolver, r] of Object.entries(byResolver)) {
    if (!Array.isArray(r)) { bad.push(`${resolver}: ${r.error}`); continue }
    const where = classifyDns(r)
    ttl = Math.max(ttl, ...r.map((a) => a.TTL ?? 0))
    const good = want instanceof RegExp ? want.test(where) : where === want
    parts.push(`${resolver} → ${where}`)
    if (!good) bad.push(`${resolver} → ${where}, want ${want}`)
  }
  if (bad.length) return fail(bad.join('; '))
  if (maxTtl && ttl > maxTtl) return warn(`${parts.join(', ')}; TTL ${ttl}s (want ≤ ${maxTtl}s before the switch)`)
  return ok(parts.join(', '))
}

export function evalTls(t, now, minDays = 7) {
  if (!t.authorized) return fail(`not trusted: ${t.authorizationError ?? 'unknown error'}`)
  const end = t.validTo ? Date.parse(t.validTo) : NaN
  if (!Number.isFinite(end)) return fail('no expiry date on the certificate')
  const days = (end - now.getTime()) / 86_400_000
  const line = `trusted${t.issuer ? `, issuer ${t.issuer}` : ''}, ${Math.floor(days)} days left`
  return days >= minDays ? ok(line) : fail(`${line} (want at least ${minDays})`)
}

const pathGet = (o, p) => p.split('.').reduce((x, k) => (x == null ? undefined : x[k]), o)
/** A health endpoint: answered, and every `expect` path holds one of its allowed values. */
export function evalHealth(reading, expect = {}) {
  if (reading.error) return fail(`no answer: ${reading.error}`)
  const body = reading.body && typeof reading.body === 'object' ? reading.body : null
  const wrong = []
  for (const [p, allowed] of Object.entries(expect)) {
    const v = body ? pathGet(body, p) : undefined
    if (![allowed].flat().includes(v)) wrong.push(`${p} is ${v === undefined ? 'missing' : JSON.stringify(v)}, want ${[allowed].flat().map((x) => JSON.stringify(x)).join(' or ')}`)
  }
  if (wrong.length) return fail(`HTTP ${reading.httpStatus}: ${wrong.join('; ')}`)
  return reading.httpStatus < 500 ? ok(`HTTP ${reading.httpStatus}${Object.keys(expect).length ? `, ${Object.keys(expect).map((p) => `${p}=${JSON.stringify(pathGet(body, p))}`).join(', ')}` : ''}`) : warn(`HTTP ${reading.httpStatus}`)
}

/** Stripe webhook endpoints: the one at `url` exists, is enabled or disabled as wanted, and listens for `events`. */
export function evalStripeEndpoint(endpoints, { url, enabled, events = [] }) {
  const e = (endpoints ?? []).find((x) => x.url === url)
  if (!e) return fail(`no endpoint at ${url}`)
  const on = e.status === 'enabled'
  if (enabled != null && on !== enabled) return fail(`${url} is ${e.status}, want ${enabled ? 'enabled' : 'disabled'}`)
  const missing = events.filter((ev) => !e.enabled_events?.includes(ev) && !e.enabled_events?.includes('*'))
  return missing.length ? fail(`${url} doesn't listen for ${missing.join(', ')}`) : ok(`${url} ${e.status}, ${e.enabled_events?.length ?? 0} event(s)`)
}

/**
 * Auth floors on the live database (MSC, 2026-11-11: live had an 8-digit sign-in code, 30 emails an hour and a
 * retired site URL until the deep pass). Only the floors you name are judged.
 */
export function evalAuthFloors(auth, postgrest, { otpLength = null, minEmailRate = null, redirects = [], minMaxRows = null } = {}) {
  const bad = []
  const good = []
  if (otpLength != null) (Number(auth?.mailer_otp_length) === otpLength ? good : bad).push(`sign-in code ${auth?.mailer_otp_length ?? 'unset'} digits${Number(auth?.mailer_otp_length) === otpLength ? '' : ` (want ${otpLength})`}`)
  if (minEmailRate != null) {
    const n = Number(auth?.rate_limit_email_sent)
    ;(Number.isFinite(n) && n >= minEmailRate ? good : bad).push(`${auth?.rate_limit_email_sent ?? 'unset'} emails an hour${n >= minEmailRate ? '' : ` (want at least ${minEmailRate})`}`)
  }
  if (redirects.length) {
    const entries = String(auth?.uri_allow_list ?? '').split(',').map((e) => e.trim()).filter(Boolean)
    const covers = (base) => entries.some((e) => e === base || e.startsWith(`${base.replace(/\/+$/, '')}/`))
    const missing = redirects.filter((b) => !covers(b))
    ;(missing.length ? bad : good).push(missing.length ? `redirects miss ${missing.map((m) => `${m}/**`).join(', ')}` : `redirects cover ${redirects.join(', ')}`)
  }
  if (minMaxRows != null) {
    const n = Number(postgrest?.max_rows)
    ;(Number.isFinite(n) && n >= minMaxRows ? good : bad).push(`API max_rows ${postgrest?.max_rows ?? 'unset'}${n >= minMaxRows ? '' : ` (want at least ${minMaxRows})`}`)
  }
  return bad.length ? fail(bad.join('; ')) : ok(good.join('; ') || 'no floors named')
}

/** A switch is on when it's true, "true"/"on", or { enabled | on | closed: true }. Missing reads as off. */
export function switchOn(value) {
  if (value === true) return true
  if (typeof value === 'string') return ['true', 'on', 'yes'].includes(value.trim().toLowerCase())
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  return value.enabled === true || value.on === true || value.closed === true
}

/** Settings that must stay off at every gate (deletion and the like, until the client approves them). */
export function evalSwitchesOff(settings, keys, isOn = switchOn) {
  const on = keys.filter((k) => isOn(settings[k]))
  if (on.length) return fail(`on: ${on.join(', ')}`)
  const absent = keys.filter((k) => !(k in settings))
  return ok(`all off${absent.length ? ` (${absent.join(', ')} not created yet; missing reads as off)` : ''}`)
}

/** One setting on or off, by gate: a data-sync lock is open before cut-over and closed after it. */
export function evalSwitchIs(settings, key, want, isOn = switchOn) {
  const on = isOn(settings[key])
  const exists = key in settings
  if (want === 'on') return on ? ok(`${key} on`) : fail(`${key} ${exists ? 'is off' : 'is not set'}, want on`)
  return on ? fail(`${key} is on, want off`) : ok(`${key} off${exists ? '' : ' (not set yet)'}`)
}

/** Reads `export const NAME = true|false` from a source file; null when it isn't there. */
export function readConstant(source, name) {
  const m = String(source).match(new RegExp(`export\\s+const\\s+${name}\\s*(?::\\s*boolean\\s*)?=\\s*(true|false)\\b`))
  return m ? m[1] === 'true' : null
}

/** Approval constants in code that must still be false. One that can't be found fails: it can't be vouched for. */
export function evalConstantsFalse(values) {
  const on = Object.entries(values).filter(([, v]) => v === true).map(([k]) => k)
  const unknown = Object.entries(values).filter(([, v]) => v === null).map(([k]) => k)
  if (on.length) return fail(`true: ${on.join(', ')}`)
  if (unknown.length) return fail(`not found in code: ${unknown.join(', ')}`)
  return ok(`${Object.keys(values).join(', ')} false`)
}

/** A count from your own SELECT: over `max` is a WARN or a FAIL, as you say (leftovers from an incident, say). */
export function evalCount(rows, { max = 0, level = 'WARN', what = 'row(s)' } = {}) {
  const first = Array.isArray(rows) ? rows[0] : null
  const n = first ? Number(Object.values(first)[0]) : NaN
  if (!Number.isFinite(n)) return fail(`the query didn't answer a number (want one row, one column: select count(*) …)`)
  return n <= max ? ok(`${n} ${what}`) : { status: level === 'FAIL' ? 'FAIL' : 'WARN', detail: `${n} ${what} (want at most ${max})` }
}

/** Each URL answers as expected (200 unless you say otherwise): assets the app and its emails link to, say. */
export function evalUrls(readings, expect = [200]) {
  const bad = readings.filter((r) => r.error || !expect.includes(r.status)).map((r) => `${r.url} → ${r.error ?? r.status}`)
  return bad.length ? fail(`${bad.length} of ${readings.length}: ${bad.slice(0, 5).join('; ')}${bad.length > 5 ? '; …' : ''}`) : ok(`all ${readings.length} answer ${expect.join(' or ')}`)
}

// ── The report ─────────────────────────────────────────────────────────────

export function exitCode(rows) {
  return rows.some((r) => r.result.status === 'FAIL') ? 1 : 0
}

/** Plain-text table, then the fix for every FAIL and WARN, then the verdict. */
export function formatTable(rows, ctx) {
  const width = Math.max(5, ...rows.map((r) => r.check.name.length))
  const pad = ' '.repeat(7 + 1 + width + 2)
  const head = ctx.info?.title ? ` (${ctx.info.title}${ctx.info.when ? `: ${ctx.info.when}` : ''})` : ''
  const lines = [`Launch preflight, gate ${ctx.gate}${head}, mode ${ctx.mode}, ${ctx.now.toISOString().slice(0, 16).replace('T', ' ')} UTC`, '']
  if (ctx.mode !== ctx.ownMode) lines.push(`Note: ${ctx.gate} is normally ${ctx.ownMode}; judging it as ${ctx.mode} because --mode says so.`, '')
  lines.push(`${'Status'.padEnd(7)} ${'Check'.padEnd(width)}  Detail`, `${'-'.repeat(7)} ${'-'.repeat(width)}  ${'-'.repeat(40)}`)
  for (const r of rows) lines.push(`${r.result.status.padEnd(7)} ${r.check.name.padEnd(width)}  ${String(r.result.detail).split('\n').join(`\n${pad}`)}`)
  const fixes = rows.filter((r) => (r.result.status === 'FAIL' || r.result.status === 'WARN') && r.check.fix)
  if (fixes.length) {
    lines.push('', 'To fix:')
    for (const r of fixes) lines.push(`  [${r.result.status}] ${r.check.name}: ${r.check.fix}`)
  }
  const n = (s) => rows.filter((r) => r.result.status === s).length
  const verdict = n('FAIL') ? 'NO-GO until every FAIL is fixed.' : n('MANUAL') ? 'Automated checks pass; the MANUAL rows need their owner\'s sign-off.' : 'All checks pass.'
  lines.push('', `${n('PASS')} pass, ${n('FAIL')} fail, ${n('WARN')} warn, ${n('MANUAL')} manual. ${verdict}`)
  return lines.join('\n')
}

/** Run each check, a few at a time (the Supabase Management API throttles a burst). A thrown error is a FAIL. */
export async function runChecks(checks, kit, ctx, width = 4) {
  const rows = new Array(checks.length)
  let next = 0
  const one = async (check) => {
    if (check.who) return { check, result: { status: 'MANUAL', detail: `${check.who}: ${check.fix ?? check.name}` } }
    try {
      const result = await check.run(kit, ctx)
      if (!result || !['PASS', 'FAIL', 'WARN', 'MANUAL'].includes(result.status)) return { check, result: fail(`the check answered ${JSON.stringify(result)?.slice(0, 80)} (a bug in the table)`) }
      return { check, result }
    } catch (e) {
      const why = e?.name === 'TimeoutError' ? 'timed out' : String(e?.message ?? e).split('\n')[0].slice(0, 200)
      return { check, result: fail(`could not check: ${why}`) }
    }
  }
  await Promise.all(Array.from({ length: width }, async () => {
    while (next < checks.length) { const i = next++; rows[i] = await one(checks[i]) }
  }))
  return rows
}

// ── Read-only access (the kit handed to each check) ────────────────────────

/** GET only. Answers { status, headers, body }, the body parsed when it's JSON. */
export async function get(url, headers = {}) {
  const res = await fetch(url, { method: 'GET', headers, redirect: 'manual', signal: AbortSignal.timeout(TIMEOUT_MS) })
  const text = await res.text()
  let body = text
  try { body = JSON.parse(text) } catch { /* not JSON */ }
  return { status: res.status, headers: Object.fromEntries(res.headers.entries()), body }
}

function vercelToken() {
  if (process.env.VERCEL_TOKEN) return process.env.VERCEL_TOKEN.trim()
  const appData = process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming')
  for (const file of [
    path.join(appData, 'com.vercel.cli', 'Data', 'auth.json'),
    path.join(os.homedir(), '.local', 'share', 'com.vercel.cli', 'auth.json'),
    path.join(os.homedir(), 'Library', 'Application Support', 'com.vercel.cli', 'auth.json'),
  ]) {
    if (!fs.existsSync(file)) continue
    const auth = JSON.parse(fs.readFileSync(file, 'utf8'))
    if (auth.expiresAt && auth.expiresAt * 1000 < Date.now()) throw new Error('the Vercel CLI login has expired: run `vercel whoami` to refresh it')
    if (auth.token) return auth.token
  }
  throw new Error('no Vercel token: log in with the Vercel CLI (`vercel login`) or set VERCEL_TOKEN')
}

/** The Supabase Management API without lodestar-lib: same shape as its managementApi. */
export async function managementApiPlain(pathname, { method = 'GET', body, token } = {}) {
  const r = await fetch(`https://api.supabase.com${pathname}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  })
  const text = await r.text()
  if (!r.ok) throw new Error(`${method} ${pathname} → ${r.status}: ${text.slice(0, 400)}`)
  try { return JSON.parse(text) } catch { return text }
}

/** The helpers a check gets, each read at most once per run. `root` is the project's folder. */
export function makeKit(root) {
  const memo = new Map()
  const once = (key, fn) => { if (!memo.has(key)) memo.set(key, fn()); return memo.get(key) }
  // The kit's lodestar-lib when this repo has it (it reads the Supabase CLI's login on Windows); otherwise
  // SUPABASE_ACCESS_TOKEN and a plain call. The preflight ships with the station kit, and a station that never
  // took the `scripts` category has no lodestar-lib (NU, 2026-11-11).
  const lib = () => once('lib', async () => {
    const file = path.join(root, 'scripts', 'lodestar-lib.mjs')
    if (fs.existsSync(file)) return import(pathToFileURL(file).href)
    return {
      getAccessToken: () => {
        if (process.env.SUPABASE_ACCESS_TOKEN) return process.env.SUPABASE_ACCESS_TOKEN.trim()
        throw new Error('no Supabase access token: set SUPABASE_ACCESS_TOKEN, or take scripts/lodestar-lib.mjs (lodestar update --only scripts) to use the CLI login')
      },
      managementApi: managementApiPlain,
    }
  })

  const vercel = async (pathname, teamId) => {
    const sep = pathname.includes('?') ? '&' : '?'
    const r = await get(`https://api.vercel.com${pathname}${teamId ? `${sep}teamId=${teamId}` : ''}`, { Authorization: `Bearer ${vercelToken()}` })
    if (r.status !== 200) throw new Error(`Vercel ${pathname.split('?')[0]} answered ${r.status}${r.body?.error?.message ? `: ${r.body.error.message}` : ''}`)
    return r.body
  }
  const supabaseToken = async () => {
    const { getAccessToken } = await lib()
    const exit = process.exit
    process.exit = () => { throw new Error('no Supabase access token: set SUPABASE_ACCESS_TOKEN or log in with the Supabase CLI') }
    try { return getAccessToken() } finally { process.exit = exit }
  }
  const supabase = async (pathname) => { const { managementApi } = await lib(); return managementApi(pathname, { token: await supabaseToken() }) }
  const select = async (ref, sql) => {
    const { managementApi } = await lib()
    return managementApi(`/v1/projects/${ref}/database/query/read-only`, { method: 'POST', body: { query: assertSelect(sql) }, token: await supabaseToken() })
  }
  const doh = async (resolver, url) => {
    try {
      const r = await get(url, { accept: 'application/dns-json' })
      if (r.status !== 200 || typeof r.body !== 'object') return { error: `HTTP ${r.status}` }
      return r.body.Answer ?? []
    } catch (e) { return { error: e.name === 'TimeoutError' ? 'timed out' : String(e.message ?? e) } }
  }
  const tlsReading = (host) => new Promise((resolve, reject) => {
    const socket = tls.connect({ host, port: 443, servername: host, rejectUnauthorized: false, timeout: TIMEOUT_MS }, () => {
      const cert = socket.getPeerCertificate()
      resolve({ authorized: socket.authorized, authorizationError: socket.authorizationError ? String(socket.authorizationError) : null, validTo: cert?.valid_to, issuer: cert?.issuer?.O ?? cert?.issuer?.CN })
      socket.end()
    })
    socket.on('timeout', () => { socket.destroy(); reject(new Error('timed out')) })
    socket.on('error', reject)
  })

  return {
    root, get, vercel, supabase, select,
    vercelEnv: (projectId, teamId) => once(`env:${projectId}`, async () => (await vercel(`/v10/projects/${projectId}/env`, teamId)).envs ?? []),
    vercelProject: (projectId, teamId) => once(`project:${projectId}`, () => vercel(`/v9/projects/${projectId}`, teamId)),
    vercelDomains: (projectId, teamId) => once(`domains:${projectId}`, async () => (await vercel(`/v9/projects/${projectId}/domains?limit=100`, teamId)).domains ?? []),
    authConfig: (ref) => once(`auth:${ref}`, () => supabase(`/v1/projects/${ref}/config/auth`)),
    health: async (url) => {
      try { const r = await get(url); return { httpStatus: r.status, body: typeof r.body === 'object' ? r.body : null } } catch (e) { return { error: String(e?.message ?? e) } }
    },
    dns: async (host) => ({
      '1.1.1.1': await doh('1.1.1.1', `https://cloudflare-dns.com/dns-query?name=${host}&type=A`),
      '8.8.8.8': await doh('8.8.8.8', `https://dns.google/resolve?name=${host}&type=A`),
    }),
    tls: tlsReading,
    stripeKey: () => {
      for (const name of ['STRIPE_SECRET_KEY_LIVE', 'STRIPE_LIVE_SECRET_KEY', 'STRIPE_RESTRICTED_KEY_LIVE', 'STRIPE_SECRET_KEY']) {
        const v = (process.env[name] ?? '').trim()
        if (/^(sk|rk)_live_/.test(v)) return v
      }
      return null
    },
  }
}

// ── Checks every app can use: put them in your table ───────────────────────

/** The named rows of a key/value settings table, as { key: value }. Never the whole table: it can hold tokens. */
export async function readSettings(kit, ref, table, keys) {
  if (!/^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$/i.test(table)) throw new Error(`not a table name: ${table}`)
  const list = keys.map((k) => `'${String(k).replace(/'/g, "''")}'`).join(', ')
  const rows = await kit.select(ref, `select key, value from ${table} where key in (${list})`)
  return Object.fromEntries((rows ?? []).map((r) => [r.key, r.value]))
}

/** Ready-made rows. Each returns { run(kit, ctx) }; spread it into a row with your id, name, gates and fix. */
export const checks = {
  /** The app's health endpoint answers, with these values: `expect` maps a dotted path to its allowed value(s). */
  health: (url, expect = {}) => ({ run: async (kit) => evalHealth(await kit.health(typeof url === 'function' ? url() : url), expect) }),
  /** An environment's crons and customer email match the gate's mode. `target` is 'production' or a custom env id. */
  arming: ({ projectId, teamId, target = 'production', switches = {} }) => ({
    run: async (kit, ctx) => evalArming(varsFor(await kit.vercelEnv(projectId, teamId), target), ctx.mode, switches),
  }),
  /** Always disarmed whatever the gate (a staging or preview environment). */
  disarmed: ({ projectId, teamId, target, switches = {} }) => ({
    run: async (kit) => evalArming(varsFor(await kit.vercelEnv(projectId, teamId), target), 'disarmed', switches),
  }),
  required: ({ projectId, teamId, target = 'production', names }) => ({
    run: async (kit) => evalRequired(varsFor(await kit.vercelEnv(projectId, teamId), target), names),
  }),
  crons: ({ projectId, teamId, vercelJson = 'vercel.json' }) => ({
    run: async (kit, ctx) => {
      const expected = JSON.parse(fs.readFileSync(path.join(kit.root, vercelJson), 'utf8')).crons?.map((c) => c.path) ?? []
      return evalCrons((await kit.vercelProject(projectId, teamId)).crons, expected, ctx.mode)
    },
  }),
  /** Every file in supabase/migrations is recorded on the database (the comparison sync-migrations makes, read-only). */
  migrations: ({ ref, dir = 'supabase/migrations' }) => ({
    run: async (kit) => {
      const ledgerFile = path.join(kit.root, 'scripts', 'migration-ledger.mjs')
      if (!fs.existsSync(ledgerFile)) return fail('scripts/migration-ledger.mjs isn\'t in this repo: take it with `lodestar update --only scripts`')
      const { reconcile } = await import(pathToFileURL(ledgerFile).href)
      const files = fs.readdirSync(path.join(kit.root, dir)).filter((f) => f.endsWith('.sql')).sort().map((f) => ({ file: f, stem: f.replace(/\.sql$/, '') }))
      const ledger = (await kit.select(ref, 'select version, name from supabase_migrations.schema_migrations')) ?? []
      return evalMigrations({ files: files.length, ledger: ledger.length, pending: reconcile(files, ledger).pending.map((f) => f.stem) })
    },
  }),
  pgCron: ({ ref, expected = [] }) => ({
    run: async (kit) => {
      const ext = ((await kit.select(ref, 'select extname from pg_extension')) ?? []).map((r) => r.extname)
      const jobs = ext.includes('pg_cron') ? ((await kit.select(ref, 'select jobname from cron.job')) ?? []) : []
      return evalPgCron(ext, jobs, expected)
    },
  }),
  backups: ({ ref, maxHours = 26 }) => ({
    run: async (kit, ctx) => evalBackups((await kit.supabase(`/v1/projects/${ref}/database/backups`)).backups ?? [], ctx.now, maxHours),
  }),
  siteUrl: ({ ref, want }) => ({ run: async (kit, ctx) => evalUrl((await kit.authConfig(ref)).site_url, typeof want === 'function' ? want(ctx) : want, 'site_url') }),
  dns: ({ host, want, maxTtl = null }) => ({ run: async (kit, ctx) => evalDns(await kit.dns(host), typeof want === 'function' ? want(ctx) : want, maxTtl) }),
  tls: ({ host, minDays = 7 }) => ({ run: async (kit, ctx) => evalTls(await kit.tls(host), ctx.now, minDays) }),
  /** A Stripe webhook endpoint, read with a live key from the shell; MANUAL without one. */
  stripeEndpoint: (spec) => ({
    run: async (kit, ctx) => {
      const key = kit.stripeKey()
      const want = typeof spec === 'function' ? spec(ctx) : spec
      if (!key) return { status: 'MANUAL', detail: `no live Stripe key in this shell: check ${want.url} in the dashboard` }
      const r = await kit.get('https://api.stripe.com/v1/webhook_endpoints?limit=100', { Authorization: `Bearer ${key}` })
      if (r.status !== 200) throw new Error(`Stripe answered ${r.status}`)
      return evalStripeEndpoint(r.body.data ?? [], want)
    },
  }),
  /** Auth floors on the live database: sign-in code length, email rate, redirect list, API max_rows. */
  authFloors: ({ ref, otpLength = null, minEmailRate = null, redirects = [], minMaxRows = null }) => ({
    run: async (kit, ctx) => evalAuthFloors(
      await kit.authConfig(ref),
      minMaxRows != null ? await kit.supabase(`/v1/projects/${ref}/postgrest`) : null,
      { otpLength, minEmailRate, redirects: typeof redirects === 'function' ? redirects(ctx) : redirects, minMaxRows },
    ),
  }),
  /** Switches in a settings table that must stay off. Only the named rows are read: such tables can hold tokens. */
  switchesOff: ({ ref, keys, table = 'public.system_settings', isOn = switchOn }) => ({
    run: async (kit) => evalSwitchesOff(await readSettings(kit, ref, table, keys), keys, isOn),
  }),
  /** One switch on or off by gate: `want` is 'on', 'off', or (ctx) => either. */
  switchIs: ({ ref, key, want, table = 'public.system_settings', isOn = switchOn }) => ({
    run: async (kit, ctx) => evalSwitchIs(await readSettings(kit, ref, table, [key]), key, typeof want === 'function' ? want(ctx) : want, isOn),
  }),
  /** `export const NAME = false` in your code, for each name, until the client approves it. */
  constantsFalse: (byFile) => ({
    run: async (kit) => {
      const values = {}
      for (const [file, names] of Object.entries(byFile)) {
        const src = fs.existsSync(path.join(kit.root, file)) ? fs.readFileSync(path.join(kit.root, file), 'utf8') : ''
        for (const n of names) values[n] = readConstant(src, n)
      }
      return evalConstantsFalse(values)
    },
  }),
  /** Your own SELECT count(*): over `max` is a WARN (or FAIL with level: 'FAIL'). */
  count: ({ ref, sql, max = 0, level = 'WARN', what }) => ({ run: async (kit) => evalCount(await kit.select(ref, sql), { max, level, what }) }),
  /** Each URL answers 200 (or `expect`): assets the app and its emails link to. */
  urls: ({ urls, expect = [200] }) => ({
    run: async (kit) => {
      const list = typeof urls === 'function' ? urls() : urls
      const readings = []
      for (const url of list) {
        try { readings.push({ url, status: (await kit.get(url)).status }) } catch (e) { readings.push({ url, error: e?.name === 'TimeoutError' ? 'timed out' : String(e?.message ?? e) }) }
      }
      return evalUrls(readings, expect)
    },
  }),
  /** Every "Launch commitment [step]: …" ticket due by this gate is verified (beat commitments). */
  commitments: ({ station, order }) => ({
    run: async (kit, ctx) => {
      const beat = await import(pathToFileURL(path.join(kit.root, 'scripts', 'beat.mjs')).href)
      const out = await beat.readCommitments({ station, by: ctx.gate, order })
      if (out.go) return ok(`${out.count} commitment(s); all due by ${ctx.gate} verified${out.dropped.length ? ` (${out.dropped.length} dropped: ${out.dropped.map((r) => r.ref).join(', ')})` : ''}`)
      const lines = out.open.map((r) => `${r.ref} [${r.step}] ${r.what} is ${r.status}`)
      return fail([`${out.open.length} commitment(s) due by ${ctx.gate} not verified`, ...lines, ...(out.unplaced ? [out.unplaced] : [])].join('\n'))
    },
  }),
}

// ── Run ────────────────────────────────────────────────────────────────────

function arg(argv, name) {
  const i = argv.indexOf(`--${name}`)
  return i >= 0 ? argv[i + 1] : undefined
}

export async function main(argv = process.argv.slice(2), root = process.cwd()) {
  const usage = 'usage: node scripts/lodestar/launch-preflight.mjs --gate <gate> [--mode disarmed|armed] [--config launch/preflight.config.mjs]'
  if (argv.includes('--help') || argv.includes('-h')) { console.log(usage); return 0 }
  const file = path.resolve(root, arg(argv, 'config') ?? path.join('launch', 'preflight.config.mjs'))
  if (!fs.existsSync(file)) {
    console.error(`No gate table at ${path.relative(root, file)}. Start from launch/preflight.example.mjs: copy it to launch/preflight.config.mjs and fill in your gates and checks.`)
    return 2
  }
  const config = (await import(pathToFileURL(file).href)).default
  const gate = String(arg(argv, 'gate') ?? '').toUpperCase()
  let ctx, table
  try {
    ctx = contextFor(config, gate, arg(argv, 'mode') ?? null)
    table = checksFor(config, gate)
  } catch (e) { console.error(`${usage}\n${e.message}`); return 2 }
  const rows = await runChecks(table, makeKit(root), ctx)
  console.log(formatTable(rows, ctx))
  return exitCode(rows)
}

const entry = process.argv[1] ? pathToFileURL(path.resolve(process.argv[1])).href : null
// Not a top-level await: the project's table imports this module for `checks`, and an entry module still awaiting
// at the top level never finishes loading, so that import would wait forever.
if (entry && import.meta.url === entry) main().then((code) => { process.exitCode = code }, (e) => { console.error(String(e?.stack ?? e)); process.exitCode = 1 })
