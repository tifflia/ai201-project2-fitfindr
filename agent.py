"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── query parsing ───────────────────────────────────────────────────────────────

# Lead-in / filler words stripped from the description so it carries only the
# keywords that matter for relevance scoring.
_FILLER_WORDS = {
    "i", "im", "i'm", "a", "an", "the", "some", "any", "looking", "look",
    "for", "find", "me", "want", "wanna", "need", "show", "searching",
    "search", "get", "got", "to", "buy", "something", "thats", "that's",
    "out", "there", "whats", "what's",
}


def _parse_query(query: str) -> dict:
    """Pull a description, optional size, and optional max_price out of a query.

    Uses plain regex/string parsing rather than an extra LLM call.

        - max_price: a "under/below/less than/max $N" phrase, or a bare "$N".
        - size:      a "size X" phrase (X may be slashed, e.g. "M/L").
        - description: whatever keywords remain after those phrases and a small
                       set of filler words are stripped.

    Returns a dict with keys "description", "size", "max_price" — exactly the
    keyword arguments search_listings() expects.
    """
    # Strip apostrophes so contractions collapse to the forms already in the
    # filler set ("i'm" -> "im", "what's" -> "whats") instead of leaving orphan
    # single-char tokens ("m", "s") behind when the apostrophe is split on below.
    lowered = query.lower().replace("'", "").replace("’", "")
    remainder = lowered

    # --- max_price: prefer an explicit ceiling phrase, fall back to a bare $N ---
    max_price = None
    price_match = re.search(
        r"(?:under|below|less than|max(?:imum)?|up to|<=?)\s*\$?\s*(\d+(?:\.\d+)?)",
        remainder,
    )
    if price_match is None:
        price_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", remainder)
    if price_match is not None:
        max_price = float(price_match.group(1))
        remainder = remainder[: price_match.start()] + " " + remainder[price_match.end() :]

    # --- size: a "size X" phrase, where X may be a slashed token like "M/L" ---
    size = None
    size_match = re.search(r"\bsize\s+([a-z0-9]+(?:\s*/\s*[a-z0-9]+)?)\b", remainder)
    if size_match is not None:
        size = size_match.group(1).upper().replace(" ", "")
        remainder = remainder[: size_match.start()] + " " + remainder[size_match.end() :]

    # --- description: leftover keywords, filler stripped, original order kept ---
    tokens = re.findall(r"[a-z0-9]+", remainder)
    keywords = [tok for tok in tokens if tok not in _FILLER_WORDS]
    description = " ".join(keywords).strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: initialize the session — the single source of truth for this run.
    session = _new_session(query, wardrobe)

    # Step 2: parse the query into description / size / max_price (regex, no LLM).
    session["parsed"] = _parse_query(query)

    # Step 3: search listings with the parsed parameters.
    results = search_listings(**session["parsed"])
    session["search_results"] = results

    # Early exit: no matches → set an error and stop before the LLM tools run.
    if not results:
        session["error"] = (
            "No listings matched that search. Try fewer keywords, a higher "
            "price, or dropping the size filter."
        )
        return session

    # Step 4: select the top-ranked result to style.
    session["selected_item"] = results[0]

    # Step 5: suggest an outfit pairing the find with the user's wardrobe.
    session["outfit_suggestion"] = suggest_outfit(
        new_item=session["selected_item"],
        wardrobe=session["wardrobe"],
    )

    # Step 6: write a shareable fit-card caption for the find.
    session["fit_card"] = create_fit_card(
        outfit=session["outfit_suggestion"],
        new_item=session["selected_item"],
    )

    # Step 7: done — error stays None on the happy path.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
