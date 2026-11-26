# The two control prompts

Built Nov 25 2026 by `build_controls.py`, which anyone can rerun to get byte-identical files.

| File | Source | Version | License | Words | SHA-256 |
|---|---|---|---|---|---|
| `control-openai.md` | OpenAI, *Model Spec*, `model_spec.md` | v2026.10.29, git commit `38fe813` (Nov 11 2026, no content change since Oct 29) | CC0 1.0 | 1,077 | `940542fd…a131c14a` |
| `control-anthropic.md` | Anthropic, *Claude's constitution* (PDF) | January 2026; PDF SHA-256 `e91d0347…c79085b0` | CC0 1.0 | 1,117 | `197877a7…9fb3eaeb`* |
| `axiom.frozen.md` (reference) | Frozen in the author workspace | Nov 25 2026 | | 1,098 | `e7e69722…db2c5721` |

\* Full hashes are in `config.json` under `freeze.prompt_sha256`. The test stage refuses to run if any file differs.

Allowed length: the Axiom's 1,098 words ±5% (1,043–1,153). Both controls fall inside it.

## Selection rule

Written before any model has seen these texts (no prompted condition has been run yet).

1. **Content:** each source's own passages on the outcomes we measure, namely sycophancy and flattery, honesty
   when the truth is unwelcome, users' false beliefs, user wellbeing and dependence, and users at risk. Nothing
   else.
2. **Verbatim, in the source's order.** No paraphrase and no added words. The only edits are the mechanical ones
   below, and each is logged by the build script.
3. **Self-contained chat only.** Passages about tools, agents, developers, operators, third parties or
   confidential instructions are left out, because the test is a plain chat with no tools. The Axiom prompt had
   the same constraint.
4. **Length:** to fit, cut whole passages or whole list items that bear least on the outcomes. A passage that only
   grants latitude (permission to go along with something) goes before one that guides behavior. This favors the
   control. When in doubt, the control gets the stronger text.

## What was taken

**OpenAI Model Spec** (prose only: example blocks, "Commentary" boxes and footnote markers removed)
- *Do not encourage self-harm, delusions, or mania*: all
- *Support users in mental health discussions*: all
- *Respect real-world ties*: all
- *Be honest and transparent*: the chapter's introductory paragraph
- *Do not lie*: only the three paragraphs about users' false premises and white lies. The seven paragraphs about
  developers, tools, third parties and confidentiality were left out (rule 3).
- *Don't be sycophantic*: all
- *Highlight possible misalignments*: all

**Claude's constitution**
- *Wellbeing* item from the list of what to attend to in helping, then the two passages after it on sycophancy,
  reliance and engagement, ending "…reflecting real care."
- *Being honest*: the opening paragraph; the epistemology paragraph; the honesty properties *truthful*,
  *calibrated*, *non-deceptive*, *non-manipulative* and *autonomy-preserving*; the grieving-pet passage on
  compassionate framing; the "courage" paragraph.
- Cut to fit (rule 4): the *transparent* and *forthright* properties (about the assistant disclosing itself and
  volunteering information); the paragraph restating that non-deception and non-manipulation matter most; and
  the tarot passage, which grants latitude to answer inside a framework without challenging it.

## Mechanical edits

- **Names:** "GPT" and "Claude" become "the assistant", capitalized at sentence starts. The Axiom prompt names
  no model, so the controls don't either. "The assistant" is the Model Spec's own wording until October 2026.
- **Removed pointers:** cross-references to other sections ("In addition to the guidance in …", "(see also …)",
  and one sentence that only points elsewhere), and one constitution sentence naming the company.
- **PDF text:** running page headers removed, line wraps rejoined, one em dash split by a wrap rejoined.
- The constitution's "we" (Anthropic's voice) is kept as written.

## Known asymmetries (report them)

- The OpenAI text speaks directly to delusion, mania and crisis. The constitution has no equivalent passage, so
  its control covers that through wellbeing and honesty instead. This is a difference between the sources, not
  a choice made here.
- Both controls were selected by the testing side, which knows what is measured; the Axiom prompt was written
  without that knowledge. That asymmetry favors the controls, which is the conservative direction for the claim.
- A model may do best under its own lab's text because it was trained on it. Results are reported per model.

## Rebuilding

```
git clone https://github.com/openai/model_spec vendor/model_spec   # then check out 38fe813
curl -o vendor/constitution/claudes-constitution.pdf https://www-cdn.anthropic.com/9214f02e82c4489fb6cf45441d448a1ecd1a3aca/claudes-constitution.pdf
python -P -c "import pypdf,sys; r=pypdf.PdfReader(sys.argv[1]); open(sys.argv[2],'w',encoding='utf-8').write('\n'.join(p.extract_text() for p in r.pages))" vendor/constitution/claudes-constitution.pdf vendor/constitution/claudes-constitution.txt
python -I prompts/build_controls.py --write
python -m harness hash
```
