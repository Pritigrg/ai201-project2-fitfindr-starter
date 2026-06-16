"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""



import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Groq model used for the LLM-backed tools. Override with GROQ_MODEL in .env.
_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


# ── search helpers ──────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Lowercase a string and split it into alphanumeric word tokens."""
    return re.findall(r"[a-z0-9.]+", text.lower())


def _size_matches(requested: str, listing_size: str) -> bool:
    """
    Case-insensitive size match. A listing matches if the requested size appears
    as a whole token in the listing's size string, so "M" matches "S/M" and
    "8" matches "US 8", while "L" does NOT spuriously match "XL".
    """
    return requested.strip().lower() in _tokenize(listing_size)


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()
    keywords = set(_tokenize(description or ""))

    scored: list[tuple[int, dict]] = []
    for listing in listings:
        # Filter by price ceiling (inclusive).
        if max_price is not None and listing["price"] > max_price:
            continue

        # Filter by size, when requested.
        if size and not _size_matches(size, listing["size"]):
            continue

        # Score by how many query keywords appear in the listing's text.
        blob_parts = [
            listing["title"],
            listing["description"],
            listing["category"],
            " ".join(listing.get("style_tags", [])),
            " ".join(listing.get("colors", [])),
            listing.get("brand") or "",
        ]
        blob_tokens = set(_tokenize(" ".join(blob_parts)))
        score = len(keywords & blob_tokens)

        # Drop listings with no keyword overlap.
        if score == 0:
            continue

        scored.append((score, listing))

    # Sort by score, highest first; stable sort preserves dataset order on ties.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [listing for _, listing in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    client = _get_groq_client()

    item_desc = (
        f"{new_item['title']} (a {new_item['category']}, "
        f"colors: {', '.join(new_item.get('colors', [])) or 'unspecified'}, "
        f"style: {', '.join(new_item.get('style_tags', [])) or 'unspecified'})"
    )

    items = wardrobe.get("items", [])
    if not items:
        # Empty wardrobe: general styling advice rather than specific pairings.
        prompt = (
            f"A shopper is considering this secondhand piece:\n{item_desc}\n\n"
            "They haven't entered any wardrobe items yet. Give general styling "
            "advice for this piece: what kinds of items pair well with it, what "
            "vibe or occasions it suits, and 1-2 example outfit ideas using "
            "common wardrobe staples. Keep it friendly and concise."
        )
    else:
        # Format the user's owned pieces so the LLM can name them specifically.
        wardrobe_lines = "\n".join(
            f"- {it['name']} ({it['category']}; "
            f"{', '.join(it.get('style_tags', [])) or 'no tags'})"
            for it in items
        )
        prompt = (
            f"A shopper is considering this secondhand piece:\n{item_desc}\n\n"
            f"Here is their current wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits that pair the new piece with specific, "
            "named items from their wardrobe above. Explain briefly why each "
            "outfit works. Keep it friendly and concise."
        )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Guard: no outfit means there's nothing to caption.
    if not outfit or not outfit.strip():
        return "Can't create a fit card without an outfit suggestion."

    client = _get_groq_client()

    prompt = (
        "Write a short, casual Instagram/TikTok OOTD caption (2-4 sentences) "
        "for a thrifted find. Sound like a real person posting their fit, not a "
        "product listing. Mention the item name, its price, and the platform "
        "naturally — once each. Capture the outfit's vibe in specific terms.\n\n"
        f"Item: {new_item['title']}\n"
        f"Price: ${new_item['price']}\n"
        f"Platform: {new_item['platform']}\n"
        f"Outfit: {outfit}"
    )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
    )
    return response.choices[0].message.content.strip()
