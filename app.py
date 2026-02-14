"""HuggingFace Spaces entry point for the Resonance Alignment Framework."""

import sys
from pathlib import Path

# Ensure the src directory is on the path so the package is importable
# without requiring pip install (needed for HuggingFace Spaces).
sys.path.insert(0, str(Path(__file__).parent / "src"))

from resonance_alignment.ui.gradio_interface import create_interface

if __name__ == "__main__":
    demo = create_interface()
    demo.launch()
