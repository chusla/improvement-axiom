"""Entry point for the Improvement Axiom interactive demo.

Works on HuggingFace Spaces, local development, or any Gradio host.
If ANTHROPIC_API_KEY is set in environment or .env, the full AI agent
is used.  Otherwise, falls back to direct framework mode.
"""

import sys
from pathlib import Path

# Ensure the src directory is on the path so the package is importable
# without requiring pip install (needed for HuggingFace Spaces).
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from resonance_alignment.ui.gradio_interface import create_interface

if __name__ == "__main__":
    demo = create_interface()
    demo.launch(share=False, show_error=True)
