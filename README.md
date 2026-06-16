# FitFindr 🛍️

FitFindr is a tool-using agent that helps you shop secondhand. You describe what you want in plain English ("vintage graphic tee under $30, size M"), and it finds a matching listing, suggests how to style it with your wardrobe, and writes a shareable caption for the fit.

## Setup

```bash
pip install -r requirements.txt
```

Add your Groq API key to a `.env` file in the project root (free key at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```


## Tool Inventory

| Tool | Type | What it does |
|------|------|--------------|
| `search_listings(description, size, max_price)` | data only | Filters the 40 mock listings by price and size, scores the rest by keyword overlap with the description, and returns them best-match first. Returns `[]` when nothing matches. |
| `suggest_outfit(new_item, wardrobe)` | LLM (Groq) | Suggests 1–2 outfits pairing the found item with named pieces from the user's wardrobe. Falls back to general styling advice if the wardrobe is empty. |
| `create_fit_card(outfit, new_item)` | LLM (Groq) | Writes a short, casual OOTD-style caption mentioning the item name, price, and platform. Runs at a higher temperature so each caption is different. |

All three live in `tools.py`. The data tool reads from `utils/data_loader.py`; the two LLM tools use `llama-3.3-70b-versatile` via Groq.

**Inputs and return values (with types):**

- **`search_listings`** — `description (str)`, `size (str | None)`, `max_price (float | None)`. Returns a `list[dict]` sorted best-match first; each dict holds `id`, `title`, `description`, `category`, `style_tags (list)`, `size`, `condition`, `price (float)`, `colors (list)`, `brand`, `platform`. Returns `[]` when nothing matches.
- **`suggest_outfit`** — `new_item (dict)` (a listing from `search_listings`), `wardrobe (dict)` (has an `items` list). Returns a non-empty `str` describing 1–2 outfits.
- **`create_fit_card`** — `outfit (str)` (from `suggest_outfit`), `new_item (dict)`. Returns a `str` caption (2–4 sentences), or an error `str` if `outfit` is empty.

## Planning Loop

The loop (`run_agent` in `agent.py`) is a fixed pipeline, not dynamic tool selection. Each step's output is the precondition for the next:

```
parse query → search_listings → (empty? stop) → pick best → suggest_outfit → create_fit_card
```

1. Parse the query into `description`, `size`, `max_price` (plain regex — no LLM).
2. Call `search_listings`. If it returns `[]`, set an error and stop.
3. Otherwise take the top result (search already sorts best-first).
4. Call `suggest_outfit` with that item.
5. Call `create_fit_card` with the resulting outfit.

The tools are never called unconditionally: `suggest_outfit` needs a real selected item, and `create_fit_card` needs a real outfit string — so each only runs once the previous step has produced its input.

## State Management

A single `session` dict (built by `_new_session`) is the source of truth for one interaction. The loop reads inputs out of it, calls a tool, and writes the result back — tools never talk to each other directly.

| Field | Holds |
|-------|-------|
| `query` | original user text |
| `parsed` | extracted `description` / `size` / `max_price` |
| `search_results` | list from `search_listings` |
| `selected_item` | the chosen listing |
| `wardrobe` | the user's wardrobe |
| `outfit_suggestion` | string from `suggest_outfit` |
| `fit_card` | string from `create_fit_card` |
| `error` | set if the run ended early (else `None`) |
| `response` | final combined message |

The UI (`handle_query` in `app.py`) reads `selected_item`, `outfit_suggestion`, and `fit_card` — or `error` — off the session and maps them to the three panels.

## Error Handling

| Tool | Failure mode | Response |
|------|--------------|----------|
| `search_listings` | no matches | returns `[]`; loop sets `error` and stops before the LLM tools |
| `suggest_outfit` | empty wardrobe | gives general styling advice instead of naming owned pieces |
| `create_fit_card` | empty outfit string | returns an error string, never calls the LLM |

**Test example** (`tests/test_tools.py`):

```python
def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []   # empty list, no exception
```

Running `python agent.py` on that same query confirms the branch end-to-end: `error` is set, and `fit_card` / `outfit_suggestion` stay `None` because `suggest_outfit` is never reached. Run the full suite with:

```bash
python -m pytest -q
```

## Spec Reflection

**How the spec helped:** Writing out each tool's inputs, return value, and failure mode in `planning.md` *before* coding meant the planning loop and the three tools fit together on the first try — `search_listings` returns exactly the dict shape `suggest_outfit` expects, and the "return `[]` on no match" contract is what the loop's early-exit branch keys off of. Having the failure modes written down up front is why the no-results path was handled by design rather than patched in later.

**Where I diverged:** The spec said "filter by size" but didn't pin down *how*. My first attempt used a substring match, which made size "L" match "XL" listings. I diverged to whole-token matching so "M" still matches "S/M" but "L" no longer leaks into "XL" results. Related lesson from testing: "combat boots size 8" returns nothing because there are no combat boots in the dataset — an empty result is correct here, not a bug.

## AI Usage

**Example 1 — `search_listings`.**
I gave the AI my Tool 1 spec from `planning.md` (inputs, return value, "return `[]` on no match") plus the docstring in `tools.py`, and asked it to implement filtering and keyword scoring using `load_listings()`. It produced a working version with token-overlap scoring. **What I changed:** its first size filter used a substring match, so "L" matched "XL" items. I had it switch to whole-token matching and verified that "vintage" + size "L" no longer returns any XL listings.

**Example 2 — `create_fit_card`.**
I gave the AI the Tool 3 spec and asked for a casual caption generator. It produced a clean version, but the captions came back nearly identical on repeated runs. **What I changed:** I asked it to raise the LLM temperature to 0.9 and then ran the tool three times on the same input to confirm the outputs actually varied before trusting it.
