"""Gradio-based web interface for the Resonance Alignment Framework."""

from __future__ import annotations

import json

try:
    import gradio as gr
except ImportError:
    gr = None

from resonance_alignment.system import ResonanceAlignmentSystem


def create_interface():
    """Create and return the Gradio Blocks interface.

    Raises:
        ImportError: If gradio is not installed.
    """
    if gr is None:
        raise ImportError("gradio is required for the UI. Install with: pip install gradio>=4.0.0")

    system = ResonanceAlignmentSystem()

    def analyze(user_id: str, experience: str, user_rating: float, context: str):
        result = system.process_experience(user_id, experience, user_rating, context)
        return (
            result["position"],
            result["quality"],
            result["intention"],
            result["resonance"],
            json.dumps(result.get("recommendations", []), indent=2),
        )

    with gr.Blocks(title="Resonance Alignment Framework") as demo:
        gr.Markdown("# Resonance-Based Alignment System")
        gr.Markdown("Test the quality-intention matrix with real experiences")

        with gr.Row():
            with gr.Column():
                user_id = gr.Textbox(label="User ID", value="demo_user")
                experience = gr.Textbox(
                    label="Experience Description",
                    placeholder="Describe an activity or experience...",
                    lines=3,
                )
                user_rating = gr.Slider(
                    minimum=0, maximum=1, value=0.5,
                    label="Your Resonance Rating (0-1)",
                )
                context = gr.Textbox(
                    label="Context (optional)",
                    placeholder="Additional context about the experience...",
                    lines=2,
                )
                submit_btn = gr.Button("Analyze Experience")

            with gr.Column():
                position_output = gr.Textbox(label="Matrix Position")
                quality_output = gr.Number(label="Quality Score")
                intention_output = gr.Textbox(label="Intention Classification")
                resonance_output = gr.Number(label="Validated Resonance")
                recommendations = gr.Textbox(label="Recommendations", lines=5)

        submit_btn.click(
            fn=analyze,
            inputs=[user_id, experience, user_rating, context],
            outputs=[
                position_output, quality_output, intention_output,
                resonance_output, recommendations,
            ],
        )

        gr.Markdown("""
## Test Cases

| Experience | Expected Quadrant |
|---|---|
| Teaching programming to beginners | Optimal |
| Binge-watching TV series | Hedonism |
| Scrolling social media mindlessly | Junk Food |
| Writing low-quality spam content | Slop |
""")

    return demo
