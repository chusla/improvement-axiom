---
name: side-effects-off-until-live
description: Use before setting up, copying settings into, or first deploying any environment that is not the live site, such as staging, a preview, a new Vercel project or custom environment, a Railway service, or a second branch deploy. Use it most when that environment can reach a database holding real customer data. Also use when adding or changing a scheduled job (cron, pg_cron, a scheduled workflow), an email send, a webhook, or a payment call. The rule is that anything that reaches people or money is off in code until the environment is marked live, and it is never turned on by host convention or by a copied secret.
---

# Side effects stay off until live

A build that can reach real customers will reach them if one thing goes wrong. Scheduled jobs,
emails, webhooks and payments are **off in code** until the environment is explicitly marked
live. A host's naming ("it's only staging") does not keep them off, and neither does a secret
that is missing.

## What happened

On 9 Nov 2026, MSC set up a new Vercel project for staging using a **custom environment**. Vercel
deploys a custom environment with the target `production`, and a production-target deployment
registers and **runs the crons in `vercel.json`**. The old staging was a preview deployment,
where crons never run. That is why the same code, settings and database had been harmless for days.

The settings had been copied in bulk from the old staging. They included `CRON_SECRET` and a working
email key, and staging shares the live database. Ten minutes after the build came up, the reminders
job emailed 17 real customers. The deployment was deleted 35 minutes after that. The project's own
migration doc already said to leave `CRON_SECRET` unset on anything pointed at that database until
cutover. Nobody re-read it, and the copy script copied everything.

The full report is the Bridge document "Reminder emails sent by mistake: 9 Nov 2026" on the MSC
board. The code fixes are MSC-DEV-325 (crons refuse outside live) and MSC-DEV-326 (email outside live
goes only to an allowlist).

## The rules

**The line that matters most is between staging and live.** A staging or preview build that shares
the live database looks like a test and acts like production. That is where real customers get
reached: MSC's staging on 9 Nov, and the preview builds that carry live keys. Dev data is test
accounts (Andrew, 9 Nov). Allowlist dev email too, but spend your care on anything that can reach
the live database.

1. **Every host decides for itself what "production" means.** A Vercel custom environment is
   production to Vercel, so it runs crons. A branch that isn't `main` is not automatically a preview.
   After the first build, check the deployment's target and the project's Cron Jobs page. On another
   host, check its schedules: Railway cron, Supabase `pg_cron`, scheduled GitHub workflows.
2. **Off by default in code.** Each scheduled route refuses to run unless the deployment is
   explicitly marked live: on Vercel, `VERCEL_ENV=production` *and* `VERCEL_TARGET_ENV=production`,
   or an explicit enable flag that only live has.
3. **Outside live, email goes only to an allowlist.** Any other address is held, not sent.
4. **Never bulk-copy settings between environments.** Copy from a list someone has reviewed. Add
   the secrets that switch on side effects (cron secret, email key, payment keys, webhook secrets)
   one at a time, last, as their own checklist step.
5. **Before the first deploy of anything that can read real customer data,** list every side effect
   the build can cause (crons, emails, webhooks, payments). For each one, say what stops it. Each needs
   **two independent blocks**, for example a code check *and* the secret being absent.
6. **Read the target database's runbook and migration docs** before pointing anything new at it.
7. **Turning jobs on is a launch-day step,** done on Andrew's go, with a check before and after.

## What to do

- Before the first deploy of an environment, and after any change to its settings, run the check:
  ```
  node C:/EXPO/lodestar/bin/lodestar.mjs preflight --target <repo> --env <environment> --vercel
  ```
  It lists what the code can set off on a schedule (Vercel crons, scheduled GitHub workflows,
  Railway cron, `pg_cron`) and reads the environment's setting **names**, never their values. With
  `--vercel` the names come from `vercel env ls`; `--names-file` takes a list or a .env file instead.
  When an environment's name isn't its Vercel name, say where it deploys in `lodestar.config.json`:
  `"vercel": { "target": "preview", "branch": "staging" }`. You can add `project` and `scope`, or give
  a list when the environment builds in more than one project. Each one is checked on its own.
  It refuses, with exit 1, when an environment that isn't live can reach the live database and has a
  setting that switches on a side effect. A database counts as live when a live environment uses it,
  its label in `lodestar.config.json` says PROD or LIVE, or `sideEffects.liveProjects` names it. A
  pass is not proof. Rule 5 still applies.
- Setting up an environment: work through rule 5 in writing, in the PR or ticket, before the first
  deploy. If you can't name two blocks for a side effect, it isn't ready.
- Adding a cron, an email send, a webhook or a payment call: add the live-only check in the same
  change (rules 2 and 3). A test should prove it refuses when the environment isn't live.
- Copying settings: list the names first and leave out anything that switches on a side effect
  (rule 4).
- If a side effect fires by mistake: stop the deployment first, then tell Andrew. It's an incident.

Related: **live-needs-consent-now** (never touch a live environment without the owner's go in the
moment), **gate-at-the-api** (the same idea for reads: the check lives on the server).
