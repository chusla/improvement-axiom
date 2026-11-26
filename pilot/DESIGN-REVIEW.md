# Design review: will this pilot give a clear answer?

Status: proposal for Andrew, Nov 25 2026. Nothing here is frozen. Items marked **DECIDE** need his call before
pre-registration.

The original plan (4 models, 3 conditions, 20 personas, 2 runs, 480 conversations) is sound in its rigor steps.
As sized and specified, though, it has five ways to end in "we can't tell". Each is listed with its fix.

## 1. Ceiling risk: recent models may not fail enough to show a difference

If the newest models already score near-perfect on the test personas with no system prompt, there is no room for
any prompt to help, and the result is an uninformative null.

**Fix: a screening stage before pre-registration of the test set.**
- Build a pool of about 40–50 candidate personas (see `personas/README.md`).
- Run them with **no system prompt only**, on the 2 newest models, 1 run each.
- Keep the personas where the baseline fails at a meaningful rate, by a rule written down before screening
  (for example: mean risky score in turns 16–20 above a fixed threshold on at least one model).
- The test then uses **fresh runs for all three conditions**. Screening transcripts are never reused as test data,
  so selecting on the baseline doesn't bias the comparison.
- Screening also yields the variance estimate that the sample-size calculation needs (item 3).

Screening touches neither the Axiom prompt nor the control, so it can't leak tuning into the test.

**Decided (Andrew, Nov 25): core models only.** Claude and GPT (the labs whose specs are the controls), plus Kimi
(open-weight). No other model is added unless screening shows the core leaves no room to measure an effect.

## 2. Control strength: a weak control makes a win meaningless

"An excerpt of a published spec, length-matched" leaves the excerpt open. If it is about formatting or tool use,
the Axiom beats a prompt that never addressed the behavior, and a reviewer will say any on-topic prompt would have.

**Fix: use the strongest fair control.** Take the published spec's own passages on sycophancy, honesty and
at-risk users, trimmed to the Axiom prompt's word count (±5%). Beating that is a real finding. Tying with it is
also a clear finding.

**Decided (Andrew, Nov 25):** get the strongest controls first. Candidates and a selection rule are in
`prompts/CONTROL-CANDIDATES.md`.

**Deferred: add a fourth condition?** A one-paragraph direct instruction ("don't flatter, don't affirm false
beliefs, …"). It answers "does a framework beat simply telling the model?". It adds 33% to the cost. Recommended
as a secondary comparison if the budget allows; otherwise named as a limitation.

**Related rule for the Axiom prompt:** it must state the Axiom's principles, not the rubric's vocabulary. If the
frozen text says "avoid sycophancy and delusion reinforcement", the pilot tests a targeted instruction, not the
Axiom. The candidate in `prompts/axiom-neutral.candidate.md` follows this rule.

## 3. Power: 20 personas can only detect a large effect

The persona is the unit that generalizes. Runs and models within a persona are correlated and add less.

| Test personas | Smallest paired effect detectable (80% power, two-sided α = .05) |
|---|---|
| 20 | d ≈ 0.66 (large) |
| 30 | d ≈ 0.53 |
| 40 | d ≈ 0.45 |
| 60 | d ≈ 0.37 |

These are textbook paired-t approximations that ignore the gain from 4 models and 2 runs per persona; the real
figure comes from the screening variance.

**Fix:**
- Prefer more personas over more runs per persona. 30–40 personas × 2 runs beats 20 × 3.
- Set the final count from the screening variance, before pre-registering.
- Analyze with a cluster bootstrap over personas (or a mixed model with persona and model as random effects), so
  the 480+ conversations aren't treated as independent.

## 4. No decision rule: "not significant" is not "no effect"

Without a threshold set in advance, a wide confidence interval can be read either way.

**Fix: pre-register a smallest effect of interest (SESOI) and three named outcomes.**

| Outcome | Rule (95% CI of Axiom − control on the primary outcome) | Reading |
|---|---|---|
| Supported | whole interval below 0 (less risky behavior) | the Axiom beats the control |
| Refuted at this size | whole interval inside ±SESOI | no effect large enough to matter |
| Inconclusive | anything else | reported as such; the sample was too small |

The sample size is chosen so "inconclusive" is unlikely if the true effect is either zero or at least the SESOI.
**DECIDE:** the SESOI. A defensible default is a fixed fraction of the baseline-to-control gap seen in screening;
Andrew sets it with the hypotheses.

## 5. Outcome definition: "the score at turn 20" is one noisy turn

**Fix:**
- **Primary:** mean per-turn risky score (sycophancy + delusion reinforcement, intensity-weighted, Spiral-Bench
  rubric) over **turns 16–20**, Axiom vs control, pooled across models.
- **Key secondary (the drift claim):** late window (16–20) minus early window (1–5), per condition. This is the
  test of "the Axiom holds over a long conversation where a spec fades".
- Other secondaries, Holm-corrected: Axiom vs none; per-model effects; protective behaviors; warmth.

**Decided (Andrew, Nov 25):** windows, not single turns. A specific turn is arbitrary.

## 6. Smaller threats, each with a guard

| Threat | Guard |
|---|---|
| The Axiom "wins" by turning cold or preachy | Add 8–10 **benign personas** (unusual but sound ideas, ordinary grief, real expertise). Report pushback and unwarranted-referral rates on them. XSTest stays as the single-turn over-refusal check. |
| Judge favors its own family | Two judges from different labs, neither grading its own lab's model where avoidable. Report judge agreement, plus Andrew's blind human scores on ~30 conversations (Cohen's kappa). |
| Judge can guess the condition from style | Can't be removed. Stated as a limitation; the human blind sample measures it. |
| Pooled result hides "helps weak models only" | Per-model estimates pre-registered as secondary. |
| User simulator varies between runs | Scripted opening turns per persona; same simulator model and settings in every condition; runs paired by persona. |
| Author tests his own framework | Pre-registration commit before any test run, frozen prompts with hashes, every transcript published, nulls reported. |
| 20 turns too short for the newest models to drift | Screening shows this. If so: extend all conversations to 30 turns, or run a 40-turn subset as exploratory. |

## 7. What Spiral-Bench does and doesn't give us (checked Nov 25)

- README says MIT. **The LICENSE file itself could not be fetched (404); confirm in the repo before forking.**
- The evaluated model gets **no system prompt** as shipped: `evaluated_system_prompt = ""` is hard-coded in
  `main.py` and unused in `conversation_runner.py`. A small patch is needed to pass one per condition.
- The judge sees only transcript chunks and the rubric, never the condition. Blinding holds by construction.
- Rubric includes sycophancy, delusion-reinforcement, escalation, pushback, de-escalation, help-referral
  (warranted and unwarranted) and benign warmth.
- It calls OpenAI-compatible endpoints and Anthropic natively. **One OpenRouter key could cover every model**,
  which shortens the key list; native keys allow prompt caching and exact version pins. **DECIDE.**
- Its public leaderboard personas may be in newer models' training data. Our test personas should be new.

## 8. Schedule against the clock (Thanksgiving is Thursday)

| When | Step | Needs |
|---|---|---|
| Wed | Patch harness; write persona pool; Andrew approves Axiom text and control | keys for screening |
| Wed night / Thu | Screening run (baseline only); variance and sample size | about $40–80 |
| Fri morning | Andrew writes hypotheses and SESOI; pre-registration committed and pushed; prompts frozen | Andrew |
| Fri | Test run | most of the budget |
| Sat | Blind human scoring (30), analysis, one-page write-up, Andrew's framing | Andrew, ~2 hours |

If the test run slips past Saturday, the application can still link the pre-registration and the screening
results honestly. A rushed, unregistered run would be worth less than that.

## 9. Cost effect of these changes

Screening adds about 80–100 conversations. Moving from 20 to 30 personas takes the test from 480 to 720
conversations (4 models) or 540 (3 models). Rough total: $450–1,000, against $300–700 originally. Cutting to 3
models keeps it near the original budget with more power than the original design.
