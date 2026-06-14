# Run with 'python -m pytest tests/'
from tools import search_listings, _size_matches

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