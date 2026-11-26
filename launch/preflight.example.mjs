// Your launch's gate table. Copy this file to launch/preflight.config.mjs, then fill in your gates, ids and
// checks. The kit keeps this example current; your copy is yours and the kit never overwrites it.
//
//   node scripts/lodestar/launch-preflight.mjs --gate G2
//
// A gate is a go when nothing FAILs and every MANUAL row is signed off by the person named. Every row says when it
// runs (`gates`: 'all', a list, or { from, to }), how it's checked (a kit check spread in, your own run(kit, ctx),
// or `who` for a person), and `fix`: what to do when it fails. Write each in plain words: the output goes on the
// gate's ticket. Brief: "Launching an app".
import { checks } from '../scripts/lodestar/launch-preflight.mjs'

// Your project's ids. None of these are secrets; the preflight reads tokens from your CLI logins.
const LIVE = { projectId: 'prj_…', teamId: 'team_…' }        // Vercel project serving live
const DB = 'abcdefghijklmnopqrst'                               // Supabase ref of the live database
const HOST = 'app.example.com'                                  // the domain customers use
const BEFORE_DNS = 'https://example-live.vercel.app'            // live before the domain moves (the hidden host)
const ORDER = ['G0', 'G1', 'G2', 'D1', 'D2', 'G3', 'D3', 'G4', 'D4', 'G5'] // gates and launch-day steps, in order

export default {
  // Launch order. `mode` is what the gate expects: everything stays disarmed until it's armed on launch day.
  gates: {
    G0: { title: 'commit the date', when: 'T-9', mode: 'disarmed' },
    G1: { title: 'the evening before', when: 'T-1', mode: 'disarmed' },
    G2: { title: 'launch day, before the move', when: 'W-30', mode: 'disarmed' },
    G3: { title: 'after the final data move', when: 'after D2', mode: 'disarmed' },
    G4: { title: 'point of no return', when: 'after the smoke tests', mode: 'disarmed' },
    G5: { title: 'after launch, fix forward only', when: 'after arming', mode: 'armed' },
  },

  checks: [
    // Arming: crons and customer email off until launch day, on after.
    { id: 'live.arming', name: 'Live crons and email', gates: { from: 'G1' }, fix: 'Disarmed: remove CRON_SECRET, set CRONS_ENABLED=false (plain), EMAIL_LIVE_ENV not production, EMAIL_ALLOWLIST set. Armed: the reverse, in one checked step on Andrew\'s word.', ...checks.arming({ ...LIVE }) },
    { id: 'live.health', name: 'Live health', gates: { from: 'G1' }, fix: 'Open /api/health on live and read what it says.', ...checks.health(() => `${BEFORE_DNS}/api/health`, {}) },
    { id: 'live.crons', name: 'Cron jobs', gates: 'all', fix: 'Armed: every job in vercel.json registered and enabled on the project.', ...checks.crons({ ...LIVE }) },

    // The database.
    { id: 'db.migrations', name: 'Migrations', gates: 'all', fix: 'Apply the pending migrations to live (Andrew\'s word), then run again.', ...checks.migrations({ ref: DB }) },
    { id: 'db.pg-cron', name: 'pg_cron', gates: 'all', fix: 'Unschedule any job not listed in the table: a database cron runs whatever the app\'s switches say.', ...checks.pgCron({ ref: DB, expected: [] }) },
    { id: 'db.backups', name: 'Backups', gates: 'all', fix: 'Check the project\'s backups in Supabase; take one before going on.', ...checks.backups({ ref: DB }) },
    { id: 'auth.floors', name: 'Auth floors', gates: 'all', fix: 'Supabase -> Auth: a 6-digit code, at least 500 emails an hour, live and pre-launch hosts on the redirect list; API max_rows at least 10,000.', ...checks.authFloors({ ref: DB, otpLength: 6, minEmailRate: 500, redirects: [`https://${HOST}`, BEFORE_DNS], minMaxRows: 10000 }) },
    { id: 'db.switches-off', name: 'Switches that stay off', gates: 'all', fix: 'Turn these off until the client approves them in writing.', ...checks.switchesOff({ ref: DB, keys: ['archive_deletion_switch'] }) },
    { id: 'db.sync-lock', name: 'Old-system sync lock', gates: 'all', fix: 'Open until the final data move; closed from the point of no return.', ...checks.switchIs({ ref: DB, key: 'old_sync_closed', want: (ctx) => (ctx.atOrAfter('G4') ? 'on' : 'off') }) },
    { id: 'code.approvals', name: 'Approval constants', gates: 'all', fix: 'Leave these false until the client approves; flip them in the same PR as the approval.', ...checks.constantsFalse({ 'lib/approvals.ts': ['DELETION_EMAILS_APPROVED'] }) },
    { id: 'db.incident-leftovers', name: 'Incident leftovers', gates: 'all', fix: 'Clean up what customers can still see from the incident.', ...checks.count({ ref: DB, sql: 'select count(*) from public.messages where incident_id is not null and archived_at is null', what: 'leftover message(s)' }) },
    { id: 'assets', name: 'Email and app assets', gates: 'all', fix: 'Upload the missing files to the public bucket.', ...checks.urls({ urls: [`https://${HOST}/logo.png`] }) },
    { id: 'auth.site-url', name: 'Auth site_url', gates: 'all', fix: 'Supabase → Auth → URL configuration.', ...checks.siteUrl({ ref: DB, want: (ctx) => (ctx.atOrAfter('G4') ? `https://${HOST}` : BEFORE_DNS) }) },

    // The domain.
    { id: 'dns.host', name: `DNS for ${HOST}`, gates: 'all', fix: 'Point the record at Vercel at the switch, and lower its TTL to 600s by G1.', ...checks.dns({ host: HOST, want: (ctx) => (ctx.atOrAfter('G4') ? 'vercel' : /./), maxTtl: 600 }) },
    { id: 'tls.host', name: `Certificate for ${HOST}`, gates: 'all', fix: 'Renew or reissue the certificate.', ...checks.tls({ host: HOST }) },

    // Promises to clients about launch (tickets titled "Launch commitment [step]: …").
    { id: 'commitments', name: 'Launch commitments', gates: 'all', fix: 'Verify each open commitment with its proof, or close it saying why and who agreed.', ...checks.commitments({ station: 'xyz', order: ORDER }) },

    // What only a person can check. Name them.
    { id: 'manual.rollback', name: 'Rollback page', gates: ['G0'], who: 'Andrew', fix: 'A rollback page someone other than Andrew can follow, rehearsed at T-3.' },
    { id: 'manual.smoke', name: 'Smoke tests', gates: ['G4'], who: 'the tester', fix: 'Every smoke test on the runbook passed on live.' },
  ],
}
