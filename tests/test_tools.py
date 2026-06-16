"""
Tests for the three FitFindr tools.

search_listings is pure/offline, so it's tested directly. suggest_outfit and
create_fit_card call the Groq LLM — those tests mock tools._get_groq_client so
the suite is fast, deterministic, and runs with no network or API key.
"""

import tools
from tools import search_listings, suggest_outfit, create_fit_card


# ── search_listings (offline, no mocking) ───────────────────────────────────────

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


def test_search_size_filter_no_over_match():
    # "L" must not spuriously match "XL" sizes.
    results = search_listings("vintage", size="L", max_price=None)
    assert all("xl" not in item["size"].lower().split() for item in results)


# ── LLM mock ────────────────────────────────────────────────────────────────────

class _FakeGroq:
    """Minimal stand-in for the Groq client used by the LLM-backed tools."""

    def __init__(self, reply="mock outfit text"):
        self.reply = reply
        self.calls = 0
        outer = self

        class _Message:
            def __init__(self, content):
                self.content = content

        class _Choice:
            def __init__(self, content):
                self.message = _Message(content)

        class _Completion:
            def create(self, **kwargs):
                outer.calls += 1
                outer.last_kwargs = kwargs
                return type("Resp", (), {"choices": [_Choice(outer.reply)]})()

        self.chat = type("Chat", (), {"completions": _Completion()})()


# ── suggest_outfit ───────────────────────────────────────────────────────────────

_ITEM = {
    "title": "Y2K Baby Tee",
    "category": "tops",
    "colors": ["pink"],
    "style_tags": ["y2k", "graphic tee"],
    "price": 18.0,
    "platform": "depop",
}


def test_suggest_outfit_empty_wardrobe(monkeypatch):
    # Empty wardrobe must not crash — it should still produce styling advice.
    fake = _FakeGroq("general styling advice")
    monkeypatch.setattr(tools, "_get_groq_client", lambda: fake)

    result = suggest_outfit(_ITEM, {"items": []})

    assert isinstance(result, str)
    assert result.strip() != ""
    assert fake.calls == 1


def test_suggest_outfit_uses_wardrobe(monkeypatch):
    fake = _FakeGroq("outfit using your jeans")
    monkeypatch.setattr(tools, "_get_groq_client", lambda: fake)

    wardrobe = {"items": [
        {"id": "w1", "name": "Baggy jeans", "category": "bottoms",
         "colors": ["blue"], "style_tags": ["denim", "baggy"]},
    ]}
    result = suggest_outfit(_ITEM, wardrobe)

    assert isinstance(result, str) and result.strip() != ""
    # The named wardrobe piece should appear in the prompt sent to the LLM.
    assert "Baggy jeans" in fake.last_kwargs["messages"][0]["content"]


# ── create_fit_card ──────────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_guard(monkeypatch):
    # Guard must return an error string WITHOUT ever touching the LLM.
    fake = _FakeGroq()

    def _boom():
        raise AssertionError("_get_groq_client should not be called for empty outfit")

    monkeypatch.setattr(tools, "_get_groq_client", _boom)

    result = create_fit_card("", _ITEM)
    assert isinstance(result, str) and result.strip() != ""

    # Whitespace-only outfit hits the same guard.
    assert create_fit_card("   ", _ITEM).strip() != ""


def test_create_fit_card_valid(monkeypatch):
    fake = _FakeGroq("just thrifted this cute tee on depop")
    monkeypatch.setattr(tools, "_get_groq_client", lambda: fake)

    result = create_fit_card("Pair the tee with baggy jeans.", _ITEM)

    assert isinstance(result, str) and result.strip() != ""
    assert fake.calls == 1
