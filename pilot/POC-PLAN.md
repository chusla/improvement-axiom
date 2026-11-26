# Proof of concept for the BlueDot application

The full pilot (`DESIGN-REVIEW.md`) becomes the funded grant work. This proof of concept is what the course
application and the grant link to, so it has to be **clean** (nobody can wave it away on method) and
**compelling** (it shows something a reviewer hasn't seen). Small is fine. Sloppy or vague is not.

## What makes it compelling

1. **A current frontier model visibly fails at baseline.** Personas are screened on the newest Claude with no
   system prompt; only the ones that still produce late-turn sycophancy or delusion reinforcement are kept.
   A null on personas nobody fails is worthless.
2. **The control is Claude's own constitution.** The strongest fair opponent on a Claude model is the text
   Anthropic wrote to shape Claude, excerpted to the Axiom's length. "Beats Claude's own constitution on Claude"
   is a headline; "ties it" is still a finding.
3. **One figure that tells the story:** risky behavior by turn, three lines (no prompt, constitution, Axiom).
   Plus one side-by-side excerpt: same persona, same late turn, baseline vs Axiom.

## What makes it clean

- A short pre-registration committed before the test run (hypotheses in Andrew's words, one primary outcome,
  the decision rule). Cheap to do and rare in applications.
- Fresh runs for every condition after screening, so choosing failure-prone personas can't bias the contrast.
- Blind judging; the contamination probe's results reported; pinned model versions; every transcript published.
- **A judge from another lab** (Kimi), so it isn't only Claude grading Claude.
- Limitations stated plainly: small N, one main model, simulated users, a judge rubric from Spiral-Bench.

## Size (Max-friendly)

| Step | What | Claude (Max) | Kimi (OpenRouter) |
|---|---|---|---|
| Screen | ~15 new personas × no prompt × 1 run | 15 conversations | judge only |
| Test | ~10 kept personas × 3 conditions × 2 runs | 60 conversations | judge, and Kimi as a second model if the budget allows |
| Judging | turns 1–5 and 16–20 only | Claude judge | Kimi judge |

OpenRouter spend: about $10–25. Claude volume runs on Max over two days, pausing at limits.

## Schedule (Thanksgiving Thursday; submit Saturday)

| When | Step | Andrew |
|---|---|---|
| Wed | Probe the Max route; draft ~15 stress personas; build the constitution control | sign in; OK the Axiom text |
| Thu | Screening runs unattended | none |
| Fri morning | Pre-registration committed; test run starts | hypotheses, ~30 min |
| Fri–Sat | Judging, analysis, figure, one-page write-up | framing and limitations in his words |

If the test run slips, the application links the pre-registration and the screening results, honestly labeled.
