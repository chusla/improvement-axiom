"""Rebuild the two control prompts from the pinned public sources.

Run from pilot/:  python -I prompts/build_controls.py
Needs pilot/vendor/model_spec (git clone of github.com/openai/model_spec at the commit below) and
pilot/vendor/constitution/claudes-constitution.txt (text of the Jan 2026 PDF, extracted with pypdf).
Every edit to the source text is one of the mechanical rules in CONTROLS.md; nothing is paraphrased.
"""
import re
import subprocess
import sys
from pathlib import Path

PILOT = Path(__file__).resolve().parent.parent
SPEC_DIR = PILOT / "vendor" / "model_spec"
SPEC_COMMIT = "38fe813406f7bdcbee07b18a058e90ec09ae117a"  # v2026.10.29, latest commit Nov 11 2026
CONST_TXT = PILOT / "vendor" / "constitution" / "claudes-constitution.txt"
TARGET = 1098                      # words in the frozen Axiom prompt
LO, HI = round(TARGET * 0.95), round(TARGET * 1.05)


def words(t: str) -> int:
    return len(t.split())


# ---------------------------------------------------------------- OpenAI Model Spec
def spec_section(spec: str, anchor: str, own_text_only: bool = True) -> str:
    m = re.search(r"^(#{1,4}) .+? \{#" + anchor + r"[ }]", spec, re.M)
    start = spec.index("\n", m.start()) + 1
    nxt = re.search(r"^#{1,4} ", spec[start:], re.M)          # next heading of any level
    body = spec[start:start + nxt.start()] if (own_text_only and nxt) else spec[start:]
    body = re.sub(r"~~~.*?~~~", "", body, flags=re.S)                         # example blocks
    body = re.sub(r"^\*\*Example\*\*:.*$", "", body, flags=re.M)               # example captions
    body = re.sub(r'^!!! meta "Commentary"\n(?:    .*\n?)+', "", body, flags=re.M)  # commentary boxes
    body = re.sub(r"\[\^[^\]]+\]", "", body)                                    # footnote markers
    body = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body)                        # links -> text
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    return paras


def openai_control() -> tuple[str, list]:
    head = subprocess.run(["git", "-C", str(SPEC_DIR), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if head != SPEC_COMMIT:
        sys.exit(f"model_spec clone is at {head}, expected {SPEC_COMMIT}")
    spec = (SPEC_DIR / "model_spec.md").read_text(encoding="utf-8")
    log = []
    picks = [  # (anchor, paragraph indexes to keep or None for all), in the spec's own order
        ("do_not_encourage_self_harm", None),
        ("support_mental_health", None),
        ("respect_real_world_ties", None),
        ("seek_truth", None),                 # the honesty chapter's introduction
        ("do_not_lie", "false_premises"),     # only the paragraphs about users' false premises and white lies
        ("avoid_sycophancy", None),
        ("highlight_misalignments", None),
    ]
    out = []
    for anchor, keep in picks:
        paras = spec_section(spec, anchor)
        if keep == "false_premises":
            idx = [i for i, p in enumerate(paras) if p.startswith(("When a user's request includes false",
                                                                   "This framing should be calibrated",
                                                                   "GPT may also follow norms of politeness"))]
            dropped = [i for i in range(len(paras)) if i not in idx]
            log.append(f"{anchor}: kept paragraphs {idx}, dropped {dropped} (developer, tool, third-party and "
                       f"confidentiality rules that do not apply to a self-contained chat)")
            paras = [paras[i] for i in idx]
        else:
            log.append(f"{anchor}: all {len(paras)} prose paragraphs")
        out.extend(paras)
    text = "\n\n".join(out)
    # Mechanical edits, each logged.
    edits = [
        (r"In addition to the guidance in \?, ", "", "dropped a cross-reference fragment to another section"),
        (r"This principle builds on the metaphor of the \"conscientious employee\" discussed in \? and the principles in \?\. ",
         "", "dropped a sentence that only points to other sections"),
        (r" \(see also \?\)", "", "dropped a cross-reference"),
        (r"\bGPT[’']s\b", "the assistant’s", "name: GPT's -> the assistant's"),
        (r"\bGPT\b", "the assistant", "name: GPT -> the assistant (the spec's own wording before Oct 2026)"),
        (r"(^|(?<=[.!?] ))the assistant", lambda m: m.group(1) + "The assistant", "capitalized at sentence starts"),
    ]
    for pat, rep, why in edits:
        text, n = re.subn(pat, rep, text, flags=re.M)
        log.append(f"edit x{n}: {why}")
    return text, log


# ---------------------------------------------------------------- Claude's constitution
def constitution_paragraphs() -> list[str]:
    raw = CONST_TXT.read_text(encoding="utf-8")
    raw = re.sub(r"^Claude’s Constitution—January 2026\s*\n\d+\s*\n", "", raw, flags=re.M)  # running headers
    return raw


def between(raw: str, start: str, end: str) -> str:
    flat = re.sub(r"\s+", " ", raw)                      # the PDF text has no paragraph marks; unwrap it
    i = flat.index(start)
    j = flat.index(end, i) + len(end)
    seg = flat[i:j].strip()
    return re.sub(r" (?=• )", "\n\n", seg)               # list items on their own lines


def anthropic_control() -> tuple[str, list]:
    raw = constitution_paragraphs()
    spans = [  # (first words, last words) of each verbatim passage, in the document's order
        ("• Wellbeing: In interactions with users", "without being paternalistic or dishonest."),
        ("Concern for user wellbeing means", "other beneficial sources of support in their life."),
        ("It is easy to create a technology", "supporting a person’s growth as reflecting real care."),
        ("Honesty is a core aspect of our vision", "while remaining honest in the sense we have in mind)."),
        ("Honesty also has a role in Claude’s epistemology.", "more or less confidence than it actually has."),
        ("• Non-deceptive: Claude never tries", "conclusions through their own reasoning process."),
        ("There will nonetheless be cases where", "frame them compassionately."),
        ("Sometimes being honest requires courage.", "constraints of honesty rather than sacrificing them."),
    ]
    log, out = [], []
    for s, e in spans:
        seg = between(raw, s, e)
        out.append(seg)
        log.append(f"passage '{s[:40]}…' → '…{e[-40:]}' ({words(seg)} words)")
    text = "\n\n".join(out)
    edits = [
        (r"—\s+", "—", "rejoined an em dash split by a PDF line break"),
        (r" Anthropic doesn’t want Claude to be like this\.", "", "dropped a sentence naming the company"),
        (r"\bClaude’s\b", "the assistant’s", "name: Claude's -> the assistant's"),
        (r"\bClaude\b", "the assistant", "name: Claude -> the assistant"),
        (r"(^|(?<=[.!?] )|(?<=[a-z]: ))the assistant", lambda m: m.group(1) + "The assistant",
         "capitalized at sentence starts"),
        (r"^• Wellbeing: ", "", "dropped the list label on the first passage, which stands alone"),
    ]
    for pat, rep, why in edits:
        text, n = re.subn(pat, rep, text, flags=re.M)
        log.append(f"edit x{n}: {why}")
    return text, log


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, (text, log) in {"control-openai.md": openai_control(), "control-anthropic.md": anthropic_control()}.items():
        n = words(text)
        print(f"\n## {name}: {n} words (target {TARGET}, allowed {LO}-{HI}) {'OK' if LO <= n <= HI else 'OUT OF RANGE'}")
        for line in log:
            print("  -", line)
        if "--write" in sys.argv:
            (PILOT / "prompts" / name).write_text(text + "\n", encoding="utf-8", newline="\n")
