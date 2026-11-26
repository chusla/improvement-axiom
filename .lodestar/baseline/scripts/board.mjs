// Tickets on the Bridge (bridge/0007): copying a project's own board, and filing on a hosted one.
//
// Two kinds of project, one table:
//
//   own     ITK, COI. The project's database holds its tickets. `mirror` copies them to the
//           Bridge on the station's beat, one way, so The Pass reads every board from one place and
//           nothing in the app ever waits on the Bridge.
//   hosted  NU, Whitespace. No ticket tables of their own; `board_tickets` is their board, and
//           `ticket` / `comment` / `status` write to it directly.
//
// The Bridge refuses a copy into a hosted project and a hosted ticket into an own one, so running
// the wrong command fails with a sentence rather than landing somewhere it shouldn't.
//
// The pure functions at the top are what the tests hold still. The rest is HTTP.

/** The columns copied from a project's `admin_change_requests`. */
export const TICKET_COLS = 'id,ticket_number,source,title,summary,user_request,status,request_type,priority_flag,environment,tags,page_label,page_path,pr_url,pr_number,admin_id,assigned_to,is_backlog,created_at,updated_at'

/** A copy keeps the latest comments, not the whole thread: enough to read the state of play. */
export const KEEP_COMMENTS = 10

/** A copy older than this is redone in full, which is also how deleted tickets leave the Bridge. */
export const FULL_EVERY_MS = 24 * 60 * 60 * 1000

/** The status words a hosted board accepts. The same closed list The Pass's voice commands use. */
export const STATUSES = [
  'proposed', 'awaiting_confirmation', 'needs_dev', 'pr_open', 'testing', 'testing_failed',
  'discuss', 'verified', 'pending_review', 'ready_to_merge', 'error',
  'deploying', 'merged', 'promoted', 'closed',
]

/** Whose move a ticket is (bridge/0061): separate from the code status, so it can be merged AND waiting on the client. */
export const WAITING_ON = ['client', 'development', 'andrew']
const SETTLED = ['closed', 'verified', 'promoted']

/**
 * Who a ticket waits on: what it says (bridge/0061), or, on a ticket nobody has set it on yet, what its status
 * implies. Testing and awaiting_confirmation have always meant the client's move. Derived rather than written
 * once, because a write restarts the ticket's 30-day clock. A finished ticket waits on nobody.
 */
export function waitingOn(t) {
  if (!t || SETTLED.includes(t.status) || t.is_backlog) return null
  if (WAITING_ON.includes(t.waiting_on)) return t.waiting_on
  return t.status === 'testing' || t.status === 'awaiting_confirmation' ? 'client' : null
}

// ── An ask, as questions with answers to pick (bridge/0062) ──────────────────────────────────────────────────
// Andrew, 2026-11-12, on the Daily Checklist: "plainspoken to do's that happen to be parented by tickets", shaped
// like "a listed number of predefined options and then an open ended one". Checked against 147 real checklist asks
// from MSC, ITK and NU: a test with steps and a place, a review of several things, several questions in one, a
// number or a date, a file to send, steps done elsewhere, and who must answer. Each is one addition to the same shape.

export const ASK_FIELDS = ['number', 'date', 'text', 'file']
const ASK_LIMITS = { questions: 10, options: 6, steps: 12, names: 6, text: 300, why: 500, label: 120, note: 200, line: 200 }
// A password or a key never goes in an answer box: those reach development through a secure link.
// Narrow on purpose: "design tokens" or "the password reset email" are ordinary asks; sending one isn't.
const SECRETISH = /\b(send|paste|enter|share|give|type|attach)\b[^.?!]{0,40}\b(password|passcode|api[ _-]?key|secret key|access token|private key)s?\b|\b[sr]k_live_/i

// What each level of an ask may carry. Anything else is refused in words: MSC's trial (2026-11-13) put a test's
// steps, place and link inside its question, where they were dropped without a word.
const ASK_KEYS = ['questions', 'ask', 'for', 'where', 'link', 'steps', 'checks', 'by', 'v']
const QUESTION_KEYS = ['id', 'text', 'why', 'pick', 'options', 'other']
const OPTION_KEYS = ['label', 'note', 'recommended', 'field', 'placeholder']
const WHOLE_ASK = ['for', 'where', 'link', 'steps', 'checks', 'by']
const list = (xs) => `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`

/** YYYY-MM-DD that is a real day, or null. */
export function askDate(v) {
  const s = String(v ?? '').trim()
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null
  const d = new Date(`${s}T00:00:00Z`)
  return Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== s ? null : s
}

const clip = (v, n, what) => {
  const s = String(v ?? '').replace(/\s+/g, ' ').trim()
  if (s.length > n) throw new Error(`${what} is ${s.length} characters; keep it under ${n}`)
  return s
}

/**
 * An ask from a station, checked and put in its stored shape: `{ ask, detail }`, where `ask` is the one line
 * a list shows and `detail` holds the questions. Throws, in words, on anything the checklist can't show.
 *
 *   { questions: [{ text, why?, pick?: 'one'|'several', options?: [{ label, note?, recommended?, field?, placeholder? }],
 *                   other?: string|false }],
 *     ask?: one line when there are several questions, for?: { names: [..], all?: bool },
 *     where?, link?: { label, url }, steps?: [..], checks?, by?: 'YYYY-MM-DD' }
 *
 * `for`, `where`, `link`, `steps`, `checks` and `by` belong to the whole ask, never inside a question. Any key the
 * checklist doesn't show is refused, so nothing is dropped without a word.
 */
export function normalizeAsk(input) {
  if (!input || typeof input !== 'object') throw new Error('an ask is an object with questions')
  const single = !Array.isArray(input.questions) && !!input.text
  const qs = Array.isArray(input.questions) ? input.questions : single ? [input] : []
  const strayTop = Object.keys(input).filter((k) => !ASK_KEYS.includes(k) && !(single && QUESTION_KEYS.includes(k)))
  if (strayTop.length) throw new Error(`the ask has ${strayTop.map((k) => `"${k}"`).join(', ')}, which the checklist doesn't show; an ask has ${list(ASK_KEYS.slice(0, -1))}`)
  if (!qs.length) throw new Error('an ask needs at least one question')
  if (qs.length > ASK_LIMITS.questions) throw new Error(`at most ${ASK_LIMITS.questions} questions in one ask; split it`)
  const ids = new Set()
  const questions = qs.map((q, i) => {
    if (!q || typeof q !== 'object') throw new Error(`question ${i + 1} is an object with text`)
    if (!single) {
      const whole = Object.keys(q).filter((k) => WHOLE_ASK.includes(k))
      if (whole.length) throw new Error(`question ${i + 1} has ${whole.map((k) => `"${k}"`).join(', ')}: ${list(WHOLE_ASK)} belong to the whole ask, beside "questions", not inside one question`)
      const stray = Object.keys(q).filter((k) => !QUESTION_KEYS.includes(k))
      if (stray.length) throw new Error(`question ${i + 1} has ${stray.map((k) => `"${k}"`).join(', ')}, which the checklist doesn't show; a question has ${list(QUESTION_KEYS)}`)
    }
    if (q.pick != null && q.pick !== 'one' && q.pick !== 'several') throw new Error(`question ${i + 1}: pick is "one" or "several", not ${q.pick}`)
    const text = clip(q.text, ASK_LIMITS.text, `question ${i + 1}`)
    if (!text) throw new Error(`question ${i + 1} has no text`)
    const id = String(q.id ?? `q${i + 1}`).trim()
    if (!/^[a-z0-9][a-z0-9_-]{0,31}$/i.test(id) || ids.has(id)) throw new Error(`question ${i + 1}: id "${id}" is missing, repeated or not a short name`)
    ids.add(id)
    const pick = q.pick === 'several' ? 'several' : 'one'
    const options = (Array.isArray(q.options) ? q.options : []).map((o, j) => {
      if (o && typeof o === 'object') {
        const stray = Object.keys(o).filter((k) => !OPTION_KEYS.includes(k))
        if (stray.length) throw new Error(`question ${i + 1}, answer ${j + 1} has ${stray.map((k) => `"${k}"`).join(', ')}, which the checklist doesn't show; an answer has ${list(OPTION_KEYS)}`)
      }
      const label = clip(typeof o === 'string' ? o : o?.label, ASK_LIMITS.label, `question ${i + 1}, answer ${j + 1}`)
      if (!label) throw new Error(`question ${i + 1}, answer ${j + 1} has no label`)
      const field = typeof o === 'object' && o.field ? String(o.field) : null
      if (field && !ASK_FIELDS.includes(field)) throw new Error(`question ${i + 1}, answer ${j + 1}: a field is ${ASK_FIELDS.join(', ')}, not ${field}`)
      const out = { label }
      if (typeof o === 'object') {
        const note = clip(o.note, ASK_LIMITS.note, `question ${i + 1}, answer ${j + 1}'s note`)
        if (note) out.note = note
        if (o.recommended === true) out.recommended = true
        if (field) out.field = field
        const ph = clip(o.placeholder, ASK_LIMITS.label, `question ${i + 1}, answer ${j + 1}'s placeholder`)
        if (ph) out.placeholder = ph
      }
      return out
    })
    if (options.length > ASK_LIMITS.options) throw new Error(`question ${i + 1} has ${options.length} answers; at most ${ASK_LIMITS.options}, and Something else is always added`)
    if (new Set(options.map((o) => o.label.toLowerCase())).size !== options.length) throw new Error(`question ${i + 1} has two answers with the same label`)
    if (pick === 'one' && options.filter((o) => o.recommended).length > 1) throw new Error(`question ${i + 1} recommends more than one answer`)
    const out = { id, text, pick, options }
    const why = clip(q.why, ASK_LIMITS.why, `question ${i + 1}'s why`)
    if (why) out.why = why
    if (q.other === false) {
      if (!options.length) throw new Error(`question ${i + 1} has no answers and no Something else: there would be nothing to press`)
      out.other = false
    } else {
      out.other = clip(typeof q.other === 'string' ? q.other : '', ASK_LIMITS.label, `question ${i + 1}'s Something else`) || 'Something else'
    }
    return out
  })
  const detail = { v: 1, questions }
  const who = input.for
  if (who) {
    const names = (Array.isArray(who.names) ? who.names : [who.names]).map((n) => clip(n, 60, 'a name')).filter(Boolean)
    if (names.length > ASK_LIMITS.names) throw new Error(`at most ${ASK_LIMITS.names} people on one ask`)
    if (names.length) detail.for = { names, all: who.all === true }
  }
  const where = clip(input.where, ASK_LIMITS.line, 'where')
  if (where) detail.where = where
  if (input.link) {
    const url = String(input.link.url ?? input.link).trim()
    if (!/^https:\/\/[^\s]+$/i.test(url)) throw new Error('a link is an https address')
    detail.link = { label: clip(input.link.label, ASK_LIMITS.label, "the link's label") || 'Open it', url }
  }
  if (input.steps) {
    const steps = (Array.isArray(input.steps) ? input.steps : [input.steps]).map((s, i) => clip(s, ASK_LIMITS.text, `step ${i + 1}`)).filter(Boolean)
    if (steps.length > ASK_LIMITS.steps) throw new Error(`at most ${ASK_LIMITS.steps} steps`)
    if (steps.length) detail.steps = steps
  }
  const checks = clip(input.checks, ASK_LIMITS.line, 'checks')
  if (checks) detail.checks = checks
  // The day the answer is needed by: it orders the list, soonest first, and the card says it (MSC's trial: the
  // list read in update order, the GitHub step above the Email 2 date).
  if (input.by != null && input.by !== '') {
    const by = askDate(input.by)
    if (!by) throw new Error(`by is the day the answer is needed, as YYYY-MM-DD, not ${input.by}`)
    detail.by = by
  }
  const ask = clip(input.ask ?? (questions.length === 1 ? questions[0].text : ''), ASK_LIMITS.line, 'the one-line ask')
  if (!ask) throw new Error(`${questions.length} questions need a one-line --ask that names them all, e.g. "Four questions on reminders after the move"`)
  const words = JSON.stringify(detail) + ask
  if (SECRETISH.test(words)) throw new Error('an ask never asks for a password, key or token: send a secure link for that, and ask "Have you used the secure link?"')
  return { ask, detail }
}

/** `--options "Three days before*|The day before"`: the quick form, * marking the recommended answer. */
export function optionsFromFlag(s) {
  return String(s ?? '').split('|').map((x) => x.trim()).filter(Boolean)
    .map((x) => (x.endsWith('*') ? { label: x.slice(0, -1).trim(), recommended: true } : { label: x }))
}

/** Which questions of an ask are answered, by whom, and whether it's complete (bridge/0062 decides the same in SQL). */
export function askProgress(detail, answers = []) {
  const qs = detail?.questions ?? []
  const names = detail?.for?.names ?? []
  const all = detail?.for?.all === true && names.length > 0
  const matches = (who, name) => String(who ?? '').toLowerCase().startsWith(String(name).toLowerCase())
  const per = qs.map((q) => {
    const got = answers.filter((a) => a.q === q.id)
    const done = all ? names.every((n) => got.some((a) => matches(a.who, n))) : got.length > 0
    return { id: q.id, answered: got.length, done }
  })
  return { questions: per, done: per.length > 0 && per.every((p) => p.done), next: per.find((p) => !p.done)?.id ?? null }
}

// ── The consolidate pass (Andrew, 2026-11-12: "we'll need a way to backfill and do a consolidate pass on existing
// boards to organize stuff") ─────────────────────────────────────────────────────────────────────────────────

/**
 * The items of a Daily Checklist document (engine/client/checklist.ts has the format): each `### Title {#key}`, whether
 * it sits under a Done heading, and its text, where ticket refs are written.
 */
export function checklistItems(md) {
  const out = []
  let section = ''
  let item = null
  for (const line of String(md ?? '').split(/\r?\n/)) {
    const h2 = /^##\s+(?!#)(.+)$/.exec(line)
    if (h2) { section = h2[1].trim().toLowerCase(); item = null; continue }
    const h3 = /^###\s+(.+)$/.exec(line)
    if (h3) {
      const raw = h3[1].trim()
      const key = /\{#([^}]+)\}\s*$/.exec(raw)?.[1] ?? null
      item = { title: raw.replace(/\s*\{#[^}]+\}\s*$/, '').trim(), key, done: section.startsWith('done'), body: '' }
      if (!/^(from|with) development/.test(section)) out.push(item)
      continue
    }
    if (item) item.body += `${line}\n`
  }
  return out.map(({ body, ...i }) => ({ ...i, text: `${i.title}\n${body}` }))
}

/** Every one of this board's tickets a piece of text names, by its full label or without the project prefix. */
export function refsIn(text, byLabel) {
  const found = new Set()
  for (const m of String(text ?? '').matchAll(/\b[A-Z][A-Z0-9]*(?:-[A-Z]+)*-\d+\b/g)) {
    const t = byLabel.get(m[0].toUpperCase())
    if (t) found.add(t)
  }
  return [...found]
}

const CONSOLIDATE_LINK_MAX = 3
const DEFAULT_ASK = { testing: 'Try it and say whether it works', awaiting_confirmation: 'Answer the question on this ticket' }
const quote = (s) => String(s).replace(/"/g, "'")

/**
 * What a consolidate pass would do to one board, as a plan, never as writes:
 *   asks   a ticket that waits on the client with no ask gets one: the title of the open checklist item that names
 *          it, or a plain default for its status. A ticket an open item names gets that ask even when its status
 *          kept it off the client's list (MSC-SAND-388 sat at merged waiting on Rachael's approval).
 *   links  a document no ticket holds that names one to three of this board's tickets is linked to them.
 *   todo   what needs the station's judgement, each with the command that does it: an open item with no ticket,
 *          a document that names no ticket or more than three.
 * A ticket the 30-day clear would close is left out, since a write restarts its clock: run `carried` first.
 */
export function consolidatePlan({ tickets, docs, links, station, envRefs = {}, now = Date.now(), quietMs = 30 * 24 * 3600 * 1000 }) {
  const label = (t) => refIn(station, t.ticket_number, t.source, envRefs).toUpperCase()
  const byLabel = new Map()
  for (const t of tickets) {
    const full = label(t)
    byLabel.set(full, t)
    const short = full.startsWith(`${station.toUpperCase()}-`) ? full.slice(station.length + 1) : full
    if (short !== full && !byLabel.has(short)) byLabel.set(short, t)
  }
  const expiring = (t) => ['testing', 'merged'].includes(t.status) && now - Date.parse(t.updated_at || '') > quietMs
  const items = docs.filter((d) => d.doc_type === 'checklist').flatMap((d) => checklistItems(d.body_md)).filter((i) => !i.done)
  const named = new Map()
  for (const i of items) for (const t of refsIn(i.text, byLabel)) if (!named.has(t.id)) named.set(t.id, i)

  const asks = []
  const skipped = []
  for (const t of tickets) {
    if (t.ask || t.is_backlog || ['closed', 'verified', 'promoted'].includes(t.status)) continue
    const item = named.get(t.id)
    if (waitingOn(t) !== 'client' && !item) continue
    if (expiring(t)) { skipped.push(label(t)); continue }
    asks.push({ ref: label(t), id: t.id, status: t.status, on: 'client', ask: (item ? item.title : DEFAULT_ASK[t.status] ?? 'See this ticket').slice(0, 200), from: item ? 'checklist item' : 'default for its status' })
  }

  const held = new Set(links.map((l) => l.document_id))
  const linksOut = []
  const todo = []
  for (const i of items) {
    if (!refsIn(i.text, byLabel).length) todo.push({ kind: 'item with no ticket', title: i.title, do: `beat ticket --station ${station} --title "${quote(i.title)}"; then beat ask --on client, and name it under Tickets:` })
  }
  const linkCount = new Map()
  for (const l of links) linkCount.set(l.document_id, (linkCount.get(l.document_id) ?? 0) + 1)
  // A document stands on one ticket (bridge/0063): its parent, or its only link. On several with none named, say which.
  const parentTodo = (d) => ({ kind: 'document on several tickets', title: d.title, id: d.id, do: `beat doc-link --station ${station} --id ${d.id} --ticket <the one it supports> --parent` })
  for (const d of docs) {
    if (standsAlone(d.doc_type)) continue
    if (held.has(d.id)) {
      if (!d.ticket_id && linkCount.get(d.id) > 1) todo.push(parentTodo(d))
      continue
    }
    const refs = refsIn(`${d.title}\n${d.body_md ?? ''}`, byLabel)
    if (refs.length >= 1 && refs.length <= CONSOLIDATE_LINK_MAX) {
      for (const t of refs) linksOut.push({ document_id: d.id, doc: d.title, ticket_id: t.id, ref: label(t) })
      if (refs.length > 1 && !d.ticket_id) todo.push(parentTodo(d))
    } else if (refs.length > CONSOLIDATE_LINK_MAX) {
      todo.push({ kind: 'document naming many tickets', title: d.title, id: d.id, names: refs.length, do: `beat doc-link --station ${station} --id ${d.id} --ticket <its parent> --parent` })
    } else {
      todo.push({ kind: 'document with no ticket', title: d.title, id: d.id, do: `beat ticket --station ${station} --title "${quote(d.title)}"; then beat doc-link --station ${station} --id ${d.id} --ticket <the new ref> --parent` })
    }
  }
  return { asks, links: linksOut, todo, skipped }
}

export const PRIORITIES = ['critical', 'blocker']

/** "Julia Park" · "julia" (from julia@acme.io) · null. The name a person would say. */
export function personName(p) {
  if (!p) return null
  // Boards name the columns differently: ITK has user_firstname, MSC has first_name.
  const full = [p.user_firstname ?? p.first_name, p.user_lastname ?? p.last_name].filter(Boolean).join(' ').trim()
  if (full) return full
  return p.email ? String(p.email).split('@')[0] : null
}

/** The name columns each board might have, tried in order until one reads. */
export const PROFILE_SHAPES = ['id,user_firstname,user_lastname,email', 'id,first_name,last_name,email', 'id,email']

/** `https://abcd.supabase.co` → `abcd`. Null for anything that is not a Supabase project URL. */
export function refFromUrl(url) {
  const m = String(url || '').match(/^https:\/\/([a-z0-9]{20})\.supabase\.(co|in)\/?$/i)
  return m ? m[1].toLowerCase() : null
}

/**
 * One board ticket → one Bridge row. `comments` are that ticket's, oldest first; `people` maps a
 * profile id to its profile. Timestamps are the board's own: the copy says when the ticket
 * changed, not when it was copied.
 */
export function mirrorRow(t, { kitchen, project, comments = [], people = new Map() }) {
  const who = (id) => personName(people.get(id))
  const requester = people.get(t.admin_id)
  return {
    kitchen_id: kitchen,
    project,
    id: t.id,
    origin: 'mirror',
    ticket_number: t.ticket_number ?? null,
    source: t.source ?? null,
    title: t.title || t.summary || `#${t.ticket_number ?? '?'}`,
    summary: t.summary ?? null,
    user_request: t.user_request ?? null,
    status: t.status || 'proposed',
    request_type: t.request_type || 'feature',
    priority_flag: t.priority_flag ?? null,
    environment: t.environment ?? null,
    tags: t.tags ?? [],
    page_label: t.page_label ?? null,
    page_path: t.page_path ?? null,
    pr_url: t.pr_url ?? null,
    pr_number: t.pr_number ?? null,
    is_backlog: t.is_backlog ?? false,
    // A copy carries no relations. `related_ticket_numbers` was dropped from board_tickets
    // (bridge/0031) because a bare integer can't say which series it means on a board with more than
    // one, and the relation now lives in board_ticket_links with ids and a kind. A mirror that kept
    // sending the field would fail on a column that isn't there (ITK asked the right question,
    // 2026-09-20: dropping a column breaks whoever still writes it).
    requester: who(t.admin_id),
    requester_email: requester?.email ?? null,
    assignee: who(t.assigned_to),
    comments: comments.slice(-KEEP_COMMENTS).map((c) => ({
      who: who(c.author_id) ?? 'someone', at: c.created_at, body: c.body ?? '',
    })),
    created_at: t.created_at,
    updated_at: t.updated_at ?? t.created_at,
  }
}

/** Every ticket → its row, with comments grouped and ordered here rather than trusted from the query. */
export function mirrorRows(tickets, comments, profiles, ctx) {
  const people = new Map((profiles ?? []).map((p) => [p.id, p]))
  const byTicket = new Map()
  for (const c of [...(comments ?? [])].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))) {
    const list = byTicket.get(c.change_request_id) ?? []
    list.push(c)
    byTicket.set(c.change_request_id, list)
  }
  return (tickets ?? []).map((t) => mirrorRow(t, { ...ctx, people, comments: byTicket.get(t.id) ?? [] }))
}

/**
 * What this run copies. Full when asked, when there has never been a full copy, or when the last
 * one is a day old; otherwise everything changed since the newest thing already copied.
 */
export function planCopy(sync, { full = false, now = Date.now() } = {}) {
  const lastFull = sync?.full_at ? Date.parse(sync.full_at) : NaN
  const stale = !Number.isFinite(lastFull) || now - lastFull > FULL_EVERY_MS
  if (full || stale || !sync?.last_source_at) return { full: true, since: null, commentSince: null }
  return { full: false, since: sync.last_source_at, commentSince: sync.last_comment_at ?? sync.last_source_at }
}

/** The latest of some ISO timestamps, or `fallback` when there are none. */
export function latest(values, fallback = null) {
  let best = fallback
  for (const v of values) if (v && (!best || Date.parse(v) > Date.parse(best))) best = v
  return best
}

export function chunk(list, size) {
  const out = []
  for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size))
  return out
}

const csv = (v) => (v === undefined || v === true ? [] : String(v).split(',').map((s) => s.trim()).filter(Boolean))

/**
 * A hosted ticket from a station's flags or a JSON entry. The request is kept word for word; a
 * ticket nobody asked for in words is refused, the same rule the expeditor keeps.
 */
export function hostedTicket(raw, project) {
  // A bare --flag parses as true; a flag with nothing after it has said nothing.
  const input = Object.fromEntries(Object.entries(raw).map(([k, v]) => [k, v === true && k !== 'backlog' ? undefined : v]))
  const title = String(input.title ?? '').trim()
  if (!title) throw new Error('a ticket needs --title: what it is, in a line')
  const request = String(input.request ?? input.user_request ?? '').trim()
  if (!request) throw new Error('a ticket needs --request: what was asked, in the words it was asked in')
  const type = String(input.type ?? input.request_type ?? 'feature').toLowerCase()
  const priority = input.priority ?? input.priority_flag ?? null
  if (priority != null && !PRIORITIES.includes(String(priority).toLowerCase())) {
    throw new Error(`--priority is ${PRIORITIES.join(' or ')}, or left off`)
  }
  const status = String(input.status ?? 'proposed').toLowerCase()
  if (!STATUSES.includes(status)) throw new Error(`--status must be one of: ${STATUSES.join(', ')}`)
  const tags = Array.isArray(input.tags) ? input.tags.map(String) : csv(input.tags)
  const row = {
    project, origin: 'hosted', title, user_request: request, status, request_type: type,
    priority_flag: priority == null ? null : String(priority).toLowerCase(),
    summary: input.summary ?? null,
    tags,
    environment: input.environment ?? input.env ?? null,
    page_label: input.page ?? input.page_label ?? null,
    page_path: input.path ?? input.page_path ?? null,
    requester: input.from ?? input.requester ?? null,
    requester_email: input['from-email'] ?? input.from_email ?? input.requester_email ?? null,
    is_backlog: input.backlog === true || input.is_backlog === true,
  }
  return row
}

/** `--number 12` → 12. Refuses anything that is not a ticket number rather than matching nothing. */
export function ticketNumber(v) {
  const n = typeof v === 'boolean' ? NaN : Number(v)
  if (!Number.isInteger(n) || n < 1) throw new Error('--number is the ticket number, e.g. --number 12')
  return n
}

/**
 * What a person typed, as a number and — when they said one — the series it belongs to.
 *
 * A bare number is unique on a board with one series and ambiguous on a board with several. ITK has
 * three tickets numbered 1: ITK-DEV-1, ITK-STG-1, and a stray. So `--number` takes a whole ref as
 * well, and the caller who knows which one they mean can say it (2026-09-21).
 *
 *   12            { n: 12, source: null }   the board decides, or refuses if it can't
 *   ITK-DEV-1     { n: 1,  source: 'dev' }
 *   ITK-1         { n: 1,  source: null }   a bare prefix says no more than the number does
 */
export function ticketTarget(v, project) {
  const raw = String(v === true ? '' : v ?? '').trim();
  const asRef = raw.match(/^([A-Za-z][A-Za-z0-9]*)(?:-([A-Za-z][A-Za-z0-9]*))?-(\d+)$/);
  if (asRef) {
    const [, head, middle, num] = asRef;
    if (String(head).toLowerCase() !== String(project).toLowerCase()) {
      throw new Error(`${raw} is not a ${String(project).toUpperCase()} ticket.`)
    }
    return { n: ticketNumber(num), source: middle ? middle.toLowerCase() : null }
  }
  return { n: ticketNumber(raw), source: null }
}

/**
 * Is `yours` an older kit than `expected`? `2026-09-16.3` is older than `2026-09-16.10` and
 * `2026-09-17.1`. Unknown versions count as old; no expectation means nothing to be behind.
 *
 * Here rather than in beat.mjs because The Pass needs the same answer, and beat.mjs is the CLI —
 * not something a browser bundle should import. Two copies of a version comparator would drift,
 * and the one that drifted would be the one nobody tests.
 */
export function kitBehind(yours, expected) {
  if (!expected) return false
  const parse = (v) => {
    const m = String(v || '').match(/^(\d{4}-\d{2}-\d{2})\.(\d+)$/)
    return m ? [m[1], Number(m[2])] : null
  }
  const a = parse(yours), b = parse(expected)
  if (!b) return false
  if (!a) return true
  return a[0] < b[0] || (a[0] === b[0] && a[1] < b[1])
}

/** The ref a person says: NU-12. */
export const refOf = (project, n) => `${String(project).toUpperCase()}-${n}`

/**
 * The ref for a ticket that knows its series: ITK-DEV-1267.
 *
 * `envRefs` says whether this BOARD numbers per environment, and it has to come from the board
 * rather than be inferred from the row. Treating `hosted` as "no series" is right for NU, WS and
 * WSWEB — one series, and `PREFIX-n` is what people there say — and wrong for ITK, which carried
 * `hosted` as a fourth series beside DEV, STG and SAND. Closing ITK-HOSTED-1 resolved correctly
 * and then echoed `ITK-1` back: resolution right, confirmation lossy, on a board where 108 numbers
 * mean two tickets. A reader checking the output of the very command that caused the June damage
 * saw the ambiguous form again (ITK, 2026-09-21).
 *
 * true  → always tag it, `hosted` included
 * false → never tag it
 * null  → the old guess, for callers that have no board to ask
 */
export const refIn = (project, n, source, envRefs = null) => {
  const tag = String(source ?? '').trim()
  if (!tag) return refOf(project, n)
  if (envRefs === false) return refOf(project, n)
  if (envRefs !== true && tag === 'hosted') return refOf(project, n)
  return `${String(project).toUpperCase()}-${tag.toUpperCase()}-${n}`
}

// ── HTTP ───────────────────────────────────────────────────────────────────

/** Headers for a project's own database. New-style secret keys are not JWTs and go in apikey only. */
export function boardHeaders(key) {
  const h = { apikey: key, 'content-type': 'application/json' }
  if (!String(key).startsWith('sb_')) h.authorization = `Bearer ${key}`
  return h
}

async function boardGet(board, path) {
  const r = await fetch(`${board.url}/rest/v1/${path}`, { headers: boardHeaders(board.key) })
  const body = await r.text()
  if (!r.ok) throw new Error(`board ${path.split('?')[0]} → ${r.status}: ${body.slice(0, 300)}`)
  return body ? JSON.parse(body) : []
}

/** Every row of a board query, a page at a time. `path` must carry its own order. */
async function boardAll(board, path, page = 1000) {
  const out = []
  for (let offset = 0; ; offset += page) {
    const rows = await boardGet(board, `${path}&limit=${page}&offset=${offset}`)
    out.push(...rows)
    if (rows.length < page) return out
  }
}

/**
 * Copy one project's board to the Bridge. `bridge` is { rest, kitchen, station } from beat.mjs:
 * already signed in, kitchen already resolved.
 */
export async function copyBoard({ rest, kitchen, station }, board, { full = false, now = Date.now() } = {}) {
  const k = encodeURIComponent(kitchen)
  const p = encodeURIComponent(station)
  const [sync] = await rest(`board_sync?kitchen_id=eq.${k}&project=eq.${p}&select=*`)
  const plan = planCopy(sync, { full, now })

  // What changed: tickets touched since the watermark, plus tickets whose comments moved on (a new
  // comment does not always touch its ticket's updated_at).
  let tickets
  let newComments = []
  if (plan.full) {
    tickets = await boardAll(board, `admin_change_requests?select=${TICKET_COLS}&order=id`)
  } else {
    tickets = await boardAll(board,
      `admin_change_requests?select=${TICKET_COLS}&updated_at=gte.${encodeURIComponent(plan.since)}&order=updated_at,id`)
    newComments = await boardAll(board,
      `admin_change_request_comments?select=change_request_id,created_at&created_at=gt.${encodeURIComponent(plan.commentSince)}&order=created_at,id`)
    const have = new Set(tickets.map((t) => t.id))
    const more = [...new Set(newComments.map((c) => c.change_request_id))].filter((id) => !have.has(id))
    for (const ids of chunk(more, 100)) {
      tickets.push(...await boardGet(board, `admin_change_requests?select=${TICKET_COLS}&id=in.(${ids.join(',')})`))
    }
  }

  const ids = tickets.map((t) => t.id)
  const comments = []
  for (const part of chunk(ids, 100)) {
    comments.push(...await boardAll(board,
      `admin_change_request_comments?select=change_request_id,body,created_at,author_id&change_request_id=in.(${part.join(',')})&order=created_at,id`))
  }
  const personIds = [...new Set([
    ...tickets.flatMap((t) => [t.admin_id, t.assigned_to]),
    ...comments.map((c) => c.author_id),
  ].filter(Boolean))]
  const profiles = []
  for (const part of chunk(personIds, 100)) {
    // Names are a courtesy. A board whose profiles can't be read still gets copied.
    for (const shape of PROFILE_SHAPES) {
      const got = await boardGet(board, `profiles?select=${shape}&id=in.(${part.join(',')})`).catch(() => null)
      if (got) { profiles.push(...got); break }
    }
  }

  const rows = mirrorRows(tickets, comments, profiles, { kitchen, project: station })
  for (const part of chunk(rows, 500)) {
    await rest('board_tickets?on_conflict=kitchen_id,project,id', {
      method: 'POST',
      headers: { prefer: 'resolution=merge-duplicates,return=minimal' },
      body: JSON.stringify(part),
    })
  }

  // A full copy is the moment to notice tickets the board no longer has.
  let removed = 0
  if (plan.full) {
    const keep = new Set(ids)
    const mirrored = []
    for (let offset = 0; ; offset += 1000) {
      const page = await rest(`board_tickets?kitchen_id=eq.${k}&project=eq.${p}&origin=eq.mirror&select=id&order=id&limit=1000&offset=${offset}`)
      mirrored.push(...page)
      if (page.length < 1000) break
    }
    const gone = mirrored.map((r) => r.id).filter((id) => !keep.has(id))
    for (const part of chunk(gone, 100)) {
      await rest(`board_tickets?kitchen_id=eq.${k}&project=eq.${p}&origin=eq.mirror&id=in.(${part.join(',')})`, { method: 'DELETE' })
    }
    removed = gone.length
  }

  const state = {
    kitchen_id: kitchen,
    project: station,
    last_source_at: latest(tickets.map((t) => t.updated_at), sync?.last_source_at ?? null),
    last_comment_at: latest([...comments, ...newComments].map((c) => c.created_at), sync?.last_comment_at ?? null),
    full_at: plan.full ? new Date(now).toISOString() : sync?.full_at ?? null,
    synced_at: new Date(now).toISOString(),
    // How many tickets the board had at the last full copy. An incremental run can't know without
    // counting the whole table, and this is for a glance, not an audit.
    rows: plan.full ? rows.length : sync?.rows ?? rows.length,
    ok: true,
    note: `${plan.full ? 'full' : 'since ' + plan.since}: ${rows.length} copied${removed ? `, ${removed} gone` : ''}`,
  }
  await rest('board_sync?on_conflict=kitchen_id,project', {
    method: 'POST',
    headers: { prefer: 'resolution=merge-duplicates,return=minimal' },
    body: JSON.stringify(state),
  })
  return { project: station, full: plan.full, since: plan.since, copied: rows.length, removed, rows: state.rows }
}

// ── Explainers (bridge/0010) ───────────────────────────────────────────────

/** How long each plain-words field may be. The chit shows the issue at a glance. */
export const EXPLAIN_LIMITS = { issue: 200, blocking: 200, risk: 200, detail: 1200, label: 60, note: 120 }

/**
 * Code in a sentence meant for a person: backticks, snake_case, a call like `run()`, a file path.
 * Returns what it found, or null. The explainer is read by someone deciding, not building.
 */
export function codeIn(text) {
  const s = String(text ?? '')
  const m = s.match(/`[^`]*`|\b[a-z]+(?:_[a-z0-9]+)+\b|\b[A-Za-z]\w*\(\)|(?:^|\s)[\w.-]+\/[\w./-]+\.\w+\b|§\s*\d/)
  return m ? m[0].trim() : null
}

/**
 * A ticket's ref, written one way: `itk stg 1240` → ITK-STG-1240. The environment tag is kept: some
 * projects (ITK) reuse numbers across environments, so the tag is part of the name (bridge/0012).
 * From a number, `env` supplies the tag: { number: 1240, env: 'stg' } → ITK-STG-1240.
 */
export function explainRef(input, prefix) {
  if (input.ref) return String(input.ref).trim().toUpperCase().split(/[\s-]+/).filter(Boolean).join('-')
  const env = input.env && input.env !== true ? `${String(input.env).trim().toUpperCase()}-` : ''
  if (env && !/^[A-Z]+-$/.test(env)) throw new Error(`env is a tag like STG, not "${input.env}"`)
  return `${String(prefix).toUpperCase()}-${env}${ticketNumber(input.number)}`
}

/** A copied ticket's ref with its tag, when the project names its environments: ITK + noh → ITK-STG-1240. */
export function taggedRef(prefix, number, source, envBySource = {}) {
  const tag = source ? envBySource[source] ?? envBySource[String(source).toLowerCase()] : null
  return `${String(prefix).toUpperCase()}-${tag ? `${tag}-` : ''}${number}`
}

/**
 * One explainer, checked. Plain words only, short, with two to four options that each say what
 * they get and what they cost. Throws with the first thing to fix.
 */
export function explainerRow(input, project, prefix = project) {
  const ref = explainRef(input, prefix)
  const where = `${ref}:`
  const text = (k, v, max, required = false) => {
    const s = v == null || v === true ? '' : String(v).replace(/\s+/g, ' ').trim()
    if (!s) { if (required) throw new Error(`${where} ${k} is required`); return null }
    if (s.length > max) throw new Error(`${where} ${k} is ${s.length} characters; keep it under ${max}`)
    const code = codeIn(s)
    if (code) throw new Error(`${where} ${k} has code in it (${code}) — say it the way you would to someone who has never seen the code`)
    return s
  }
  const issue = text('issue', input.issue, EXPLAIN_LIMITS.issue, true)
  const blocking = text('blocking', input.blocking, EXPLAIN_LIMITS.blocking)
  const risk = text('risk', input.risk, EXPLAIN_LIMITS.risk)
  const detail = text('detail', input.detail, EXPLAIN_LIMITS.detail)
  const raw = Array.isArray(input.options) ? input.options : []
  if (raw.length === 1 || raw.length > 4) throw new Error(`${where} give two to four options, or none`)
  const options = raw.map((o, i) => {
    const id = String(o.id ?? String.fromCharCode(97 + i)).toLowerCase()
    if (!/^[a-z]$/.test(id)) throw new Error(`${where} option ids are single letters (a, b, c)`)
    return {
      id,
      label: text(`option ${id}`, o.label, EXPLAIN_LIMITS.label, true),
      gain: text(`option ${id} gain`, o.gain, EXPLAIN_LIMITS.note, true),
      cost: text(`option ${id} cost`, o.cost, EXPLAIN_LIMITS.note, true),
      ...(o.reversible === false ? { reversible: false } : {}),
    }
  })
  const recommend = input.recommend ? String(input.recommend).toLowerCase() : null
  if (recommend && !options.some(o => o.id === recommend)) throw new Error(`${where} recommend names an option that isn't there`)
  return {
    project, ref, issue, blocking, risk, options, recommend, detail,
    ticket_updated_at: input.ticket_updated_at ?? input.updated_at ?? null,
  }
}

// ── What arrived since you last looked (bridge/0041) ───────────────────────

/** How far back a station looks the first time, before it has a watermark. */
export const FIRST_LOOK_MS = 24 * 60 * 60 * 1000

/**
 * The tickets to show this tick, and the watermark to keep if the station says it has read them.
 *
 * `seenAt` is where it got to last time; null means it has never looked, and a day is far enough
 * back to be useful without reading a year of history on the first tick.
 *
 * The next watermark is the NEWEST TICKET SHOWN, not now(): a ticket filed while the station was
 * reading this list is not one it has seen, and now() would skip it silently. Nothing shown, nothing
 * moves.
 */
export function freshTickets(rows, { seenAt = null, now = Date.now() } = {}) {
  const since = seenAt ? Date.parse(seenAt) : now - FIRST_LOOK_MS
  const list = (Array.isArray(rows) ? rows : [])
    .filter((t) => t && t.created_at && Date.parse(t.created_at) > since)
    .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at))
  const newest = list.length ? list[list.length - 1].created_at : (seenAt ?? null)
  return { since: new Date(since).toISOString(), tickets: list, nextSeenAt: newest }
}

// ── Merging on your own ────────────────────────────────────────────────────
//
// Andrew approved every merge by hand, and most of them were a station asking "may I take the kit
// update?" (2026-09-21). So some PRs a station now merges itself: the kinds on its project's merge
// list (projects.merge_policy, bridge/0038), into the branches named there, once checks pass.
//
// The station doesn't decide whether a PR qualifies; this does, from the PR's own file list, so
// the answer is the same whoever asks and a PR that half-fits goes to Andrew as before. A list can
// only NARROW what doctrine allows: the NEVER paths below go to Andrew whatever a list says.

/** The kinds a merge list can name. */
export const MERGE_KINDS = ['kit', 'docs', 'deps_patch', 'fired_ticket']

/**
 * Where a ticket can be while its work merges, if its list allows. The status alone doesn't say anyone
 * said go: the assistant's handoffs arrive at needs_dev on their own, and a Developer's start reaches
 * it too (MSC, 2026-10-31). So code also needs ticket.go, Andrew's word on record (bridge/0059).
 */
export const FIRED_STATUSES = ['needs_dev', 'pr_open', 'testing_failed', 'ready_to_merge']

/**
 * Which lock categories are "kit": tooling Lodestar writes for the station to run, where the PR is
 * the mechanical output of `lodestar update`. `schema` and `functions` are not — they reach a
 * database or a deployed function, and the NEVER paths send them to Andrew anyway. Nor is `client`:
 * it ships inside the app.
 */
export const KIT_CATEGORIES = ['station', 'scripts']

/** What `lodestar update --only station` writes, as each host receives it. */
export const KIT_FILES = [
  'scripts/beat.mjs', 'scripts/board.mjs',
  '.claude/skills/station/SKILL.md', '.claude/skills/zid-proof/SKILL.md', '.claude/skills/kelly-proof/SKILL.md',
  '.claude/skills/side-effects-off-until-live/SKILL.md',
  // The two public-page skills (kit 2026-11-19.1): agent-ready existed since Oct but never reached a station.
  '.claude/skills/agent-ready-public-pages/SKILL.md', '.claude/skills/search-ready-public-pages/SKILL.md',
  // The launch preflight and its example (kit 11.4, station kit since 11.5). The lock on main doesn't name a file
  // the update is adding, so without these ITK's #1265 was held as code (2026-11-12). A project's own
  // launch/preflight.config.mjs isn't here: the station writes that, so it stays code.
  'scripts/lodestar/launch-preflight.mjs', 'launch/preflight.example.mjs',
]

/**
 * path → category, from a host's lodestar.lock. Null when there isn't one to read: the caller then
 * falls back to the built-in list of kit files.
 */
export function managedFiles(lock) {
  const files = lock && typeof lock === 'object' ? lock.files : null
  if (!files || typeof files !== 'object') return null
  return new Map(Object.entries(files).map(([path, v]) => [path, v?.category ?? null]))
}

/**
 * Paths that always go to Andrew, and the plain reason. Checked on every file, old name and new.
 *
 * A note ABOUT a migration isn't one: MSC's `docs/migration/bubble-to-stage-prod.md` was refused as
 * "a database migration" (2026-11-10). Prose under a migrations folder passes that rule, and only
 * that one: `supabase/migrations/README.md` still goes to Andrew as Supabase.
 */
export const NEVER = [
  [/(^|\/)migrations?\/(?!.*\.(md|mdx|txt)$)/i, 'a database migration'],
  [/\.sql$/i, 'SQL'],
  [/^supabase\//i, 'Supabase functions or config'],
  [/^\.github\//i, 'CI or deploy workflows'],
  [/(^|\/)(vercel|eas|app|netlify)\.json$|(^|\/)app\.config\.[cm]?[jt]s$/i, 'deploy or app config'],
  [/(^|\/)\.env/i, 'environment settings'],
  [/(^|\/)lodestar\.config\.json$/i, 'Lodestar config'],
]

/**
 * Words in a PATH that make a change Andrew's, wherever the file lives.
 *
 * Read them as a guess about a file nobody has read, because that is what they are. Each one buys a
 * refusal on a file that might be dangerous, and costs a refusal on one that isn't — so the list is
 * short, and a word that is some product's ordinary vocabulary is not on it:
 *
 *   `polic(y|ies)` and `rls` came off (MSC, 2026-09-22). They were there for RLS policies, which
 *   live in SQL and under supabase/ and are already refused by the path rules above — while
 *   "policy" is the core noun of an insurance product. MSC has PolicySummary.tsx, a policies
 *   route, policyBucket, policyHref: the rule made a station unable to touch its own domain, and a
 *   reason line that reads as nonsense teaches people to skip reason lines.
 *
 *   `session` and `token` came off for the same reason: a gym booking is a session, a design system
 *   has tokens. What they were guarding — a file that really is about signing in — is still caught
 *   by auth, login or credential, and code needs a fired ticket regardless.
 *
 * A host whose vocabulary still collides declares it: `merge.domainWords` in lodestar.config.json.
 */
export const NEVER_WORDS = [
  [/stripe|payment|billing|checkout|subscription|paywall|purchase|revenuecat/i, 'payments'],
  [/auth|login|permission|credential|secret|password|api[_-]?key|middleware/i, 'auth, permissions or secrets'],
]

/**
 * A host's own words, taken out of a path before the word rules read it: "policy" on an insurance
 * board, "session" on a gym booking app. Only the host knows, so only the host can say.
 */
export function scrubDomainWords(path, domainWords) {
  const words = (Array.isArray(domainWords) ? domainWords : []).map((w) => String(w).trim()).filter(Boolean)
  if (!words.length) return String(path)
  const escaped = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
  return String(path).replace(new RegExp(escaped, 'gi'), '')
}

const LOCKFILE = /(^|\/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|deno\.lock)$/
const PACKAGE = /(^|\/)package\.json$/

/**
 * kit · docs · deps · code: what one changed file is.
 *
 * `managed` is the host's lodestar.lock, path → category, so a file Lodestar writes is known from
 * the host rather than guessed from a list. MSC hit this on the engine-script change that added
 * `edge-logs --messages`: a plain `lodestar update`, refused as code because scripts/ wasn't in the
 * built-in list while .claude/skills was (2026-09-22). Without a lock, the built-in list still answers.
 */
export function fileClass(p, managed = null) {
  const f = String(p)
  const bare = f.replace(/^\.lodestar\/baseline\//, '')
  if (managed && KIT_CATEGORIES.includes(managed.get(bare))) return 'kit'
  if (f === 'lodestar.lock' || KIT_FILES.includes(f) || KIT_FILES.includes(bare)) return 'kit'
  if (PACKAGE.test(f) || LOCKFILE.test(f)) return 'deps'
  // Agent instructions change how a station behaves, so they are code, not docs.
  const agent = /^\.claude\//.test(f) || /(^|\/)(CLAUDE|AGENTS)\.md$/i.test(f)
  if (!agent && (/\.(md|mdx|txt)$/i.test(f) || /^docs\//.test(f))) return 'docs'
  if (/(^|\/)(__tests__|tests?|e2e)\//.test(f) || /\.(test|spec)\.[cm]?[jt]sx?$/.test(f)) return 'docs'
  return 'code'
}

const SEMVER = /^([\^~]?)(\d+)\.(\d+)\.(\d+)(.*)$/

/**
 * Whether a package.json diff only moves dependency versions within their minor (1.4.2 → 1.4.7).
 * Null when it does; otherwise the reason, in words. Anything else on a changed line (a script,
 * a new dependency, a removed one, a range widened) is a reason.
 */
export function patchBumpOnly(patch) {
  if (!patch) return 'GitHub gave no diff for package.json to read'
  const was = new Map()
  const now = new Map()
  for (const line of String(patch).split('\n')) {
    if (line.startsWith('@@') || line.startsWith('---') || line.startsWith('+++')) continue
    const sign = line[0]
    if (sign !== '-' && sign !== '+') continue
    const m = line.slice(1).match(/^\s*"([^"]+)"\s*:\s*"([^"]*)"\s*,?\s*$/)
    if (!m) return `package.json changes a line that isn't a version: ${line.slice(1).trim().slice(0, 60)}`
    const into = sign === '-' ? was : now
    into.set(m[1], m[2])
  }
  if (!now.size) return 'package.json has no version change'
  for (const [name, to] of now) {
    if (!was.has(name)) return `adds ${name}`
    const a = was.get(name).match(SEMVER)
    const b = to.match(SEMVER)
    if (!a || !b) return `${name}: ${was.get(name)} → ${to} isn't a plain version`
    if (a[1] !== b[1] || a[5] !== b[5]) return `${name}: ${was.get(name)} → ${to} changes the range`
    if (a[2] !== b[2] || a[3] !== b[3]) return `${name}: ${was.get(name)} → ${to} is more than a patch`
    if (Number(b[4]) < Number(a[4])) return `${name}: ${was.get(name)} → ${to} goes backwards`
  }
  for (const name of was.keys()) if (!now.has(name)) return `removes ${name}`
  return null
}

/** One check from `gh pr view --json statusCheckRollup`: ok · pending · failed. */
export function checkState(c) {
  const name = c?.name || c?.context || 'a check'
  if (c?.__typename === 'StatusContext' || (c?.state && !c?.status)) {
    const s = String(c.state).toUpperCase()
    return { name, state: s === 'SUCCESS' ? 'ok' : s === 'PENDING' || s === 'EXPECTED' ? 'pending' : 'failed' }
  }
  if (String(c?.status).toUpperCase() !== 'COMPLETED') return { name, state: 'pending' }
  const done = String(c?.conclusion).toUpperCase()
  return { name, state: ['SUCCESS', 'NEUTRAL', 'SKIPPED'].includes(done) ? 'ok' : 'failed' }
}

const KIND_OF = { kit: 'kit', docs: 'docs', deps: 'deps_patch', code: 'fired_ticket' }

/**
 * May this station merge this PR itself? `merge: true` comes with the command to run; anything
 * else comes with every reason, because the station passes them to Andrew.
 *
 *   policy  the project's merge list: { "<branch>": ["kit", "docs", …] }
 *   pr      from `gh pr view --json number,state,isDraft,baseRefName,mergeStateStatus,
 *                  isCrossRepository,changedFiles,statusCheckRollup`
 *   files   from the pulls/<n>/files API: [{ filename, previous_filename, patch }]
 *   ticket  the ticket the PR is for, when it has one: { ref, status, go }. `go` is Andrew's word on
 *           record, from a fire on The Pass or `beat go`; a start from the app doesn't set it.
 *   managed path -> lock category for this host (managedFiles), so what Lodestar writes is known
 *           rather than guessed. Used only in a PR that also restamps lodestar.lock.
 *   domainWords this host's ordinary vocabulary (merge.domainWords in lodestar.config.json), taken
 *           out of a path before the word rules read it.
 */
export function mergeVerdict({ policy, pr, files, ticket = null, managed = null, domainWords = null }) {
  const why = []
  const n = pr?.number
  const base = pr?.baseRefName
  const list = policy && typeof policy === 'object' && !Array.isArray(policy) ? policy : null
  const allowed = new Set((list?.[base] ?? []).filter((k) => MERGE_KINDS.includes(k)))
  if (!list || !Object.keys(list).length) why.push("your project has no merge list on the Bridge, so every merge is Andrew's")
  else if (!allowed.size) why.push(`nothing merges into ${base} without Andrew`)
  if (pr?.state && pr.state !== 'OPEN') why.push(`the PR is ${String(pr.state).toLowerCase()}`)
  if (pr?.isDraft) why.push('the PR is a draft')
  if (pr?.isCrossRepository) why.push('the PR comes from another repository')
  if (pr?.mergeStateStatus === 'DIRTY') why.push('the PR has merge conflicts')
  const changed = Array.isArray(files) ? files : []
  if (!changed.length) why.push("could not read the PR's files")
  else if (Number.isInteger(pr?.changedFiles) && pr.changedFiles !== changed.length) {
    why.push(`read ${changed.length} of the PR's ${pr.changedFiles} files`)
  }

  // A LOCK-MANAGED FILE COUNTS AS KIT ONLY IN A PR THAT RESTAMPS THE LOCK. Every `lodestar update`
  // writes lodestar.lock, so its absence means these files were edited by hand — a change to tooling
  // that runs with the host's tokens, which belongs on a fired ticket.
  const stamped = (Array.isArray(files) ? files : []).some((f) => f?.filename === 'lodestar.lock')
  const never = new Set()
  const classes = new Set()
  for (const f of changed) {
    for (const p of [f.filename, f.previous_filename].filter(Boolean)) {
      // The path as written decides the path rules; the host's own vocabulary is taken out of it
      // before the word rules read it.
      const scrubbed = scrubDomainWords(p, domainWords)
      const hit = NEVER.find(([re]) => re.test(p)) ?? NEVER_WORDS.find(([re]) => re.test(scrubbed))
      if (hit) never.add(`${p} is ${hit[1]}`)
      classes.add(fileClass(p, stamped ? managed : null))
    }
  }
  why.push(...never)

  // A package.json that isn't a plain version bump is CODE, not a failed bump. MSC's PR #75 added
  // one npm script and was refused as "test:unit:watch: vitest -> vitest isn't a plain version"
  // (2026-09-22): true, and beside the point. A new script is a change to how the project builds and
  // tests, so it belongs on a fired ticket like any other code — which is what calling it code does.
  const notBumps = []
  if (classes.has('deps')) {
    const pkgs = changed.filter((x) => PACKAGE.test(x.filename))
    if (!pkgs.length) why.push('a lockfile changed with no package.json change')
    for (const f of pkgs) {
      const off = patchBumpOnly(f.patch)
      if (off) notBumps.push(`${f.filename} changes more than versions (${off}), so it counts as code`)
    }
    if (notBumps.length) { classes.delete('deps'); classes.add('code') }
  }
  if (allowed.size) {
    for (const c of classes) {
      if (!allowed.has(KIND_OF[c])) why.push(`it changes ${c} files, and "${KIND_OF[c]}" isn't on your list for ${base}`)
    }
  }
  if (classes.has('code')) {
    if (!ticket) why.push('it changes code, so it needs a fired ticket: pass --ticket <ref>')
    else if (!FIRED_STATUSES.includes(ticket.status)) why.push(`${ticket.ref} is ${ticket.status}, not fired work (${FIRED_STATUSES.join(', ')})`)
    else if (!ticket.go) why.push(`${ticket.ref} has no go from Andrew on record. A status or a start from the app isn't one: it takes his fire on The Pass, or \`beat go\` with his words when he says it in your session`)
  }

  const checks = (pr?.statusCheckRollup ?? []).map(checkState)
  const failed = checks.filter((c) => c.state === 'failed').map((c) => c.name)
  if (failed.length) why.push(`checks failed: ${failed.join(', ')}`)
  const pending = checks.filter((c) => c.state === 'pending').map((c) => c.name)

  const kind = KIND_OF[['code', 'deps', 'docs', 'kit'].find((c) => classes.has(c)) ?? 'kit']
  if (why.length) {
    return { pr: n, base, kind, merge: false, why, ...(notBumps.length ? { notes: notBumps } : {}), do: 'leave it for Andrew: say HANDS on the ticket with the PR link and these reasons' }
  }
  return {
    pr: n, base, kind, merge: true, why: [], ...(notBumps.length ? { notes: notBumps } : {}),
    ...(pending.length ? { waiting_on: pending } : {}),
    do: `gh pr merge ${n} --auto --merge (GitHub merges it once the required checks pass), then NOTE on the ticket: "merged on my own: ${kind}"`,
  }
}

// ── Documents (bridge/0022) ────────────────────────────────────────────────
//
// A station posts a document the way it files a ticket: straight onto its project's board, where
// the Documents tab reads it (Andrew, 2026-09-21: "stations should be able to post docs like they
// post tickets"). MSC had a spec Andrew had asked for and no way to put it there.

export const DOC_LIMITS = { title: 300, body: 500000 }

/**
 * A document from a station's flags: title, type, and the markdown body (from --file). Checked
 * here with the Bridge's own limits, so a bad one is refused with a sentence before anything is sent.
 */
export function documentRow(input, station) {
  const title = String(input.title ?? '').trim()
  const body = String(input.body_md ?? input.body ?? '')
  const type = String(input.type ?? input.doc_type ?? 'plan').trim().toLowerCase()
  if (!title) throw new Error('a document needs --title')
  if (title.length > DOC_LIMITS.title) throw new Error(`--title is ${title.length} characters; ${DOC_LIMITS.title} at most`)
  if (!body.trim()) throw new Error('a document needs its text: --file <markdown file>')
  if (body.length > DOC_LIMITS.body) throw new Error(`the document is ${body.length} characters; ${DOC_LIMITS.body} at most`)
  if (!/^[a-z][a-z0-9_-]{0,39}$/.test(type)) throw new Error('--type is one word, like plan, design, audit, spec or runbook')
  const as = input.as && input.as !== true ? String(input.as) : `the ${station} station`
  return { project: station, title, doc_type: type, body_md: body, created_by: as }
}

/**
 * A document that is a view of the board, not work on it, stands alone: no parent ticket is made for it, and its
 * comments stay its own (bridge/0063 board_document_stands_alone says the same).
 */
export const STANDS_ALONE = ['checklist', 'test-report']
export const standsAlone = (type) => STANDS_ALONE.includes(String(type ?? ''))

/** Where a document opens in the project's admin. */
export const documentLink = (id) => `/admin/lodestar?tab=documents&doc=${id}`

/**
 * Comments on documents, grouped by the document they are on.
 *
 * ONE THREAD PER DOCUMENT, because that is what they are: MSC's 36 waiting comments were all on one
 * spec (2026-09-27). A flat list of 36 reads as 36 problems. Each group carries the document, and
 * each comment its author, the passage it is anchored to and its words — the four things a station
 * needs to answer without opening anything.
 */
export function docComments(rows, docs = []) {
  const title = new Map((Array.isArray(docs) ? docs : []).map((d) => [d.id, d.title]))
  const byDoc = new Map()
  for (const c of (Array.isArray(rows) ? rows : [])) {
    if (!c?.document_id) continue
    const g = byDoc.get(c.document_id) ?? { document_id: c.document_id, title: title.get(c.document_id) ?? null, link: documentLink(c.document_id), comments: [] }
    g.comments.push({
      id: c.id, author: c.author ?? null, at: c.created_at,
      // The highlighted passage, when there is one: it says WHERE in the document they mean.
      anchor: c.anchor_text ?? null, body: c.body,
      ...(c.resolved_at ? { resolved_at: c.resolved_at, resolved_by: c.resolved_by ?? null } : {}),
      // Answered stays listed, with its answer (bridge/0057).
      ...(c.answered_at ? { answered_at: c.answered_at, answered_by: c.answered_by ?? null, answer: c.answer ?? null } : {}),
    })
    byDoc.set(c.document_id, g)
  }
  const groups = [...byDoc.values()]
  for (const g of groups) g.comments.sort((a, b) => Date.parse(a.at) - Date.parse(b.at))
  // Newest conversation first: the document someone just commented on is the one to read.
  groups.sort((a, b) => Date.parse(b.comments.at(-1).at) - Date.parse(a.comments.at(-1).at))
  return { documents: groups, count: groups.reduce((n, g) => n + g.comments.length, 0) }
}
