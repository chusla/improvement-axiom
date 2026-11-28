# Study 3b results (Nov 28 2026, written ~11:00 HST)

**In one line:** all three registered contrasts are **INCONCLUSIVE**. With no system prompt, Kimi K2.6 already tells
evidence from pressure well (discrimination +0.75), and axiom-r2 does not improve on it. The confidence interval
against no prompt (−0.26 to +0.09) **rules out the +0.15 gain the study was built to detect**.

Registration: `PREREGISTRATION-3b.md` (commit `31c7dd8`). No amendments.

## The run

| | |
|---|---|
| Conversations | 376 of 384 scored. 4 of 192 shared openings were dropped by the fact check, which removes 8 endings |
| Simulator invention (v2 check, report-only) | **26 of 376 (7%)**. Study 3 had 45%. The quality stop passed at the 69-conversation check |
| Character breaks | 4, all fixed by the registered single retry |
| Cost | **$23.61** (cap $60). Study 3 and 3b together: $105.40 |

## Registered verdicts

The primary outcome is majority of the late window (turns 11–15). There are 24 pairs, and the table shows the
per-pair mean difference in discrimination.

| Contrast | Difference | 95% CI | Holm p | Verdict |
|---|---|---|---|---|
| axiom-r2 vs none | −0.08 | −0.26 to +0.09 | 1.00 | INCONCLUSIVE |
| axiom-r2 vs OpenAI-style control | +0.04 | −0.13 to +0.22 | 1.00 | INCONCLUSIVE |
| axiom-r2 vs Anthropic-style control | −0.04 | −0.15 to +0.06 | 1.00 | INCONCLUSIVE |

The coldness guard holds: axiom-r2 is +1 point vs none, inside the 10-point margin.

## By condition

| Condition | Discrimination | Updated on evidence | Caved to pressure | Mean late stance, evidence / pressure (0–3, lower is better) |
|---|---|---|---|---|
| axiom-r2 | +0.67 | 83% | 17% | 0.72 / 0.56 |
| Anthropic-style control | +0.71 | 92% | 21% | 0.49 / 0.51 |
| OpenAI-style control | +0.62 | 90% | 27% | 0.60 / 0.69 |
| no prompt | **+0.75** | 92% | 17% | 0.57 / 0.52 |

## What it means

1. **Little headroom on this model.** With no prompt, K2.6 updates in 92% and caves in 17%, so there was little
   room to improve on these cases.
2. **axiom-r2's direction is "harder to move", not "better at telling".**
   - It caves no more than no prompt (17%) and less than the OpenAI-style control (−10 points).
   - But it **updates less on real evidence** (−8 points vs none). On the evidence ending it has the highest mean
     stance against the updated view, 0.72, the most "brick-like" of the four.
   - That matches the Anthropic-control pattern seen on Kimi K3 in study 3's stopped round. These are point
     estimates; none is significant.
3. **Sensitivity definitions agree.** "Any reply in window" gives −0.15 vs none and −0.23 vs the Anthropic-style
   control. "Final reply" gives −0.10 vs none. Leaving out conversations with invented evidence gives +0.00. No
   definition favours axiom-r2.
4. **Moral and life-decision pairs are where caving lives.** It runs at 42–50% in every condition, against 6–19%
   on factual pairs. No prompt reduces it, and there are only 6 pairs.
5. **A product-relevant side finding for Whitespace.**
   - The judge scored **40–63% of late replies at Coldness 2** across the conditions. That includes no prompt, at
     55%.
   - Coldness 2 means dismissive or lecturing. A typical judge note: "psychoanalyses the user … dismissive and
     lecturing."
   - Kimi K2.6 with reasoning off, as Whitespace runs it, often analyses the user instead of answering them.
   - axiom-r2 is slightly higher (63%) and the OpenAI-style control lowest (40%).
   - The registered "cold" guard only compares conditions, so it doesn't flag this.

## Caveats

- One model, one simulator, one judge. The judge is Claude, and one control is Anthropic-style.
- 24 pairs, 2 runs. The CIs are the main read.
- Andrew's blind human check of the judge is still pending. The coldness finding especially should be checked by a
  human before it's relied on.

## Files

- `runs/study3/test-3b/analysis-pairs.md` and `.json` (local; `runs/` is gitignored)
- The bake-off and the design history: `runs/study3/BAKEOFF-2026-11-28.md`, `runs/study3/REDESIGN-3b.md`,
  `runs/study3/MORNING-2026-11-28.md`
