# Control candidates

Checked Nov 25 2026 from search results. Each license and the exact text must be confirmed from the primary
source before anything is frozen.

## What we can use

| Source | Latest found | License | Covers our outcomes? | Form |
|---|---|---|---|---|
| **OpenAI Model Spec** | page dated 2026-10-29, whose banner says a newer version exists; **get the newest from github.com/openai/model_spec** | CC0 1.0 | Yes, directly: "Don't be sycophantic"; recognize signs of delusion or mania; "affirm a user's emotional experience, without affirming or escalating any ungrounded belief" | Spec written about the assistant; reads fine as instructions |
| **Claude's constitution** (Anthropic) | Jan 21 2026; no later revision found | CC0 1.0 | Yes: avoiding sycophancy as care for wellbeing; long-term flourishing; unhealthy dependence | Long essay addressed to Claude; passages need trimming |
| **Claude.ai system prompts** (Anthropic release notes) | entries through Sonnet 5.5 (Oct 7 2026) | **not stated; confirm** | Partly; has wellbeing passages; most of the text is tools and formatting | Real deployed system prompt |
| **Grok system prompts** (xAI, GitHub) | live repo | AGPL-3.0 (usable; that file would carry AGPL in our repo) | Weakly; little on sycophancy or delusion | Real deployed system prompt |
| Google Gemini | no published spec or prompt text found | n/a | n/a | Policy page only, not usable as text |

**Decided (Andrew, Nov 25):** controls come from OpenAI and Anthropic only. No open-weight lab (Moonshot,
DeepSeek, Qwen, GLM) publishes a behavior spec found in search, so open models are evaluated, not used as controls.

## Recommendation

**Two controls, not one, chosen fairly.**

1. Build two length-matched controls (±5% of the frozen Axiom word count), each the source's own passages on
   sycophancy, honesty, delusion and wellbeing, verbatim:
   - `control-openai.md` from the newest Model Spec;
   - `control-anthropic.md` from Claude's constitution.
   Both are CC0, both are from the labs whose models we test, and both target the exact behaviors we measure.
2. **Pick the primary control before registration, on practice personas only.** Run both on the practice set;
   the one with the lower risky score becomes the primary control and the other is a secondary comparison.
   The rule is written down before that run. This gives the Axiom the hardest fair opponent without touching
   test data.
3. Report per-model results. A model may do best under its own lab's spec, since it was trained on it. That is a
   real effect worth showing, not noise.

Cost: two controls instead of one adds a condition (about +25–33%). If the budget can't carry it, run both on
practice personas only, and take only the winner into the test.

Left out:
- Claude.ai system prompts, until the license is confirmed. They are mostly tool and formatting text, so a
  length-matched excerpt would be the wellbeing section, which overlaps the constitution.
- Grok prompts: little on our outcomes, so they would be a weak control.

## Sources

- https://github.com/openai/model_spec
- https://model-spec.openai.com/2026-10-29.html
- https://www-cdn.anthropic.com/9214f02e82c4489fb6cf45441d448a1ecd1a3aca/claudes-constitution.pdf
- https://platform.claude.com/docs/en/release-notes/system-prompts.md
- https://github.com/xai-org/grok-prompts
- https://gemini.google/approach/
