# Improvement Axiom pilot

**Question.** Does the Improvement Axiom, used as a model's instructions, reduce sycophancy and delusion
reinforcement late in long conversations, compared with length-matched excerpts of published model specs, and
without making the model colder toward people who aren't at risk?

**Status (Nov 25 2026):** harness built and tested offline. No real model has been called. Nothing is frozen or
registered.

| File | What it is |
|---|---|
| `DESIGN-REVIEW.md` | Where the first plan could end in "can't tell", the fixes, and Andrew's decisions so far. |
| `PREREGISTRATION.md` | Skeleton. Becomes the registration once complete and committed before any test run. |
| `config.json` | Models, conditions, stages, analysis settings. `FILL_ME` marks what is still open. |
| `prompts/` | Candidate neutral Axiom text, control candidates and the rule for building them. |
| `personas/` | Stress-case design; `practice/` has 3 examples, `pool/`, `test/`, `benign/` are still empty. |
| `simulator/base.md` | Instructions for the simulated user (draft, for Andrew's review). |
| `harness/` | The code. Python standard library only; nothing to install. |

**Decisions so far:** windows, not single turns; core models only (Claude, GPT, Kimi); controls from OpenAI's
Model Spec and Anthropic's constitution only, with the primary chosen on practice personas.

## Stages

1. **Practice.** Any condition, practice personas only. Tune the Axiom text; run the control bake-off.
2. **Screen.** No-prompt baseline only, on the pool. Keep the personas that still cause failures; measure
   variance; set the sample size.
3. **Register.** Hypotheses, smallest effect of interest, frozen prompts with hashes, pinned models. Commit, push.
4. **Test.** All conditions, fresh runs, test + benign personas.
5. **Grade and analyze.** Two blind judges, Andrew's blind sample, the registered analysis.
6. **Publish.** Code, prompts, every transcript, settings, dates, costs, and the result whichever way it falls.

## Running it

From `pilot/`. Keys are read from environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`OPENROUTER_API_KEY`) and never written anywhere.

One-time: the rubric is read from a pinned Spiral-Bench clone, which is gitignored:

```
git clone https://github.com/sam-paech/spiral-bench vendor/spiral-bench
git -C vendor/spiral-bench checkout 35411a02d39410cfb8b722a965940784a81cee57
```

```
python -m harness validate                      # lists every blocker; READY when clear
python -m harness run --stage practice --mock   # offline dry run, no API calls
python -m unittest discover -s harness/tests -t .

python -m harness run --stage practice --go     # real run; --go is required to spend money
python -m harness judge --stage practice --go
python -m harness status --stage practice       # progress, errors, cost so far
python -m harness analyze --stage practice

python -m harness run --stage screening --go
python -m harness judge --stage screening --go
python -m harness screen-report --stage screening

python -m harness hash                          # SHA-256 of every prompt, for the freeze
python -m harness blind-sample --stage test --n 30
```

Runs are resumable: rerunning a command picks up where it stopped, per message and per judged turn.

## Rigor guards in the code

- Screening runs the `none` condition only, and refuses until its keep-threshold is set in the config.
- Outside the test stage, prompted conditions only run on practice personas.
- The test stage refuses to run unless every prompt matches its frozen SHA-256 and the registration commit
  holds a completed `PREREGISTRATION.md`.
- The judge prompt is built from the transcript alone: never the condition, system prompt or model name.
- Every conversation records the pinned model id, the id the API actually served, the serving host, token
  usage and timestamps. Every run records the repo commit and prompt hashes.

## Still open before a real run

- Exact model ids (Claude, GPT, Kimi, simulator, two judges) and Kimi's pinned OpenRouter host.
- API keys in the environment.
- `prompts/control-openai.md` and `prompts/control-anthropic.md` (need the Axiom text to settle first).
- Andrew's OK on the Axiom candidate and the simulator instructions.
- The persona pool (about 45), test set rule, and benign set.
- Spiral-Bench LICENSE (README says MIT; no LICENSE file in the repo).
