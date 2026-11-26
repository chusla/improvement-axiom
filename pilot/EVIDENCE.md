# Where current models still fail (evidence gathered Nov 25 2026)

Figures marked † came partly from model-extracted summaries of the papers' later sections. **Check every number
against the PDF before quoting it in an application.**

## 1. Simple delusion confirmation: frontier closed models mostly pass

**Lost in Delusion** (arXiv 2606.00975, May 2026). 30 personas built from 40 real case reports, 16 turns.
- Share of turns confirming a delusion: Claude Haiku 4.5 and GPT-5.5 **under 5%**. Llama-3.3-70B 41%. The
  7–30B open models 53–61%.†
- Delusional framing suppresses safety interventions by up to 4.5x (abstract).
- An "assess, then guide" system prompt significantly cut confirmation in open models (OR 0.40).† A plain
  safety prompt raised interventions but did not significantly cut confirmation.†

→ A closed frontier model on simple delusion scenarios is at ceiling. Andrew's concern is correct here.

## 2. Sustained pressure: frontier models still collapse

**SPINE** (arXiv 2609.09090, Oct 2026). Adaptive pressure over 25 turns on a factual position
(false-presupposition task):

| Model | Collapsed by turn 5 | by turn 25 |
|---|---|---|
| Claude Sonnet 5 | 42% | 74% |
| GPT-5.6 Terra | 25% | 65% |
| Gemini 3.1 Pro | 51% | 97% |
| DeepSeek V4 Pro (open-weight) | 50% | 92% |

- Collapse rises at every checkpoint, with no plateau reported.
- Emotional appeals (pity, anger) are the strongest lever.†
- In 50–89% of collapse turns, the model's own reasoning still held the correct answer when it gave in
  (abstract): it knows, and yields anyway.
- No mitigation prompt was tested.

## 3. The trade-off: less sycophancy costs warmth

**FIGS** (arXiv 2609.39863, Sep 2026). 500 scenarios, 10 turns. Two axes: sycophancy, and *calibrated
validation* (does the reply still engage with what the person shared?).

| Model | Sycophancy fail, no prompt | with a "factual" prompt | Coldness fail, no prompt | with "factual" prompt |
|---|---|---|---|---|
| Claude Fable 5.1 | 49.2% | 7.3% | 1.8% | 12.8% |
| Kimi K3 | 59.7% | 22.3% | 4.5% | 9.1% |
| GPT-5.6-Sol | 53.8% | 7.2% | 0.9% | 25.5% |
| Gemini 3.8 Flash | 64.4% | 7.4% | 5.5% | 41.8% |
| GPT-6-Astra | 27.4% | 3.1% | 0.9% | 15.5% |

- 94% of failures come after the first reply.†
- A plain "be factual, hold your position" prompt cuts sycophancy for every model but makes most of them colder.
- The authors' tuned "optimal" prompt avoids the trade-off on four models, but they tuned it on their own rubric.

→ This is the Axiom's exact claim ("a doctor, not a priest"; "add, don't grade"): **less sycophancy without
getting colder.** FIGS supplies the measure and the comparison arms.

## 4. Real transcripts: long context still erodes behavior

**DelusionEval** (arXiv 2608.05004, Aug 2026). Replays of real spiral transcripts from 18 users.
- GPT-5.4, the best performer, is still flagged on metaphysical themes 39.5% and romantic interest 17%.†
- Claude Opus 4.7 relationship prevalence 27%.†
- Each extra 100 messages of history raises delusional behavior by about 4 points.
- Bigger and newer is not reliably better: Qwen3.5-397B did worse than Qwen3.5-9B.
- Failing to discourage self-harm rose from 30.0% to 41.1% with 350 more messages of history (abstract).

## 5. Not found

- **Claude Fable 5.2's own numbers.** The system card PDF was too large to fetch. Commentary says the card
  reports gains on sycophancy, and that Fable 5.2 holds beliefs under pressure at "the standard good rate".
  No documented Fable 5.2 failure was found.
- **The live Spiral-Bench leaderboard** (the table loads by script).

## Sources

- https://arxiv.org/abs/2606.00975 Lost in Delusion
- https://arxiv.org/abs/2609.09090 SPINE
- https://arxiv.org/abs/2609.39863 FIGS
- https://arxiv.org/abs/2608.05004 DelusionEval
- https://www.anthropic.com/system-cards and https://thezvi.substack.com/p/fable-and-mythos-52-the-system-card
