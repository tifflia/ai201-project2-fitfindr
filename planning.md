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
<!-- Describe what this tool does in 1–2 sentences -->
Searches the mock listings dataset for items matching a keyword description, optional size, and optional price ceiling.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): Keywords describing the desired item used for relevance scoring against each listing's `title`, `description`, and `style_tags`.
- `size` (str): Size string to filter by, or None to skip size filtering. Matching is case-insensitive (e.g., "M" matches "S/M").
- `max_price` (float): Maximum price (inclusive), or None to skip price filtering.

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
A list of matching listing dicts, sorted by relevance (best match first). Each listing dict contains an `id` (str), `title` (str), `description` (str), `category` (str - tops/bottoms/outerwear/shoes/accessories), `style_tags` (list[str]), `size` (str), `condition` (str - excellent/good/fair), `price` (float), `colors` (list[str]), `brand` (str | None), and `platform` (str). Returns an empty list if nothing matches and does not raise an exception.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
Returns an empty list `[]` rather than raising an exception. The planning loop checks for the empty list, sets a `session["error"]`, and returns early so the downstream tools are never called with empty input.

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Given a thrifted item and the user's wardrobe, prompts the LLM (Groq) to suggest 1–2 complete outfits that pair the new item with specific, named pieces the user already owns.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): A listing dict for the item the user is considering buying. The prompt uses its `title`, `category`, `colors`, and `style_tags`.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts. Each wardrobe item has `id` (str), `name` (str), `category` (str), `colors` (list[str]), `style_tags` (list[str]), and optional `notes` (str | None). May be empty.

**What it returns:**
<!-- Describe the return value -->
A non-empty string with outfit suggestions in natural language. When the wardrobe has items, it names specific pieces.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
If the wardrobe is empty, offer general styling advice for the item rather than raising an exception or returning an empty string. If the LLM call itself errored, return a short fallback message rather than an empty string.

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Generate a short, shareable outfit caption for the thrifted find. It uses a higher LLM temperature so captions vary across runs.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (str): The outfit suggestion string from `suggest_outfit()`.
- `new_item` (dict): The same listing dict for the selected thrifted item. The caption pulls its `title`, `price`, and `platform` so they appear naturally (once each).

**What it returns:**
<!-- Describe the return value -->
A 2-4 sentence string usable as an Instagram/TikTok caption. It should mention the item name, price, and platform, and capture the outfit vibe.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
If the outfit is empty or missing, return a descriptive error message string rather than raising an exception. The outfit string should be populated at this point in the planning loop though.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->
The loop is a fixed sequence with early exit guards. Each step reads from and writes to the shared `session` dict.

1. Initialize: `session = _new_session(query, wardrobe)`.
2. Parse the query: Extract `description`, `size`, and `max_price` from query and store the result in `session["parsed']`. If size and max price aren't mentioned, set them to `None`.
3. Call `search_listings`: Get `results = search_listing(**session["parsed"])` and store in `session["search_results"]`. If the results are empty, set an error message in `session["error"]` and return early. Otherwise, set `session["selected_item"] = results[0]` and proceed to `suggest_outfit`.
4. Call `suggest_outfit`: Get `suggest_outfit(new_item=session["selected_item"],wardrobe=session["wardrobe"])` and store the results in `session["outfit_suggestion"]`. If the user's wardrobe is empty, the string result will be slightly different, but no conditional logic is different here.
5. Call `create_fit_card`: Get `create_fit_card(outfit=session["outfit_suggestion"],new_item=session["selected_item"])` and store the results in `session["fit_card"]`. If the results are empty or missing, the string result will be slightly different (error message), but no conditional logic is different here.
6. Done: `return session` to terminate the loop after `create_fit_card` runs. Callers check `session["error"]` to see if it was terminated early.

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->
The agent stores and accesses states within a session via a `session` dict initialized by `_new_session(query, wardrobe)` at the beginning of the loop. Instead of having the tools pass data to each other directly, the planning loop reads outputs from `session`, passes them as arguments to the next tool, and writes that tool's result back into `session` in the corresponding field in `agent.py`. The session tracks these fields:

- **`query`** (str): the original user query. Written by `_new_session`; read by the parse step.
- **`parsed`** (dict): extracted `description`, `size`, `max_price`. Written by the parse step; read by `search_listings`.
- **`search_results`** (list[dict]): ranked matching listing dicts. Written by `search_listings`; read by the empty-check and item-selection step.
- **`selected_item`** (dict | None): the top result, `search_results[0]`. Written by the item-selection step; read by `suggest_outfit`, `create_fit_card`, and the final output.
- **`wardrobe`** (dict): the user's wardrobe, passed in by the caller. Written by `_new_session`; read by `suggest_outfit`.
- **`outfit_suggestion`** (str | None): the styling text. Written by `suggest_outfit`; read by `create_fit_card` and the final output.
- **`fit_card`** (str | None): the shareable caption. Written by `create_fit_card`; read by the final output.
- **`error`** (str | None): set only on the no-results branch (otherwise stays `None`). Written by the no-results branch; read by the caller / Gradio UI.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | `search_listings` returns `[]`. The planning loop detects the empty list, sets `session["error"]` to a helpful message naming what failed, and returns the session early. It doesn't call `suggest_outfit` or `create_fit_card`. The UI shows the error in the listing panel and leaves the outfit and fit-card panels empty. |
| suggest_outfit | Wardrobe is empty | The tool does not fail/raise an exception. Instead, it prompts the LLM for general styling advice for the item (i.e. what pieces pair well, what vibe it suits) instead of naming specific wardrobe items. It always returns a non-empty string, so the loop proceeds normally to `create_fit_card`. |
| create_fit_card | Outfit input is missing or incomplete | The tool returns a descriptive error-message string (e.g. "Can't make a fit card without an outfit suggestion.") rather than raising an exception. The caption is just ommited or replaced with that message and the rest of the session output is still displayed. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

```
                    User query + wardrobe choice  (Gradio UI: handle_query)
                                  │
                                  ▼
   ┌──────────────────────────  PLANNING LOOP  (run_agent in agent.py)  ──────────────────────────┐
   │                                                                                               │
   │   _new_session(query, wardrobe)                                                               │
   │        │  creates SESSION dict ◄────────────── single source of truth ──────────────┐         │
   │        ▼                                                                             │        │
   │   parse query  ──writes──►  session["parsed"] = {description, size, max_price}       │        │
   │        │                                                                             │        │
   │        │  reads parsed                                                               │        │
   │        ▼                                                                             │        │
   │   search_listings(description, size, max_price) ──writes──► session["search_results"]│        │
   │        │                                                                             │        │
   │        ├─ results == []  ─►  session["error"] = "No listings found…"  ──┐            │        │
   │        │   [ERROR BRANCH]                                               │            │        │
   │        │                                                                │            │        │
   │        │  results == [item, …]                                          │            │        │
   │        ▼                                                                │            │        │
   │   select top result  ──writes──►  session["selected_item"] = results[0] │            │        │
   │        │                                                                │            │        │
   │        │  reads selected_item + wardrobe                                │            │        │
   │        ▼                                                                │            │        │
   │   suggest_outfit(selected_item, wardrobe) ──writes──► session["outfit_suggestion"]   │        │
   │        │   (empty wardrobe → general styling advice, no branch)         │            │        │
   │        │                                                                │            │        │
   │        │  reads outfit_suggestion + selected_item                       │            │        │
   │        ▼                                                                │            │        │
   │   create_fit_card(outfit_suggestion, selected_item) ──writes──► session["fit_card"]  │        │
   │        │                                                                │            │        │
   │        ▼                                                                ▼            │        │
   │   return session  ◄──────────────────────  early return  ◄──────────────             │        │
   │        │                                                                             │        │
   └────────┼─────────────────────────────────────────────────────────────────────────────┘        │
            │                                                                                      │
            ▼                                                                                       
   Gradio UI reads session:
     - error set?  ─► show error in listing panel, outfit + fit-card panels empty
     - else        ─► show selected_item / outfit_suggestion / fit_card in the three panels
```

---

## AI Tool Plan

AI Tool Plan — names specific spec sections used to prompt AI tools and describes how generated code was verified against the spec.

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

I'll use Claude to implement the three tools one at a time, giving it the matching spec from this doc as the prompt.

- **`search_listings`**: As input, I'll provide the Tool 1 spec (inputs, the full list of return fields, and the empty-list failure mode) plus the docstring for `load_listings()` in `utils/data_loader.py`. I'll ask it to implement a function that loads listings, applies the `size`/`max_price` filters, scores by keyword overlap against `title`/`description`/`style_tags`, drops zero-score items, and returns the list sorted best-first. I'll verify by running it against 3 queries: a normal one ("vintage graphic tee", `max_price=30`), a size-filtered one, and a deliberate no-match ("designer ballgown XXS under $5"). I'll confirm that the first returns ranked dicts with all expected fields, and the last returns `[]` (not an error).
- **`suggest_outfit`**: As input, I'll provide the Tool 2 spec (the `new_item` and `wardrobe` shapes, the empty-wardrobe fallback) and the Groq client setup. I'll ask it to implement a function that branches on `wardrobe["items"]` being empty, builds the appropriate prompt, calls the LLM, and returns a non-empty string. I'll verify by calling the func once with `get_example_wardrobe()` (confirm it names real wardrobe pieces) and once with `get_empty_wardrobe()` (confirm it still returns general advice, no crash).
- **`create_fit_card`**: As input, I'll provide the Tool 3 spec (the caption style rules, the empty-`outfit` guard, higher temperature). I'll ask it to implement a function that guards an empty/whitespace `outfit`, otherwise prompts for a 2–4 sentence caption mentioning item name/price/platform. I'll verify by calling the func with a real outfit string (confirm it reads casual and mentions price + platform once each, and varies across two runs) and with `""` (confirm it returns the error-message string, not an exception).

I'll test each tool in isolation before wiring it into the agent, so a bug is localized to one tool rather than the whole loop.

**Milestone 4 — Planning loop and state management:**

I'll use Claude to implement `run_agent()` in `agent.py`, giving it the Planning Loop, State Management, and Architecture (diagram) sections of this doc plus the `_new_session()` field list as the prompt.

I'll ask it to implement a `run_agent(query, wardrobe)` that initializes the session, parses the query into `session["parsed"]`, calls the three tools in order, writes each result into the matching session field, and checks for `search_results == []` and returns early with `session["error"]` set before calling `suggest_outfit`. I'll point Claude at the diagram so the early-return branch matches exactly.

For query parsing I'll have it use simple regex/string parsing (pull `max_price` from a `$`/"under" pattern, `size` from a "size X" pattern, `description` from the remaining keywords) and document that choice here, rather than an extra LLM call.

I'll verify by running the `__main__` block in `agent.py`. A successful query should populate `selected_item`, `outfit_suggestion`, and `fit_card` with `error is None`. The no-results query ("designer ballgown size XXS under $5") should set `error` and leave the other fields `None`. Then run `app.py` and submit both the successful and the no-results example query to confirm the UI maps the session to the three panels correctly (error in the listing panel, others empty).

---

## A Complete Interaction (Step by Step)

FitFindr runs a planning loop which walks through three tools in a set sequence, passing states between them, with early exit if a step (searching listings) returns nothing. It should parse a user query for a requested thrifted clothing item, then find matching listings and pick the best find, suggest how to style it with the user's wardrobe, and write a shareable caption for the thrifted find.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:** Initialize the session and parse the user's query to extract query parameters.
 - `description` = "vintage graphic tee"
 - `size` = None
 - `max_price` = 30.0

**Step 2:** Use the extracted parameters to call `search_listings("vintage graphic tee", size=None, max_price=30.0)` which returns 3 matching listings sorted by relevance.

**Step 3:** Select the top result: "Faded Band Tee — $22, Depop, Good condition."

**Step 4:** Use the selected item and the user's wardrobe to call `suggest_outfit(new_item=<band tee>, wardrobe=<user's wardrobe>)` which returns: "Pair this with your wide-leg jeans and platform Docs for a classic 90s grunge look. Roll the sleeves once and tuck the front corner slightly for shape."

**Step 5:** Pass the outfit string and selected item to `create_fit_card(outfit=<suggestion>, new_item=<band tee>)` which returns: "thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories"

**Final output to user:** The app shows the matched listing, the outfit suggestion, and the shareable fit card caption pulled from `session["selected_item"]`, `session["outfit_suggestion"]`, and `session["fit_card"]`.
