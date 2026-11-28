# Rule for lengthening the controls (study 3)

Written Nov 27, 2026 (HST) by the testing side, **after** the round-two Axiom prompt was frozen in the author
workspace (`axiom-prompt-studio/outputs/round2/FREEZE.md`, SHA-256 `ae521dd4…71d8f8e06`, 1,951 words), and
**before** the testing side has read its text. The only facts about it used here are its word count and hash,
taken from the freeze record.

The plan was to write this rule before the freeze; the freeze came first. What matters for fairness is that the
rule does not depend on the new prompt's content, and it was written without seeing it.

## Target

The round-two Axiom's 1,951 words ±5%: **1,853–2,049 words**, counted the same way as in study 1
(`len(text.split())`).

## Rule

Everything in `CONTROLS.md` (selection rule, mechanical edits, known asymmetries) still applies. To lengthen each
control from its current study 1 version:

1. **Keep every passage already in the control**, unchanged, in its place.
2. **Restore first what study 1 cut to fit**, in source order:
   - Claude's constitution: the *transparent* and *forthright* honesty properties; the paragraph restating that
     non-deception and non-manipulation matter most; the tarot passage.
   - OpenAI Model Spec: nothing was cut to fit (the left-out *Do not lie* paragraphs were excluded by rule 3,
     tools and third parties, and stay out).
3. **Then add further passages from the same source on the same outcome topics** listed in `CONTROLS.md` rule 1
   (sycophancy and flattery, honesty when the truth is unwelcome, users' false beliefs, user wellbeing and
   dependence, users at risk), verbatim and in the source's own order, until the target range is reached. Rule 3
   (self-contained chat only) still excludes passages about tools, agents, developers, operators, third parties
   or confidential instructions.
4. **If a source runs out** of such passages before reaching the target, stop and report the shortfall; do not
   add off-topic text to make up length. The comparison is then reported with the length gap stated.
5. **If adding a passage would overshoot** the range, take the next whole passage or list item that fits; if
   none fits, stop at the closest length inside or below the range and report it. As in study 1, when choosing
   between candidates, a passage that only grants latitude goes before one that guides behavior, so the control
   gets the stronger text.
6. Every passage added is listed, with its location in the source, in the study 3 version of `CONTROLS.md`, and
   `build_controls.py` is extended so the files rebuild byte for byte.
7. The study 1 control files stay as they are; study 3 gets new files (`control-openai-3.md`,
   `control-anthropic-3.md`).

## What this rule does not decide

Which conditions study 3 runs (including whether the round-one Axiom is kept), and everything else in study 3's
design, are left to its pre-registration.
