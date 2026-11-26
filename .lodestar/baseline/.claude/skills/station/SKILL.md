---
name: station
description: Work one project as a station on the line — beat on the Bridge so The Pass can see you, read the station brief it hands you, pick up what Andrew has fired to you, answer him on tickets, and call back WALKING / HANDS / REPLY. Use when asked to "work the station", "join the line", "start the station loop", or when fired by a station Routine. One thread per project; the Pass quarterbacks.
---

# The station

You are one station on the line: one Claude Code thread working one project. Andrew runs every
station from The Pass and isn't reading this thread.

**This file is only the bootstrap.** How to work a station (tickets, calls, replies, plain-words
explainers) lives in the **station brief** on the Bridge. The Bridge hands it to you, filled in
with who you are. When Andrew changes how stations work, he publishes a new brief, and your next
beat tells you to read it. Nobody has to paste you a prompt.

## Start

1. **Your key** is `station.key` in `lodestar.config.json`. If it's missing, you aren't a station:
   say so and stop.
2. **Beat:**
   ```bash
   node scripts/beat.mjs beat --station <key>
   ```
   - If this fails, stop and say so. A station that can't beat shows as quiet, and Andrew goes
     looking for it.
   - Missing credentials are named in the error. **Never ask for a password or key, and never
     write one anywhere.** Filling them in is Andrew's job.
3. **Read the output.** It has three parts:
   - `you`: your key, **your prefix** (use it on every ref, e.g. `NU-12`), and where your tickets
     live. Trust these values over anything you remember. `you: null` means stop and tell Andrew.
   - `brief.do`: if it says **READ THE BRIEF FIRST**, run
     `node scripts/beat.mjs brief --station <key>`, read all of it, and work from it.
   - `kit.do`: whether your scripts are older than the brief expects. The brief says what to do.
4. **Follow the brief.** It holds the loop, the ticket rules and the "never" list.

## Every tick

Beat first, and do what `brief.do` says before anything else. Then follow the brief. Beat even
when nothing happened: a station that stops beating looks exactly like one that died.

If no brief has been published yet, beat, run `fires` and `calls`, call back with `say`, and keep
beating. Never act on a ticket Andrew hasn't fired.

**Roll call.** A call whose `ref` starts with `roll:` is the expeditor calling the whole line. It
is **one tick, not a loop**, and it usually reaches you as a direct message from HQ rather than on a
timer. Do exactly this and stop: sync (`lodestar update` from HQ's checkout if this repo has the
CLI, else `git pull`), `node scripts/beat.mjs beat --station <key>`, then
`node scripts/beat.mjs roll --station <key> --note "<one line: what you are on, what is waiting on Andrew>"`.
That posts your report (kit, branch@commit, open, fired, your line) as a REPLY to the call and marks
it heard; The Pass shows who is back. Do not start or restart `/station` because of a roll call —
whether your loop runs is Andrew's separate decision.

**The watch.** On each tick, if the watch isn't running, arm it with the Monitor tool:
`node scripts/beat.mjs watch --station <key>`. It checks your line every two minutes and prints one
line per new call, and each line wakes you mid-work. For each one, do the calls part of a tick:
`calls`, act, `heard`. While nothing comes it costs nothing. Monitor ends it after a while; the next
tick arms it again. Without it, a client's comment waits for your next tick, 20 to 40 minutes (MSC,
2026-11-09). If your session has no Monitor tool, skip this; HQ's bell still reaches you.

## Running it

Andrew starts you with a loop:

```
/loop 30m /station
```

Thirty minutes (Andrew, 2026-09-21). It was five, then ten; both were more ticks than the work needed.

The loop is a scheduled job inside this session. A job can stay listed in `CronList` and still stop
firing, so a listed job proves nothing. At the start of each tick, check your own `last_seen_at`
with `node scripts/beat.mjs line`. If it's more than **75 minutes** old, the loop stalled: replace
the `/station` job with a fresh one. Not thirty: on a thirty-minute loop a thirty-minute-old beat is
normal, and a threshold equal to the interval replaces a healthy loop on every tick. Not sixty
either: that's exactly two beats with no room for a slow one, and the timer only fires while the
session is idle, so one long piece of work pushes the next beat late (MSC). Seventy-five is two and
a half beats, which allows for that and still acts before the Pass shows you quiet at ninety. When asked to restart the loop, always replace
the job.

**The job does not survive a session restart.** It belongs to the session, so a restart doesn't
pause it, it removes it; "no scheduled jobs" means dead, not idle. After any restart, create the loop
first. A station without a working loop looks exactly like a dead one.
