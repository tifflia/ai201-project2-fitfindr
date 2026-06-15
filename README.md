# FitFindr

FitFindr is a multi-tool AI agent that turns a natural-language request like *"vintage graphic tee under $30, size M"* into (1) a matching secondhand listing, (2) an outfit built from the user's own wardrobe, and (3) a shareable "fit card" caption.

The agent is built from **three tools** orchestrated by a **planning loop** (`run_agent` in [agent.py](agent.py)) that passes state between them through a single `session` dict. A Gradio UI ([app.py](app.py)) wraps the loop.

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (free key at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Run it:

```bash
python app.py          # launch the Gradio UI
python agent.py        # run the CLI demo (happy path + no-results path)
python -m pytest -q    # run the test suite (25 tests)
```

The LLM model is configured in [config.py](config.py) (`llama-3.3-70b-versatile` via Groq).

---

## Tools

All three tools live in [tools.py](tools.py). Each is a standalone function, tested in isolation before being wired into the loop.

### 1. `search_listings(description, size, max_price)` → `list[dict]`

**Purpose:** Find secondhand listings matching the user's request by scoring keyword overlap against a 40-item mock dataset.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `description` | str | Keywords describing the desired item (e.g. `"vintage graphic tee"`). Scored against each listing's `title`, `style_tags`, and `description`. |
| `size` | str \| None | Size to filter by, or `None` to skip. Case-insensitive, token-aware (`"M"` matches `"S/M"`). |
| `max_price` | float \| None | Inclusive price ceiling, or `None` to skip. |

**Returns:** A `list[dict]` of matching listings **sorted by relevance, best first**. Each dict has: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str). Returns an empty list `[]` when nothing matches and never raises an exception.

**How it ranks:** keywords matched in the `title` score 3, in `style_tags` score 2, in `description` score 1. Listings scoring 0 are dropped. This is the only tool with no LLM call.

### 2. `suggest_outfit(new_item, wardrobe)` → `str`

**Purpose:** Ask the LLM to style the found item against the user's actual wardrobe, naming specific pieces they already own.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `new_item` | dict | The listing chosen by the loop. Its `title`, `category`, `colors`, `style_tags` go into the prompt. |
| `wardrobe` | dict | A dict with an `items` key (list of wardrobe-item dicts, each with `name`, `category`, `colors`, `style_tags`, optional `notes`). May be empty. |

**Returns:** A non-empty `str` with 1–2 outfit ideas in natural language. When the wardrobe has items, it references them by name ("pair with your Black combat boots…"). When the wardrobe is empty, it returns general styling advice instead. It never returns an empty list and never raises.

### 3. `create_fit_card(outfit, new_item)` → `str`

**Purpose:** Turn the outfit into a short, casual OOTD caption ready to post.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `outfit` | str | The styling text returned by `suggest_outfit`. |
| `new_item` | dict | The same listing dict. Its `title`, `price`, `platform` are woven into the caption (once each). |

**Returns:** A 2–4 sentence `str` usable as an Instagram/TikTok caption, mentioning the item name, price, and platform. Uses a higher LLM temperature (`1.0` vs. `suggest_outfit`'s `0.7`) so captions vary across runs. If `outfit` is empty/whitespace, it returns a descriptive error message string rather than raising.

**All three tools are exercised in a single interaction** by `run_agent` (see [agent.py:162-186](agent.py#L162-L186)) and end-to-end in the UI handler [app.py:57-65](app.py#L57-L65).

---

## The Planning Loop

The loop is a fixed sequence with early exit guards. Each step reads from and writes to the shared `session` dict.

**Step 1 — Parse the query (no LLM).** `_parse_query` uses regex/string parsing to split the raw query into `description`, `size`, and `max_price`. If size or price aren't mentioned, they're left as `None`, which tells `search_listings` to skip that filter. This is the first place behavior diverges by input: a query with no price/size produces an unfiltered search; a query with them produces a narrower one. I chose regex over an LLM call here because the patterns are small and deterministic, and it keeps the loop fast and testable.

**Step 2 — Search, then branch on the result count.** The loop calls `search_listings(**session["parsed"])` and inspects the returned list:

- **If the list is empty** → the loop sets
  `session["error"]` to *"No listings matched that search. Try fewer keywords, a higher price, or dropping the size filter."* and returns immediately. It does not call `suggest_outfit` or `create_fit_card`, because styling and captioning an item that doesn't exist is meaningless. `outfit_suggestion`/`fit_card` stay `None`.
- **If the list is non-empty** → the loop selects `results[0]` (the highest-relevance match) as `session["selected_item"]` and continues.

**Step 3 — Suggest an outfit.** The loop calls `suggest_outfit` with the selected item and the wardrobe. There is no control-flow branch here, but the tool itself branches on wardrobe contents (named-piece outfits vs. general advice), so the agent's output adapts to whether the user's wardrobe is empty or not.

**Step 4 — Make the fit card** from the outfit text and the same item, then return the session. The loop knows it's done when `create_fit_card` returns (happy path, `error` stays `None`) or the moment the no-results branch fires.

---

## State Management

There is no direct tool-to-tool calling. Instead, a single `session` dict, created by `_new_session(query, wardrobe)` at the start of the run, is the single source of truth. The planning loop reads a field from `session`, passes it as an argument to the next tool, and writes that tool's result back into the matching field. Because every tool's output is stored, the next tool gets its input from the loop, not from the user.

| Field | Type | Written by | Read by |
|-------|------|-----------|---------|
| `query` | str | `_new_session` | parse step |
| `parsed` | dict | parse step | `search_listings` |
| `search_results` | list[dict] | `search_listings` | empty-check + item selection |
| `selected_item` | dict \| None | item-selection step | `suggest_outfit`, `create_fit_card`, UI |
| `wardrobe` | dict | `_new_session` (from caller) | `suggest_outfit` |
| `outfit_suggestion` | str \| None | `suggest_outfit` | `create_fit_card`, UI |
| `fit_card` | str \| None | `create_fit_card` | UI |
| `error` | str \| None | no-results branch only | caller / UI |

---

## Error Handling

Each tool has a defined failure mode and the loop/UI has a defined response. No tool raises an exception on its expected failure and instead returna a sentinel value (empty list or a message string) that the loop handles.

| Tool | Failure mode | What the agent does |
|------|-------------|---------------------|
| `search_listings` | No listing matches the query | Returns `[]`. The loop detects the empty list, sets `session["error"]` to an actionable message ("Try fewer keywords, a higher price, or dropping the size filter"), and returns early, skipping the two LLM tools. The UI shows the error in the listing panel and leaves the outfit/fit-card panels blank. |
| `suggest_outfit` | Empty wardrobe (or LLM call errors) | Never raises. On an empty wardrobe it prompts for general styling advice instead of named pieces. On an LLM exception or a blank reply it returns a non-empty fallback string. Either way the loop proceeds normally. |
| `create_fit_card` | Missing/empty `outfit` (or LLM errors) | Returns the message "Can't make a fit card without an outfit suggestion." for an empty outfit, or a templated fallback caption if the LLM errors. Never raises. |

### Concrete example from testing

The query `"designer ballgown size XXS under $5"` is constructed to match nothing. Running it results in:

```
error:   No listings matched that search. Try fewer keywords, a higher price, or dropping the size filter.
outfit:  None
fit_card: None
```

The response is specific (it names what failed) and actionable (it tells the user what to try next). The two LLM tools are never called on this path as the agent notices that no matching listings were found and saved.

---

## A Complete Interaction (Step by Step)

**Query:** *"I'm looking for a vintage graphic tee under $30. I mostly wear
baggy jeans and chunky sneakers. What's out there and how would I style it?"*

1. **Parse** → `description="vintage graphic tee"`, `size=None`, `max_price=30.0`. Stored in `session["parsed"]`.
2. **`search_listings("vintage graphic tee", None, 30.0)`** → ranked listings under $30; the literal "Graphic Tee" ranks above items that only match "vintage." Stored in `session["search_results"]`.
3. **Branch:** results non-empty → `session["selected_item"] = results[0]` (e.g. *Faded Band Tee — $22, Depop, good condition*).
4. **`suggest_outfit(selected_item, wardrobe)`** → e.g. *"Pair this with your wide-leg jeans and chunky white sneakers for a 90s look…"* Stored in `session["outfit_suggestion"]`.
5. **`create_fit_card(outfit_suggestion, selected_item)`** → e.g. *"thrifted this faded band tee off Depop for $22 and it was made for my wide-legs 🖤"* Stored in `session["fit_card"]`.
6. **Return** the session; the UI renders the listing, the outfit, and the fit
   card in three panels.

---

## Spec Reflection

**One way the spec helped.** The tool specs let me design the planning loop's control flow before writing either piece. They also doubled as a test checklist: each "what happens if it fails" line became a test (`test_search_empty_results`, `test_create_fit_card_empty_outfit_*`, the LLM-error fallbacks). It forced me to go into enough detail to result in a robust document I could provide as context for the AI tool during the implementation stage.

**One divergence and why.** The starter `search_listings` spec described size matching only as "case-insensitive," which a simple substring check satisfies. I diverged to token-aware size matching that splits both the requested and listing sizes on `/`, whitespace, and parentheses and requires a subset match. Since a plain substring check both produced false positives (`"M"` matching the `M` inside other tokens) and broke multi-token sizes, `"US 7"` was never found because the code compared the whole requested string against the listing's individual tokens. Tokenizing both sides fixed both issues.

---

## AI Usage

### Instance 1 — Query parsing

As a part of milestone 4, I asked Claude to implement query parsing in `agent.py` so that description/size/max_price could be extracted from the query and eventually passed to `search_listings`. I directed it to use simple regex/string parsing rather than an extra LLM call.

With the given implementation, I asked whether searching by sizes like `"W29"` or `"US 7"` actually worked. Claude tested both and found single-token sizes matched but multi-token sizes returned nothing, because the code compared the whole requested string against the listing's tokens, so `"us 7"` was never found among `{"us", "7"}`.

I had it fix `_size_matches()` to tokenize both sides and require a subset match. I verified end-to-end (`US 7` → `lst_009`, `US 8.5` → `lst_028`, `W29` → `lst_011`) and confirmed no regressions (`M` still matches `S/M`; `M`/`S` do *not* match `US 7`).

### Instance 2 — Strengthening the `search_listings` tests

After implememting `search_listings`, I pointed out the starter tests only checked result *shape* (is it a list? non-empty? price ≤ cap?) and directed Claude to add accuracy-focused tests including at least two size cases.

I kept tests that assert against known dataset facts (a literal "Graphic Tee" must outrank a leather belt that only matches "vintage"; the top hit for "vintage graphic tee" must be a tee) plus a direct `_size_matches` unit test with hardcoded expectations as the regression guard for the query parsing.

### Instance 3 — Implementing `suggest_outfit` (Tool 2)

I gave Claude the Tool 2 spec (item/wardrobe shapes, empty-wardrobe fallback) and the Groq setup and asked it to branch on an empty `wardrobe["items"]`, build the right prompt, call the LLM, and always return a non-empty string. I verified once with the example wardrobe and once empty.

I accepted Claude's `_complete()` helper so the LLM-backed tools could be unit-tested by monkeypatching one function. I reviewed both prompt branches and the fallbacks (try/except + blank-reply guard). I verified live behavior (named real pieces with a wardrobe; general advice when empty, no crash) and added mocked tests asserting branch logic and the never-empty guarantee rather than exact wording.