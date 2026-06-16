# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the 40 mock secondhand listings for items matching a keyword description, with optional size and price filters, and returns them ranked by relevance. This is pure Python (no LLM) — it filters, scores by keyword overlap, and sorts.

**Input parameters:**
- `description` (str): Keywords describing the item the user wants, e.g. "vintage graphic tee".
- `size` (str | None): Size to filter by, matched case-insensitively (e.g. "M" matches "S/M"). `None` skips size filtering.
- `max_price` (float | None): Inclusive price ceiling. `None` skips price filtering.

**What it returns:**
A list of matching listing dicts sorted best-match-first. Each dict has: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand`, `platform`. Returns an empty list when nothing matches — it never raises.

**What happens if it fails or returns nothing:**
Returns `[]`. The agent treats an empty list as a stop condition: it sets `session["error"]` to a friendly "no matches, try loosening your filters" message and returns early without calling `suggest_outfit` or `create_fit_card`.

---

### Tool 2: suggest_outfit

**What it does:**
Uses the LLM (Groq) to suggest 1–2 complete outfits that pair the found item with pieces from the user's wardrobe. It formats the wardrobe items into the prompt so the suggestions name real pieces the user already owns.

**Input parameters:**
- `new_item` (dict): The listing the user is considering — the same dict shape returned by `search_listings`.
- `wardrobe` (dict): The user's wardrobe with an `items` key (list of wardrobe item dicts). May be empty.

**What it returns:**
A non-empty string describing the outfit ideas in natural language.

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, it does NOT fail — it asks the LLM for general styling advice for the item (what pairs well, what vibe it suits) instead of referencing owned pieces. It always returns a usable string rather than raising or returning empty.

---

### Tool 3: create_fit_card

**What it does:**
Uses the LLM (at a higher temperature for variety) to write a short, casual, shareable OOTD-style caption for the thrifted find, based on the outfit suggestion and the item details.

**Input parameters:**
- `outfit` (str): The outfit suggestion string produced by `suggest_outfit`.
- `new_item` (dict): The listing dict, used to mention the item name, price, and platform naturally.

**What it returns:**
A 2–4 sentence string usable as an Instagram/TikTok caption — casual and authentic, mentioning the item name, price, and platform once each, and capturing the outfit's vibe.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, it returns a descriptive error string (e.g. "Can't make a fit card without an outfit") rather than raising or calling the LLM with empty input.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
The loop is deterministic — a fixed pipeline rather than dynamic tool selection. Each step's output is the precondition for the next:

1. Parse the query into `description`, `size`, `max_price`.
2. Call `search_listings`. **Branch:** if it returns an empty list, set `session["error"]` and stop — the loop is done (early exit).
3. Otherwise select the top result and call `suggest_outfit`.
4. Call `create_fit_card` with the outfit text.
5. Done — all three output fields are populated and the session is returned.

The loop "knows it's done" when `fit_card` is set (success) or `error` is set (early exit). The only condition that changes behavior is whether search returned any results.

---

## State Management

**How does information from one tool get passed to the next?**
A single `session` dict (created by `_new_session` in `agent.py`) is the source of truth for one interaction. Tools don't talk to each other directly — the loop reads inputs out of the session, calls a tool, and writes the result back in. Fields tracked:

- `query` — the original user text
- `parsed` — extracted `description` / `size` / `max_price`
- `search_results` — list returned by `search_listings`
- `selected_item` — the top result, the input to `suggest_outfit` and `create_fit_card`
- `wardrobe` — the user's wardrobe dict (passed in at the start)
- `outfit_suggestion` — string from `suggest_outfit`, the input to `create_fit_card`
- `fit_card` — final caption string
- `error` — set to a message if the interaction ended early (otherwise `None`)

The loop returns the whole session; the UI reads `selected_item`, `outfit_suggestion`, and `fit_card` (or `error`) from it.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Returns `[]`; loop sets `session["error"]` to a friendly "no matches — try loosening size/price" message and returns early, skipping the LLM tools. |
| suggest_outfit | Wardrobe is empty | Detects empty `items` and asks the LLM for general styling advice for the item instead of referencing owned pieces; still returns a usable string. |
| create_fit_card | Outfit input is missing or incomplete | Guards against empty/whitespace `outfit` and returns a descriptive error string instead of raising or calling the LLM. |

---

## Architecture

```
        User query + wardrobe choice (Gradio UI, app.py)
                          │
                          ▼
                   ┌──────────────┐
                   │ Planning Loop │  run_agent()  ──reads/writes──►  ┌─────────────┐
                   │  (agent.py)   │ ◄──────────────────────────────  │   session   │
                   └──────────────┘                                   │  (state dict)│
                          │                                           └─────────────┘
        ┌─────────────────┼───────────────────────────┐                  ▲   ▲   ▲
        ▼                 ▼                           ▼                   │   │   │
  parse query      search_listings()           (empty list?)             │   │   │
  → parsed   ───►  Tool 1 (data only)  ──┬── yes ─► set error, STOP ──────┘   │   │
                                         │                                    │   │
                                      no │ top result = selected_item         │   │
                                         ▼                                    │   │
                                  suggest_outfit()  Tool 2 (LLM) ─► outfit ───┘   │
                                         │   (empty wardrobe → general advice)    │
                                         ▼                                        │
                                  create_fit_card() Tool 3 (LLM) ─► fit_card ─────┘
                                         │
                                         ▼
                  session returned → UI shows listing / outfit / fit card
```

Trigger summary: `parsed` triggers Tool 1 → the top listing triggers Tool 2 → the outfit string triggers Tool 3. The only branch is the empty-results early exit after Tool 1.

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
I'll use **Claude** one tool at a time. For each, I give it that tool's section from this planning.md (inputs, return value, failure mode) plus the relevant docstring/stub from `tools.py`.
- `search_listings`: ask Claude to implement filtering + keyword scoring using `load_listings()` from `utils/data_loader.py`. Verify by running it against 3 queries — a clear match, a size-filtered query, and the deliberate no-results query ("designer ballgown size XXS under $5") — and confirm it returns sorted dicts / an empty list, never raises.
- `suggest_outfit`: give Claude the Tool 2 spec and the wardrobe schema; ask it to branch on empty `items`. Verify with the example wardrobe (names real pieces) and the empty wardrobe (gives general advice).
- `create_fit_card`: give Claude the Tool 3 spec; ask for a higher-temperature caption. Verify it mentions item/price/platform once each, stays 2–4 sentences, and returns an error string when `outfit` is empty.

**Milestone 4 — Planning loop and state management:**
I'll give **Claude** the Architecture diagram, the Planning Loop and State Management sections, and the `run_agent`/`_new_session` stubs in `agent.py`, and ask it to wire the three tools together through the session dict with the empty-results early exit. Then I'll give it the `handle_query` stub in `app.py` to map the session onto the three UI panels. Verify by running `python agent.py` (happy path + no-results path both behave) and `python app.py`, then exercising the example queries in the browser — including the no-results one to confirm the error appears in the first panel.

---

## A Complete Interaction (Step by Step)

FitFindr takes a shopper's natural-language request and turns it into a concrete secondhand find plus styling help: the parsed request (description, size, max price) triggers `search_listings`, the top matching listing triggers `suggest_outfit` against the user's wardrobe, and that outfit text triggers `create_fit_card` to write a shareable caption. If `search_listings` returns nothing, the agent stops and reports a helpful "no matches" message instead of calling the later tools; if the wardrobe is empty, `suggest_outfit` falls back to general styling advice, and if the outfit text is missing, `create_fit_card` returns an error string rather than raising.

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
Parse the query into `{description: "vintage graphic tee", size: None, max_price: 30.0}` and store it in `session["parsed"]`. The "baggy jeans / chunky sneakers" detail is kept as style context for the outfit step.

**Step 2:**
Call `search_listings("vintage graphic tee", max_price=30)`. It drops anything over $30, scores the rest by keyword overlap, and returns matches like lst_006 "Graphic Tee — 2003 Tour Bootleg Style" ($24) and lst_033 "Vintage Band Tee" ($19), stored in `session["search_results"]`. **Failure path:** if the list comes back empty, set `session["error"]` to a "no matches" message and return early — do not call the later tools.

**Step 3:**
Select the top result (lst_006) into `session["selected_item"]`, then call `suggest_outfit(selected_item, wardrobe)` → an outfit pairing the tee with the user's baggy jeans and chunky sneakers, stored in `session["outfit_suggestion"]`. Finally call `create_fit_card(outfit_suggestion, selected_item)` → a caption naming the item, $24 price, and platform, stored in `session["fit_card"]`. (If the wardrobe were empty, `suggest_outfit` returns general styling advice instead.)

**Final output to user:**
The listing details, the outfit idea, and the fit-card caption — one per UI panel in the Gradio app.
