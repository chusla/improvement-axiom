---
title: Resonance Alignment Framework
emoji: "\U0001F300"
colorFrom: blue
colorTo: purple
sdk: gradio
app_file: app.py
python_version: "3.10"
sdk_version: "4.0.0"
suggested_hardware: cpu-basic
tags:
  - alignment
  - ai-safety
  - resonance
  - framework
---

# Resonance-Based Alignment Framework

An AI alignment system grounded in natural law observation rather than rigid moral taxonomies. Uses a quality-intention matrix and Ouroboros cycle principles to classify and guide human-AI interactions toward high-quality creative outcomes.

## Core Idea

Actions are mapped onto a 2x2 matrix:

|                  | Consumptive                | Creative                        |
|------------------|----------------------------|---------------------------------|
| **High Quality** | Hedonism (WALL-E)          | **Optimal -- "Better"** (target)|
| **Low Quality**  | Junk Food                  | Slop                            |

The framework measures **resonance** (subjective experience quality), classifies **intention** (creative vs. consumptive), and validates results against wireheading, classification drift, and adversarial exploitation.

## Quick Start

```bash
# Clone
git clone https://github.com/chusla/improvement-axiom.git
cd improvement-axiom

# Install
pip install -e ".[dev]"

# Run the demo UI
python app.py

# Run tests
pytest
```

## Project Structure

```
├── app.py                          # HuggingFace Spaces / demo entry point
├── src/resonance_alignment/        # Core package
│   ├── core/                       # ResonanceTracker, IntentionClassifier, etc.
│   ├── safety/                     # OuroborosAnchor, SafetyConstraints, etc.
│   ├── explainability/             # ExplainableResonance
│   ├── ui/                         # Gradio interface
│   └── system.py                   # Orchestrator
├── tests/                          # Test suite
├── docs/                           # Documentation
└── resonance-alignment-framework/  # Original SKILL.md specification
```

## Components

- **ResonanceTracker** - Measures and predicts resonance from user experiences
- **IntentionClassifier** - Classifies actions as creative, consumptive, or mixed
- **QualityAssessor** - Multi-dimensional quality scoring
- **ResonanceValidator** - Anti-wireheading validation
- **OuroborosAnchor** - Ground truth anchors preventing classification drift
- **SafetyConstraints** - Hard safety limits
- **ExplainableResonance** - Transparency layer for recommendations

## Status

**v0.3.0** -- Five independent defence layers implemented, 119 tests passing. Quality and resonance measurement are evidence-based (signal depth over breadth). Internet access layer enables artifact verification and evidence-based extrapolation. See [`docs/skill-analysis.md`](docs/skill-analysis.md) for a detailed analysis.

## License

MIT - See [LICENSE](LICENSE) for details.
