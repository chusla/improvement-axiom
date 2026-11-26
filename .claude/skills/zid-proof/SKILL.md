---
name: zid-proof
description: Use when writing or reviewing any words a person reads — UI copy, button labels, tab names, empty states, onboarding, emails, a chit's plain sentence or options, a station callback. Zid-proof is the WORDS test: a distracted stranger reads once, fast, cold, and still knows what this is, what tapping does, and where it goes. Pairs with kelly-proof, which is the composition test.
---

# Zid-proof — the words test

**Zid-proof** copy survives Zid: a real tester who reads the way most people do — skimming,
non-technical, no patience for insider vocabulary. Named after his review rounds on Whitespace
(Aug 2026), where labels like "state" and "World" proved skim-lossy and a whole flow read as dense.

## The test

A distracted stranger reads the words **once, fast, cold**. Do they know:

1. **what this is,**
2. **what tapping it does,**
3. **where it takes them?**

If any answer needs the product's internal doctrine, it fails.

## Rules

- **Say the plain noun, not the internal one.** Whitespace says "meditation", never "session" or
  "practice", wherever a not-yet-committed person reads. Internal nouns stay internal.
- **No metaphor before value.** "Four Rooms" failed; "four tabs" passed. Poetry is earned once the
  reader is inside and invested.
- **A control names its destination or its effect.** "Make this a goal ›", "See plans ›". Never a
  clever verb, a mystery icon, or "Get started".
- **Specific beats vague.** "Two-minute resets", not "quick resets". An example goal carries a
  behaviour, a number and a timeframe.
- **One idea per screen.** If it needs a second read, cut it.
- **Plain beats poetic on a tie**, before commitment.

## In Lodestar

Everything a person reads from Lodestar is held to this, not only product copy:

- **A chit's plain sentence (`eli5`)** — two sentences a non-technical person reads once. No file
  paths, ticket numbers or jargon; the anchors carry those.
- **A chit's options** — each label says what happens, and its risk is quoted, never paraphrased
  ("11 people get an email tonight", not "several").
- **A station callback** — eight words or fewer, and it says what happened, not what was run.
- **A reply to a client** — their words back to them, then the plain answer.

It is not the same test as [kelly-proof](../kelly-proof/SKILL.md). A page can have perfect words and
still fail on composition, and the reverse. Ship things that pass both.

**Provenance:** Zid's review rounds, whitespace-native, Aug 2026 (`docs/onboarding-welcome-v2.md`,
"The zid-proof rule"). The "personal session" line that broke it on Aug 14 2026 is the worked
example of an internal noun leaking out.
