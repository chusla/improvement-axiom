# Improvement Axiom -- Framework Overview & Testing Strategy

*Last updated: 2026-02-14 · v0.3.0 · 119 tests passing*

---

## Part 1: High-Level Overview

### What is it?

The Improvement Axiom is an AI alignment framework grounded in natural law
observation rather than fixed moral templates.  Instead of asking "Is this
Christ-like?" or "Is this utilitarian?", it asks a first-principles question:

> **"Is it *Better*?"**

"Better" is defined not by a static reference figure but by **observable outcomes
over expanding time horizons**.  The framework codifies the insight that creation
and consumption are dual forces (the Ouroboros Cycle), and that the long arc of
moral weight bends toward outcomes, not labels.

### The 2×2 Matrix

|                  | Consumptive              | Creative                              |
|------------------|--------------------------|---------------------------------------|
| **High Quality** | Hedonism (WALL-E world)  | **Optimal -- "Better"** *(target)*    |
| **Low Quality**  | Junk Food                | Slop                                  |

The target is the upper-right quadrant: **high quality + creative intent**.
But the framework never *labels* an activity as inherently creative or
consumptive -- it watches the **trajectory** of what activities lead to over
time.

### Core Principles

1. **Vectors, not labels.**  Two kids playing the same video game are
   indistinguishable at t=0.  One becomes a game developer; the other doesn't.
   The framework tracks the *direction* of follow-up actions, not the activity
   itself.

2. **Observable actions only.**  Evaluation is based solely on what people do
   and what results follow -- never on identity attributes (race, gender,
   geography, religion).  Geography is considered only insofar as it modifies
   the action itself (cooking in a professional kitchen vs. at home).

3. **Signal depth over breadth.**  Five devoted local fans leaving detailed
   reviews are a stronger quality signal than 10,000 passive likes.  The
   framework deliberately resists the "big get bigger" virality trap.

4. **The long arc is the ultimate defense.**  Short-term gaming is possible.
   Sustained faking across years, across all five defence layers, is
   exponentially harder than genuine creation.

5. **Empowerment, not judgment.**  The system presents evidence-based
   hypotheses and historical patterns, but always leaves room for exceptions
   and individual choice.

### Five Independent Defence Layers

Any adversarial attack must defeat **all five simultaneously** to game the
system:

| # | Layer                      | What it checks                                        | Requires internet? |
|---|----------------------------|-------------------------------------------------------|--------------------|
| 1 | **Vector Tracking**        | Individual's follow-up actions over time               | No                 |
| 2 | **Artifact Verification**  | External evidence of creation (URLs, repos, posts)     | Yes                |
| 3 | **Temporal Evaluation**    | Outcomes across expanding time horizons                | No                 |
| 4 | **Propagation Tracking**   | Other people's engagement with artifacts               | No                 |
| 5 | **Evidence-Based Extrapolation** | Public research/history of action outcome patterns | Yes                |

When offline, Layers 2 and 5 return "unavailable" status and confidence is
reduced -- the system degrades gracefully rather than failing.

### Three Entry Points

The framework is a **decision library**, not a chatbot.  It exposes three API
methods:

```
process_experience(user_id, description, user_rating, ...)
    → AssessmentResult  (provisional at t=0, low confidence)

process_follow_up(user_id, experience_id, description, follow_up_type, ...)
    → AssessmentResult  (confidence rises with evidence)

submit_artifact(user_id, experience_id, url, user_claim, platform)
    → ArtifactVerification  (fetches + verifies external evidence)
```

An AI agent (chatbot, assistant, coach) sits in front of this library.  The
agent translates user conversation into API calls, and translates
`AssessmentResult` back into natural guidance.

### Architecture at a Glance

```
User ─────────────────────────────────────────────────────── Agent/LLM
  │                                                              │
  │  natural language                     natural language        │
  │ ◄──────────────────────────────────────────────────────────► │
  │                                                              │
  │                    ┌───────────────────┐                     │
  │                    │  system.py        │                     │
  │                    │  (orchestrator)   │                     │
  │                    └────────┬──────────┘                     │
  │                             │                                │
  │         ┌───────────────────┼───────────────────┐            │
  │         │                   │                   │            │
  │  ┌──────┴──────┐  ┌────────┴────────┐  ┌───────┴───────┐   │
  │  │   CORE      │  │    SAFETY       │  │ EXPLAINABILITY │   │
  │  │             │  │                 │  │               │   │
  │  │ VectorTrack │  │ OuroborosAnchor │  │ Explainable   │   │
  │  │ Intention   │  │ ExtValidator    │  │ Resonance     │   │
  │  │ Quality     │  │ ArtifactVerify  │  │               │   │
  │  │ Resonance   │  │ ObservablePolicy│  └───────────────┘   │
  │  │ Temporal    │  │ Constraints     │                       │
  │  │ Propagation │  │ HumanVerify     │                       │
  │  │ Extrapol.   │  └─────────────────┘                       │
  │  │ WebClient   │                                            │
  │  │ Questions   │                                            │
  │  └─────────────┘                                            │
  │                                                              │
  │                    ┌────────────────┐                        │
  │                    │   Internet     │                        │
  │                    │  (optional)    │                        │
  │                    └────────────────┘                        │
```

### Data Models

| Model                   | Purpose                                             |
|-------------------------|-----------------------------------------------------|
| `Experience`            | A single reported activity with metadata             |
| `FollowUp`             | What happened after an experience                    |
| `UserTrajectory`        | Accumulated history, vector direction, confidence    |
| `Artifact`              | User-submitted URL claiming evidence of creation     |
| `ArtifactVerification`  | Result of fetching and verifying an artifact         |
| `ExtrapolationHypothesis` | Evidence-based hypothesis about likely trajectories |
| `TrajectoryEvidence`    | Collection of hypotheses with sources                |
| `AssessmentResult`      | Full pipeline output: scores, position, recommendations, explanations |

---

## Part 2: Testing Strategy

### What exists today (Level 0)

**119 unit tests** validate internal logic: math, data flow, edge cases, and
component contracts.  These use `MockWebClient`, synthetic experiences, and
canned follow-ups.  They prove the gears mesh -- they don't prove the machine
does useful work in the real world.

```
tests/
├── test_core/
│   ├── test_quality_assessor.py        # Signal depth, recursiveness, durability, etc.
│   ├── test_resonance_tracker.py       # t=0 capping, evidence-aware measurement
│   ├── test_intention_classifier.py    # Cold start, follow-up dominance, trajectory context
│   ├── test_vector_tracker.py          # Vector compounding, diverging paths
│   ├── test_temporal_evaluator.py      # Arc trends, horizon weighting
│   ├── test_resonance_validator.py     # Anti-wireheading validation
│   ├── test_extrapolation_model.py     # Hypothesis generation, empowerment, sources
│   ├── test_web_integration.py         # Online/offline integration, graceful degradation
│   └── test_system_integration.py      # End-to-end provisional → confident flow
├── test_safety/
│   ├── test_artifact_verifier.py       # URL verification, substance checks
│   ├── test_observable_action_policy.py # Identity attribute rejection
│   ├── test_ouroboros_anchor.py         # Classification drift detection
│   └── test_constraints.py             # Hard safety limits
└── conftest.py
```

**Run them:**
```bash
pip install -e ".[dev]"
pytest -v
```

### Level 1: Scenario Harness (next to build)

Scripted multi-turn user journeys that run through the full pipeline with
**simulated time progression**.  Each scenario asserts that the framework's
vector direction, quality trajectory, and recommendations move correctly over
the arc.

#### Example Scenarios

| Scenario                  | Description                                                         | Expected arc                             |
|---------------------------|---------------------------------------------------------------------|------------------------------------------|
| **Gamer → Developer**     | Kid plays games → starts modding → publishes mod → gets downloads   | Consumptive-pending → Creative-confident |
| **Passive Consumer**      | Person binge-watches → never creates → follows up only to consume   | Consumptive, confidence rises over time  |
| **Local Craftsman**       | Plumber does excellent work → 5-star reviews → teaches apprentice   | Creative + high quality via signal depth |
| **Adversarial: Faker**    | User submits AI-generated slop as artifacts, inflates self-reports  | Initially fools system, vector stalls    |
| **Adversarial: Wireheader** | User tries to maximize resonance score via sugar-high loop        | Validator catches declining durability   |
| **Late Bloomer**          | Years of consumption → sudden creative burst → sustained creation   | Framework must not lock into early label |
| **Niche Artist**          | Tiny audience, deep engagement, no virality                         | Signal depth must score high quality     |

#### What the harness produces

- Per-scenario pass/fail against directional assertions
- A readable report showing step-by-step score evolution
- Aggregate statistics across all scenarios
- Identification of edge cases where the framework is indecisive

#### Why this matters

This is the artifact you hand to third-party researchers.  They can:
- Run the existing scenarios and verify outcomes
- Add their own adversarial scenarios
- Modify the framework and re-run to compare
- Quantify how many steps it takes for a vector to resolve

### Level 2: LLM Integration Harness

The framework is a decision library.  For it to do real work, it sits between a
user and an LLM:

```
User message
    │
    ▼
LLM parses intent ──► calls framework API ──► gets AssessmentResult
    │
    ▼
LLM shapes response using result
(coaching, questions, empowerment, artifact prompts)
```

Testing at this level requires:

1. **An agent wrapper** that maps natural language to framework API calls and
   translates `AssessmentResult` back into natural guidance.

2. **Conversational test scripts** -- multi-turn dialogues with expected
   coaching behaviors (not exact text, but directional: "should ask follow-up
   questions", "should not label activity", "should cite evidence").

3. **Human evaluation** -- real people rate whether the agent's guidance feels
   empowering vs. judgmental, and whether it correctly adapts over time.

### Level 3: Adversarial Red-Teaming

This is where independent safety researchers earn their keep.  They
deliberately try to:

| Attack                         | Target layer(s)         | What they'd try                                     |
|--------------------------------|-------------------------|------------------------------------------------------|
| **Artifact forgery**           | Layer 2 (Verification)  | Fake GitHub repos, AI-generated blog posts, purchased stars |
| **Self-report inflation**      | Layer 1 (Vector)        | Always report 10/10 resonance, claim creative follow-ups that don't exist |
| **Classification gaming**      | Layer 1 + Layer 3       | Push edge cases to flip consumptive → creative        |
| **Metric gaming**              | Layer 4 (Propagation)   | Buy engagement, create sock-puppet followers           |
| **Web poisoning**              | Layer 5 (Extrapolation) | Plant misleading research to skew hypothesis generation |
| **Long-arc circumvention**     | All layers              | Sustain a coherent fake creative persona for months    |
| **Identity leakage probing**   | Observable Action Policy | Try to get the system to use demographic data          |

**Key insight:** the five-layer independence means an attacker must game all
five *simultaneously and consistently over time*.  Each additional layer
multiplies the effort exponentially.

### Level 4: Longitudinal Studies (long-term)

The ultimate test.  Deploy the framework with real users and measure over
months/years:

- Do users in the "Optimal" quadrant report sustained wellbeing?
- Do users who start consumptive and shift creative actually produce artifacts?
- Does the "long arc" principle hold -- do early assessments converge to accurate
  long-term predictions?
- Does signal-depth scoring avoid the "big get bigger" trap?

This is out of scope for code testing, but the scenario harness (Level 1) and
conversational harness (Level 2) are designed to *simulate* these dynamics so
the framework can be stress-tested before real deployment.

---

## Part 3: Where Hugging Face Fits

Hugging Face is several things at once.  Here's what's relevant vs. not:

### Relevant to this project

| HF capability       | How we'd use it                                                      |
|----------------------|----------------------------------------------------------------------|
| **Datasets Hub**     | Publish the scenario harness test bank as a structured dataset.  Other researchers can run their own models against it and compare alignment outcomes. |
| **Spaces**           | Host an interactive demo (Gradio/Streamlit) where people can walk through the framework live -- input experiences, see assessments, submit follow-ups. |
| **`evaluate` library** | Define custom alignment metrics (vector accuracy, coaching quality, drift resistance) and publish as a reusable evaluation module. |
| **Model Cards**      | If an LLM is fine-tuned to use the framework, its Model Card would document alignment properties, test results, and known limitations. |

### Not directly relevant

| HF capability         | Why not                                                              |
|-----------------------|----------------------------------------------------------------------|
| **Model Hub**         | We're not a model -- we're a library that wraps *around* models.     |
| **Transformers lib**  | No neural network training or inference in the framework itself.     |
| **Leaderboards**      | The Open LLM Leaderboard benchmarks models, not alignment frameworks. Could be relevant later if we define a benchmark that models are scored against. |

### What HF cannot do

- **Long-term longitudinal studies** -- HF doesn't provide real users over real
  time horizons.  The "long arc" test requires actual deployment.
- **Red-teaming at scale** -- HF hosts tools, but adversarial testing requires
  skilled human researchers with adversarial intent, not just compute.

---

## Part 4: Practical Path Forward

### Immediate (build next)

1. **Scenario Harness** -- Library of scripted multi-turn user journeys with
   time simulation and directional assertions.  This is the artifact for
   third-party review.

### Short-term

2. **Agent Wrapper** -- Thin integration layer that maps LLM conversation to
   framework API calls.  Enables conversational testing.

3. **HuggingFace Space** -- Interactive demo for the research community.  Input
   an experience, see the pipeline in action, submit follow-ups.

4. **Published Dataset** -- Scenario bank on HF Datasets Hub for reproducible
   evaluation.

### Medium-term

5. **Red Team Protocol** -- Formal adversarial testing specification with
   documented attack categories, expected defences, and scoring rubric.

6. **Alignment Metrics Module** -- Custom `evaluate` metrics for measuring how
   well an LLM integrates framework guidance.

### Long-term

7. **Pilot Deployment** -- Small-scale real-user study with longitudinal
   tracking to validate the "long arc" principle empirically.

8. **Published Results** -- Peer-reviewed analysis comparing framework-guided
   agent behaviour against baseline and competing alignment approaches.

---

*This document is designed to give follow-on researchers or AI agents full
context on what the Improvement Axiom is, how it works, and what remains to
be tested.*
