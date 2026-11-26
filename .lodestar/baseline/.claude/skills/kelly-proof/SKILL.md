---
name: kelly-proof
description: Use when building or reviewing how any screen LOOKS — a page, a sheet, a card, a chit, a dashboard, an email layout. Kelly-proof is the COMPOSITION test: seen for one second from across the room, is there one thing to look at, with a type scale that holds still and nothing said twice? Informative and beautiful without being loud. Pairs with zid-proof, which is the words test.
---

# Kelly-proof — the composition test

**Kelly-proof** is a screen that survives a **one-second look from across the room** by someone
who cares how it *feels*. It fails on clutter, on a type scale that wanders, on colours that all
want attention, and on two things competing to be the action.

The reference is Kelly's "Whitespace" board: earth ground, one serif line, one thin-line control,
one small tracked label, texture over flat, nearly every frame one idea under ten words.
**Quiet is not empty.** A screen can carry a lot of information and still pass, if the hierarchy
does the work instead of volume.

## The five questions

1. **One thing to look at?** One primary. A second control near the centre competes with the task.
2. **Is anything said twice?** This is usually the *cause* of a wandering type scale: the second
   copy needs a smaller treatment, and that treatment needs a label. Delete the duplicate first.
3. **How many tracked uppercase labels?** One per screen or card. Two stacked a few lines apart is
   the most reliable "this feels busy" signal found so far.
4. **Does the type sit on the ladder?** Every size is a rung, and there are few rungs (below). A
   size off the ladder is nearly always a duplicate or an afterthought in disguise.
5. **Can a number become a mark?** "0 of 5" as text costs a label, a size and a second head. A
   drawn line, dot or stone says it at a glance.

## The ladder

Each project writes its ladder down once, next to its tokens, and everything uses it. The shape:

| Rung | Role |
|---|---|
| **Label** | the one tracked uppercase kicker — nothing else is tracked |
| **Body** | meta, actions, verbs, group heads (plain case, medium weight — not tracked capitals) |
| **Row** | the serif of a list row or an option |
| **Line** | the serif sentence the screen is about |
| **Display** | a screen's own title, where it has one |

Whitespace's values (pt): label 12–13 · body 14 · row 19 · line 21–24 · display 31–33.
**Four or five distinct sizes per component.** Marks that are not text (a pause glyph, a slider's
end labels) keep their own size and say why beside it.

## Colour and type families

- **Two families at most:** a serif for what the screen is *about*, a sans or mono for everything
  that supports it. A third family is a third voice.
- **One accent, used rarely.** It marks the one thing that needs a person. Everything else is ink,
  muted ink, and the ground. A warning colour that appears on every card is no longer a warning.
- **Warmth comes from the ground, not from adding colours.** Earth, linen, sand, bark.
- **Weight and space carry hierarchy before colour and size do.**

## How to check

Count distinct sizes per component (`grep -o "font-size: [^;]*" file | sort -u`, or `fontSize: N`
in React Native), count tracked labels, count colours that aren't ground or ink. Four or fewer
sizes, one tracked label, one accent. Then ask question 2 before restyling anything.

**Provenance:** whitespace-native, Sep 2026 (`docs/design-system-v3-standards.md` §5). The Goal
step page on Sep 11 was perfectly zid-proof and failed this with eight type sizes and a sentence
printed twice. Reflect went from eight sizes to four by deleting a label row and a caption, not by
restyling. Andrew, Sep 16: "too many fonts and sizes make pages harder to read."

Related: [zid-proof](../zid-proof/SKILL.md), the words test. Ship things that pass both.
