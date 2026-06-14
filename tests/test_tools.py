# Run with 'python -m pytest tests/'
import tools
from tools import search_listings, suggest_outfit, create_fit_card, _size_matches
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# --- search_listings ---

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0

def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []   # empty list, no exception

def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


# --- Accuracy: is the ranking actually right? ---

def test_top_result_is_relevant():
    # The best match for "vintage graphic tee" should actually be a tee
    results = search_listings("vintage graphic tee", size=None, max_price=30)
    top = results[0]
    haystack = (top["title"] + " " + " ".join(top["style_tags"])).lower()
    assert "tee" in haystack

def test_more_relevant_item_ranks_higher():
    # lst_006 is literally a "Graphic Tee" (matches graphic + tee + vintage);
    # lst_014 is a leather belt that only matches the word "vintage".
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    ids = [item["id"] for item in results]
    assert ids.index("lst_006") < ids.index("lst_014")


# --- Accuracy: does the size filter in search_listings do the right thing? ---

def test_size_matches_unit():
    # Single-token request against a slashed listing size.
    assert _size_matches("M", "S/M") is True
    assert _size_matches("M", "M/L") is True
    # Multi-token size.
    assert _size_matches("US 7", "US 7") is True
    # No false positives.
    assert _size_matches("M", "US 7") is False
    assert _size_matches("S", "US 7") is False
    assert _size_matches("L", "XL") is False

def test_size_filter_applied_to_results():
    # Every returned item must genuinely match the requested size,
    # and the known multi-token match (lst_009, "US 7") must be found.
    results = search_listings("platform", size="US 7", max_price=None)
    assert all(_size_matches("US 7", item["size"]) for item in results)
    assert any(item["id"] == "lst_009" for item in results)


# --- suggest_outfit ---

# Minimal listing carrying the fields suggest_outfit and create_fit_card read
# (title/category/colors/style_tags for outfits; title/price/platform for caption cards).
SAMPLE_ITEM = {
    "id": "lst_test",
    "title": "Vintage Band Tee",
    "category": "tops",
    "style_tags": ["vintage", "grunge", "band tee"],
    "colors": ["grey", "charcoal"],
    "price": 19.0,
    "platform": "depop",
}

def test_suggest_outfit_feeds_real_wardrobe_pieces_into_prompt(monkeypatch):
    captured = {}
    def fake_complete(messages, temperature):
        captured["messages"] = messages
        return "Pair it with your Chunky white sneakers."
    monkeypatch.setattr(tools, "_complete", fake_complete)

    result = suggest_outfit(SAMPLE_ITEM, get_example_wardrobe())

    prompt = captured["messages"][-1]["content"]
    # Non-empty branch must put named wardrobe pieces into the prompt so the
    # model can reference them by name, and describe the considered item too.
    assert "Chunky white sneakers" in prompt
    assert "Baggy straight-leg jeans, dark wash" in prompt
    assert "Vintage Band Tee" in prompt
    assert result.strip() != ""

def test_suggest_outfit_empty_wardrobe_asks_for_general_advice(monkeypatch):
    captured = {}
    def fake_complete(messages, temperature):
        captured["messages"] = messages
        return "This tee is super versatile — style it with denim and boots."
    monkeypatch.setattr(tools, "_complete", fake_complete)

    result = suggest_outfit(SAMPLE_ITEM, get_empty_wardrobe())

    prompt = captured["messages"][-1]["content"]
    # Empty wardrobe → general-advice branch, no crash, non-empty result.
    assert "general styling advice" in prompt.lower()
    assert result.strip() != ""

def test_suggest_outfit_llm_error_returns_nonempty_fallback(monkeypatch):
    def boom(messages, temperature):
        raise RuntimeError("groq unavailable")
    monkeypatch.setattr(tools, "_complete", boom)

    result = suggest_outfit(SAMPLE_ITEM, get_example_wardrobe())
    # Must not raise; must return a usable non-empty string.
    assert isinstance(result, str)
    assert result.strip() != ""

def test_suggest_outfit_blank_response_returns_nonempty_fallback(monkeypatch):
    monkeypatch.setattr(tools, "_complete", lambda messages, temperature: "   ")

    result = suggest_outfit(SAMPLE_ITEM, get_empty_wardrobe())
    # A whitespace-only model reply still yields a non-empty fallback.
    assert result.strip() != ""


# --- create_fit_card ---

def test_create_fit_card_empty_outfit_returns_error_message():
    # Hits the guard before any LLM call → deterministic, no key needed.
    result = create_fit_card("", SAMPLE_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""
    assert "outfit" in result.lower()

def test_create_fit_card_whitespace_outfit_returns_error_message():
    result = create_fit_card("   \n  ", SAMPLE_ITEM)
    assert "outfit" in result.lower()

def test_create_fit_card_prompt_has_item_details_and_high_temp(monkeypatch):
    captured = {}
    def fake_complete(messages, temperature):
        captured["messages"] = messages
        captured["temperature"] = temperature
        return "thrifted this vintage band tee off depop for $19 — it's a vibe"
    monkeypatch.setattr(tools, "_complete", fake_complete)

    outfit = "Pair it with baggy jeans and combat boots."
    result = create_fit_card(outfit, SAMPLE_ITEM)

    prompt = captured["messages"][-1]["content"]
    # Name, price, platform, and the styling text must all reach the model.
    assert "Vintage Band Tee" in prompt
    assert "depop" in prompt
    assert "19" in prompt
    assert outfit in prompt
    # Higher temperature than suggest_outfit's 0.7 → captions vary across runs.
    assert captured["temperature"] >= 0.9
    assert result.strip() != ""

def test_create_fit_card_llm_error_returns_nonempty_fallback(monkeypatch):
    def boom(messages, temperature):
        raise RuntimeError("groq unavailable")
    monkeypatch.setattr(tools, "_complete", boom)

    result = create_fit_card("Pair it with baggy jeans.", SAMPLE_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""