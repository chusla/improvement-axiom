"""Improvement Axiom pilot harness.

Runs simulated long conversations under several system-prompt conditions, grades every assistant turn with
Spiral-Bench's rubric (loaded from a pinned local clone, never copied), and analyzes the result with a
cluster bootstrap over personas. Standard library only.
"""

__version__ = "0.1.0"
