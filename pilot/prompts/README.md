# Prompts

| File | State |
|---|---|
| `axiom.frozen.md` | **Frozen Nov 25 2026** in the walled-off author workspace (`axiom-prompt-studio/outputs/FREEZE.md`), copied here by Andrew, hash verified. Never edit. |
| `control-openai.md` | Built Nov 25 from the OpenAI Model Spec. See `CONTROLS.md`. |
| `control-anthropic.md` | Built Nov 25 from Claude's constitution. See `CONTROLS.md`. |
| `build_controls.py` | Rebuilds both controls byte for byte from the pinned sources. |
| `axiom-neutral.candidate.md` | **Retired.** An early draft written on the testing side, which knows the test. Not used in any condition; kept only as a record. |

All four hashes are in `config.json` under `freeze.prompt_sha256`. The test stage refuses to run if any file has
changed.

Which control is primary is decided on practice personas only, by the rule in `CONTROL-CANDIDATES.md`, written
down before that run.
