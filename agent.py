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


# ── query parsing ─────────────────────────────────────────────────────────────

# Standalone clothing sizes we recognize when no explicit "size" word is present.
_SIZE_WORDS = ["xxl", "xl", "xs", "s", "m", "l"]


def _parse_query(query: str) -> dict:
    """
    Pull a description, size, and max price out of a natural-language query.

    This is plain regex/string parsing (no LLM) so it's fast and predictable.
    Examples:
        "vintage graphic tee under $30"  -> description="vintage graphic tee", max_price=30.0
        "90s track jacket in size M"     -> description="90s track jacket", size="M"
        "black combat boots size 8"      -> description="black combat boots", size="8"

    Returns a dict with keys: description (str), size (str|None), max_price (float|None).
    """
    text = query.strip()
    size = None
    max_price = None

    # 1. Max price: a number after "under" / "below" / "less than" / "$".
    price_match = re.search(
        r"(?:under|below|less than|cheaper than|\$)\s*\$?\s*(\d+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if price_match:
        max_price = float(price_match.group(1))
        # Remove the whole "under $30" phrase from the text we'll use as the description.
        text = text[: price_match.start()] + text[price_match.end():]

    # 2. Size: prefer an explicit "size X" phrase (X = a size word or a shoe number).
    size_match = re.search(
        r"\bsize\s+([a-z]{1,3}|\d+(?:\.\d+)?)\b", text, flags=re.IGNORECASE
    )
    if size_match:
        size = size_match.group(1).upper()
        text = text[: size_match.start()] + text[size_match.end():]
    else:
        # Otherwise look for a standalone size word like "XL" or "M".
        for word in _SIZE_WORDS:
            standalone = re.search(rf"\b{word}\b", text, flags=re.IGNORECASE)
            if standalone:
                size = word.upper()
                text = text[: standalone.start()] + text[standalone.end():]
                break

    # 3. Description: whatever text is left, cleaned up. Drop common filler words.
    text = re.sub(r"\b(in|size|under|below|less than|for|a|an|the)\b", " ", text,
                  flags=re.IGNORECASE)
    description = re.sub(r"\s+", " ", text).strip(" ,.-")

    # Fall back to the original query if stripping left nothing useful to search on.
    if not description:
        description = query.strip()

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
        "response": None,            # final human-readable message for the user
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
    # Step 1: start a fresh session — the single source of truth for this run.
    session = _new_session(query, wardrobe)

    # Step 2: parse the natural-language query into search parameters.
    session["parsed"] = _parse_query(query)
    parsed = session["parsed"]

    # Step 3: search FIRST. Everything downstream depends on having a listing,
    # so this is always the first tool we call.
    session["search_results"] = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )

    # Branch: no matches -> stop here with a helpful message. We do NOT call
    # suggest_outfit or create_fit_card, because they need a real item to work on.
    if not session["search_results"]:
        message = (
            "I couldn't find any listings matching that. "
            "Try loosening the size or raising the price limit."
        )
        session["error"] = message
        session["response"] = message
        return session

    # Step 4: pick the best listing. search_listings already sorts best-first,
    # so the top result is our selection.
    session["selected_item"] = session["search_results"][0]
    item = session["selected_item"]

    # Step 5: only now that we have an item do we ask for an outfit.
    session["outfit_suggestion"] = suggest_outfit(item, wardrobe)

    # Step 6: only now that we have an outfit do we turn it into a fit card.
    session["fit_card"] = create_fit_card(session["outfit_suggestion"], item)

    # Build the final human-readable response from everything we gathered.
    session["response"] = (
        f"Found: {item['title']} — ${item['price']} on {item['platform']}\n\n"
        f"Outfit idea:\n{session['outfit_suggestion']}\n\n"
        f"Fit card:\n{session['fit_card']}"
    )

    # Step 7: hand the whole session back to the caller (UI, CLI, etc.).
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
