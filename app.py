"""
app.py

Gradio interface for FitFindr. The layout and wiring are already set up —
your job is to fill in handle_query() so it calls run_agent() and maps
the session results to the three output panels.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Args:
        user_query:     The text the user typed into the search box.
        wardrobe_choice: Either "Example wardrobe" or "Empty wardrobe (new user)".

    Returns:
        A tuple of three strings:
            (listing_text, outfit_suggestion, fit_card)
        Each string maps to one of the three output panels in the UI.
    """
    # 1. Guard against an empty query — nothing to search for.
    if not user_query or not user_query.strip():
        return "Please enter what you're looking for.", "", ""

    # 2. Pick the wardrobe the user selected (default to empty for safety).
    if wardrobe_choice == "Example wardrobe":
        wardrobe = get_example_wardrobe()
    else:
        wardrobe = get_empty_wardrobe()

    # 3. Run the planning loop.
    session = run_agent(user_query, wardrobe)

    # 4. Early-exit path: show the error in the listing panel, leave the rest blank.
    if session["error"]:
        return session["error"], "", ""

    # 5. Happy path: format the selected listing and return all three panels.
    listing_text = _format_listing(session["selected_item"])
    return listing_text, session["outfit_suggestion"], session["fit_card"]


def _format_listing(item: dict) -> str:
    """Render the selected listing dict as readable multi-line text for the UI."""
    price = item.get("price")
    price_str = f"${price:g}" if isinstance(price, (int, float)) else "—"
    lines = [
        item.get("title", "Untitled listing"),
        f"{price_str} · {item.get('condition', 'unknown')} condition · {item.get('platform', 'unknown')}",
    ]
    if item.get("brand"):
        lines.append(f"Brand: {item['brand']}")
    lines.append(f"Size: {item.get('size', 'n/a')}")
    if item.get("colors"):
        lines.append(f"Colors: {', '.join(item['colors'])}")
    if item.get("style_tags"):
        lines.append(f"Style: {', '.join(item['style_tags'])}")
    if item.get("description"):
        lines.append("")
        lines.append(item["description"])
    return "\n".join(lines)


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
