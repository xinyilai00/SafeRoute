import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import llm  # noqa: E402


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.delenv("LLM_DISABLED", raising=False)
    llm._cache.clear()


def test_grounded_accepts_only_numbers_from_the_source():
    src = "- minutes_added: 2\n- hazards_avoided: 1 unprotected left turn, 3 high-crash zones"
    assert llm.grounded("It adds 2 minutes and avoids 1 unprotected left turn and 3 high-crash zones.", src)
    assert not llm.grounded("It adds 5 minutes.", src)                       # invented number
    assert not llm.grounded("It adds two minutes.", src)                     # number word, can't be checked
    assert not llm.grounded("", src)
    assert llm.grounded("No numbers here at all.", src)
    assert llm.grounded("About 1,200 crashes.", "there were 1200 crashes")   # thousands separators ignored


def test_explain_route_uses_gemini_when_grounded_and_falls_back_otherwise(monkeypatch):
    facts = {"minutes_added": 2, "hazards_avoided": ["1 unprotected left turn", "3 high-crash zones"]}
    monkeypatch.setattr(llm, "_call", lambda p: "Adds 2 minutes but avoids 1 unprotected left turn and 3 high-crash zones.")
    assert llm.explain_route(facts, "FALLBACK").startswith("Adds 2 minutes")
    llm._cache.clear()
    monkeypatch.setattr(llm, "_call", lambda p: "Adds 9 minutes but avoids 4 crashes.")        # hallucinated numbers
    assert llm.explain_route(facts, "FALLBACK") == "FALLBACK"
    llm._cache.clear()
    monkeypatch.setattr(llm, "_call", lambda p: (_ for _ in ()).throw(RuntimeError("quota")))   # Gemini errors
    assert llm.explain_route(facts, "FALLBACK") == "FALLBACK"


def test_only_whitelisted_facts_leave_the_machine(monkeypatch):
    sent = []
    monkeypatch.setattr(llm, "_call", lambda p: sent.append(p) or "Adds 2 minutes.")
    llm.explain_route({"minutes_added": 2, "origin": {"lat": 30.28, "lng": -97.73}, "user_id": "abc123",
                       "address": "123 Main St"}, "FALLBACK")
    assert sent and "Extra driving time" in sent[0]
    for secret in ("30.28", "97.73", "abc123", "123 Main", "origin", "address", "user_id"):
        assert secret not in sent[0]


def test_disabled_or_empty_never_calls_gemini(monkeypatch):
    called = []
    monkeypatch.setattr(llm, "_call", lambda p: called.append(p) or "x")
    monkeypatch.setenv("LLM_DISABLED", "1")
    assert llm.explain_route({"minutes_added": 2}, "FALLBACK") == "FALLBACK" and llm.summarize_report("# r") is None
    monkeypatch.delenv("LLM_DISABLED")
    assert llm.explain_route({"origin": "x"}, "FALLBACK") == "FALLBACK"       # nothing whitelisted to send
    assert llm.explain_route({"minutes_added": 0}, "FALLBACK") == "FALLBACK"  # nothing worth saying
    assert called == []


def test_calls_are_cached_and_time_limited(monkeypatch):
    n = []
    monkeypatch.setattr(llm, "_call", lambda p: n.append(1) or "Adds 2 minutes.")
    facts = {"minutes_added": 2}
    llm.explain_route(facts, "F")
    llm.explain_route(facts, "F")
    assert len(n) == 1
    llm._cache.clear()
    import time
    monkeypatch.setattr(llm, "TIMEOUT_S", 0.05)
    monkeypatch.setattr(llm, "_call", lambda p: time.sleep(0.5) or "Adds 2 minutes.")
    assert llm.explain_route({"minutes_added": 2}, "FALLBACK") == "FALLBACK"   # too slow: use the fallback


def test_summarize_report_rejects_made_up_numbers(monkeypatch):
    report = "# Data refresh: ACCEPTED\n- capture 58.9%\n- 63 passed"
    monkeypatch.setattr(llm, "_call", lambda p: "- Accepted\n- Capture 58.9%, 63 tests passed")
    assert "58.9" in llm.summarize_report(report)
    llm._cache.clear()
    monkeypatch.setattr(llm, "_call", lambda p: "- Accepted, capture 71.2%")
    assert llm.summarize_report(report) is None


def test_call_keeps_the_client_alive(monkeypatch):
    """Regression: a temporary genai.Client() gets garbage-collected and closed before the request is sent."""
    import gc
    import types
    import weakref

    class Interactions:
        def __init__(self, owner):
            self.owner = weakref.ref(owner)      # like the real SDK, doesn't keep the client alive

        def create(self, model, input):
            gc.collect()
            owner = self.owner()
            if owner is None or owner.closed:
                raise RuntimeError("Cannot send a request, as the client has been closed.")
            return types.SimpleNamespace(output_text=" ok ")

    class FakeClient:
        def __init__(self):
            self.closed = False
            self.interactions = Interactions(self)

        def __del__(self):
            self.closed = True

    genai = types.ModuleType("google.genai")
    genai.Client = FakeClient
    google = types.ModuleType("google")
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    llm._client_holder.clear()
    assert llm._call("hi") == "ok"
    assert llm._call("hi again") == "ok"         # the same client is reused
    llm._client_holder.clear()


def test_weather_is_labelled_as_context_not_something_avoided(monkeypatch):
    sent = []
    monkeypatch.setattr(llm, "_call", lambda p: sent.append(p) or "Adds 2 minutes.")
    llm.explain_route({"minutes_added": 2, "weather": "rain", "hazards_avoided": ["1 left turn"]}, "F")
    assert "background context only" in sent[0] and "does not avoid it" in sent[0]
