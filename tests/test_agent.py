# Run with 'python -m pytest tests/'
import agent
from agent import run_agent, _parse_query
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# --- query parsing (regex, no LLM) ---

def test_parse_extracts_price_and_description():
    parsed = _parse_query("I'm looking for a vintage graphic tee under $30")
    assert parsed["description"] == "vintage graphic tee"
    assert parsed["size"] is None
    assert parsed["max_price"] == 30.0

def test_parse_extracts_size():
    parsed = _parse_query("90s track jacket in size M")
    assert parsed["size"] == "M"
    assert "track jacket" in parsed["description"]
    assert "90s" in parsed["description"]

def test_parse_extracts_size_price_and_description_together():
    parsed = _parse_query("designer ballgown size XXS under $5")
    assert parsed["description"] == "designer ballgown"
    assert parsed["size"] == "XXS"
    assert parsed["max_price"] == 5.0

def test_parse_bare_dollar_amount():
    parsed = _parse_query("flowy midi skirt $40")
    assert parsed["max_price"] == 40.0

def test_parse_no_filters():
    parsed = _parse_query("black combat boots")
    assert parsed["size"] is None
    assert parsed["max_price"] is None
    assert parsed["description"] == "black combat boots"


# --- planning loop happy path (tools stubbed so no LLM/network is hit) ---

def _stub_llm_tools(monkeypatch):
    monkeypatch.setattr(agent, "suggest_outfit",
                        lambda new_item, wardrobe: "Pair it with your jeans.")
    monkeypatch.setattr(agent, "create_fit_card",
                        lambda outfit, new_item: "thrifted and thriving ✨")


def test_run_agent_happy_path_populates_all_fields(monkeypatch):
    _stub_llm_tools(monkeypatch)
    session = run_agent("vintage graphic tee under $30", get_example_wardrobe())

    assert session["error"] is None
    assert session["selected_item"] is not None
    assert session["search_results"]  # non-empty
    # selected_item is the top-ranked search result.
    assert session["selected_item"] is session["search_results"][0]
    assert session["outfit_suggestion"] == "Pair it with your jeans."
    assert session["fit_card"] == "thrifted and thriving ✨"


def test_run_agent_passes_selected_item_and_wardrobe_into_outfit(monkeypatch):
    captured = {}
    def fake_suggest(new_item, wardrobe):
        captured["new_item"] = new_item
        captured["wardrobe"] = wardrobe
        return "outfit text"
    monkeypatch.setattr(agent, "suggest_outfit", fake_suggest)
    monkeypatch.setattr(agent, "create_fit_card",
                        lambda outfit, new_item: "card")

    wardrobe = get_example_wardrobe()
    session = run_agent("vintage graphic tee", wardrobe)

    assert captured["new_item"] is session["selected_item"]
    assert captured["wardrobe"] is wardrobe


def test_run_agent_feeds_outfit_into_fit_card(monkeypatch):
    captured = {}
    monkeypatch.setattr(agent, "suggest_outfit",
                        lambda new_item, wardrobe: "style it casually")
    def fake_card(outfit, new_item):
        captured["outfit"] = outfit
        return "card"
    monkeypatch.setattr(agent, "create_fit_card", fake_card)

    run_agent("vintage graphic tee", get_example_wardrobe())
    assert captured["outfit"] == "style it casually"


# --- planning loop no-results path (must not call the LLM tools) ---

def test_run_agent_no_results_sets_error_and_skips_llm_tools(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("LLM tool should not run on the no-results path")
    monkeypatch.setattr(agent, "suggest_outfit", boom)
    monkeypatch.setattr(agent, "create_fit_card", boom)

    session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())

    assert session["error"] is not None
    assert session["search_results"] == []
    assert session["selected_item"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None


def test_run_agent_empty_query_is_treated_as_no_results(monkeypatch):
    # An all-filler query yields an empty description → no matches → error branch.
    monkeypatch.setattr(agent, "suggest_outfit",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    session = run_agent("looking for", get_empty_wardrobe())
    assert session["error"] is not None
    assert session["selected_item"] is None
